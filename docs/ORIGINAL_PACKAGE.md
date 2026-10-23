# Tidelight reproduction inputs

This archive repeats the fixed, known-model three-parameter experiment in a new `replays/` folder. It preserves the original mixed result: A and C passed; B failed parameter accuracy. Every case had a budget of 70 candidate renders. The maximum accepted parameter error is 8% of each allowed range, with at least 50% image RMSE reduction on training and both held-out conditions.

The target arrays and hidden labels are included for reproducibility. Labels were withheld through the fitting process interface during the original experiment; this was not cryptographic isolation. The replay supplies target arrays to the fitter and labels only to the evaluator.

## Run

Requirements: Blender 5.1.2 with Cycles, Python 3 with NumPy and SciPy, and zsh. The default launcher paths target macOS. Set `CINEMATIC_BLENDER` and `CINEMATIC_PYTHON` to use other installed executable paths. Compute runs locally; this is a full render-and-fit replay, not a quick website build.

```sh
zsh reproduce.sh
```

The command prints the new results path. It does not overwrite the original `RESULTS.json`. Exact pixel bytes or cross-platform equality are not promised. `scene.py` contains the original scene builder; `PROTOCOL.md` contains the fixed settings and acceptance criteria.

## Contents

- Scene, fitter, renderer service, evaluator and reproduction launcher.
- Three target float RGB arrays and display PNGs.
- Evaluation labels, frozen protocol and identity receipts.
- Original results, rebuild receipt and numerical verification receipt.

The editable `.blend`, construction movie and interactive website are separate downloads in the Tidelight page. Rendering uses Blender Cycles and denoising; the PNG display transform differs from the scene-linear arrays used for acceptance metrics.
