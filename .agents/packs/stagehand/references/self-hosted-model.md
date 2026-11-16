# A self-hosted model for Stagehand v4

Stagehand v4 has no base-URL option. A model outside its five built-in providers is a
**callback**: Stagehand calls it with `messages`, an optional system prompt and temperature, and
a JSON-schema `response_format`, and expects the parsed object back. Both callbacks below send
that as one Chat Completions request to an OpenAI-compatible server. The model must support
JSON-schema output; for `extract({ screenshot: true })` it must also accept images.

## TypeScript

```typescript
import { localBrowser, Stagehand } from "@browserbasehq/stagehand";

type Block = { type: "text"; text: string } | { type: "image"; data: string; mimeType: string };
type Generation = {
  messages: Array<{ role: "user" | "assistant"; content: Block | Block[] }>;
  systemPrompt?: string;
  temperature?: number;
  responseFormat?: { type: "text" } | { type: "json_schema"; name: string; schema: unknown };
};

const baseUrl = process.env.STAGEHAND_MODEL_BASE_URL!; // e.g. http://127.0.0.1:8000/v1
const model = process.env.STAGEHAND_MODEL!;
const apiKey = process.env.STAGEHAND_MODEL_API_KEY;

function parts(content: Block | Block[]) {
  return (Array.isArray(content) ? content : [content]).map((block) =>
    block.type === "text"
      ? { type: "text", text: block.text }
      : { type: "image_url", image_url: { url: `data:${block.mimeType};base64,${block.data}` } },
  );
}

async function generate(params: Generation) {
  if (params.responseFormat?.type !== "json_schema") {
    throw new TypeError("Stagehand only issues structured generations");
  }
  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(apiKey ? { authorization: `Bearer ${apiKey}` } : {}),
    },
    body: JSON.stringify({
      model,
      messages: [
        ...(params.systemPrompt ? [{ role: "system", content: params.systemPrompt }] : []),
        ...params.messages.map((m) => ({ role: m.role, content: parts(m.content) })),
      ],
      ...(params.temperature === undefined ? {} : { temperature: params.temperature }),
      response_format: {
        type: "json_schema",
        json_schema: { name: params.responseFormat.name, schema: params.responseFormat.schema, strict: true },
      },
    }),
  });
  if (!response.ok) throw new Error(`model endpoint answered ${response.status}: ${await response.text()}`);
  const text: string = (await response.json()).choices[0].message.content;
  return {
    role: "assistant",
    content: { type: "text", text },
    outputFormat: "json_schema",
    structuredContent: JSON.parse(text),
  };
}

const browser = await localBrowser.launch({ headless: true });
const stagehand = await Stagehand.create({ browser, model: { generate } });
```

## Python

```python
import json
import os

import httpx
from stagehand import LLMStructuredGenerateResult, Stagehand, local_browser

BASE_URL = os.environ["STAGEHAND_MODEL_BASE_URL"].rstrip("/")  # e.g. http://127.0.0.1:8000/v1
MODEL = os.environ["STAGEHAND_MODEL"]
API_KEY = os.environ.get("STAGEHAND_MODEL_API_KEY")


def part(block):
    block = block.root
    if block.type == "text":
        return {"type": "text", "text": block.text}
    return {"type": "image_url", "image_url": {"url": f"data:{block.mime_type};base64,{block.data}"}}


async def generate(params):
    form = params.response_format
    messages = [{"role": "system", "content": params.system_prompt}] if params.system_prompt else []
    for message in params.messages:
        blocks = message.content if isinstance(message.content, list) else [message.content]
        messages.append({"role": message.role.value, "content": [part(b) for b in blocks]})
    body = {
        "model": MODEL,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": form.name, "schema": form.schema_.model_dump(mode="json"), "strict": True},
        },
    }
    if params.temperature is not None:
        body["temperature"] = params.temperature
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(f"{BASE_URL}/chat/completions", json=body, headers=headers)
    response.raise_for_status()
    text = response.json()["choices"][0]["message"]["content"]
    return LLMStructuredGenerateResult.model_validate({
        "role": "assistant",
        "content": {"type": "text", "text": text},
        "output_format": "json_schema",
        "structured_content": json.loads(text),
    })


browser = await local_browser.launch(headless=True)
stagehand = await Stagehand.create(browser=browser, model=generate)
```

## When a call fails

- **No JSON, or JSON that doesn't fit**: the server isn't constraining output to the schema.
  Turn on its structured-output support (vLLM's guided decoding, for example), or pick a model
  that follows JSON schemas. A reasoning model that prints `<think>…</think>` first needs the
  server to separate that out.
- **`Model inference requires a provider API key or a Browserbase session`**: a model was given
  by name rather than as a callback. Pass the callback.
- **A schema name the server rejects**: some servers allow only `[A-Za-z0-9_-]` in
  `json_schema.name`; replace other characters.
