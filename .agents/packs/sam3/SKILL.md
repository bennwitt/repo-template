---
name: sam3
description: "Meta SAM 3 and SAM 3.1 segmentation: hosted sam-3.1 on Meta Model API, transformers Sam3Model, or the native facebookresearch/sam3 repo. Concept prompts, box and mask coordinates, numpy/OpenCV/COCO hand-off, GPU sharing, gated weights, SAM License. Use when code segments, counts, cuts out or tracks objects with SAM 3, or feeds it VLM output."
---

# Segmenting with SAM 3 and SAM 3.1

SAM 3 takes a **concept** (a short noun phrase, or an exemplar box) and returns a box and a mask
for every matching instance, with ids that stay stable across video frames. SAM 3.1 adds Object
Multiplex, faster tracking of many objects in video. The three ways to run it share the prompt
rules and differ in everything else: coordinates, install, cost and license duties.

Related skills: `opencv-python` (cv2 I/O, colour order, codecs), `compose-gpu-serving` (SAM in a
GPU container next to vLLM), `local-model-serving` (sizing vLLM on a shared GPU), `uv` (project
setup), `gradio`, `hf-gradio` and `fastapi` (demos and APIs), `supply-chain-risk-auditor`
(before adding a new dependency).

## 1. Pick the path

| Path | Weights | Choose it when |
|---|---|---|
| Hosted `sam-3.1`, Meta Model API | none local | the media may leave the machine; video without a local GPU |
| transformers `Sam3Model`, `Sam3VideoModel`, `Sam3TrackerModel` | `facebook/sam3` (SAM 3.0) | private media; the simplest local install |
| Native `facebookresearch/sam3` at a pinned commit | `facebook/sam3.1` or `facebook/sam3` | SAM 3.1 locally (Object Multiplex video) |

- Sending user media to Meta is the user's decision; ask. Uploaded files persist until deleted
  (section 5). Private media goes to a local path.
