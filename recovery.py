"""Bounded parameter recovery for the procedural cinematic inlet.

The solver runs in the ordinary Python environment.  Rendering is deliberately
kept behind a small file queue because Blender's Python environment is not the
same environment as the solver's SciPy installation.  The queue contains only
candidate parameters and render settings; targets are never copied into it and
no labels are accepted by the protocol.

This module does not start a fit at import time.  The ``fit`` command is an
explicit operation and is intended to be run only after the target directory
and the prospective protocol have been frozen by the controlling workflow.
"""

from __future__ import annotations

import argparse
import json
import math
from numbers import Real
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np


PARAMETER_NAMES = ("mist_density", "key_energy", "water_roughness")
BOUNDS = {
    "mist_density": (0.012, 0.060),
    "key_energy": (3.0, 8.0),
    "water_roughness": (0.08, 0.25),
}
DEFAULT_PARAMETERS = {
    "mist_density": 0.028,
    "key_energy": 5.5,
    "water_roughness": 0.14,
}

# Frozen before any target is read.  The coarse term prevents a handful of
# high-frequency pixels from deciding a fit while the full-resolution term
# retains the RGB image signal.  This is a metric definition, not a claim of
# perceptual equivalence.
OBJECTIVE_VERSION = "log1p-rgb-rmse-multiscale-v2"
FULL_WEIGHT = 0.80
COARSE_WEIGHT = 0.20
COARSE_GRID = (36, 64)  # height, width; only used when the image is larger.

FORBIDDEN_REQUEST_KEYS = frozenset(
    {
        "target",
        "target_path",
        "targets",
        "label",
        "labels",
        "truth",
        "ground_truth",
        "groundtruth",
        "objective",
        "loss",
        "score",
        "answer",
    }
)


class RecoveryError(RuntimeError):
    """Base class for recoverable protocol/fit failures."""


class ProtocolError(RecoveryError):
    pass


class ServiceTimeout(RecoveryError):
    pass


class RenderFailure(RecoveryError):
    pass


class TargetMismatchError(RecoveryError):
    pass


