"""Small protocol and failure-path tests for the cinematic inlet recovery lane."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

import recovery
import render_service


class RecoveryProtocolTests(unittest.TestCase):
    def test_objective_is_zero_for_identical_linear_rgb(self):
        image = np.linspace(0.0, 1.0, 3 * 8 * 8, dtype=np.float64).reshape(8, 8, 3)
        self.assertEqual(recovery.objective(image, image.copy()), 0.0)

    def test_objective_is_full_pixel_log1p_rmse_without_trimming(self):
        rendered = np.zeros((2, 2, 3), dtype=np.float64)
        target = np.zeros((2, 2, 3), dtype=np.float64)
        target[0, 0, :] = 100.0
        expected = float(np.sqrt(np.mean(np.square(np.log1p(target) - np.log1p(rendered)))))
        self.assertAlmostEqual(recovery.objective(rendered, target), expected, places=12)
        self.assertAlmostEqual(recovery.raw_rgb_rmse(rendered, target), float(np.sqrt(np.mean(np.square(target)))), places=12)

    def test_negative_scene_linear_values_fail_closed(self):
        image = np.zeros((2, 2, 3), dtype=np.float64)
        image[0, 0, 0] = -1e-6
        with self.assertRaises(recovery.TargetMismatchError):
            recovery.objective(image, np.zeros_like(image))

    def test_optimizer_coordinates_are_normalized(self):
        physical = dict(recovery.DEFAULT_PARAMETERS)
        unit = recovery.parameters_to_unit(physical)
        self.assertTrue(np.all(unit >= 0.0))
        self.assertTrue(np.all(unit <= 1.0))
        recovered = recovery.unit_to_parameters(unit)
        for name in recovery.PARAMETER_NAMES:
            self.assertAlmostEqual(recovered[name], physical[name], places=12)

    def test_render_service_accepts_returned_float_array_before_empty_render_result(self):
        class EmptyImages:
            @staticmethod
            def get(_name):
                return None

        class FakeBpy:
            data = type("Data", (), {"images": EmptyImages()})()

        returned = np.arange(12, dtype=np.float32).reshape(2, 2, 3)
        pixels, source, flipped = render_service._extract_render_pixels(
            returned,
            bpy=FakeBpy,
            width=2,
            height=2,
            exr_path=Path("/nonexistent/render.exr"),
        )
        self.assertEqual(source, "worker_float_array")
        self.assertFalse(flipped)
        self.assertEqual(pixels[0:3], [0.0, 1.0, 2.0])

    def test_exr_float_depth_uses_total_bits_per_image(self):
        class Image:
            size = (2, 2)
            channels = 4
            is_float = True
            depth = 128
            pixels = [0.0] * (2 * 2 * 4)
            colorspace_settings = type("ColorSpace", (), {"name": "Linear Rec.709"})()

        accepted = render_service._image_pixels(Image(), 2, 2, require_float32=True)
        self.assertEqual(len(accepted), 16)
        Image.depth = 64
        with self.assertRaises(RuntimeError):
            render_service._image_pixels(Image(), 2, 2, require_float32=True)

    def test_case_trace_is_durable_after_mismatch_failure(self):
        class BadClient:
            def __init__(self, root):
                self.root = Path(root)

            def render(self, parameters, **kwargs):
                path = self.root / "bad.npy"
                np.save(path, np.zeros((2, 2, 3), dtype=np.float32))
                return recovery.RenderResult("bad", path, None, {})

        with tempfile.TemporaryDirectory() as temporary:
            target_path = Path(temporary) / "case.npy"
            np.save(target_path, np.zeros((3, 3, 3), dtype=np.float32))
            out_dir = Path(temporary) / "out"
            result = recovery.FitRunner(BadClient(temporary), out_dir=out_dir, budget=2).fit_case(target_path)
            self.assertEqual(result.status, "failed")
            live = out_dir / "cases" / "case" / "fit_trace.live.json"
            self.assertTrue(live.exists())
            self.assertEqual(len(json.loads(live.read_text(encoding="utf-8"))["trace"]), 1)

    def test_malformed_parameter_state_is_rejected(self):
        with self.assertRaises(recovery.ProtocolError):
            recovery.validate_parameters({
                "mist_density": 0.028,
                "key_energy": 5.5,
                "water_roughness": 0.14,
                "unexpected": 1,
            })
        with self.assertRaises(ValueError):
            render_service.validate_request({
                "protocol": "cinematic-inlet-render-v1",
                "request_id": "a1",
                "op": "render",
                "parameters": {
                    "mist_density": 0.028,
                    "key_energy": 5.5,
                    "water_roughness": 0.14,
                },
                "view": {"camera_shift": 0.0},
                "render": {"array_path": "/tmp/render.npy"},
                "label": "secret truth",
            })
        with self.assertRaises(recovery.ProtocolError):
            recovery.validate_parameters({
                "mist_density": "0.028",
                "key_energy": 5.5,
                "water_roughness": 0.14,
            })
        with self.assertRaises(recovery.ProtocolError):
            recovery.validate_parameters({
                "mist_density": 0.028,
                "key_energy": True,
                "water_roughness": 0.14,
            })

    def test_solver_labels_are_not_accepted(self):
        with self.assertRaises(recovery.ProtocolError):
            recovery.validate_parameters({
                "mist_density": 0.028,
                "key_energy": 5.5,
                "water_roughness": 0.14,
                "label": "target-1",
            })
        with self.assertRaises(ValueError):
            render_service.validate_request({
                "protocol": "cinematic-inlet-render-v1",
                "request_id": "a1",
                "op": "render",
                "parameters": {
                    "mist_density": 0.028,
                    "key_energy": 5.5,
                    "water_roughness": 0.14,
                    "loss": 0.1,
                },
                "view": {"camera_shift": 0.0},
                "render": {"array_path": "/tmp/render.npy"},
            })

    def test_mismatched_render_target_is_a_failure(self):
        candidate = np.zeros((2, 2, 3), dtype=np.float32)
        target = np.zeros((3, 3, 3), dtype=np.float32)
        with self.assertRaises(recovery.TargetMismatchError):
            recovery.objective(candidate, target)

    def test_queue_request_is_atomic_and_response_is_correlated(self):
        with tempfile.TemporaryDirectory() as temporary:
            queue = Path(temporary)
            client = recovery.RenderClient(queue, timeout=2.0, poll=0.01)

            def fake_service():
                request_path = None
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline and request_path is None:
                    paths = list((queue / "requests").glob("*.request.json"))
                    if paths:
                        request_path = paths[0]
                        break
                    time.sleep(0.005)
                self.assertIsNotNone(request_path)
                request = json.loads(request_path.read_text(encoding="utf-8"))
                array_path = Path(request["render"]["array_path"])
                array_path.parent.mkdir(parents=True, exist_ok=True)
                np.save(array_path, np.zeros((4, 6, 3), dtype=np.float32))
                response = {
                    "request_id": request["request_id"],
                    "status": "ok",
                    "array_path": str(array_path),
                    "png_path": None,
                }
                response_path = queue / "responses" / f"{request['request_id']}.response.json"
                recovery._json_dump_atomic(response_path, response)

            worker = threading.Thread(target=fake_service, daemon=True)
            worker.start()
            result = client.render(recovery.DEFAULT_PARAMETERS, case_name="test", candidate_index=0)
            worker.join(timeout=1.0)
            self.assertTrue(result.array_path.exists())
            self.assertEqual(result.metadata["request_id"], result.request_id)


if __name__ == "__main__":
    unittest.main()