- transformers has no SAM 3.1 (5.19.0: PRs #45110 and #46128 open, #47226 closed unmerged), and
  `facebook/sam3.1` holds only the native checkpoint `sam3.1_multiplex.pt`. Re-check the PRs
  before choosing native for 3.1.
- Hosted price (https://dev.meta.ai/docs/pricing-rate-limits.md, 2026-10-14): $2.50 per 1,000
  images, $0.20 per 1,000 video frames; 3,000 requests per minute per team. Each concept is its
  own request, so cost scales with images × concepts.
- Ultralytics also wraps SAM 3; the `ultralytics` package is AGPL-3.0, so it fits only a repo
  already under AGPL or one holding an Ultralytics Enterprise License.

## 2. Write concept prompts

From https://dev.meta.ai/docs/sam/segmenting.md. They describe the model, so they hold on every
path:

- Name **one** concept as a short noun phrase: "yellow school bus", "red hat". Commands
  ("segment the bus") and questions return nothing reliable.
- Comma, semicolon and plus lists ("bus, bicycle") return zero matches; "and", a newline or a
  second text part segments only one of the concepts. Several concepts means several requests,
  or a list of separate phrases where an API takes one (`Sam3VideoProcessor.add_text_prompt`).
- Attributes narrow predictably ("red square" is a subset of "square"); plurals, case and
  punctuation change nothing; padding words hurt.
- Negation, OR and position ("person on the left") are unreliable: segment the plain concept
  and filter by box in code. There is no OCR (Meta's SAM 3 Agent prompt): "black ball", not
  "8-ball".
- Zero matches is a completed, valid result. Branch on it rather than retrying it as an error.
- A box on `Sam3Model`, the native image `add_geometric_prompt` or a native video `add_prompt`
  is an **exemplar**: it returns every object like the boxed one. For just that object, use
  `Sam3TrackerModel`, native `predict_inst` (a model built with
  `enable_inst_interactivity=True`), or native video **point** prompts with an `obj_id`.

## 3. Coordinates

Each API has its own convention. Convert once at the boundary, and name the convention in the
variable (`box_xyxy_px`, `box_cxcywh_norm`).

| Source | Boxes | Points | Masks |
|---|---|---|---|
| Hosted wire text | `x1,y1,x2,y2` px, **inclusive**; `w,h` = frame size | none documented | `data=H,W,` base85, box-sized |
| `meta_sam_parser` records | `left,top,right,bottom` px, half-open | none | `height × width` = the box, placed at `(left, top)` |
| Native image `Sam3Processor` | in: `add_geometric_prompt` normalized `cx,cy,w,h`; out: `boxes` xyxy px | none | `masks` `(N,1,H,W)` bool, full image |
| Native `predict_inst` | `box` xyxy px | `point_coords` `[[x,y]]` px | float32 numpy `(C,H,W)` |
| Native video predictor | in and out: normalized `x,y,w,h` (inputs must lie in 0..1) | normalized; need an `obj_id` | `out_binary_masks` `(N,H,W)` bool numpy; ids in `out_obj_ids` |
| transformers `Sam3Model`, `Sam3VideoModel` | in: `input_boxes` `[image][box][x1,y1,x2,y2]` px; out: xyxy px | none | full size; image masks int64, video bool |
| transformers `Sam3TrackerModel` | xyxy px | `input_points` `[image][object][point][x,y]` px | `post_process_masks` |
| COCO | `bbox` `x,y,w,h` px | none | RLE, column-major |
| Qwen3-VL `bbox_2d` | 0–1000 relative (Qwen2.5-VL: absolute px) | | |
| Muse Spark grounding | 0–1000 grid on the image sent | | |

Labels are `1` positive, `0` negative (transformers pads batches with `-10`). Hosted boxes and
sizes refer to the media as displayed, after EXIF rotation. A model with no documented
convention (Muse Glimmer, for one) is asked for concept nouns, never geometry.

## 4. Hand masks to numpy and OpenCV

- Hosted masks cover the box only: paste each into a `(height, width)` frame at `(top, left)`.
  `decode_mask_to_rle` is box-local too; `full_frame_mask()` in
  [references/hosted-api.md](references/hosted-api.md) does the paste.
- Normalize the image once, then use those exact pixels everywhere: decode, apply EXIF
  orientation, convert to RGB. `cv2.imread` applies EXIF rotation and returns BGR;
  `PIL.Image.open` ignores the rotation until `ImageOps.exif_transpose(...)`, and only
  `.convert("RGB")` guarantees three channels. A rotated JPEG read both ways gives transposed
  sizes and masks in the wrong place.
- Native `Sam3Processor.set_image` takes a PIL image. Given an HWC ndarray it records height=W
  and width=3 and returns masks of that shape, with no error.
- Masks arrive as bool (native, transformers video), int64 (transformers
  `post_process_instance_segmentation`) or float32 (`predict_inst`). OpenCV wants uint8:
  `(mask > 0).astype(np.uint8) * 255` for drawing and `cv2.findContours`, which rejects bool and
  int64 arrays.
- COCO RLE: a full-frame mask as `np.asfortranarray(mask.astype(np.uint8))` into
  `pycocotools.mask.encode`, then `rle["counts"].decode("ascii")` for JSON.
- Torch outputs: `.cpu().numpy()`; drop the channel axis of native `(N,1,H,W)` with `[:, 0]`.

## 5. Hosted sam-3.1

- `POST https://api.meta.ai/v1/responses` with `model="sam-3.1"`, one user message holding an
  `input_text` concept and one `input_image` (`image_url`: URL or `data:` URL) or
  `input_video` (`video_url` or a Files API `file_id`). Use the OpenAI SDK with
  `base_url="https://api.meta.ai/v1"`.
- Pass the key explicitly: `api_key=os.environ["MODEL_API_KEY"]`. The OpenAI SDK otherwise
  reads `OPENAI_API_KEY` and would send that key to Meta. Add an empty `MODEL_API_KEY=` to
  `.env.example`; the value stays in the environment, never in code, logs, images or commits.
- Parse with `meta_sam_parser==0.1.0` (published 2026-10-06; newer: take the newest PyPI
  release at least 7 days old): `parse_responses_stream(stream, image_segmentation_format())`
  or `video_segmentation_format()`. Masks are base85 in two encodings; let the parser decode
  them. Request `metadata={"mask_encoding": "one_bit"}` for smaller payloads.
- Use records only after `result.outcome.status == "completed"` and no error diagnostics.
- Video frames can be skipped and arrive out of order: key by `(frame_index, object_id)`.
- Uploaded files never expire unless the upload sets `expires_after`; delete them when done.
- The API docs describe text concepts only. `meta_sam_parser` also ships `build_object_prompt`
  (boxes and points) and mentions `include_confidence` and `propagation_direction`; confirm each
  with one live request before building on it.

Request, parse, paste, upload and test code: [references/hosted-api.md](references/hosted-api.md).

## 6. Local weights and access

- `facebook/sam3` and `facebook/sam3.1` are gated with manual approval. The person requests
  access on each model page while logged in to Hugging Face; an agent can't do it for them.
- Check access without printing a token:
  `uv run --no-project --with huggingface-hub==2.1.1 python -c "from huggingface_hub import auth_check; auth_check('facebook/sam3'); auth_check('facebook/sam3.1')"`
  is silent when approved and raises `GatedRepoError` when not (2.1.1 was the newest release at
  least 7 days old on 2026-10-14). `hf auth whoami` shows which account is logged in.
- Authenticate with `hf auth login`, or `HF_TOKEN` from a git-ignored `.env` (add an empty
  `HF_TOKEN=` to `.env.example`). Never run `hf auth token`, echo `HF_TOKEN`, or bake a token
  into an image or compose file.
- `facebook/sam3` holds `model.safetensors` (transformers) and `sam3.pt` (native), fp32, about
  3.4 GB each, about 0.84 B parameters.

## 7. transformers (SAM 3.0)

- `transformers>=5.0`: the Sam3 classes first shipped in 5.0.0 (absent in 4.57.6). 5.19.0 was
  the newest release at least 7 days old on 2026-10-14.
- `from_pretrained` defaults to `dtype="auto"`, which is fp32 for this checkpoint;
  `dtype=torch.bfloat16` halves the weights. The docs' `device_map="auto"` needs `accelerate`
  installed (a `ValueError` otherwise); without it, load and call `.to("cuda")`.
- A bf16 `Sam3VideoModel` also needs `init_video_session(..., dtype=torch.bfloat16)`; the
  session defaults to fp32 and the first frame fails with "Input type (float) and bias type
  (c10::BFloat16) should be the same". The docs' examples are all fp32.
- Several concepts on one image: `model.get_vision_features()` once, then one text prompt each
  with `vision_embeds=`.
- Video post-processing logs that it skips NMS, hole filling and sprinkle removal without the
  optional `kernels` package, which downloads compiled kernels from the Hugging Face Hub. Adding
  it is the person's supply-chain decision.

Code for images, trackers and video: [references/local.md](references/local.md).

## 8. Native facebookresearch/sam3

- The repo has no tags or releases. Pin a full commit SHA at least 7 days old; this skill was
  checked at `0570b3a5be9c4e694f23d85232fb55f4a6f1f7fc` (2026-10-07). Newer commits:
  `gh api repos/facebookresearch/sam3/commits --jq '.[] | .sha + " " + .commit.committer.date'`.
- Install from git. PyPI `sam3` 0.1.4 has no SAM 3.1 builders and no BPE vocabulary file.
- Its metadata misses runtime imports: add `einops`, `pycocotools`, `psutil` and
  `setuptools<82` (it imports `pkg_resources`, which setuptools 82.0.0 removed).
- `numpy>=1.26,<2` caps Python at 3.12 (numpy 1.26 has no newer wheels) and conflicts with
  `opencv-python-headless` 4.12 and later, which native video needs for MP4 input
  (`cv2.VideoCapture`, imported lazily, not declared);
  [references/local.md](references/local.md) gives the two ways out.
- SAM 3.1 video is broken out of the box at every commit since 2026-04-21: `start_session`
  raises `TypeError: ... init_state() got an unexpected keyword argument 'offload_state_to_cpu'`
  (issue #544, fix PR #543 open). Wrap `predictor.model.init_state` to drop that argument, as in
  [references/local.md](references/local.md), and remove the wrapper once #543 merges.
- Pass `use_fa3=False` unless the GPU is Hopper (compute capability 9.0).
  `build_sam3_predictor` and `build_sam3_multiplex_video_predictor` default to `True`, which
  imports FlashAttention 3 (H100/H800 only) and casts attention inputs to float8. Skip the
  README's optional `flash-attn-3` (Hopper only) and `cc_torch` (an unpinned git install; on
  CUDA, sam3 falls back to a Triton kernel).
- Wrap image-model calls in `torch.autocast("cuda", dtype=torch.bfloat16)`, as Meta's
  examples do. Without it they fail with "mat1 and mat2 must have the same dtype". Autocast is
  per thread: the multiplex video predictor switches it on only in the thread that built it, so
  wrap every call in the thread that runs it (a FastAPI worker thread, for one).
- Stream results arrive as `{"frame_index": i, "outputs": {...}}`: masks are
  `item["outputs"]["out_binary_masks"]`, whatever the builder docstring shows.
- Keep vLLM out of this environment; call it over HTTP.

## 9. Share the GPU

- Measured peaks (`torch.cuda.max_memory_allocated()`, real weights, the CUDA context comes on
  top; the model works at 1008 px whatever the photo size):

  | Workload | fp32 weights | bf16 weights |
  |---|---|---|
  | One image, transformers 5.19.0 (2 MP / 12 MP photo) | 3.8 / 4.0 GiB | 2.0 / 2.3 GiB |
  | One image, native at `0570b3a` (2 MP) | 3.9 GiB | n/a |
  | 200 frames of 960×540 video, transformers `Sam3VideoModel` | 7.2 GiB | 4.4 GiB |
  | The same clip, native SAM 3.1 multiplex, frames offloaded | 22–25 GiB | n/a |

  Native SAM 3.1 video needs several times the transformers budget; next to vLLM, prefer
  transformers video or the hosted API. Then measure your own largest request and `nvidia-smi`
  with every service loaded, and record the peak in the repo's `AGENTS.md`.
- vLLM claims `--gpu-memory-utilization` of the whole card at start (default 0.92 in v0.31.0,
  so 8% is left), and refuses to start if that much isn't free, so a SAM process already
  holding memory blocks it. Lower vLLM's share, time-share the GPU, or use the hosted API (see
  `compose-gpu-serving` and `local-model-serving`).
- `torch.cuda.set_per_process_memory_fraction()` in the SAM process makes SAM, not its
  neighbour, hit the out-of-memory error.
- Masks are upsampled to full image size as float32 before thresholding, so large photos with
  many matches add memory per instance (48 MB each at 12 megapixels, native).
- Load the model once per process and serve one request at a time on it: in FastAPI, an
  `asyncio.Lock` around `await anyio.to_thread.run_sync(...)` so inference doesn't block the
  event loop; in Gradio, leave the event's `concurrency_limit` at its default of 1.
- Long videos: keep frames in host RAM (`offload_video_to_cpu=True` native,
  `video_storage_device="cpu"` transformers).

## 10. SAM License duties

The weights, the `facebookresearch/sam3` code, `meta_sam_parser` and the `@meta-sam/*` npm
packages are under the **SAM License** (Last Updated November 19, 2025). The sam3 package's
trove classifier says MIT, but its License field and LICENSE file are the SAM License: record it
as the SAM License in license inventories. A repo that uses them:

- ships a copy of the Agreement with anything that distributes SAM Materials or derivatives,
  such as a Docker image with weights or sam3 code, a wheel, or vendored parser code (1.b.i);
- acknowledges SAM in any publication of results (1.b.ii);
- complies with privacy law and Trade Controls, with no ITAR, military, weapons, nuclear or
  espionage use (1.b.iii, 1.b.v), and no reverse engineering (1.b.iv).

Questions about what the terms allow go to the person; the agent reports the text.

## 11. VLM output into concepts

A VLM decides what to look for, SAM where it is: ask the VLM for JSON concept nouns, validate
each against section 2, send one SAM request per concept, then resolve "which one" in code or
back in the VLM. Validator, tool design and Meta's SAM 3 Agent rules:
[references/vlm-concepts.md](references/vlm-concepts.md).

## Check before you hand it back

- A concept that is present returns at least one mask; an absent one completes with zero
  records and no exception.
- Every hosted mask's `height × width` equals its box; every local mask matches the frame; an
  overlay lands on the object, including on an EXIF-rotated photo.
- COCO round trip: `pycocotools.mask.decode(rle)` equals the mask.
- `use_fa3=False` unless `torch.cuda.get_device_capability()` is `(9, 0)`.
- Native SAM 3.1 video: one `start_session` on a real clip succeeds (the #544 wrapper is in
  place until upstream fixes it).
- Peak VRAM measured with the largest input and recorded.
- Tests run offline: replay recorded stream events through `parse_responses_stream`; live
  tests skip without `MODEL_API_KEY` or without access to the gated weights.
- `.env.example` lists `MODEL_API_KEY=` and `HF_TOKEN=` with no values, and the diff holds no key
  or token.
