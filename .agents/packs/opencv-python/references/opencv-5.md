# OpenCV 5 for Python code

The source is the OpenCV 4-to-5 migration guide:
https://github.com/opencv/opencv/wiki/OpenCV-4-to-5-migration. Its raw Markdown is at
https://raw.githubusercontent.com/wiki/opencv/opencv/OpenCV-4-to-5-migration.md. Re-read it
before you move, because it is still being edited (its VLM section says TBD).

## When to move

As of 2026-10-14 the only 5.x wheel is 5.0.0.93 (2026-07-02). It predates 4.14.0.94, and the
opencv-python tracker has these issues open against it:

- #1244: the `cv2.data.haarcascades` XML files are missing.
- #1263: `applyColorMap` returns a different shape than in 4.x.
- #1272: CVEs in the bundled FFmpeg 8.1.1 that are fixed only in FFmpeg 9.
- #1276: the Linux wheels can't decode AV1 (no dav1d).
- #1260: the macOS arm64 wheel bundles a GPL-configured FFmpeg, which contradicts the README's
  LGPL statement.

Move only once a newer 5.x wheel is at least 7 days old and its release notes address the issues
that affect you. Then pin `opencv-python-headless>=5.x.y,<6`.

## What breaks for Python code

- `cv2.CascadeClassifier` and `cv2.HOGDescriptor` are gone from the main wheels (moved to
  `xobjdetect` in contrib). Use a contrib wheel, where they keep their `cv2.` names (5.0.0.93
  lacks the cascade XML files, #1244), or replace face detection with `cv2.FaceDetectorYN`
  (ONNX YuNet, in the main `objdetect` module).
- `cv2.ml` is contrib-only; the guide suggests scikit-learn.
- `cv2.dnn.readNetFromCaffe` and `readNetFromDarknet` are removed. Convert those models to ONNX
  and load them with `readNetFromONNX`. A new default DNN engine runs on CPU only; choose one with
  `engine=` or `OPENCV_FORCE_DNN_ENGINE`.
- A NumPy array passed as `InputArray` maps to a true 1D `Mat`, not an `Nx1` column, so code
  that relied on the column layout needs checking.
- `VideoCapture.get()` returns -1 for an unsupported property (4.x returns 0), so test for `< 0`.
- `INTER_NEAREST` resize now follows Pillow's rounding, and `warpAffine`, `warpPerspective` and
  `remap` give slightly different bilinear and bicubic output. Regenerate pixel-exact test
  baselines.
- `putText` with `FONT_HERSHEY_*` still works, but it now renders with the embedded Rubik
  TrueType font, so text size and look change. The new `cv2.FontFace` takes UTF-8 text and
  `.ttf`/`.otf` fonts.
- Function locations moved in C++ (calib3d split into geometry, calib and stereo; features2d
  became features), but every function is still `cv2.<name>` in Python.

## Check after the move

```bash
uv run python -c "import cv2; print(cv2.__version__, hasattr(cv2, 'CascadeClassifier'), hasattr(cv2, 'ml'))"
uv run pytest   # expect resize/warp/putText baselines to need regenerating
```
