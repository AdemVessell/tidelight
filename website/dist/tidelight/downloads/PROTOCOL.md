# Cinematic inlet construction and parameter recovery

Status: DEVELOPMENT. Local work only. No publication, submission, third-party contact or paid compute.

## Scene and visual acceptance

Build an original fully procedural 3D inlet: irregular wet stone, rippling reflective water, volumetric mist, warm directional light and cool ambient light. No target photograph, downloaded texture, generated bitmap or hidden pixel lookup is part of the scene. Geometry and texture seeds are fixed. Preserve UMBRA v1 unchanged.

Review actual rendered pixels for readable depth, rock relief, water reflections, mist, controlled highlights and a composed focal area. A passing renderer test does not decide beauty; retain development previews and distinguish our visual judgment from Stevenson's acceptance. The final hero image must come from the same procedural scene used for recovery, with differences in resolution/sample count disclosed.

## Question and unit

Can ordinary numerical optimization recover three continuous parameters of this known scene from a rendered image, sufficiently well to predict another camera view and a prescribed lighting edit? One unit is one withheld parameter setting. This tests known-model parameter recovery, not arbitrary-photo reconstruction, discovery of equations, or a new optimization method.

Parameters: mist_density in [0.012,0.060], key_energy in [3.0,8.0], water_roughness in [0.08,0.25]. All other geometry, materials, camera intrinsics, tone treatment and sampling settings remain known and fixed. Default state: [0.028,5.5,0.14]. A separate camera_shift in [-0.6,0.6] is a prescribed view setting, not an inferred parameter.

## Development and freeze

First establish render cost, visual quality, deterministic replay and finite parameter sensitivity at default and chosen development perturbations. These are exposed development checks. Once source, objective, parameter bounds, sample settings and evaluation budget are frozen, generate three test settings in the interior of the ranges. Never reuse development targets as withheld tests.

The fitting process receives target float RGB images, renderer and bounds; it does not receive target parameter labels. Truth is kept outside its input directory and is read by the evaluator only after fitted parameters are saved. This is process-level label withholding on a shared local filesystem, not a security sandbox or independent human blinding. Scene design and solver code are AI assisted.

## Baselines, controls and measurements

- Starting baseline: the fixed default parameter state, rendered with the same settings.
- Additional held-out comparison: reuse the training pixels without a scene model, where dimensions match.
- Calibration: default-state deterministic replay; finite outputs; nonzero pixel sensitivity for each fitted parameter.
- Failure paths: malformed and out-of-range requests reject; an incompatible image must not be reported as successful merely because optimization terminates.
- Record every candidate, objective value and elapsed time. Save first-attempt outputs and any genuine failures. Later repairs or experiments get distinct result names.

The frozen fitting objective is 0.8 times full-resolution RMSE plus 0.2 times coarse RMSE, both after log1p of nonnegative scene-linear RGB. Acceptance uses raw full-resolution scene-linear RGB RMSE. Bounded Powell optimization starts after three declared probes (default and low/high interior corners), with a total budget of 70 render evaluations per case. Training images use 256 x 144 pixels, 16 Cycles samples and seed 13579. The display PNGs use AgX; the optimizer receives float arrays exported through 32-bit EXR. Blender denoising is enabled throughout. No objective, bounds or budget changes after targets are generated.

Calibration requires finite images, RMSE sensitivity greater than 1e-6 for every 15%-of-range parameter perturbation, and same-seed replay RMSE at most 1e-4. Report byte equality separately rather than infer it from the tolerance. Test settings are drawn uniformly from the central 76% of each parameter range, rejecting draws unless at least two coordinates differ from default by more than 12% of their allowed range. This selection prevents a near-default baseline from making relative improvement ill-conditioned; it narrows the tested population.

## Acceptance and held-out evaluation

Report all three parameter errors individually, normalized by their allowed range. A case passes parameter recovery only if each is at most 8% of its range. Report training-image RMSE and improvement over the fixed default; require at least 50% RMSE reduction for an image-fit PASS.

After fitting, render true and recovered parameters at camera_shift=0.45, and at that view with key_energy set to the known value 6.5. These images are not fitting inputs. Use 256 x 144 pixels, 64 samples and seed 24680 for the compared true/recovered/default renders. Require at least 50% RMSE improvement over default for each held-out comparison. Report failures per case rather than pooling them away. A seed-change comparison and higher-resolution hero render test are distinct from byte-identical replay.

No threshold is a promise of success. A good-looking fit with wrong parameters or failed edits remains a failed or ambiguous recovery case. Preserve successful visual work even if the inverse test fails.

## Deliverables

Editable .blend and scene source; final hero PNG; development previews; target/recovered/difference comparisons; parameter/error table; candidate traces and measured runtimes; local review page with equations and controlled visual changes; concise reproduction instructions. Show the finished results to Stevenson before preparing any public artifact.
