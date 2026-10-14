# Running SAM 3 locally

Checked 2026-10-14 against transformers v5.19.0 (`docs/source/en/model_doc/sam3*.md`) and
facebookresearch/sam3 at commit `0570b3a5be9c4e694f23d85232fb55f4a6f1f7fc`, and run with the real
weights on an Ampere GPU (compute capability 8.6) with torch 2.14.1. Both paths need approved
access to the gated weights (SKILL.md section 6) and a CUDA build of torch.

## torch

PyPI's Linux torch wheels target CUDA 13.0 (since 2.11.0; 2.14.1 was the newest release at least
7 days old on 2026-10-14), which needs a driver that `nvidia-smi` reports as CUDA 13.0 or later.
For an older driver, take torch and torchvision from a PyTorch index, following
https://docs.astral.sh/uv/guides/integration/pytorch/ (2.14.1 is on `cu126` and `cu130`):

```toml
[[tool.uv.index]]
name = "pytorch-cu126"
url = "https://download.pytorch.org/whl/cu126"
explicit = true

[tool.uv.sources]
torch = [{ index = "pytorch-cu126", marker = "sys_platform == 'linux'" }]
torchvision = [{ index = "pytorch-cu126", marker = "sys_platform == 'linux'" }]
```

## transformers (SAM 3.0)

```toml
dependencies = [
  "transformers>=5.0",  # Sam3* classes first shipped in 5.0.0; checked with 5.19.0
  "accelerate",         # device_map= raises ValueError without it (5.19.0)
  "torch",
  "pillow",
]
```

```python
import torch
from PIL import Image
from transformers import Sam3Model, Sam3Processor

model = Sam3Model.from_pretrained("facebook/sam3", dtype=torch.bfloat16, device_map="auto")
processor = Sam3Processor.from_pretrained("facebook/sam3")
image = Image.open("photo.jpg").convert("RGB")  # apply ImageOps.exif_transpose first for photos

# Vision features once, then one text prompt per concept.
img_inputs = processor(images=image, return_tensors="pt").to(model.device)
with torch.inference_mode():
    vision_embeds = model.get_vision_features(pixel_values=img_inputs.pixel_values)
    for concept in ["forklift", "pallet"]:
        text_inputs = processor(text=concept, return_tensors="pt").to(model.device)
        outputs = model(vision_embeds=vision_embeds, **text_inputs)
        result = processor.post_process_instance_segmentation(
            outputs, threshold=0.5, mask_threshold=0.5,
            target_sizes=img_inputs.get("original_sizes").tolist(),
        )[0]
        # result["masks"]: (N, H, W) int64 0/1 at the original size
        # result["boxes"]: xyxy pixels; result["scores"]: confidence
```

- `dtype` defaults to `"auto"`, which for `facebook/sam3` means fp32 (the checkpoint is F32);
  `torch.bfloat16` halves the weights.
- Box prompts: `input_boxes=[[[x1, y1, x2, y2]]]` in pixels with `input_boxes_labels=[[1]]`
  (`0` excludes, `-10` pads a batch). On `Sam3Model` a box is an exemplar of the concept.
- One object per click or box (SAM 2 style): `Sam3TrackerModel` / `Sam3TrackerProcessor`, with
  `input_points=[[[[x, y]]]]` (image, object, point, xy) and `input_labels=[[[1]]]`, masks from
  `processor.post_process_masks(outputs.pred_masks.cpu(), inputs["original_sizes"])`. A point
  returns three candidate masks ranked by `outputs.iou_scores`; pass `multimask_output=False` to
  the model for one.
