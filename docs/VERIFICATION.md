# Repository verification — 23 October 2026

The packaged source was exercised before its first GitHub publication on macOS,
Apple M1 Max, host Python 3.9.6 and Blender 5.1.2 / Cycles Metal.

| Check | Result |
| --- | --- |
| Frozen source, target and extension hashes | 10 verified |
| Recovery protocol tests | 11 passed |
| Asset-fetch tests | 3 passed, including changed-file and bad-checksum rejection |
| Motion/state verifier | 26 passed |
| Water formula comparison | 21,901 vertices; maximum absolute error 7.44e-9 scene units |
| Fresh preview render | Frame 120, 960×540, 24 samples, completed |
| Portable compositor | Five 1600×900 annotated stills generated from existing rendered frames |
| Published asset download | Seven assets verified by byte count and SHA-256 |
| Complete original inverse replay | Completed; A/C pass, B fails parameter accuracy |

The download helper correctly refused to overwrite a locally regenerated
`shot.blend`. After that smoke-test output was moved aside, the public asset
download completed. An initial helper test exposed macOS temporary-path symlink
normalization; the helper was corrected and all three tests rerun successfully.

## Fresh recovery replay

[`REPLAY_2026-10-23.json`](REPLAY_2026-10-23.json) records a complete run of the
documented `reproduce.sh` command from this repository, with 70 evaluations per
case and separate held-out renders. The original [`../RESULTS.json`](../RESULTS.json)
is preserved unchanged.

| Case | Largest parameter error, fraction of declared range | Training RMSE reduction | New-view reduction | New-view + light-edit reduction | Overall |
| --- | ---: | ---: | ---: | ---: | --- |
| A | 0.38% | 93.75% | 88.16% | 89.15% | Pass |
| B | 17.90% | 67.94% | 64.60% | 57.24% | Fail |
| C | 0.10% | 97.19% | 95.53% | 96.96% | Pass |

The rule requires every parameter error to be at most 8% of its declared range
and every image RMSE reduction to be at least 50%. The fixed-default negative
control was rejected in all three cases. All optimizations exhausted their
70-evaluation budget; completion is not a convergence claim.

The replay reproduces the mixed pass/fail conclusion, not the exact fitted
numbers or pixels. Renderer/optimization numerical variation matters. It does
not demonstrate recovery from photographs, recovery of unknown geometry, or
recovery of the cinematic extension's motion parameters.

## Historical receipts and limits

The root `VERIFICATION.json` and `REPLAY.json` belong to the earlier original
experiment; their local-preview/publication status fields describe that run,
not the current GitHub or website status. The motion receipt is
[`../cinematic-shot/qa/MOTION_CHECKS.json`](../cinematic-shot/qa/MOTION_CHECKS.json).

The full 240-frame film had already been rendered and checked before packaging.
This packaging pass rendered one fresh frame and exercised still composition;
it did not repeat the entire 79-minute movie render or re-encode both films.
The delivered MP4s are retrieved with recorded SHA-256 hashes.

These checks establish source integrity and behavior within the specified
scene. They do not validate a coupled fluid model or measured coastal physics.
See the README's ARSENAL comparison for the different contracts demonstrated by
Countercurrent and The Cove.
