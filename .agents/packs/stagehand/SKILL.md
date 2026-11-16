---
name: stagehand
description: Write, review or debug Stagehand v4 code (TypeScript @browserbasehq/stagehand, Python stagehand) that automates a browser with act, extract and observe, self-hosted on your own Chrome and model. Use when a project builds AI browser automation with Stagehand.
---

# Stagehand, self-hosted

Stagehand drives a browser with plain-language actions answered by a model. Here it is
**self-hosted**: a Chrome you launch or host, and a model you host. Browserbase's cloud is out of
scope; there is no account.

## 1. Find the version

Read the project's lockfile. This guide is Stagehand **v4** (the template's baseline is 4.4.0):
TypeScript needs Node 22.18 or later, Python 3.11 or later. Code shaped like v3
(`new Stagehand({ env: "LOCAL" })`, `stagehand.agent()`, `page.act()`) is a migration: confirm it
with the user before rewriting. For any API detail, search the `stagehand-docs` MCP server at
the project's version; skip the pages about Browserbase features.

## 2. Wire the browser and the model

1. **Browser.** Launch a headless Chrome on the machine, or attach to one you host:
   - TypeScript: `localBrowser.launch({ headless: true })`, `localBrowser.connect({ cdpUrl })`
   - Python: `local_browser.launch(headless=True)`, `local_browser.connect(cdp_url=...)`

   Close what you open: `await browser.close()`.
2. **Model.** Pass a callback that sends each generation to your OpenAI-compatible endpoint
   (vLLM, Ollama, llama.cpp, LM Studio). Read [references/self-hosted-model.md](references/self-hosted-model.md)
   for the TypeScript and Python callbacks. The endpoint, model name and optional key come from
   the environment (`STAGEHAND_MODEL_BASE_URL`, `STAGEHAND_MODEL`, `STAGEHAND_MODEL_API_KEY`).
   The model must answer with JSON that fits a JSON schema; act, extract and observe ask for
   nothing else.
3. **Stagehand.** TypeScript: `Stagehand.create({ browser, model: { generate } })`. Python:
   `Stagehand.create(browser=browser, model=generate)`.

The wiring is done when one `extract` against a local test page returns schema-valid data.

Browserbase-only, and so unavailable: `browserbase.launch()` and `browserbase.connect()`; a model
given by name without its own key (the Model Gateway and automatic routing); the `cache` option
(v4 caches only on Browserbase, so every local call runs inference); Verified browsers, proxies
and CAPTCHA solving; cloud contexts; `browserbase.fetch()` and `browserbase.search()`; Functions.
Code that relies on one needs a self-hosted replacement, or the user's decision.

## 3. Use the primitives

- **act**: one action per call, in plain language (`"click the Sign in button"`). Chain calls for
  a flow. An action from `observe` passed back to `act` runs with no model call: the
  deterministic path, and the one to use for steps that repeat, since nothing is cached.
- **extract**: an instruction and a schema (zod in TypeScript, a Pydantic model in Python);
  the result is in `data`. Without a schema the result is `{ extraction: string }`.
- **observe**: candidate actions, each `{ selector, description, method, arguments }`. Check
  `method` before you act on one.
- **Secrets**: write `%name%` in the instruction and pass the values in `variables`, loaded from
  the environment. The model sees only the names.
- **Pages**: `const [page] = await browser.context.pages()` (Python:
  `await browser.context.pages()`), then `page.goto(url)`. Pass `page` to any primitive to
  target one tab. The page API also has `snapshot()`, `screenshot()` and `locator()`.

## 4. Test it

Unit-test the model callback against a stubbed endpoint. Run end-to-end tests on a headless
local Chrome against pages the test serves itself, so no test depends on the public internet.

## Stagehand and Playwright

The stagehand and playwright packs exclude each other, so each repository uses one browser
stack. Stagehand v4 needs no Playwright package: build on Stagehand's own page API. To drive a
browser in this session rather than write code, use the `stagehand` MCP server's tools or the
`stagehand-browse` skill.
