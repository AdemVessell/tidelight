"""Build, preview, and render the deterministic TIDELIGHT cinematic shot.

Examples (run from ``cinematic-shot``):

    Blender --background --factory-startup --python render_shot.py -- --samples 32
    Blender --background --factory-startup --python render_shot.py -- --movie --samples 64

The default action builds ``shot.blend`` and renders three 960x540 / 32 spp
sample frames.  ``--movie`` is intentionally explicit because it renders all
240 frames in the current Blender process.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import bpy

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import shot_scene


PREVIEWS = HERE / "previews"
METADATA = HERE / "metadata"


def _args():
    raw = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--movie", action="store_true", help="Render all 240 frames at the requested size")
    parser.add_argument("--frame", type=int, help="Render one frame number")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--full", action="store_true", help="Use 1920x1080 output instead of preview size")
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(raw)


def _configure_render(scene, args):
    # Reuse the frozen source's tested Metal selection and Cycles defaults;
    # applying our shot-specific resolution/sampling after that avoids a
    # device probe that can leave the first render on CPU.
    shot_scene._load_frozen_scene()._configure_cycles(scene, samples=args.samples)
    scene.render.resolution_x = 1920 if args.full else args.width
    scene.render.resolution_y = 1080 if args.full else args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_persistent_data = True
    scene.cycles.samples = max(1, int(args.samples))
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 7
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 4
    scene.cycles.transmission_bounces = 4
    scene.cycles.volume_bounces = 2
    scene.cycles.use_animated_seed = False
    scene.cycles.seed = 13579
    # Keep device selection in the frozen source's tested path, but do not fail
    # on a machine where Blender has no Metal device exposed.
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.refresh_devices()
        if any(getattr(device, "type", "") == "METAL" for device in getattr(prefs, "devices", [])):
            prefs.compute_device_type = "METAL"
            scene.cycles.device = "GPU"
            scene["render_device"] = "METAL"
        else:
            scene.cycles.device = "CPU"
            scene["render_device"] = "CPU"
    except Exception as exc:
        scene.cycles.device = "CPU"
        scene["render_device"] = "CPU"
        scene["render_device_note"] = str(exc)


def _render_one(scene, path, frame, samples):
    scene.frame_set(int(frame))
    # frame_set runs the registered handler and therefore applies real water
    # vertices, shader drift, mist drift, and camera position for this frame.
    scene.render.filepath = str(path)
    scene.cycles.samples = int(samples)
    started = time.perf_counter()
    bpy.ops.render.render(write_still=True)
    elapsed = time.perf_counter() - started
    return {"frame": int(frame), "time_seconds": elapsed, "path": str(path)}


def main():
    args = _args()
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    METADATA.mkdir(parents=True, exist_ok=True)
    scene = shot_scene.build_shot_scene()
    _configure_render(scene, args)
    shot_scene.set_time(scene, 0.0)
    shot_scene.save_shot(HERE / "shot.blend")

    records = []
    if args.movie:
        width = 1920 if args.full else args.width
        height = 1080 if args.full else args.height
        movie_dir = args.output or (HERE / f"frames_{width}x{height}")
        movie_dir.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(movie_dir / "frame_####.png")
        scene.frame_start = shot_scene.FRAME_START
        scene.frame_end = shot_scene.FRAME_END
        started = time.perf_counter()
        bpy.ops.render.render(animation=True, write_still=True)
        records.append({"mode": "movie", "frames": shot_scene.FRAME_END - shot_scene.FRAME_START + 1,
                        "width": width, "height": height, "samples": args.samples,
                        "elapsed_seconds": time.perf_counter() - started,
                        "output": str(movie_dir)})
    elif args.frame is not None:
        path = args.output or (PREVIEWS / f"frame-{args.frame:04d}.png")
        records.append(_render_one(scene, path, args.frame, args.samples))
    else:
        for frame in (0, 120, shot_scene.FRAME_END):
            path = PREVIEWS / f"sample-{frame:04d}.png"
            records.append(_render_one(scene, path, frame, args.samples))

    receipt = {
        "status": "LOCAL_RENDER_COMPLETE",
        "mode": "movie" if args.movie else ("frame" if args.frame is not None else "samples"),
        "blender_version": bpy.app.version_string,
        "render_device": scene.get("render_device", "unknown"),
        "width": scene.render.resolution_x,
        "height": scene.render.resolution_y,
        "samples": args.samples,
        "fps": shot_scene.FPS,
        "duration_seconds": shot_scene.DURATION_SECONDS,
        "frame_range": [shot_scene.FRAME_START, shot_scene.FRAME_END],
        "records": records,
        "shot_blend": str(HERE / "shot.blend"),
        "water_equation": scene["water_wave_equation"],
        "water_constants": shot_scene.WAVES,
        "water_gravity": shot_scene.GRAVITY,
        "water_artistic_time_scale": shot_scene.WAVE_TIME_SCALE,
        "mist_field": scene["mist_field_model"],
    }
    if args.movie:
        receipt_path = METADATA / "movie_receipt.json"
    elif args.frame is not None:
        receipt_path = METADATA / "frame_receipt.json"
    else:
        receipt_path = METADATA / "render_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
