# Muse Glimmer from LangChain and Deep Agents

These notes were checked against langchain-openai 1.6.7, langchain-core 1.6.7, openai 3.26.0,
langchain 1.4.3 and deepagents 0.7.23 (the newest releases at least 7 days old on 2026-10-14).
For a newer version, check its release date before you pin it:
`curl -s https://pypi.org/pypi/langchain-openai/json | jq -r '.releases | to_entries[] | select(.value | length > 0) | "\(.value[0].upload_time[:10]) \(.key)"' | sort | tail -5`

## Why plain ChatOpenAI isn't enough

`ChatOpenAI` handles the endpoint, tool calls and streaming, but its module docstring says that
non-standard response fields added by third-party providers are not extracted or preserved.
vLLM's `reasoning` field is one of them. So you can't log or show the reasoning, and it isn't
sent back in a tool loop.

Other options fall short. `langchain-deepseek`'s `ChatDeepSeek` reads `reasoning` into
`additional_kwargs["reasoning_content"]`, but its `_get_request_payload` never sends it back.
There is no `langchain-vllm` package on PyPI.

## The subclass

Keep this as project code. Its overrides are private `BaseChatOpenAI` methods
(`_create_chat_result`, `_convert_chunk_to_generation_chunk`, `_get_request_payload`), so pin
`langchain-openai` and keep the test below. It is the test that tells you when an upgrade breaks
a hook.

```python
"""ChatOpenAI for Muse Glimmer on vLLM: keeps `reasoning` and sends it back."""

from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI


class ChatMuseGlimmer(ChatOpenAI):
    # The hooks below cover Chat Completions only; never switch to Responses.
    use_responses_api: bool | None = False

    def _create_chat_result(self, response: Any, generation_info: Any = None):
        result = super()._create_chat_result(response, generation_info)
        data = response if isinstance(response, dict) else response.model_dump()
        for gen, choice in zip(result.generations, data.get("choices") or []):
            if reasoning := (choice.get("message") or {}).get("reasoning"):
                gen.message.additional_kwargs["reasoning"] = reasoning
        return result

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        gen = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        choices = chunk.get("choices") or []
        if gen and choices and isinstance(gen.message, AIMessageChunk):
            if reasoning := (choices[0].get("delta") or {}).get("reasoning"):
                gen.message.additional_kwargs["reasoning"] = reasoning  # chunks concatenate
        return gen

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        messages = self._convert_input(input_).to_messages()
        for src, out in zip(messages, payload["messages"], strict=True):
            if isinstance(src, AIMessage) and (r := src.additional_kwargs.get("reasoning")):
                out["reasoning"] = r
        return payload
```

The code relies on three facts:

- Chat Completions builds one payload message per input message, in order. That is what makes
  the `zip(..., strict=True)` safe, and `strict=True` turns any future mismatch into an error
  instead of misplaced reasoning.
- When streamed chunks are added together, string values in `additional_kwargs` are joined, so
  the full reasoning ends up on the merged message.
- `use_responses_api=False` matters. ChatOpenAI switches to the Responses API by itself when
  certain fields are set (`reasoning`, `include`, `truncation` and others), and these hooks don't
  run on that path.

This replays all of the reasoning in the history. In a long chat you may want to keep only the
reasoning from the current tool loop, meaning the messages after the last human message. Choose
deliberately and cover the choice in the test.

## The test

```python
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage

from muse_glimmer import ChatMuseGlimmer  # wherever the class lives

llm = ChatMuseGlimmer(model="muse-glimmer", base_url="http://127.0.0.1:8000/v1", api_key="unused")
RESPONSE = {
    "id": "x", "object": "chat.completion", "created": 0, "model": "muse-glimmer",
    "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "reasoning": "Call the tool.",
        "tool_calls": [{"id": "c1", "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city": "Paris"}'}}]}}],
}


def test_reasoning_is_read_and_replayed():
    msg = llm._create_chat_result(RESPONSE).generations[0].message
    assert msg.additional_kwargs["reasoning"] == "Call the tool."
    payload = llm._get_request_payload(
        [HumanMessage("Weather in Paris?"), msg, ToolMessage("18C", tool_call_id="c1")]
    )
    assert [m.get("reasoning") for m in payload["messages"]] == [None, "Call the tool.", None]


def test_streamed_reasoning_concatenates():
    chunks = [
        llm._convert_chunk_to_generation_chunk({"choices": [{"index": 0, "delta": d}]}, AIMessageChunk, {})
        for d in ({"role": "assistant", "reasoning": "Think "}, {"reasoning": "more."}, {"content": "Hi"})
    ]
    merged = chunks[0].message + chunks[1].message + chunks[2].message
    assert merged.additional_kwargs["reasoning"] == "Think more."
    assert merged.content == "Hi"
```

The tests make no network calls, so they run in CI.

## Constructing it

```python
import os

llm = ChatMuseGlimmer(
    model=os.environ.get("MUSE_GLIMMER_MODEL", "muse-glimmer"),  # the served name
    base_url=os.environ.get("MUSE_GLIMMER_BASE_URL", "http://127.0.0.1:8000/v1"),
    api_key=os.environ.get("MUSE_GLIMMER_API_KEY", "unused"),  # vLLM --api-key, if set
    temperature=1.0,
    top_p=0.95,
    timeout=600,
    streaming=True,
    extra_body={"top_k": 64, "chat_template_kwargs": {"reasoning_strength": "high"}},
)
```

- Add the three variables to the repository's `.env.example` with placeholder values. Real
  values never go in a committed file.
- `top_k` and `chat_template_kwargs` aren't OpenAI parameters, so they go in `extra_body` rather
  than `model_kwargs`. If the server already sets them, through `--override-generation-config` and
  `--default-chat-template-kwargs`, you can leave them out here.
- Leave `reasoning_effort` and `reasoning` unset. The first does nothing on Glimmer, and the
  second is a Responses API parameter.

## Agents

`create_agent(model=llm, ...)` (langchain) and `create_deep_agent(model=llm, ...)` (deepagents)
both accept the instance. Glimmer-specific points:

- Any system message, including the system prompt agent middleware writes, makes the chat
  template drop its own date line, so put today's date in your `system_prompt`.
- Structured output: vLLM v0.31.0 enforces no schema for Glimmer (SKILL.md, section 5), so the
  model has to see the schema and your code has to check the result. With a bare schema,
  `create_agent(response_format=Schema)` finds no provider-side structured output for
  `muse-glimmer` (the model has no profile) and uses `ToolStrategy`. That is the right choice:
  the schema becomes a tool the model can see, and invalid arguments go back to the model for a
  retry (`handle_errors=True` by default). Use a Pydantic model, a dataclass or a `TypedDict`,
  because a raw JSON-schema dict isn't validated. `ToolStrategy` asks for `tool_choice="any"`,
  which ChatOpenAI sends as `"required"` and Glimmer's parser doesn't enforce, so the model can
  still finish in prose: tell it in the system prompt to finish by calling the tool, and check
  that `result["structured_response"]` is present.
- Don't pass `ProviderStrategy(Schema)`. It sends `response_format`, which vLLM skips for
  Glimmer, and the model never sees the schema, so parsing the prose answer fails. For the same
  reason, call `llm.with_structured_output(Schema, method="function_calling", include_raw=True)`
  on a bare model rather than the default `method="json_schema"`, and handle `parsed` being
  `None` (no tool call) or `parsing_error` being set.
