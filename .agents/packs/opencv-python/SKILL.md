---
name: opencv-python
description: "OpenCV (cv2) in Python: one headless wheel below 5; BGR/RGB, dtype, strides and EXIF at hand-offs to PIL, NumPy, PyTorch and Gradio; video codecs the wheels lack (H.264); server threads and pixel caps; typed tests. Use when code imports cv2, adds an opencv-* dependency, or shows wrong colours, rotated images, empty videos or libGL errors."
---

# OpenCV in Python

cv2 is a thin binding over C++ that hands back plain NumPy arrays, so most bugs sit at the
edges: which wheel is installed, what the array is when it leaves cv2 (channel order, dtype,
layout, orientation), what the video writer can encode, and how a server shares the CPU. Each
section handles one. The facts below were checked against opencv-python-headless 4.14.0.94
(OpenCV 4.14.0). Check the installed version first
(`uv run python -c "import cv2; print(cv2.__version__)"`), and look up anything that depends on
the version at the installed tag (section 7).

## 1. One wheel: headless, below 5

- `opencv-python`, `opencv-contrib-python`, `opencv-python-headless` and
  `opencv-contrib-python-headless` all install the same `cv2` package, so install exactly one
  (opencv-python README).
- Default: `uv add "opencv-python-headless>=4.14.0.94,<5"`. Use a GUI wheel only for a desktop
  tool that calls `cv2.imshow`/`waitKey`, and a contrib wheel only when you need a contrib module.
- Why below 5: PyPI shows 5.0.0.93 (2026-07-02) as the latest version because it is the highest
  number. But 4.14.0.94 (2026-07-29) is newer: it moves to FFmpeg 8.1.2 to fix CVE-2026-8461 and
  adds AV1 (dav1d) decoding. 5.0 moves `CascadeClassifier`, `HOGDescriptor`, `cv2.ml` and
  `cv2.gapi` to contrib, removes the Caffe/Darknet loaders, and changes the output of resize,
  warp and `putText`. Read [references/opencv-5.md](references/opencv-5.md) before you move.
- Resolvers take the highest version, so a dependency that requires `opencv-python` (ultralytics
  does) brings in 5.0.0.93 next to your 4.14 pin. The two wheels overwrite each other's files;
  in a test, `import cv2` then reported 5.0.0. Find the culprit with
  `uv tree --invert --package opencv-python`, and exclude the extra wheel in the workspace-root
  `pyproject.toml`. This needs uv 0.9.8+, and uv reads the setting only at the workspace root:

  ```toml
  [tool.uv]
  exclude-dependencies = ["opencv-python"]
  ```

  Removing the extra wheel also deletes the files it shared, which leaves a broken `cv2` (no
  `__version__`). Follow it with `uv sync --reinstall-package opencv-python-headless`. The
  dependency then runs on the headless `cv2`, so any window it opens (`imshow`) fails.
- NumPy: 4.13 and later need numpy>=2, 4.12.0.88 needs numpy>=2,<2.3, and 4.11.0.86 is the last
  release that accepts numpy 1.x. A dependency pinned to numpy<2 therefore holds you at
  4.11.0.86.
- To find a newer release, list the upload dates, take the newest release at least 7 days old,
  and read its notes at https://github.com/opencv/opencv-python/releases:

  ```bash
  curl -s https://pypi.org/pypi/opencv-python-headless/json \
    | jq -r '.releases | to_entries[] | select(.value | length > 0) | "\(.value[0].upload_time) \(.key)"' \
    | sort | tail -4
  ```

- `ImportError: libGL.so.1` (or `libgthread`/`libglib`) in a container means a GUI wheel is
  installed: its bundled Qt links against the system libGL and glib. Switch to the headless
  wheel, which needs only glibc, libstdc++ and zlib; don't apt-install `libgl1` to make the GUI
  wheel import.
- In the headless wheel, `cv2.imshow` raises `The function is not implemented. Rebuild the
  library with ...`. Don't follow its advice to install `libgtk2.0-dev`; write the image to a
  file, or return it to the caller.
