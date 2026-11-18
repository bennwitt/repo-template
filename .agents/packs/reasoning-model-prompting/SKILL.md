---
name: reasoning-model-prompting
description: "Prompting reasoning (thinking) models versus instant models: brief zero-shot prompts and effort for Claude adaptive thinking and OpenAI reasoning models, chain-of-thought and few-shot for instant ones, an effort sweep. Use when picking a model or effort level, or a prompt over- or underthinks."
license: MIT
---

# Prompting reasoning models versus instant models

A **reasoning model** thinks before it answers: it plans, checks and revises in a hidden
reasoning pass, and you pay for that pass as output tokens. An **instant model** writes the answer
straight away, so any reasoning has to happen in the visible output, where your prompt scaffolds
it. "System 1 / System 2" is Kahneman's analogy for the two modes of human thought (fast and
automatic versus slow and deliberate, *Thinking, Fast and Slow*, 2011); it is a loose picture of
the two model classes, not a description of how either works. If you meant **System One Models**,
that is a product name of TypeSafe AI: decision models (Jev) that return typed choices with
calibrated probabilities, documented at https://docs.typesafe.ai/introduction, not covered here.

This skill covers the choice between the classes and what changes in the prompt. General prompt
patterns, structured outputs and system prompts are in the sibling `prompt-engineer` skill;
measuring and optimizing prompts in `promptfoo-evals` and the DSPy skills; Claude model ids and
request parameters in the global `claude-api` skill, which wins on API detail.

## 1. Choose the class

| Task | Run on | Why |
| --- | --- | --- |
| Classification, extraction, routing, labeling, short rewrites | An instant model, or a reasoning model at `low` effort | Well-specified input, one short output; speed and cost dominate |
| A tool loop whose every step is small, latency-bound | Instant or `low` effort | Thinking on each turn adds time; lower effort also makes fewer, terser tool calls |
| Planning, multi-step problems, ambiguous specs, debugging, code review, judging other outputs | A reasoning model at `high` effort or above | The model has to decide what the task is before doing it |
| A planner that farms out well-defined steps | Reasoning model plans, cheaper model executes | OpenAI's pattern: reasoning models are "the planners", GPT models "the workhorses" |

Measure before you downgrade: at `low` effort a frontier model is often competitive on cost per
task with a smaller model at high effort while scoring higher, so put "big model, low effort" in
every comparison (section 6).

## 2. Prompt a reasoning model

Say what you want, not how to think. The model's own plan usually beats a hand-written one, and
a step-by-step script makes it follow worse steps.

- **Brief and direct.** State the goal, the constraints, the output format and what counts as
  done ("until every failing test passes", "a budget under $500"). Give the whole task up front.
- **Zero-shot first.** Add examples only when format or tone drifts, 3 to 5 of them, wrapped in
  `<example>` tags; worked examples do shape how Claude reasons, so keep them correct.
- **Delimit the parts.** XML tags or Markdown headings for instructions, context, input and
  examples, so the model never mistakes data for instructions.
- **Leave planning to the model.** Skip "think step by step", "explain your reasoning",
  `<scratchpad>` instructions and `STEP 1 ... STEP n` choreography; keep numbered steps only where
  the order is a hard requirement (destructive commands, auth flows).
- **Ask for the answer, not the reasoning.** On Fable 5.x, Opus 5.5 / 5 and Sonnet 5.5 a prompt
  that asks the model to write out its reasoning can be declined (`reasoning_extraction`); read
  thinking from the API's thinking blocks instead.
- **Self-check** with one line ("Before you finish, verify the answer against the tests"); drop
  it where the model already verifies, or you get over-verification.

## 3. Prompt an instant model

With no hidden pass, the visible output is the reasoning. Here the classic techniques earn their
tokens:

- **Explicit chain of thought:** ask it to reason through the problem before answering, and to
  put the final answer in `<answer>` tags so you can extract it.
- **Few-shot examples** of input, method and answer; instant models lean on them harder.
- **Structured scaffolds:** numbered steps, a rubric, a checklist, a fixed output template.
- **Narrow scope:** one decision per call; chain calls in code rather than asking for a plan.

On Claude, "instant" is a setting rather than a separate model: every current model thinks
adaptively, so run a reasoning model at `low` effort first, and keep the chain-of-thought
fallback for routes where thinking is off (Haiku 5.5 with `disabled` at `high` or below,
Sonnet 5.5 with `between_tools`). Exact shapes: `claude-api`.

## 4. Claude: adaptive thinking and effort

