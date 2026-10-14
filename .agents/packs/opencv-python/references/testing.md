# Typed cv2 code and its tests

Tested with opencv-python-headless 4.14.0.94, numpy 2.5.3, Pillow 12.3.0, pytest 9.1.1,
Hypothesis 6.168.5 and `mypy --strict` 2.4.0, on Python 3.12.

## A small typed boundary module

Keep decoding, orientation and mask conversion in one module, so the rest of the code receives
arrays whose shape, dtype and channel order are known.

```python
# src/<package>/images.py
import cv2
import numpy as np
from cv2.typing import MatLike


def decode_bgr(data: bytes) -> MatLike:
    """Decode an upload to BGR uint8 (h, w, 3), EXIF orientation applied."""
    try:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as e:  # empty input, or over OPENCV_IO_MAX_IMAGE_PIXELS
        raise ValueError("image rejected by the decoder") from e
    if img is None:
        raise ValueError("not a decodable image")
    return img


def mask_contours(mask: np.ndarray) -> list[MatLike]:
    """Outer contours of a bool or 0/1 mask (cv2 rejects bool arrays)."""
    m = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return list(contours)
```

Under `mypy --strict`, `return cv2.cvtColor(cv2.imread(path), ...)` fails because `imread`
returns `MatLike | None`, and passing an array typed as bool fails because `MatLike` excludes
bool. Treat both errors as real bugs; don't silence them with `cast` or `# type: ignore`.

## Tests

```python
# tests/test_images.py
import io
import os
import subprocess
import sys

import cv2
import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays
from PIL import Image

from <package>.images import decode_bgr, mask_contours

bgr_images = arrays(np.uint8, st.tuples(st.integers(1, 64), st.integers(1, 64), st.just(3)))


@given(bgr_images)
def test_png_round_trip_is_lossless(img: np.ndarray) -> None:
    ok, buf = cv2.imencode(".png", img)
    assert ok
    np.testing.assert_array_equal(decode_bgr(buf.tobytes()), img)


def test_jpeg_round_trip_is_close() -> None:
    img = np.zeros((32, 48, 3), np.uint8)
    img[:, :24] = (255, 0, 0)  # blue, in BGR
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    out = decode_bgr(buf.tobytes())
    assert out.shape == img.shape
    assert np.abs(out.astype(np.int16) - img).mean() < 3  # lossy: tolerance, not equality


def test_exif_orientation_is_applied() -> None:
    # 40 wide x 20 high, tagged "rotate 90 degrees clockwise to display" (orientation 6)
    exif = Image.Exif()
    exif[0x0112] = 6
    raw = io.BytesIO()
    Image.new("RGB", (40, 20), (255, 0, 0)).save(raw, "JPEG", exif=exif.tobytes())
    assert decode_bgr(raw.getvalue()).shape == (40, 20, 3)  # rotated: h=40, w=20


@pytest.mark.parametrize("data", [b"", b"not an image"])
def test_bad_input_is_rejected(data: bytes) -> None:
    with pytest.raises(ValueError):
        decode_bgr(data)


def test_pixel_cap_rejects_large_images() -> None:
    # cv2 reads the cap once, when it loads, so test it in a fresh process
    ok, buf = cv2.imencode(".png", np.zeros((100, 100, 3), np.uint8))
    code = (
        "import sys\n"
        "from <package>.images import decode_bgr\n"
        "decode_bgr(sys.stdin.buffer.read())"
    )
    env = {**os.environ, "OPENCV_IO_MAX_IMAGE_PIXELS": "1000"}
    cmd = [sys.executable, "-c", code]
    r = subprocess.run(cmd, input=buf.tobytes(), env=env, capture_output=True)
    assert r.returncode != 0
    assert b"ValueError: image rejected by the decoder" in r.stderr


def test_bool_mask_contours() -> None:
    mask = np.zeros((20, 20), bool)
    mask[5:10, 5:10] = True
    assert len(mask_contours(mask)) == 1
```

- Build inputs in code: shapes, colours and expected outputs stay visible in the test, and
  nothing depends on a binary fixture.
- Use exact equality only for lossless paths. JPEG, resize and warp need a tolerance; 5.0 also
  changed nearest-neighbour resize and bilinear/bicubic warp output, so pixel-exact baselines
  break on upgrade.
- Test the decompression-bomb cap in a subprocess with `OPENCV_IO_MAX_IMAGE_PIXELS` set in its
  environment, as above: cv2 reads the variable once, when it loads, so changing `os.environ`
  inside the test process does nothing.
