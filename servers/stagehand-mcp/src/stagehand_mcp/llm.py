"""Stagehand's model calls, answered by a self-hosted OpenAI-compatible endpoint.

Stagehand v4 has no base-URL option: a model outside its five providers is a callback. This one
speaks Chat Completions with a JSON-schema response format, which vLLM, Ollama, llama.cpp's
server and LM Studio accept. The model must return valid JSON for the schema it is given.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from stagehand import LLMMessageGenerateResult, LLMStructuredGenerateResult

FENCE = re.compile(r"\A\s*```(?:json)?\s*(.*?)\s*```\s*\Z", re.S)
THINKING = re.compile(r"\A\s*<think>.*?</think>\s*", re.S)  # reasoning a server didn't split off
SCHEMA_NAME = re.compile(r"[^A-Za-z0-9_-]")


@dataclass(frozen=True)
class Endpoint:
    """Where the model is: an OpenAI-compatible base URL (ending in /v1) and a model name."""

    base_url: str
    model: str
    api_key: str | None = None
    timeout: float = 120.0

    @property
    def url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"


def _part(block: Any) -> dict[str, Any]:
    block = getattr(block, "root", block)
    if block.type == "text":
        return {"type": "text", "text": block.text}
    if block.type == "image":
        url = f"data:{block.mime_type};base64,{block.data}"
        return {"type": "image_url", "image_url": {"url": url}}
    raise ValueError(f"Stagehand sent {block.type} content; this server passes text and images")


def _content(content: Any) -> str | list[dict[str, Any]]:
    parts = [_part(block) for block in (content if isinstance(content, list) else [content])]
    if all(part["type"] == "text" for part in parts):
        return "\n\n".join(part["text"] for part in parts)  # the form every server takes
    return parts


def request_body(endpoint: Endpoint, params: Any) -> dict[str, Any]:
    """The Chat Completions request for one Stagehand generation."""
    if getattr(params, "tools", None):
        raise ValueError("Stagehand asked the model to call tools; this server doesn't pass them")
    messages: list[dict[str, Any]] = []
    if params.system_prompt:
        messages.append({"role": "system", "content": params.system_prompt})
    messages += [
        {"role": str(message.role.value), "content": _content(message.content)}
        for message in params.messages
    ]
    body: dict[str, Any] = {"model": endpoint.model, "messages": messages}
    if params.temperature is not None:
        body["temperature"] = params.temperature
    if params.stop_sequences:
        body["stop"] = list(params.stop_sequences)
    form = params.response_format
    if form is not None and form.type == "json_schema":
        schema = form.schema_.model_dump(mode="json") if form.schema_ is not None else {}
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": SCHEMA_NAME.sub("_", form.name)[:64] or "result",
                "schema": schema,
                "strict": True,
            },
        }
    return body


def _text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, list):  # a server that answers in parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content if isinstance(content, str) else ""


def _usage(raw: Any) -> dict[str, int] | None:
    if not isinstance(raw, dict):
        return None
    given, made = raw.get("prompt_tokens"), raw.get("completion_tokens")
    if not isinstance(given, int) or not isinstance(made, int):
        return None
    total = raw.get("total_tokens")
    return {
        "input_tokens": given,
        "output_tokens": made,
        "total_tokens": total if isinstance(total, int) else given + made,
    }


def parse_response(params: Any, payload: dict[str, Any]) -> Any:
    """The Stagehand result for a Chat Completions response."""
    choice = (payload.get("choices") or [None])[0]
    if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
        raise ValueError(f"the model endpoint answered without a message: {str(payload)[:300]}")
    text = _text(choice["message"])
    result: dict[str, Any] = {"role": "assistant", "content": {"type": "text", "text": text}}
    if isinstance(choice.get("finish_reason"), str):
        result["stop_reason"] = choice["finish_reason"]
    usage = _usage(payload.get("usage"))
    if usage:
        result["usage"] = usage
    form = params.response_format
    if form is None or form.type != "json_schema":
        return LLMMessageGenerateResult.model_validate({**result, "output_format": "text"})
    raw = THINKING.sub("", text)
    fenced = FENCE.match(raw)
    try:
        data = json.loads(fenced.group(1) if fenced else raw)
    except json.JSONDecodeError:
        raise ValueError(
            f"the model returned no JSON for {form.name!r} (does it support JSON-schema "
            f"output?): {text[:300]!r}"
        ) from None
    return LLMStructuredGenerateResult.model_validate(
        {**result, "output_format": "json_schema", "structured_content": data}
    )


def generator(endpoint: Endpoint, client: httpx.AsyncClient) -> Callable[[Any], Awaitable[Any]]:
    """Stagehand's model callback: each generation as one Chat Completions request."""
    headers = {"Authorization": f"Bearer {endpoint.api_key}"} if endpoint.api_key else {}

    async def generate(params: Any) -> Any:
        response = await client.post(
            endpoint.url,
            json=request_body(endpoint, params),
            headers=headers,
            timeout=endpoint.timeout,
        )
        if response.is_error:
            raise RuntimeError(
                f"the model endpoint {endpoint.url} answered {response.status_code}: "
                f"{response.text[:300]}"
            )
        return parse_response(params, response.json())

    return generate