- The wheels are built without CUDA: `cv2.cuda.getCudaEnabledDeviceCount()` returns 0 even on a
  GPU host. Run GPU inference in PyTorch, ONNX Runtime or a model server, and use cv2 for I/O and
  pre- and post-processing.

## 2. Know what the array is at every hand-off

A cv2 image is a NumPy array: HWC, BGR, uint8. `img.shape` is `(h, w, c)`, but sizes and points
are `(w, h)` and `(x, y)`: `cv2.resize(img, (w, h))`, `cv2.VideoWriter(..., (w, h))`. Keep BGR
inside cv2 code and convert once, at the boundary:

| Hand-off | Do |
|---|---|
| cv2 → PIL, matplotlib `imshow`, Gradio output, RGB-trained models | `rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)` |
| PIL → cv2 | `cv2.cvtColor(np.asarray(ImageOps.exif_transpose(im).convert("RGB")), cv2.COLOR_RGB2BGR)` |
| Gradio `gr.Image(type="numpy")` → cv2 | with the default `image_mode="RGB"` the input is RGB uint8 `(h, w, 3)`, so `cv2.cvtColor(x, cv2.COLOR_RGB2BGR)` |
| cv2 → PyTorch | `torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1)))`: CHW; `from_numpy` shares memory with the array it is given |
| cv2 → base64 for a VLM | `ok, buf = cv2.imencode(".jpg", bgr)`: imencode takes BGR, so don't convert |
| file → RGB directly | `cv2.imread(path, cv2.IMREAD_COLOR_RGB)` (4.11+) |

- Swap channels with `cvtColor`, not `img[..., ::-1]`. The slice is a negative-stride view:
  cv2 drawing functions refuse to write into it, and `torch.from_numpy` rejects it.
  `np.asarray(pil_image)` is read-only, so drawing into it fails too (`torch.from_numpy` only
  warns). These errors say `Overload resolution failed` and end with
  `Expected Ptr<cv::UMat> for argument '<name>'`. Ignore that last line: the earlier lines name
  the real cause (output layout incompatible, array marked as readonly, data type not supported).
  `np.ascontiguousarray(...)` fixes the layout and `.copy()` the writability.
- Masks: cv2 and its stubs reject bool arrays (`findContours`, `mask=`). Threshold a model's
  float mask first (`probs > 0.5`, which is bool), then pass `mask.astype(np.uint8) * 255`.
- Coordinates: drawing functions take integer points, and float tuples fail with an overload
  error. Round model boxes with `int(round(v))`. Polygons for `fillPoly`/`polylines` must be
  integer arrays: float32 fails `p.checkVector(2, CV_32S)`.
- NumPy uint8 arithmetic wraps (`200 + 100` gives 44); `cv2.add` and `cv2.addWeighted` saturate
  at 255.
- `cvtColor` takes uint8, uint16 or float32, not float64, so `astype(np.float32)` first.
- `resize` defaults to `INTER_LINEAR`. Its docstring recommends `INTER_AREA` for shrinking, and
  `INTER_CUBIC` or `INTER_LINEAR` for enlarging.
- `imwrite` and `imencode` convert to uint8 any depth the format can't store, with only a log
  warning and no scaling, so a float image in `[0, 1]` saves as near-black. Write
  `np.clip(x * 255, 0, 255).astype(np.uint8)`.
- `imwrite` returns `False` instead of raising when it can't write the file (a missing directory,
  for example), so check its result. It raises `cv2.error` only for an extension it has no
  writer for.

## 3. Reading images

- `imread` and `imdecode` return `None` for a missing or undecodable input. `imdecode` raises
  `cv2.error` for an empty buffer, and both raise it past the pixel cap below. So check for
  `None` straight after the call, and catch `cv2.error` where the input is untrusted. Decode
  uploads from bytes with `cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)`; the
  format comes from the content, not the file name.
