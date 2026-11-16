from __future__ import annotations

import json

import httpx
import pytest
from stagehand import (
    LLMMessageGenerateParams,
    LLMMessageGenerateResult,
    LLMStructuredGenerateParams,
    LLMStructuredGenerateResult,
)
from stagehand_mcp.llm import Endpoint, generator, parse_response, request_body

ENDPOINT = Endpoint("http://127.0.0.1:8000/v1/", "qwen3")
SCHEMA = {"type": "object", "properties": {"price": {"type": "number"}}, "required": ["price"]}


def _structured(**extra: object) -> LLMStructuredGenerateParams:
    return LLMStructuredGenerateParams.model_validate(
        {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "find the price"}]},
                {"role": "assistant", "content": {"type": "text", "text": "ok"}},
            ],
            "system_prompt": "You extract.",
            "temperature": 0.1,
            "response_format": {"type": "json_schema", "name": "Extraction v2", "schema": SCHEMA},
            **extra,
        }
    )


def _answer(text: str, **extra: object) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}, **extra}]}


def test_a_structured_generation_is_a_json_schema_chat_completion() -> None:
    body = request_body(ENDPOINT, _structured(stop_sequences=["END"]))

    assert ENDPOINT.url == "http://127.0.0.1:8000/v1/chat/completions"
    assert body == {
        "model": "qwen3",
        "messages": [
            {"role": "system", "content": "You extract."},
            {"role": "user", "content": "find the price"},
            {"role": "assistant", "content": "ok"},
        ],
        "temperature": 0.1,
        "stop": ["END"],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "Extraction_v2", "schema": SCHEMA, "strict": True},
        },
    }


def test_images_go_as_data_urls_beside_the_text() -> None:
    params = LLMStructuredGenerateParams.model_validate(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "what is shown"},
                        {"type": "image", "data": "aGk=", "mime_type": "image/png"},
                    ],
                }
            ],
            "response_format": {"type": "json_schema", "name": "x", "schema": SCHEMA},
        }
    )

    assert request_body(ENDPOINT, params)["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is shown"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,aGk="}},
            ],
        }
    ]


@pytest.mark.parametrize(
    "text",
    ['{"price": 4.5}', '```json\n{"price": 4.5}\n```', '<think>hmm</think>\n{"price": 4.5}'],
)
def test_the_answer_becomes_structured_content(text: str) -> None:
    payload = _answer(text, finish_reason="stop")
    payload["usage"] = {"prompt_tokens": 7, "completion_tokens": 3}

    result = parse_response(_structured(), payload)

    assert isinstance(result, LLMStructuredGenerateResult)
    assert result.structured_content.model_dump(mode="json") == {"price": 4.5}
    assert result.stop_reason == "stop"
    assert (result.usage.input_tokens, result.usage.total_tokens) == (7, 10)


def test_an_answer_that_isnt_json_says_what_the_model_returned() -> None:
    with pytest.raises(ValueError, match=r"no JSON for 'Extraction v2'.*'about four dollars'"):
        parse_response(_structured(), _answer("about four dollars"))


def test_a_text_generation_returns_text() -> None:
    params = LLMMessageGenerateParams.model_validate(
        {"messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}]}
    )

    assert "response_format" not in request_body(ENDPOINT, params)
    result = parse_response(params, _answer("hello"))
    assert isinstance(result, LLMMessageGenerateResult)
    assert result.content.root.text == "hello"


async def test_the_callback_posts_with_the_machines_key_and_reports_errors() -> None:
    requests: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if json.loads(request.content)["model"] == "missing":
            return httpx.Response(404, text="model not found")
        return httpx.Response(200, json=_answer('{"price": 1}'))

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        keyed = Endpoint("http://models.internal/v1", "qwen3", api_key="local-key")
        result = await generator(keyed, client)(_structured())
        assert result.structured_content.model_dump(mode="json") == {"price": 1}
        assert requests[0].headers["authorization"] == "Bearer local-key"

        missing = Endpoint("http://models.internal/v1", "missing")
        with pytest.raises(RuntimeError, match="answered 404: model not found"):
            await generator(missing, client)(_structured())
        assert "authorization" not in requests[1].headers