- **Adaptive thinking** (`thinking: {type: "adaptive"}`): the model decides per request whether
  and how much to think. On Fable 5.2 / 5.1 / 5, Mythos and Opus 5.5 it is the only mode and
  always on; `disabled` returns a 400 there. **`budget_tokens`** (`type: "enabled"`) was the 4.x
  control: deprecated on 4.6, a 400 on 4.7 and later.
- **Effort** is the depth control: `output_config.effort` in `low`, `medium`, `high`, `xhigh`,
  `max`; default `high` except Opus 5.5 and Haiku 5.5 (`medium`). It shapes every output token,
  tool calls included, and barely changes reply length, so prompt for length separately.
- **Overthinking: lower effort, not prose.** Effort is calibrated; wording is not. A line such
  as "answer directly without deliberating" does not stop Fable 5.2 at `medium` and above,
  Sonnet 5.5 or Haiku 5.5. At `high` Fable 5.2 thinks before almost every reply, greetings
  included: route those turns to a lower level. Excessive exploration also comes from
  over-prompting ("if in doubt, use the tool"): remove that before touching effort.
- **The prompt can trigger thinking.** "This task involves multistep reasoning. Think carefully
  before responding." in the system prompt, or "Please think hard before responding." on one
  user turn, raises the chance of a thinking block; use it when a route must stay at `low`.
  Verify on a traffic sample: count thinking blocks, output tokens, latency and quality.
- **Prompts written for older models are often too prescriptive** and reduce output quality on
  Fable 5.x and Opus 5.5: step-by-step scripts, "if in doubt" tool nudges, anti-laziness lines,
  "think less" lines, token budgets shown in the prompt, built-up cautions in memory files. A/B
  the workload with that scaffolding removed; state goal and constraints instead. At `low` and
  `medium`, Fable 5.2 can stop a long task early; the docs' "Finish the whole task" text fixes
  that, not more steps.
- **Caching:** a changed top-level effort can invalidate the prompt cache; vary it across
  workloads, or per message on models with the per-message effort beta.

## 5. OpenAI reasoning models

The same shape, in OpenAI's terms (reasoning best practices guide):

- Use **developer messages** rather than system messages.
- **Keep prompts simple and direct**; "Avoid chain-of-thought prompts": "think step by step"
  and "explain your reasoning" are unnecessary.
- **Delimiters** (Markdown, XML tags, section titles); **zero shot first, then few shot**;
  specific guidelines; be very specific about the end goal.
- API reasoning models skip Markdown unless the developer message starts with
  `Formatting re-enabled`.
- Depth is `reasoning.effort` (Responses API; `reasoning_effort` in Chat Completions), values
  and default model-dependent; treat it "as a tuning knob, not the primary way to recover
  quality". Reasoning tokens are billed as output and sit in the context window: reserve room
  (the guide suggests at least 25,000 tokens to start), and pass reasoning items back between
  tool calls to cut repeat reasoning.

## 6. Sweep effort and model

Effort names do not mean the same amount of thinking across models, so re-run the sweep on
every migration instead of carrying a setting over.

1. Build an eval set from real traffic (`promptfoo-evals`, or `/claude-api build-eval`): 50 to
   200 cases, graded by a check you trust, covering the hard and the routine.
2. Fix `max_tokens` large enough for thinking plus the answer; thinking counts toward it even
   when its text is not returned.
3. Run the matrix: each candidate model at `low`, `medium`, `high` and, where supported,
   `xhigh`; `max` only to measure the ceiling. Record score, cost per completed task (a cheap
   request that needs retries is not cheap), p50 and p95 latency, and
   `usage.output_tokens_details.thinking_tokens`.
4. Pick the cheapest cell whose score holds, per route rather than globally. Only then tune
   the prompt, one change at a time, re-running the same set.

## 7. Cost and latency

Thinking is billed as output tokens at the model's output rate, whatever `display` shows, and
prior thinking blocks that stay in context bill as input. Above `high` the gains are uneven and
the tokens are not: Anthropic reports `xhigh` raising coding scores slightly at many more tokens,
and `max` slower still. Time to first token grows with thinking, so stream, show thinking
summaries or progress updates, and keep interactive turns at `medium` or below. If responses
stop at `max_tokens`, raise the cap when the truncated cases needed the reasoning, lower effort
when they did not.

## Sources checked on 2026-11-18

- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost
- https://platform.claude.com/docs/en/build-with-claude/effort
- https://platform.claude.com/docs/en/build-with-claude/extended-thinking
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2
- https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1
- https://developers.openai.com/api/docs/guides/reasoning-best-practices
- https://developers.openai.com/api/docs/guides/reasoning, and the global `claude-api` skill
