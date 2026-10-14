# Smoke test for Muse Glimmer on vLLM

The script uses only the Python standard library and exits 1 on any FAIL. Save it as
`smoke_glimmer.py` and run it against a running server:

```bash
MUSE_GLIMMER_BASE_URL=http://127.0.0.1:8000/v1 MUSE_GLIMMER_MODEL=muse-glimmer python3 smoke_glimmer.py
```

Add `MUSE_GLIMMER_API_KEY` if vLLM runs with `--api-key`. What it checks:

- The served name, checkpoint (`root`) and `max_model_len` from `GET /v1/models`.
- That `reasoning_strength` reaches the chat template and `reasoning_effort` doesn't. These checks
  read the rendered prompt through vLLM's `/tokenize` and `/detokenize`, so they give the same
  result every run.
- How many `Reasoning strength:` lines the prompt carries when the system prompt has its own
  (2 means the older template on the quantized checkpoints).
- A tool call, the `reasoning` field, no raw channel markup in `content`, and an answer after the
  reasoning and the tool result are sent back.
- Image input, with a generated red PNG.

The tool and image checks sample, so rerun once before you treat a failure as real. Afterwards,
confirm the sampling log line from section 3 of the skill.

```python
"""Smoke-test Muse Glimmer on vLLM. Standard library only; exits 1 on any FAIL."""
import base64, json, os, struct, sys, urllib.request, zlib

BASE = os.environ.get("MUSE_GLIMMER_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
MODEL = os.environ.get("MUSE_GLIMMER_MODEL", "muse-glimmer")
KEY = os.environ.get("MUSE_GLIMMER_API_KEY", "")
ROOT = BASE.removesuffix("/v1")
FAILED = []


def call(url, body=None):  # GET without a body, POST with one
    req = urllib.request.Request(url, None if body is None else json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    if KEY:
        req.add_header("Authorization", f"Bearer {KEY}")
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.load(resp)


def check(name, ok, detail=""):
    print("PASS" if ok else "FAIL", name, detail)
    if not ok:
        FAILED.append(name)


def chat(messages, **extra):
    body = {"model": MODEL, "messages": messages, "max_tokens": 8192,
            "chat_template_kwargs": {"reasoning_strength": "low"}, **extra}
    return call(f"{BASE}/chat/completions", body)["choices"][0]


def rendered(system, **kwargs):  # the prompt the chat template produces
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": "Hi"}]
    tokens = call(f"{ROOT}/tokenize", {"model": MODEL, "messages": msgs, **kwargs})["tokens"]
    return call(f"{ROOT}/detokenize", {"model": MODEL, "tokens": tokens})["prompt"]


def png(rgb, size=224):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    rows = (b"\x00" + bytes(rgb) * size) * size
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


cards = call(f"{BASE}/models")["data"]
card = next((c for c in cards if c["id"] == MODEL), None)
check("served model name", card is not None, str([c["id"] for c in cards]))
print("     root:", card and card.get("root"), "max_model_len:", card and card.get("max_model_len"))
check("reasoning_strength reaches the template",
      "Reasoning strength: low." in rendered("Be brief.", chat_template_kwargs={"reasoning_strength": "low"}))
check("reasoning_effort does not reach the template",
      "Reasoning strength: low." not in rendered("Be brief.", chat_template_kwargs={"reasoning_effort": "low"}))
lines = rendered("Be brief.\nReasoning strength: low.").count("Reasoning strength:")
print("INFO strength lines when the system prompt carries one:", lines, "(2 = older template)")

tools = [{"type": "function", "function": {
    "name": "get_weather", "description": "Current weather for a city.",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
ask = [{"role": "user", "content": "What is the weather in Paris? Use the tool."}]
first = chat(ask, tools=tools)
msg, calls = first["message"], first["message"].get("tool_calls") or []
check("tool call parsed", any(c["function"]["name"] == "get_weather" for c in calls),
      f"finish_reason={first.get('finish_reason')} calls={len(calls)}")
check("reasoning field filled", bool(msg.get("reasoning")))
check("no raw markup in content", not any(t in (msg.get("content") or "") for t in ("<|", "<atem:")))
if calls:
    history = ask + [{"role": "assistant", "content": msg.get("content"), "tool_calls": calls,
                      "reasoning": msg.get("reasoning")}]
    history += [{"role": "tool", "tool_call_id": c["id"], "content": '{"temp_c": 18}'} for c in calls]
    answer = chat(history, tools=tools)["message"].get("content") or ""
    check("answer after replaying reasoning and tool result", bool(answer) and "<|" not in answer)

image = "data:image/png;base64," + base64.b64encode(png((220, 20, 20))).decode()
reply = chat([{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": image}},
    {"type": "text", "text": "Answer with one word: what colour fills this image?"}]}])
check("image input", "red" in (reply["message"].get("content") or "").lower())
sys.exit(1 if FAILED else 0)
```
