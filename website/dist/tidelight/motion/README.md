# TIDELIGHT motion source

This is the public, source-only companion to the TIDELIGHT cinematic review. It
contains the editable Blender scene, the procedural motion extension, the math
specification, the independent state checks, and the small local review UI.
Rendered PNG frames and MP4 films are intentionally omitted from this archive;
the published review supplies those separately.

## Layout

- `../scene.py` is the preserved parent scene. Its SHA-256 is
  `03484bd17d1f9c3e0a280c0d1302462181d1b1ec1e348d643232afb1faa6562c`.
- `shot_scene.py` adds deterministic water, mist, wet-stone and camera motion.
- `render_shot.py` rebuilds the scene and renders previews or a full sequence.
- `shot.blend` is an editable snapshot of the authored geometry, materials and
  initial camera. Runtime Python handlers are installed by the script rather
  than persisted in the Blender file.
- `metadata/motion_spec.json` records the authored constants and claim limits.
- `qa/MOTION_CHECKS.json` records the independent geometry, rewind, control and
  source-preservation checks.
- `review.html`, `review.js`, `review.css` and `review-data.js` are the browser
  explanation UI. The source archive does not include its MP4 or poster assets.

## Reproduce the checks

Run from `tidelight-motion/cinematic-shot` with Blender 5.1.2 or a compatible
version:

```sh
blender --background --factory-startup --python verify_motion.py
```

The check rebuilds the parent scene, samples the motion at multiple times,
rewinds it, applies nearest no-motion controls, and compares all 21,901 water
vertices with an independent vectorized four-wave formula. A passing result is
about deterministic scene state; it is not a claim of calibrated fluid physics
or cross-GPU pixel identity.

## Render the shot

```sh
blender --background --factory-startup --python render_shot.py -- \
  --frame 120 --width 960 --height 540 --samples 24 \
  --output previews/check-0120.png
```

The full 1600 × 900, 24 fps, 240-frame render is deliberately opt-in:

```sh
blender --background --factory-startup --python render_shot.py -- \
  --movie --width 1600 --height 900 --samples 24
```

On the reference M1 Max machine this completed in 4,749.034911 seconds
(79m09s). That is a measured local receipt, not a promise of the same runtime
on another machine. `compose_film.py` then assembles the rendered frames and
equation overlays:

```sh
python3 compose_film.py
```

The compositor expects Pillow, NumPy, Matplotlib, `/opt/homebrew/bin/ffmpeg`,
and `/System/Library/Fonts/Supplemental/Arial.ttf`. Those executable and font
paths are macOS/Homebrew assumptions and need adjustment elsewhere. The source
is a recipe for reproduction, not a hosted build service.

## What the equations do

The water surface is displaced by four traveling sine waves. Mist is a moving
3D noise density field with a height falloff; it is procedural advection, not a
fluid simulation. Wet-stone roughness and coat are mapped from world-space
height. A smoothstep camera rail supplies the slow parallax move. Lengths are
scene units; the historical `_m` field names describe an assumed scale rather
than a physical calibration.

The browser wave controls alter its explanatory diagram only. They do not
rerender the film. The earlier three-parameter inverse experiment remains a
separate artifact and is not silently reinterpreted as recovery of this moving
scene.

## Local preview

The review UI expects the two MP4 files and `poster.png` beside `review.html`.
Those media files are absent from this source-only package. To serve a complete
local review, obtain the published media or place compatible files at the names
referenced by `review.html`, then run the loopback-only server:

```sh
python3 serve_review.py
```

Companion pages and media:

- Original experiment: https://www.xn--arkh-eva.org/tidelight/
- Motion study: https://www.xn--arkh-eva.org/tidelight/motion/
- Clean film: https://www.xn--arkh-eva.org/tidelight/motion/tidelight-cinematic-shot.mp4
- Math film: https://www.xn--arkh-eva.org/tidelight/motion/tidelight-motion-and-math.mp4
- Poster: https://www.xn--arkh-eva.org/tidelight/motion/poster.png


## Rights and dependencies

The procedural source and scene are provided for inspection and reproduction;
no blanket open-source licence is granted. Blender/Cycles is a separately
installed renderer. KaTeX and bundled fonts retain their upstream licences in
`vendor/katex/LICENSE` and `vendor/licenses/`. See `NOTICE.txt` for the
third-party notices.
