"""Persistent Blender-side renderer for the cinematic inlet recovery harness.

Run from Blender, for example::

    blender -b --python render_service.py -- --queue-dir /tmp/inlet-queue \
        --scene /path/to/scene.py

Requests and responses are atomic JSON files.  The service never reads target
images or evaluator labels; it receives only bounded scene parameters and view
settings, then writes a float32 RGB ``.npy`` array plus an optional PNG.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import math
import os
import struct
import sys
import time
import traceback
import uuid
from numbers import Real
from pathlib import Path
from typing import Any, Mapping


PARAMETER_NAMES = ("mist_density", "key_energy", "water_roughness")
BOUNDS = {
    "mist_density": (0.012, 0.060),
    "key_energy": (3.0, 8.0),
    "water_roughness": (0.08, 0.25),
    "camera_shift": (-0.6, 0.6),
}
FORBIDDEN_KEYS = {
    "target",
    "target_path",
    "targets",
    "label",
    "labels",
    "truth",
    "ground_truth",
    "objective",
    "loss",
    "score",
    "answer",
}


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    return value


def _finite_bounded(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    lo, hi = BOUNDS[name]
    if not math.isfinite(result) or not lo <= result <= hi:
        raise ValueError(f"{name} outside [{lo}, {hi}]")
    return result


def validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"protocol", "request_id", "op", "parameters", "view", "render"}
    unknown = set(request) - allowed
    forbidden = set(request) & FORBIDDEN_KEYS
    if unknown:
        raise ValueError(f"unknown request keys: {sorted(unknown)}")
    if forbidden:
        raise ValueError(f"forbidden evaluator keys: {sorted(forbidden)}")
    if request.get("protocol") != "cinematic-inlet-render-v1":
        raise ValueError("unsupported protocol")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id or any(c not in "0123456789abcdef" for c in request_id.lower()):
        raise ValueError("request_id must be a hexadecimal string")
    if request.get("op") != "render":
        raise ValueError("unsupported operation")
    parameters = request.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ValueError("parameters must be an object")
    if set(parameters) != set(PARAMETER_NAMES):
        raise ValueError("parameters must contain exactly the three visible controls")
    params = {name: _finite_bounded(name, parameters[name]) for name in PARAMETER_NAMES}
    view = request.get("view", {})
    if not isinstance(view, Mapping) or set(view) != {"camera_shift"}:
        raise ValueError("view must contain exactly camera_shift")
    view_out = {"camera_shift": _finite_bounded("camera_shift", view["camera_shift"])}
    render = request.get("render")
    if not isinstance(render, Mapping):
        raise ValueError("render must be an object")
    allowed_render = {"array_path", "png_path", "exr_path", "width", "height", "samples", "seed"}
    if set(render) - allowed_render:
        raise ValueError(f"unknown render keys: {sorted(set(render) - allowed_render)}")
    if not isinstance(render.get("array_path"), str) or not render["array_path"]:
        raise ValueError("render.array_path is required")
    if "png_path" in render and render["png_path"] is not None and not isinstance(render["png_path"], str):
        raise ValueError("render.png_path must be a string or null")
    if not isinstance(render.get("exr_path"), str) or not render["exr_path"]:
        raise ValueError("render.exr_path is required for scene-linear float output")
    if not render["exr_path"].lower().endswith(".exr"):
        raise ValueError("render.exr_path must use the .exr suffix")
    output = {"array_path": render["array_path"], "png_path": render.get("png_path"), "exr_path": render["exr_path"]}
    for name, default, lo, hi in (
        ("width", 256, 16, 2048),
        ("height", 144, 16, 2048),
        ("samples", 16, 1, 256),
        ("seed", 13579, -2**31, 2**31 - 1),
    ):
        value = render.get(name, default)
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"render.{name} must be an integer")
        try:
            integer = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"render.{name} must be an integer") from exc
        if integer != float(value) or not lo <= integer <= hi:
            raise ValueError(f"render.{name} outside [{lo}, {hi}]")
        output[name] = integer
    return {"request_id": request_id, "parameters": params, "view": view_out, "render": output}


def _safe_output(path_value: str, queue_root: Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    try:
        path.relative_to((queue_root / "renders").resolve())
    except ValueError as exc:
        raise ValueError(f"output must be inside queue renders directory: {path}") from exc
    return path


def _flatten_values(value: Any) -> list[float]:
    """Flatten a returned RGB/RGBA array without requiring NumPy in Blender."""

    reshape = getattr(value, "reshape", None)
    if callable(reshape):
        try:
            return [float(item) for item in reshape(-1).tolist()]
        except (AttributeError, TypeError, ValueError):
            pass
    if isinstance(value, (list, tuple)):
        result: list[float] = []
        for item in value:
            if isinstance(item, (list, tuple)):
                result.extend(_flatten_values(item))
            else:
                result.append(float(item))
        return result
    return [float(value)]


def _rgba_pixels(value: Any, width: int, height: int) -> list[float]:
    """Normalize RGB/RGBA values to Blender-style flat RGBA pixels."""

    values = _flatten_values(value)
    expected_rgb = width * height * 3
    expected_rgba = width * height * 4
    if len(values) == expected_rgb:
        result: list[float] = []
        for offset in range(0, len(values), 3):
            result.extend((values[offset], values[offset + 1], values[offset + 2], 1.0))
        return result
    if len(values) == expected_rgba:
        return values
    raise RuntimeError(f"returned float array has {len(values)} values; expected {expected_rgb} or {expected_rgba}")


def _read_npy_pixels(path: Path, width: int, height: int) -> list[float]:
    """Read a simple C-order float RGB/RGBA NPY without importing NumPy."""

    with path.open("rb") as handle:
        if handle.read(6) != b"\x93NUMPY":
            raise RuntimeError(f"not an NPY file: {path}")
        major, minor = handle.read(2)
        if (major, minor) != (1, 0):
            raise RuntimeError(f"unsupported NPY version {(major, minor)}: {path}")
        header_size = struct.unpack("<H", handle.read(2))[0]
        header = ast.literal_eval(handle.read(header_size).decode("latin1"))
        shape = tuple(int(item) for item in header.get("shape", ()))
        if len(shape) != 3 or shape[:2] != (height, width) or shape[2] not in (3, 4):
            raise RuntimeError(f"NPY shape {shape} does not match {(height, width)}: {path}")
        descr = header.get("descr")
        if descr not in ("<f4", "<f8"):
            raise RuntimeError(f"unsupported NPY dtype {descr!r}: {path}")
        data = handle.read()
    item_size = 4 if descr == "<f4" else 8
    count = height * width * shape[2]
    if len(data) != count * item_size:
        raise RuntimeError(f"NPY byte count mismatch: {path}")
    values = [item[0] for item in struct.iter_unpack("<f" if item_size == 4 else "<d", data)]
    return _rgba_pixels(values, width, height)


def _image_pixels(image: Any, width: int, height: int, *, require_float32: bool = False) -> list[float]:
    if require_float32:
        if hasattr(image, "is_float") and not bool(image.is_float):
            raise RuntimeError("linear image is not a float image")
        colorspace = getattr(image, "colorspace_settings", None)
        colorspace_name = getattr(colorspace, "name", None)
        if colorspace_name is None or "linear" not in str(colorspace_name).lower():
            raise RuntimeError(f"linear image colorspace is {colorspace_name!r}")
    size = tuple(int(item) for item in image.size[:2])
    if size != (width, height):
        raise RuntimeError(f"image size mismatch: got {size} expected {(width, height)}")
    pixels = image.pixels[:]
    if not pixels:
        raise RuntimeError("image pixel buffer is empty")
    if require_float32:
        channels = int(getattr(image, "channels", 0) or len(pixels) // (width * height))
        depth = getattr(image, "depth", None)
        # Blender reports total image depth: RGBA float32 is 128, RGB float32
        # is 96.  A 64-bit RGBA EXR is half-float and must be rejected.
        if channels not in (3, 4) or depth != channels * 32:
            raise RuntimeError(
                f"linear image format is {channels} channels/{depth} bits; expected RGB96 or RGBA128"
            )
    return _rgba_pixels(pixels, width, height)


def _extract_render_pixels(render_return: Any, *, bpy: Any, width: int, height: int, exr_path: Path) -> tuple[list[float], str, bool]:
    """Extract float pixels from a worker return, EXR/NPY, or loaded image.

    A scene worker may return a float array or a path to an EXR/NPY.  If it
    returns neither, the required 32-bit EXR is loaded directly.  PNG and the
    generic ``Render Result`` datablock are deliberately excluded because they
    can silently move the objective out of the scene-linear domain.
    """

    direct_values: list[Any] = []
    path_values: list[Path] = []
    if isinstance(render_return, Mapping):
        for key in ("pixels", "array", "float_array"):
            if key in render_return:
                direct_values.append(render_return[key])
        for key in ("array_path", "image_path", "exr_path", "path"):
            if key in render_return and render_return[key]:
                path_values.append(Path(str(render_return[key])))
    elif isinstance(render_return, (str, os.PathLike)):
        path_values.append(Path(render_return))
    elif hasattr(render_return, "pixels") and hasattr(render_return, "size"):
        try:
            return _image_pixels(render_return, width, height, require_float32=True), "worker_image_float32", True
        except RuntimeError:
            pass
    elif render_return is not None:
        direct_values.append(render_return)
    for value in direct_values:
        try:
            return _rgba_pixels(value, width, height), "worker_float_array", False
        except (TypeError, ValueError, RuntimeError):
            continue
    for path in path_values:
        if path.suffix.lower() == ".npy" and path.exists():
            return _read_npy_pixels(path, width, height), "worker_npy", False
    # Load only a 32-bit EXR; the required path is also checked even when the
    # worker returned a different path so a missing linear receipt cannot pass.
    exr_candidates = [path for path in path_values if path.suffix.lower() == ".exr"]
    if exr_path not in exr_candidates:
        exr_candidates.append(exr_path)
    for path in exr_candidates:
        if not path.exists():
            continue
        try:
            loaded = bpy.data.images.load(str(path), check_existing=False)
            return _image_pixels(loaded, width, height, require_float32=True), "loaded_exr32", True
        except RuntimeError:
            continue
    raise RuntimeError("no non-empty 32-bit scene-linear EXR or explicitly returned float array available")


def _render_with_outputs(scene_module: Any, scene: Any, png_path: Path, exr_path: Path, render: Mapping[str, Any]) -> Any:
    """Call either the revised one-pass PNG+EXR API or the old explicit API."""

    kwargs = {
        "width": render["width"],
        "height": render["height"],
        "samples": render["samples"],
        "seed": render["seed"],
    }
    try:
        return scene_module.render(scene, str(png_path), exr_path=str(exr_path), **kwargs)
    except TypeError:
        try:
            return scene_module.render(scene, str(png_path), str(exr_path), **kwargs)
        except TypeError:
            # Compatibility with the original scene.py API.  The second call
            # is required to obtain a linear EXR; its pixels are the only
            # accepted objective input.
            scene_module.render(scene, str(png_path), exr=False, **kwargs)
            exr_result = scene_module.render(scene, str(exr_path), exr=True, **kwargs)
            return {"png_path": str(png_path), "exr_path": str(exr_path), "exr_result": exr_result}


def _write_npy_rgb(path: Path, pixels: Any, width: int, height: int, *, flip_vertical: bool = True) -> None:
    """Write a NumPy v1.0 float32 RGB array without importing NumPy in Blender."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    header = {"descr": "<f4", "fortran_order": False, "shape": (height, width, 3)}
    header_text = repr(header).replace("'", "'")
    # NPY v1 header is padded to a 64-byte alignment after the 10-byte prefix.
    encoded = header_text.encode("latin1")
    padding = 64 - ((10 + len(encoded) + 1) % 64)
    encoded += b" " * (padding - 1) + b"\n"
    with temp.open("wb") as handle:
        handle.write(b"\x93NUMPY")
        handle.write(bytes((1, 0)))
        handle.write(struct.pack("<H", len(encoded)))
        handle.write(encoded)
        # Blender's image buffers are bottom-to-top; worker arrays are assumed
        # to use ordinary top-to-bottom image order.
        rows = range(height - 1, -1, -1) if flip_vertical else range(height)
        for y in rows:
            row_start = y * width * 4
            for x in range(width):
                offset = row_start + x * 4
                handle.write(struct.pack("<fff", float(pixels[offset]), float(pixels[offset + 1]), float(pixels[offset + 2])))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _load_scene(scene_path: Path):
    spec = importlib.util.spec_from_file_location("cinematic_inlet_scene", scene_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import scene module: {scene_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BlenderRenderService:
    def __init__(self, queue_dir: Path, scene_path: Path):
        self.queue_dir = queue_dir.expanduser().resolve()
        self.request_dir = self.queue_dir / "requests"
        self.response_dir = self.queue_dir / "responses"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.request_dir.mkdir(parents=True, exist_ok=True)
        self.response_dir.mkdir(parents=True, exist_ok=True)
        self.scene_module = _load_scene(scene_path.expanduser().resolve())
        self.scene = self.scene_module.build_scene()

    def _respond(self, request_id: str, payload: Mapping[str, Any]) -> None:
        atomic_json(self.response_dir / f"{request_id}.response.json", {"request_id": request_id, **payload})

    def process(self, request_path: Path) -> None:
        request_id = request_path.stem.split(".", 1)[0]
        began = time.perf_counter()
        try:
            request = validate_request(read_json(request_path))
            request_id = request["request_id"]
            render = request["render"]
            array_path = _safe_output(render["array_path"], self.queue_dir)
            png_value = render.get("png_path")
            png_path = _safe_output(png_value, self.queue_dir) if png_value else None
            exr_path = _safe_output(render["exr_path"], self.queue_dir)
            if exr_path.suffix.lower() != ".exr":
                raise ValueError("scene-linear output must use .exr")
            params = dict(request["parameters"])
            params.update(request["view"])
            try:
                self.scene_module.apply_parameters(self.scene, params)
            except TypeError:
                # Keep the bridge tolerant of the convenient one-argument API.
                self.scene_module.apply_parameters(params)
            if png_path is None:
                png_path = array_path.with_suffix(".png")
            render_return = _render_with_outputs(self.scene_module, self.scene, png_path, exr_path, render)
            import bpy  # imported only inside Blender

            width, height = render["width"], render["height"]
            pixels, pixel_source, flip_vertical = _extract_render_pixels(
                render_return,
                bpy=bpy,
                width=width,
                height=height,
                exr_path=exr_path,
            )
            _write_npy_rgb(array_path, pixels, width, height, flip_vertical=flip_vertical)
            actual_png = str(png_path) if png_path.exists() else None
            if not exr_path.exists():
                raise RuntimeError(f"scene worker did not write required EXR: {exr_path}")
            self._respond(request_id, {
                "status": "ok",
                "array_path": str(array_path),
                "png_path": actual_png,
                "exr_path": str(exr_path),
                "shape": [height, width, 3],
                "dtype": "float32",
                "pixel_source": pixel_source,
                "parameters": request["parameters"],
                "view": request["view"],
                "runtime_seconds": time.perf_counter() - began,
                "blender_version": getattr(bpy.app, "version_string", "unknown"),
            })
        except Exception as exc:
            self._respond(request_id, {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "runtime_seconds": time.perf_counter() - began,
            })
            print(f"RENDER_ERROR {request_path}: {exc}", file=sys.stderr, flush=True)
        finally:
            # Retain the request as a receipt, but mark it consumed atomically.
            consumed = request_path.with_suffix(request_path.suffix + ".done")
            try:
                os.replace(request_path, consumed)
            except OSError:
                pass

    def run(self, *, once: bool = False, poll: float = 0.10) -> None:
        print("CINEMATIC_INLET_RENDER_SERVICE_READY", flush=True)
        while True:
            requests = sorted(self.request_dir.glob("*.request.json"))
            if requests:
                self.process(requests[0])
                if once:
                    return
                continue
            if once:
                return
            time.sleep(poll)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else (argv or [])
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-dir", required=True, type=Path)
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", type=float, default=0.10)
    parsed = parser.parse_args(args)
    service = BlenderRenderService(parsed.queue_dir, parsed.scene)
    service.run(once=parsed.once, poll=max(0.01, parsed.poll))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