- Video: `Sam3VideoModel` and `Sam3VideoProcessor`. `init_video_session(video=frames,
  inference_device="cuda", processing_device="cpu", video_storage_device="cpu",
  dtype=torch.bfloat16)` (the dtype must match the model's; it defaults to fp32), then
  `add_text_prompt(session, ["person", "bed"])` (a list of separate phrases is fine here), then
  `model.propagate_in_video_iterator(inference_session=session)` and
  `processor.postprocess_outputs(session, out)` per frame: `object_ids`, `scores`, `boxes`
  (xyxy pixels), `masks`, and `prompt_to_obj_ids`.
- `config.image_size` below 1008 saves memory and costs accuracy (the docs warn).

## Native facebookresearch/sam3

```toml
[project]
requires-python = ">=3.12,<3.13"   # numpy>=1.26,<2 has no wheels past 3.12
dependencies = [
  "sam3",
  "torch",
  "torchvision",
  "einops",            # imported, not declared, at 0570b3a
  "pycocotools",       # imported, not declared
  "psutil",            # imported, not declared
  "setuptools<82",     # model_builder imports pkg_resources, removed in setuptools 82.0.0
]

[tool.uv.sources]
sam3 = { git = "https://github.com/facebookresearch/sam3", rev = "0570b3a5be9c4e694f23d85232fb55f4a6f1f7fc" }
```

Video from an MP4 file reads frames with `cv2.VideoCapture` (a folder of JPEG frames does not
need OpenCV), and every `opencv-python-headless` from 4.12 on requires `numpy>=2`. Pick one:

- `[tool.uv] override-dependencies = ["numpy>=2,<2.4"]` plus
  `opencv-python-headless>=4.14.0.94,<5` (4.14.0.94 bumped FFmpeg for CVE-2026-8461; 5.0.0.93
  is older and lacks it). Image and SAM 3.1 video smoke tests passed with numpy 2.3.5; run your
  own before relying on it.
- Keep numpy 1.26 and pin `opencv-python-headless==4.11.0.86`, the last wheel without
  `numpy>=2`. It predates that FFmpeg fix, so keep untrusted video away from its decoder.

Image, text prompt:

```python
import torch
from PIL import Image
from sam3.model.sam3_image_processor import Sam3Processor
from sam3.model_builder import build_sam3_image_model

model = build_sam3_image_model()  # downloads sam3.pt from facebook/sam3 (gated)
processor = Sam3Processor(model, confidence_threshold=0.5)
image = Image.open("photo.jpg").convert("RGB")  # PIL only: an HWC ndarray gets the wrong size

with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
    state = processor.set_image(image)
    out = processor.set_text_prompt(prompt="forklift", state=state)
masks = out["masks"][:, 0].cpu().numpy()  # (N, H, W) bool
boxes = out["boxes"].float().cpu().numpy()  # (N, 4) xyxy pixels
scores = out["scores"].float().cpu().numpy()
```

Box exemplar on an image: `processor.add_geometric_prompt(box=[cx, cy, w, h], label=True,
state=state)`, normalized to 0..1 (`sam3.model.box_ops.box_xywh_to_cxcywh` converts); it returns
every similar object. For one object (SAM 1 style), build with
`build_sam3_image_model(enable_inst_interactivity=True)` and call
`model.predict_inst(state, point_coords=None, point_labels=None, box=np.array([x1, y1, x2, y2]),
multimask_output=False)` after `set_image`, in pixels; it returns float32 numpy masks
`(C, H, W)`, scores and logits.

SAM 3.1 video (Object Multiplex):

```python
import torch
from sam3.model_builder import build_sam3_multiplex_video_predictor

predictor = build_sam3_multiplex_video_predictor(use_fa3=False)  # downloads facebook/sam3.1

# sam3 issue #544: start_session passes offload_state_to_cpu, which the SAM 3.1 model rejects.
_init_state = predictor.model.init_state
def _init_state_compat(*args, offload_state_to_cpu=False, **kwargs):
    return _init_state(*args, **kwargs)
predictor.model.init_state = _init_state_compat

with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
    session = predictor.handle_request({
        "type": "start_session",
        "resource_path": "clip.mp4",            # or a folder of frames named 0.jpg, 1.jpg, ...
        "offload_video_to_cpu": True,           # frames in host RAM, not VRAM
    })["session_id"]
    try:
        predictor.handle_request({"type": "add_prompt", "session_id": session,
                                  "frame_index": 0, "text": "forklift"})
        tracks = {}
        for item in predictor.handle_stream_request({"type": "propagate_in_video",
                                                     "session_id": session}):
            o = item["outputs"]                 # not item["out_binary_masks"]
            tracks[item["frame_index"]] = (o["out_obj_ids"], o["out_boxes_xywh"], o["out_binary_masks"])
    finally:
        predictor.handle_request({"type": "close_session", "session_id": session})
```

- Outputs are numpy arrays. `out_boxes_xywh` is normalized `x, y, w, h` (top-left origin);
  multiply by the frame size. `out_binary_masks` is `(N, H, W)` bool at video resolution, row `i`
  belonging to `out_obj_ids[i]`; `out_probs` holds scores.
- `propagation_direction` defaults to `"both"`, so frame indices arrive forward from the prompt
  frame, then backward. Key results by `frame_index`.
- Boxes on `add_prompt` (`bounding_boxes=[[x, y, w, h]]`, `bounding_box_labels=[1]`) are
  always normalized to 0..1 and act as exemplars: every similar object comes back. Points
  (`points=[[x, y]]`, `point_labels=[1]`, normalized while `rel_coordinates=True`, the default)
  add or refine one object and require an `obj_id`; they can't share a request with text or
  boxes.
- Changing the text prompt means `{"type": "reset_session", ...}` first, or results mix.
- Nothing at this commit enforces `session_expiration_sec` (1200): an unclosed session keeps
  its state until `close_session`, so close sessions in a `finally`.
- `build_sam3_predictor(version="sam3.1", use_fa3=False)` is the same builder behind one name.
- The docstring's `compile=True` speedup is described for SAM 3.1; measure before keeping it.

## Smoke test and VRAM

```python
import torch

print(torch.cuda.get_device_name(), torch.cuda.get_device_capability())  # FA3 needs (9, 0)
torch.cuda.reset_peak_memory_stats()
# ... one realistic request: largest image size, longest clip, most objects ...
print(f"peak {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
```

Check: a present concept gives at least one mask, an absent one gives none, masks match the
frame size, and the overlay lands on the object. Record the peak in the repo's `AGENTS.md`.
