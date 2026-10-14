# From VLM output to SAM concepts

A VLM decides **what** to look for; SAM decides **where** it is. Meta's docs recommend this split
(https://dev.meta.ai/docs/sam/segmenting.md: caption or identify with a vision model, then pass
the concept to SAM), and Meta's SAM 3 Agent (`examples/sam3_agent.ipynb`, tools and rules in
`sam3/agent/system_prompts/system_prompt.txt`) runs it as a tool loop with Qwen3-VL served by
vLLM in a separate environment.

## The pipeline

1. Ask the VLM for concepts as structured JSON, one noun phrase each:
   `{"concepts": ["red forklift", "pallet"]}`. Use the server's structured-output or JSON-schema
   mode rather than parsing prose. The prompt states the rules: short noun phrases naming whole
   objects, no counts, no positions, no relations, no text read from the image.
2. Validate every phrase in code (below). A rejected phrase goes back to the VLM once with the
   reason, or is dropped and logged.
3. One SAM request per concept. Run them concurrently within the hosted rate limit, or
   sequentially on a local model. Zero matches is an answer, not a retry.
4. Resolve "which one" after segmentation: filter by box position, size or score in code, or
   send the VLM the image with numbered boxes or masks drawn on it and ask for the ids it means.
5. Return ids, boxes, scores and mask references. Keep raw masks out of model context.

## Validate phrases

```python
import re

# Lists, boolean words and negation: one SAM prompt handles none of them.
_COMPOUND = re.compile(r"[,;+/\n]|\b(and|or|not|without|except)\b", re.IGNORECASE)
# Position and order: segment the plain concept, then filter by box in code.
_SPATIAL = re.compile(
    r"\b(left|right|leftmost|rightmost|top|bottom|above|below|behind|beside|between|"
    r"next to|in front of|on top of|first|second|third|last)\b",
    re.IGNORECASE,
)
# Commands and questions: SAM reads a concept, not an instruction.
_COMMAND = re.compile(
    r"^(segment|find|show|detect|locate|highlight|mask|count|track|where|what|which|how)\b",
    re.IGNORECASE,
)


def clean_concept(text: str, max_words: int = 5) -> str | None:
    """Return a SAM-ready noun phrase, or None when it must be split or filtered in code."""
    if "?" in text:
        return None
    phrase = " ".join(text.strip().strip(".!\"'").split())
    if not phrase or _COMMAND.search(phrase) or _COMPOUND.search(phrase) or _SPATIAL.search(phrase):
        return None
    if len(phrase.split()) > max_words:  # an app limit: Meta says short phrases match best
        return None
    return phrase
```

Deduplicate after cleaning; plurals and case don't change SAM's result ("red squares" equals
"red square"). The word lists also reject some real objects ("top hat", "first aid kit",
"mask"): log rejections and widen the lists for your domain.

## Rules from the SAM 3 Agent prompt

Meta's agent prompt encodes what works in practice. Carry these into your VLM prompt:

- Ground the whole target, not the part that identifies it: "person", not "white hat", for
  "guy with white hat"; "giraffe" for "a giraffe with its head up".
- Use visual attributes, not text or numbers on objects: "black ball", not "8-ball". When only
  writing tells objects apart, segment the category and let the VLM pick among the masks.
- Replace actions, relations and comparatives with the plain category and select afterwards:
  "vase", not "the bigger vase"; "dog", not "the dog lying down".
- On zero matches, retry once with a more general noun ("person" for "elementary school
  teacher", "statue" for "sundial").
- One tool call per turn, and the final answer is chosen from masks SAM produced.

## As an agent tool

For LangGraph, Deep Agents or any tool-calling loop, expose one tool such as
`segment(concept: str, media_id: str) -> {"count", "objects": [{"id", "box_xyxy", "score"}], "mask_ref"}`.

- Validate `concept` inside the tool with `clean_concept` and return the reason on rejection, so
  the model can rephrase.
- Keep masks server-side (a file, a cache key, or COCO RLE in your store) and return a
  reference. A mask list in a tool result costs thousands of tokens and the model can't read it.
- Draw numbered overlays when the model has to choose between instances, and send that image
  back as the next observation.
- Run the VLM in its own server (vLLM in a container) and call it over HTTP from the SAM
  process. Meta's agent notebook installs vLLM in a separate environment to avoid dependency
  conflicts with SAM 3.
- Don't copy that notebook's `vllm serve ... --allowed-local-media-path /`: it lets any API
  caller read images and videos anywhere on the server's file system (vLLM calls the option a
  security risk). Send images as data URLs, or name one media directory.

## VLM boxes as SAM prompts

Prefer concept text. If you do pass a VLM's box to SAM, convert it with SAM SKILL.md section 3:

- Qwen3-VL `bbox_2d` is relative 0–1000 (Qwen2.5-VL used absolute pixels of its resized input):
  `x_px = x / 1000 * width`.
- Muse Spark perception grounding uses a 0–1000 grid on the image it received.
- A box on `Sam3Model`, the native `add_geometric_prompt` or a native video `add_prompt` is an
  exemplar and returns every similar object. For that one object, use `Sam3TrackerModel`,
  native `predict_inst`, or native video point prompts with an `obj_id`.
- Don't ask a model without a documented coordinate convention (Muse Glimmer, for one) for
  geometry; ask it for concept nouns.
