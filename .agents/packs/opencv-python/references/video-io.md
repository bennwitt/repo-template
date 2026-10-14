# Video I/O with the pip wheels

Tested with opencv-python-headless 4.14.0.94 on Linux x86_64 and Python 3.12, PyAV 19.0.1, an
`ffmpeg` binary that has libx264, and `mypy --strict` 2.4.0. Builds differ by platform:
opencv-python #1260 reports that the macOS arm64 5.0.0.93 wheel bundles libx264. So test the
codec on the platform you deploy to, and don't rely on what one machine accepts.

## Read frames safely

```python
import cv2


def count_frames(path: str) -> int:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {path}")
    try:
        n = 0
        while True:
            ok, frame = cap.read()  # (False, None) at the end
            if not ok:
                break
            n += 1  # frame is BGR uint8 (h, w, 3)
        return n
    finally:
        cap.release()
```

- Use `try`/`finally` rather than `with`: the context manager works at runtime from 4.14, but
  the 4.14.0.94 stubs don't declare it, so mypy fails on it.
- In 5.0, `get()` returns -1 for an unsupported property (4.x returns 0), so test for `< 0`.

## What `cv2.VideoWriter` can write

| fourcc | container | result in the 4.14.0.94 Linux wheel |
|---|---|---|
| `mp4v` | .mp4 | works (MPEG-4 Part 2) |
| `VP80`, `VP90` | .webm | works; ignore the "tag is not supported" log line |
| `MJPG`, `XVID` | .avi | works |
| `FFV1` | .mkv | works (lossless) |
| `avc1`, `H264`, `X264`, `hev1` | .mp4/.mkv | `isOpened()` is False: no H.264/HEVC encoder |
| `av01`, `AV01` | .mp4/.mkv | `isOpened()` is False: no AV1 encoder |

```python
import cv2

writer = cv2.VideoWriter("out.webm", cv2.VideoWriter.fourcc(*"VP90"), 25.0, (w, h))
if not writer.isOpened():
    raise RuntimeError("codec/container not available in this cv2 build")
try:
    for frame in frames:  # every frame must be BGR uint8 with shape (h, w, 3)
        writer.write(frame)
finally:
    writer.release()
```

## H.264 through an ffmpeg binary

Get the binary from the OS package manager in the image (Debian/Ubuntu `ffmpeg`), or from
imageio-ffmpeg: `imageio_ffmpeg.get_ffmpeg_exe()` returns a bundled static GPL build (0.6.0
ships FFmpeg 7.0.2). Either is fine for encoding frames you produced; don't use an older FFmpeg
to decode untrusted video.

```python
import os
import subprocess
from collections.abc import Iterable

import numpy as np
from cv2.typing import MatLike


def write_h264(
    path: str, frames: Iterable[MatLike], w: int, h: int, fps: float, ffmpeg: str = "ffmpeg"
) -> None:
    cmd = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart",
        path,
    ]
    # cv2 prepends its library directory to LD_LIBRARY_PATH on import, leaving an empty
    # (current-directory) entry when it was unset (opencv-python #1268); don't pass that on.
    env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, env=env)
    assert proc.stdin is not None
    try:
        for frame in frames:
            if frame.shape != (h, w, 3) or frame.dtype != np.uint8:
                raise ValueError(f"bad frame {frame.shape} {frame.dtype}")
            proc.stdin.write(np.ascontiguousarray(frame).tobytes())
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg exited with {proc.returncode}")
```

- Pass `-pix_fmt yuv420p`. Given `bgr24` input, libx264 otherwise picks `yuv444p` (the High 4:4:4
  Predictive profile). The FFmpeg H.264 guide notes that QuickTime and most other players
  support only 4:2:0 H.264, so `yuv420p` is the one that plays widely.
- `-movflags +faststart` moves the index (the moov atom) to the start of the file, so a browser
  can start playing before the whole file has downloaded.
- The pipe carries raw bytes, so a frame of the wrong size shifts every frame after it; check
  the shape before you write, as above.

## H.264 with PyAV

PyAV (`av`, BSD-3-Clause, Python 3.12+) wheels bundle FFmpeg with libx264, except on 32-bit ARM
(19.0.1 bundles FFmpeg 9.0.2). Pin the newest release that is at least 7 days old.

```python
from collections.abc import Iterable

import av
import numpy as np
from cv2.typing import MatLike


def write_h264_av(path: str, frames: Iterable[MatLike], w: int, h: int, fps: int) -> None:
    with av.open(path, mode="w") as container:
        stream = container.add_stream("libx264", rate=fps)
        stream.width, stream.height = w, h
        stream.pix_fmt = "yuv420p"
        for bgr in frames:
            if bgr.shape != (h, w, 3) or bgr.dtype != np.uint8:
                raise ValueError(f"bad frame {bgr.shape} {bgr.dtype}")
            frame = av.VideoFrame.from_ndarray(np.asarray(bgr, np.uint8), format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():  # flush
            container.mux(packet)
```

cv2 reads the result back (`VideoCapture` reports fourcc `h264`). Check the frame shape
yourself: PyAV rescales a frame whose size differs from the stream's instead of rejecting it.
`np.asarray(bgr, np.uint8)` is a no-op after the check, and gives mypy the uint8 type PyAV's
stubs require.

## Untrusted video

- Write the upload to a temporary file you created, and pass that path to `VideoCapture`.
  `VideoCapture` also accepts `http(s)` URLs (FFmpeg fetches them) and camera indexes, so a
  string taken from a request is a server-side request forgery (SSRF) hole. To make FFmpeg open
  local files only, set `OPENCV_FFMPEG_CAPTURE_OPTIONS="protocol_whitelist;file"` in the process
  environment (`key;value` pairs, separated by `|`); with it, a URL fails to open and a local
  file still reads.
- Cap the duration and resolution after opening (`CAP_PROP_FRAME_COUNT`, `CAP_PROP_FRAME_WIDTH`,
  `CAP_PROP_FRAME_HEIGHT`), and stop reading once you pass the cap.
- 4.14.0.94 bundles FFmpeg 8.1.2. opencv-python #1272 (open) reports CVEs fixed only in FFmpeg 9,
  and a contributor there confirms that 8.1.2 is still in the affected range. Decode in a
  separate worker with resource limits, or with PyAV, whose 19.0.1 wheels bundle FFmpeg 9.0.2.
- Tuning and debugging variables (`OPENCV_FFMPEG_CAPTURE_OPTIONS`, `OPENCV_VIDEOIO_DEBUG`,
  `OPENCV_FFMPEG_READ_ATTEMPTS`) are listed in `env_reference.markdown` at the installed tag.