def _json_dump_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid JSON response {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProtocolError(f"response must be an object: {path}")
    return value


def validate_parameters(values: Mapping[str, Any], *, allow_camera_shift: bool = False) -> dict[str, float]:
    """Validate and bound-check the three visible scene controls.

    Exact keys are required.  In particular, a target, label, loss, or score
    cannot enter the render request by accident or by a future caller trying to
    smuggle evaluator state into the service.
    """

    if not isinstance(values, Mapping):
        raise ProtocolError("parameters must be an object")
    keys = set(values)
    expected = set(PARAMETER_NAMES)
    if allow_camera_shift:
        expected.add("camera_shift")
    unknown = keys - expected
    missing = expected - keys
    forbidden = keys & FORBIDDEN_REQUEST_KEYS
    if unknown:
        raise ProtocolError(f"unknown parameter keys: {sorted(unknown)}")
    if missing:
        raise ProtocolError(f"missing parameter keys: {sorted(missing)}")
    if forbidden:
        raise ProtocolError(f"forbidden evaluator keys: {sorted(forbidden)}")
    result: dict[str, float] = {}
    bounds = dict(BOUNDS)
    if allow_camera_shift:
        bounds["camera_shift"] = (-0.6, 0.6)
    for name, (lo, hi) in bounds.items():
        value = values[name]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ProtocolError(f"{name} must be numeric")
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise ProtocolError(f"{name} must be numeric") from exc
        if not math.isfinite(value) or not (lo <= value <= hi):
            raise ProtocolError(f"{name}={value!r} outside [{lo}, {hi}]")
        result[name] = value
    return result


def _as_rgb_image(value: Any, *, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 3 or array.shape[-1] != 3:
        raise TargetMismatchError(f"{name} must have shape (height,width,3), got {array.shape}")
    if array.shape[0] < 2 or array.shape[1] < 2:
        raise TargetMismatchError(f"{name} is too small: {array.shape}")
    if not np.issubdtype(array.dtype, np.number):
        raise TargetMismatchError(f"{name} must be numeric")
    array = np.asarray(array, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise TargetMismatchError(f"{name} contains non-finite values")
    if np.any(array < 0.0):
        raise TargetMismatchError(f"{name} contains negative scene-linear RGB values")
    return array


def _resize_average(image: np.ndarray, height: int, width: int) -> np.ndarray:
    """Deterministic area-ish resize without an extra image dependency."""

    h, w, _ = image.shape
    if height >= h and width >= w:
        return image
    y_edges = np.linspace(0, h, height + 1).astype(int)
    x_edges = np.linspace(0, w, width + 1).astype(int)
    rows = []
    for y0, y1 in zip(y_edges[:-1], y_edges[1:]):
        y1 = max(y1, y0 + 1)
        row = []
        for x0, x1 in zip(x_edges[:-1], x_edges[1:]):
            x1 = max(x1, x0 + 1)
            row.append(image[y0:y1, x0:x1].mean(axis=(0, 1)))
        rows.append(np.stack(row, axis=0))
    return np.stack(rows, axis=0)


def robust_rgb_rmse(rendered: Any, target: Any) -> float:
    """Return the frozen full-resolution log1p RGB RMSE component.

    The logarithm keeps HDR/specular scale from dominating every pixel while
    retaining all pixels.  A mismatch or negative scene-linear value is a hard
    failure; corrupted highlights must remain visible to the evaluator.
    """

    candidate = _as_rgb_image(rendered, name="rendered")
    reference = _as_rgb_image(target, name="target")
    if candidate.shape != reference.shape:
        raise TargetMismatchError(
            f"rendered shape {candidate.shape} does not match target shape {reference.shape}"
        )
    candidate_log = np.log1p(candidate)
    reference_log = np.log1p(reference)
    squared = np.mean(np.square(candidate_log - reference_log), axis=2)
    return float(np.sqrt(np.mean(squared)))


def raw_rgb_rmse(rendered: Any, target: Any) -> float:
    """Return the untransformed full RGB RMSE for final evaluation reporting."""

    candidate = _as_rgb_image(rendered, name="rendered")
    reference = _as_rgb_image(target, name="target")
    if candidate.shape != reference.shape:
        raise TargetMismatchError(
            f"rendered shape {candidate.shape} does not match target shape {reference.shape}"
        )
    return float(np.sqrt(np.mean(np.square(candidate - reference))))


def objective(rendered: Any, target: Any) -> float:
    """Compute the fixed log1p RGB objective, raising on shape/data mismatch."""

    candidate = _as_rgb_image(rendered, name="rendered")
    reference = _as_rgb_image(target, name="target")
    if candidate.shape != reference.shape:
        raise TargetMismatchError(
            f"rendered shape {candidate.shape} does not match target shape {reference.shape}"
        )
    full = robust_rgb_rmse(candidate, reference)
    h, w, _ = candidate.shape
    coarse_h = min(COARSE_GRID[0], h)
    coarse_w = min(COARSE_GRID[1], w)
    if coarse_h == h and coarse_w == w:
        coarse = full
    else:
        coarse_candidate = _resize_average(candidate, coarse_h, coarse_w)
        coarse_reference = _resize_average(reference, coarse_h, coarse_w)
        coarse = robust_rgb_rmse(coarse_candidate, coarse_reference)
    return float(FULL_WEIGHT * full + COARSE_WEIGHT * coarse)


def parameters_to_unit(values: Mapping[str, Any]) -> np.ndarray:
    """Map physical controls into the normalized [0,1]^3 optimizer domain."""

    checked = validate_parameters(values)
    return np.asarray(
        [
            (checked[name] - BOUNDS[name][0]) / (BOUNDS[name][1] - BOUNDS[name][0])
            for name in PARAMETER_NAMES
        ],
        dtype=float,
    )


def unit_to_parameters(values: Sequence[float]) -> dict[str, float]:
    """Map normalized optimizer coordinates back to bounded physical controls."""

    if len(values) != len(PARAMETER_NAMES):
        raise ProtocolError("normalized parameter vector must have length three")
    result = {}
    for value, name in zip(values, PARAMETER_NAMES):
        value = float(value)
        if not math.isfinite(value):
            raise ProtocolError("normalized parameter vector must be finite")
        lo, hi = BOUNDS[name]
        result[name] = lo + max(0.0, min(1.0, value)) * (hi - lo)
    return result


def discover_targets(directory: os.PathLike[str] | str) -> list[Path]:
    """Discover only numeric ``.npy`` target images, without reading labels."""

    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise RecoveryError(f"target directory does not exist: {root}")
    paths = sorted(path for path in root.rglob("*.npy") if path.is_file())
    if not paths:
        raise RecoveryError(f"no .npy targets found under {root}")
    return paths


def load_target(path: os.PathLike[str] | str) -> np.ndarray:
    """Load a target array and reject object arrays or malformed RGB data."""

    try:
        array = np.load(Path(path), allow_pickle=False)
    except (OSError, ValueError) as exc:
        raise TargetMismatchError(f"cannot load target {path}: {exc}") from exc
    return _as_rgb_image(array, name=f"target {path}")


@dataclass
class RenderResult:
    request_id: str
    array_path: Path
    png_path: Path | None
    metadata: dict[str, Any]

    @property
    def exr_path(self) -> Path | None:
        value = self.metadata.get("exr_path")
        return Path(value) if value else None


class RenderClient:
    """Atomic file-queue client for the persistent Blender render service."""

    def __init__(self, queue_dir: os.PathLike[str] | str, *, timeout: float = 180.0, poll: float = 0.05):
        self.queue_dir = Path(queue_dir).expanduser().resolve()
        self.request_dir = self.queue_dir / "requests"
        self.response_dir = self.queue_dir / "responses"
        self.output_dir = self.queue_dir / "renders"
        self.timeout = float(timeout)
        self.poll = float(poll)
        for path in (self.request_dir, self.response_dir, self.output_dir):
            path.mkdir(parents=True, exist_ok=True)

    def render(
        self,
        parameters: Mapping[str, Any],
        *,
        case_name: str = "case",
        candidate_index: int = 0,
        width: int | None = None,
        height: int | None = None,
        samples: int | None = None,
        seed: int = 13579,
        camera_shift: float = 0.0,
    ) -> RenderResult:
        params = validate_parameters(parameters)
        if not isinstance(camera_shift, (int, float)) or not math.isfinite(float(camera_shift)):
            raise ProtocolError("camera_shift must be finite")
        camera_shift = float(camera_shift)
        if not -0.6 <= camera_shift <= 0.6:
            raise ProtocolError("camera_shift outside [-0.6, 0.6]")
        request_id = uuid.uuid4().hex
        safe_case = "".join(char if char.isalnum() or char in "._-" else "_" for char in case_name)
        stem = f"{safe_case}-{candidate_index:04d}-{request_id}"
        array_path = self.output_dir / f"{stem}.npy"
        png_path = self.output_dir / f"{stem}.png"
        exr_path = self.output_dir / f"{stem}.exr"
        request: dict[str, Any] = {
            "protocol": "cinematic-inlet-render-v1",
            "request_id": request_id,
            "op": "render",
            "parameters": params,
            "view": {"camera_shift": camera_shift},
            "render": {
                "array_path": str(array_path),
                "png_path": str(png_path),
                "exr_path": str(exr_path),
                "seed": int(seed),
            },
        }
        if width is not None:
            request["render"]["width"] = int(width)
        if height is not None:
            request["render"]["height"] = int(height)
        if samples is not None:
            request["render"]["samples"] = int(samples)
        request_path = self.request_dir / f"{request_id}.request.json"
        _json_dump_atomic(request_path, request)
        response_path = self.response_dir / f"{request_id}.response.json"
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if response_path.exists():
                response = _read_json(response_path)
                if response.get("request_id") != request_id:
                    raise ProtocolError(f"response request id mismatch: {response_path}")
                if response.get("status") != "ok":
                    raise RenderFailure(str(response.get("error", "render service failed")))
                actual_array = Path(str(response.get("array_path", array_path)))
                if not actual_array.exists():
                    raise RenderFailure(f"render service omitted array: {actual_array}")
                actual_png_value = response.get("png_path")
                actual_png = Path(actual_png_value) if actual_png_value else None
                return RenderResult(request_id, actual_array, actual_png, response)
            time.sleep(self.poll)
        raise ServiceTimeout(f"render request timed out after {self.timeout:.1f}s: {request_id}")


@dataclass
class CaseFit:
    case: str
    target_path: str
    shape: tuple[int, int, int]
    starting_loss: float | None = None
    best_loss: float | None = None
    best_parameters: dict[str, float] | None = None
    status: str = "pending"
    evaluations: int = 0
    failure: str | None = None
    optimizer: str = "powell"
    trace: list[dict[str, Any]] = field(default_factory=list)


class BudgetExceeded(RecoveryError):
    pass


class FitRunner:
    def __init__(
        self,
        client: RenderClient,
        *,
        out_dir: os.PathLike[str] | str,
        budget: int = 70,
        width: int | None = None,
        height: int | None = None,
        samples: int | None = None,
        seed: int = 13579,
    ):
        if budget < 1:
            raise ValueError("budget must be positive")
        self.client = client
        self.out_dir = Path(out_dir).expanduser().resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.budget = int(budget)
        self.width = width
        self.height = height
        self.samples = samples
        self.seed = int(seed)

    def _persist_case_trace(self, case: CaseFit) -> None:
        """Persist the live case receipt after every attempted candidate."""

        case_dir = self.out_dir / "cases" / case.case
        case_dir.mkdir(parents=True, exist_ok=True)
        _json_dump_atomic(
            case_dir / "fit_trace.live.json",
            {
                "protocol": "cinematic-inlet-recovery-case-trace-v1",
                "objective_version": OBJECTIVE_VERSION,
                "case": case.case,
                "target_path": case.target_path,
                "shape": list(case.shape),
                "starting_loss": case.starting_loss,
                "best_loss": case.best_loss,
                "best_parameters": case.best_parameters,
                "status": case.status,
                "evaluations": case.evaluations,
                "failure": case.failure,
                "trace": case.trace,
            },
        )

    def _candidate(
        self,
        case: CaseFit,
        target: np.ndarray,
        params: Sequence[float],
        *,
        index: int,
    ) -> float:
        if case.evaluations >= self.budget:
            raise BudgetExceeded(f"render budget exhausted at {self.budget}")
        values = dict(zip(PARAMETER_NAMES, [float(x) for x in params]))
        began = time.perf_counter()
        record: dict[str, Any] = {
            "candidate_index": index,
            "parameters": values,
            "objective": None,
            "started_at": time.time(),
        }
        try:
            result = self.client.render(
                values,
                case_name=case.case,
                candidate_index=index,
                width=self.width,
                height=self.height,
                samples=self.samples,
                seed=self.seed,
            )
            rendered = np.load(result.array_path, allow_pickle=False)
            loss = objective(rendered, target)
            record.update(
                {
                    "status": "ok",
                    "objective": loss,
                    "array_path": str(result.array_path),
                    "png_path": str(result.png_path) if result.png_path else None,
                }
            )
        except Exception as exc:
            loss = float("inf")
            record.update({"status": "failure", "error": f"{type(exc).__name__}: {exc}"})
        record["runtime_seconds"] = time.perf_counter() - began
        record["finished_at"] = time.time()
        case.evaluations += 1
        case.trace.append(record)
        if not math.isfinite(loss):
            self._persist_case_trace(case)
            raise RenderFailure(record["error"])
        if case.best_loss is None or loss < case.best_loss:
            case.best_loss = loss
            case.best_parameters = values
        self._persist_case_trace(case)
        return loss

    def fit_case(self, target_path: Path, *, optimizer: str = "powell") -> CaseFit:
        target = load_target(target_path)
        case = CaseFit(
            case=target_path.stem,
            target_path=str(target_path),
            shape=tuple(int(x) for x in target.shape),
            optimizer=optimizer,
        )
        case_dir = self.out_dir / "cases" / case.case
        case_dir.mkdir(parents=True, exist_ok=True)
        starts = [
            np.array([DEFAULT_PARAMETERS[name] for name in PARAMETER_NAMES], dtype=float),
            np.array([BOUNDS[name][0] for name in PARAMETER_NAMES], dtype=float),
            np.array([BOUNDS[name][1] for name in PARAMETER_NAMES], dtype=float),
        ]
        index = 0
        try:
            case.starting_loss = self._candidate(case, target, starts[0], index=index)
            self._persist_case_trace(case)
            index += 1
            # Two bounded corners are cheap coverage before the local optimizer.
            for start in starts[1:]:
                if case.evaluations >= min(3, self.budget):
                    break
                self._candidate(case, target, start, index=index)
                index += 1
            if case.best_parameters is None:
                raise RenderFailure("no valid starting candidate")
            if case.evaluations < self.budget and optimizer == "powell":
                from scipy.optimize import minimize

                x0 = parameters_to_unit(case.best_parameters)
                bounds = [(0.0, 1.0)] * len(PARAMETER_NAMES)

                def fn(values: Sequence[float]) -> float:
                    nonlocal index
                    bounded = unit_to_parameters(values)
                    result = self._candidate(
                        case,
                        target,
                        [bounded[name] for name in PARAMETER_NAMES],
                        index=index,
                    )
                    index += 1
                    return result

                minimize(
                    fn,
                    x0,
                    method="Powell",
                    bounds=bounds,
                    options={"maxfev": self.budget, "maxiter": max(1, self.budget // 3), "xtol": 0.005, "ftol": 1e-5},
                )
            case.status = "completed"
        except BudgetExceeded as exc:
            # A bounded optimizer may spend its final permitted render while
            # still having a valid incumbent.  Preserve that distinction from
            # a renderer/protocol failure so the receipt says exactly why it
            # stopped.
            case.status = "budget_exhausted"
            case.failure = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            case.status = "failed"
            case.failure = f"{type(exc).__name__}: {exc}"
        if case.best_parameters and case.best_loss is not None:
            best_record = next(
                (record for record in reversed(case.trace) if record.get("status") == "ok" and record.get("objective") == case.best_loss),
                None,
            )
            if best_record and best_record.get("array_path"):
                best_array = Path(best_record["array_path"])
                if best_array.exists():
                    np.save(case_dir / "fit.npy", np.load(best_array, allow_pickle=False))
            if best_record and best_record.get("png_path"):
                best_png = Path(best_record["png_path"])
                if best_png.exists():
                    (case_dir / "fit.png").write_bytes(best_png.read_bytes())
        _json_dump_atomic(case_dir / "case_result.json", {
            "case": case.case,
            "target_path": case.target_path,
            "shape": list(case.shape),
            "starting_loss": case.starting_loss,
            "best_loss": case.best_loss,
            "best_parameters": case.best_parameters,
            "status": case.status,
            "evaluations": case.evaluations,
            "failure": case.failure,
            "optimizer": case.optimizer,
        })
        return case

    def fit(self, targets: Iterable[Path], *, optimizer: str = "powell") -> tuple[list[CaseFit], list[dict[str, Any]]]:
        if optimizer not in {"powell"}:
            raise ValueError("optimizer must be powell")
        results = [self.fit_case(path, optimizer=optimizer) for path in targets]
        summary = {
            "protocol": "cinematic-inlet-recovery-v1",
            "objective_version": OBJECTIVE_VERSION,
            "bounds": BOUNDS,
            "defaults": DEFAULT_PARAMETERS,
            "budget_per_case": self.budget,
            "cases": [
                {
                    "case": item.case,
                    "target_path": item.target_path,
                    "shape": list(item.shape),
                    "starting_loss": item.starting_loss,
                    "best_loss": item.best_loss,
                    "best_parameters": item.best_parameters,
                    "status": item.status,
                    "evaluations": item.evaluations,
                    "failure": item.failure,
                }
                for item in results
            ],
        }
        trace = {
            "protocol": "cinematic-inlet-recovery-trace-v1",
            "objective_version": OBJECTIVE_VERSION,
            "budget_per_case": self.budget,
            "cases": {
                item.case: item.trace for item in results
            },
        }
        _json_dump_atomic(self.out_dir / "recovered_parameters.json", summary)
        _json_dump_atomic(self.out_dir / "fit_trace.json", trace)
        return results, [record for item in results for record in item.trace]


def _start_blender(args: argparse.Namespace, queue_dir: Path) -> tuple[subprocess.Popen[str] | None, Any]:
    if not args.blender:
        return None, None
    scene_path = Path(args.scene).expanduser().resolve()
    service_path = Path(__file__).resolve().with_name("render_service.py")
    command = [
        args.blender,
        "-b",
        "--python",
        str(service_path),
        "--",
        "--queue-dir",
        str(queue_dir),
        "--scene",
        str(scene_path),
    ]
    queue_dir.mkdir(parents=True, exist_ok=True)
    log_handle = (queue_dir / "service.log").open("a", encoding="utf-8")
    process = subprocess.Popen(command, text=True, stdout=log_handle, stderr=subprocess.STDOUT)
    return process, log_handle


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    fit_parser = subparsers.add_parser("fit", help="fit bounded parameters against .npy targets")
    fit_parser.add_argument("--targets", required=True, type=Path)
    fit_parser.add_argument("--out", required=True, type=Path)
    fit_parser.add_argument("--queue-dir", type=Path, default=None)
    fit_parser.add_argument("--blender", default=None, help="Blender executable; starts persistent render service")
    fit_parser.add_argument("--scene", default=str(Path(__file__).with_name("scene.py")))
    fit_parser.add_argument("--timeout", type=float, default=180.0)
    fit_parser.add_argument("--budget", type=int, default=70)
    fit_parser.add_argument("--width", type=int, default=None)
    fit_parser.add_argument("--height", type=int, default=None)
    fit_parser.add_argument("--samples", type=int, default=None)
    fit_parser.add_argument("--seed", type=int, default=13579)
    args = parser.parse_args(argv)
    if args.command != "fit":
        parser.error("unsupported command")
    targets = discover_targets(args.targets)
    queue_dir = (args.queue_dir or (args.out / "queue")).expanduser().resolve()
    process, log_handle = _start_blender(args, queue_dir)
    try:
        client = RenderClient(queue_dir, timeout=args.timeout)
        runner = FitRunner(client, out_dir=args.out, budget=args.budget, width=args.width, height=args.height, samples=args.samples, seed=args.seed)
        results, _ = runner.fit(targets)
        print(json.dumps({"cases": len(results), "out": str(args.out)}, sort_keys=True))
        return 0 if all(item.status == "completed" for item in results) else 2
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if log_handle is not None:
            log_handle.close()


if __name__ == "__main__":
    raise SystemExit(cli())