- EXIF orientation: `imread` and `imdecode` rotate by the EXIF orientation tag by default, and
  `IMREAD_IGNORE_ORIENTATION` and `IMREAD_UNCHANGED` turn that off. PIL's `Image.open` never
  rotates. So the same phone JPEG comes out rotated differently in cv2 and PIL (a 90-degree tag
  also swaps h and w), and boxes computed in one land in the wrong place in the other.
  Normalise orientation once at ingestion (cv2's default flags, or `ImageOps.exif_transpose`),
  and pass pixels onward, not files.
- `IMREAD_UNCHANGED` keeps alpha (BGRA) and 16-bit depth, and it also skips the EXIF rotation.
  The default `IMREAD_COLOR` drops alpha and reduces a 16-bit PNG, such as a depth map, to 8 bits.
  Read a 16-bit single-channel image with `IMREAD_ANYDEPTH` (which also converts colour to
  grey), and 16-bit colour with `IMREAD_ANYDEPTH | IMREAD_COLOR` or `IMREAD_UNCHANGED`. Write
  transparent cut-outs as 4-channel BGRA PNGs.
- Decompression bombs: by default cv2 decodes up to 2^30 pixels (3 GiB as BGR) and 2^20 pixels
  per side, and a 4 KB PNG can decode to 4 megapixels. For untrusted images, set
  `OPENCV_IO_MAX_IMAGE_PIXELS` to the largest image you accept, in the process environment
  before the process starts (a Dockerfile `ENV` or Compose `environment`). cv2 reads it once, at
  load, so setting `os.environ` after `import cv2` has no effect. Past the cap, `imread` and
  `imdecode` raise `cv2.error`. Pillow 12.3.0 has its own
  guard: `Image.MAX_IMAGE_PIXELS` is 89,478,485 pixels; above it Pillow warns, and above twice it
  raises `DecompressionBombError`.

## 4. Video

- `VideoCapture` and `VideoWriter` don't raise when they fail; they only log. Check
  `isOpened()` after opening. `read()` returns `(False, None)` at the end of the stream. A writer
  drops any frame that isn't exactly its `(w, h)`, with only a log warning, so an empty output
  file usually means a size or codec mismatch.
- Release them in `try`/`finally`. `with cv2.VideoCapture(...)` works at runtime from 4.14, but
  the 4.14.0.94 stubs lack `__enter__`/`__exit__`, so mypy rejects it.
- Don't count on the wheels to encode H.264, HEVC or AV1. With the Linux x86_64 4.14.0.94 wheel,
  a `VideoWriter` opened with `avc1`, `H264`, `X264`, `hev1` or `av01` reports
  `isOpened() == False`. It can write `mp4v` (.mp4, MPEG-4 Part 2), `VP80`/`VP90` (.webm), `MJPG`
  (.avi) and `FFV1` (.mkv, lossless), and it can decode H.264. Other platforms' wheels differ, so
  test the codec where you deploy.
- For H.264 (browser playback, small files), encode outside cv2. Either pipe `bgr24` frames into
  an `ffmpeg` binary, or use PyAV (`av`, Python 3.12+), whose wheels bundle libx264. x264 is
  GPL-2.0-or-later, so check the licence fits before you ship either route.
  [references/video-io.md](references/video-io.md) has tested code for both, and a safe read loop.
- `VideoCapture` opens a path, an `http://` or `https://` URL (FFmpeg fetches it) or a camera
  index. In a server, give it only a path you wrote yourself (save the upload to a temporary file
  first), never a string from the request. Setting
  `OPENCV_FFMPEG_CAPTURE_OPTIONS="protocol_whitelist;file"` in the environment makes FFmpeg
  refuse URLs as well (quote it: `;` ends a shell command).
- The wheels' FFmpeg parses whatever bytes it is given. opencv-python #1272 (open) reports CVEs
  in the bundled FFmpeg that are fixed only in FFmpeg 9, and a contributor there confirms that
  FFmpeg 8.1.2, which 4.14.0.94 bundles, is still in the affected range. Decode untrusted video
  in an isolated worker, or with PyAV 19.0.1, which bundles FFmpeg 9.0.2.

## 5. Servers and worker pools

- OpenCV sizes its own thread pool to the CPU count (it honours cgroup CPU quotas), and cv2 calls
  release the GIL. Several worker processes (Uvicorn or Gunicorn workers, Celery, PyTorch
  `DataLoader` workers, `ProcessPoolExecutor`) therefore oversubscribe the CPU. Call
  `cv2.setNumThreads(1)` once at worker start (1 runs everything sequentially), or set
  `OPENCV_FOR_THREADS_NUM=1` in the environment. The setting is process-wide and not
  thread-safe, so set it once, never per request. A single batch process can keep the default.
- FastAPI: do cv2 work in a `def` endpoint, which FastAPI runs in a threadpool, or with
  `run_in_threadpool`. Done inline in an `async def` endpoint, it blocks the event loop. See the
  `fastapi` skill.
- Untrusted uploads: cap bytes at the HTTP layer and pixels with `OPENCV_IO_MAX_IMAGE_PIXELS`
  (section 3), and keep the wheel current, because its bundled codecs parse attacker-controlled
  bytes.

## 6. Types and tests

- The wheels ship `cv2/__init__.pyi` and `py.typed` (stubs since 4.8.0.74, `cv2.typing` since
  4.8.0.76), so mypy checks cv2 calls; don't add `ignore_missing_imports` for cv2. Annotate
  images as `cv2.typing.MatLike`.
- The stubs catch an unguarded `imread`, which returns `MatLike | None`, and a mask typed as a
  bool array, because `MatLike` allows only integer and floating dtypes. They can't catch BGR vs
  RGB, `(w, h)` vs `(h, w)`, negative strides or a bare `np.ndarray` of bools; those need tests.
- Write `cv2.VideoWriter.fourcc(*"mp4v")`. The older `cv2.VideoWriter_fourcc` still works at
  runtime, but the stubs don't declare it, so mypy rejects it.
- Build test images in code (`np.zeros` plus `cv2.rectangle`), not from photos. Compare lossless
  paths (PNG) exactly. Compare lossy or interpolated ones (JPEG, resize, warp) with a tolerance,
  because resize and warp output changes between OpenCV versions. A PNG round trip makes a good
  property test (see the `property-based-testing` skill).
  [references/testing.md](references/testing.md) has tested examples, including an EXIF-rotated
  JPEG fixture and a pixel-cap test.

## 7. Reading the docs

docs.opencv.org answers scripted fetches such as curl with a 403 Cloudflare challenge. Read
these instead, in order:

- The binding's docstrings, which carry the full reference text:
  `uv run python -c "import cv2; print(cv2.resize.__doc__)"`.
- The installed stubs: `__init__.pyi` in the directory of `cv2.__file__`.
- The headers at the installed tag, for example
  `https://raw.githubusercontent.com/opencv/opencv/4.14.0/modules/imgcodecs/include/opencv2/imgcodecs.hpp`.
  The environment variables are in `doc/tutorials/introduction/env_reference/env_reference.markdown`
  at the same tag.
- For packaging, codecs and licences: the opencv/opencv-python README and release notes.

Online tutorials often reach for `cv2.imshow`, SURF (non-free, not in the wheels), `cv2.cuda`
(the module exists, but the wheels are built without CUDA) or Haar cascades (legacy, and
contrib-only from 5.0). Check each against the installed wheel before you use it.

## Check before you hand it back

```bash
# exactly one opencv distribution
uv run python -c "import importlib.metadata as m; print(sorted(d.metadata['Name'] for d in m.distributions() if d.metadata['Name'].lower().startswith('opencv')))"
# version, and GUI: NONE on a headless wheel
uv run python -c "import cv2; print(cv2.__version__); print(cv2.getBuildInformation())" | grep -E "^[0-9]|GUI:|FFMPEG:"
uv run ruff check . && uv run mypy src && uv run pytest
```
