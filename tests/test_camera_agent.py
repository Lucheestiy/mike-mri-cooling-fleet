import importlib.util
import json
import os
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from PIL import Image


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "roles/camera_edge/files/edge/scheduled_capture.py"
)


class Response:
    def __init__(self, status_code):
        self.status_code = status_code


class CameraAgentTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.environment = mock.patch.dict(
            os.environ,
            {
                "HOME": self.home.name,
                "SITE_ID": "TESTMR",
                "UPLOAD_ENABLED": "true",
                "UPLOAD_MODE": "full_and_crop",
                "DEBUG_SAVE_IMAGES": "false",
                "CAMERA_BASE_DIR": str(Path(self.home.name) / "camera-test"),
            },
            clear=False,
        )
        self.environment.start()
        name = f"camera_agent_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
        self.agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.agent)

    def tearDown(self):
        for handler in self.agent.logger.handlers:
            handler.close()
        self.environment.stop()
        self.home.cleanup()

    def test_payload_respects_upload_mode(self):
        image = Image.new("RGB", (16, 16), "white")
        payload = self.agent.build_payload(image, image, "TEST_01", 1, {})
        self.assertIn("full_image_base64", payload)
        self.agent.UPLOAD_MODE = "cropped_only"
        payload = self.agent.build_payload(image, image, "TEST_02", 2, {})
        self.assertNotIn("full_image_base64", payload)
        self.assertEqual(payload["source"], "camera_edge_v3")
        self.assertIsNone(payload["return_pressure"])
        self.assertIsNone(payload["confidence"])
        self.assertEqual(
            set(payload),
            {
                "site_id", "cropped_image_base64", "return_pressure",
                "confidence", "source", "timestamp", "crop_coordinates",
            },
        )

    def test_http_retries_server_errors_but_not_client_errors(self):
        self.agent.HTTP_ATTEMPTS = 3
        with mock.patch.object(
            self.agent.requests,
            "post",
            side_effect=[Response(503), Response(201)],
        ) as post, mock.patch.object(self.agent.time, "sleep"):
            self.assertEqual(self.agent.post_payload({}), (True, None))
            self.assertEqual(post.call_count, 2)
        with mock.patch.object(
            self.agent.requests, "post", return_value=Response(400)
        ) as post:
            self.assertEqual(self.agent.post_payload({}), (False, "HTTP 400"))
            self.assertEqual(post.call_count, 1)

    def test_failed_payload_is_atomic_bounded_and_recoverable(self):
        self.agent.RETRY_MAX_FILES = 2
        self.agent.RETRY_MAX_BYTES = 1048576
        self.agent.save_failed_payload({"site_id": "one"}, "offline")
        self.agent.save_failed_payload({"site_id": "two"}, "offline")
        self.agent.save_failed_payload({"site_id": "three"}, "offline")
        records = sorted(self.agent.FAILED_DIR.glob("capture-*.json"))
        self.assertEqual(len(records), 2)
        self.assertFalse(list(self.agent.FAILED_DIR.glob("*.tmp")))
        old = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for path in records:
            value = json.loads(path.read_text())
            value["created_at"] = old.isoformat()
            value["last_attempt_at"] = old.isoformat()
            self.agent.atomic_json(path, value)
        now = datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc)
        with mock.patch.object(
            self.agent, "post_payload", return_value=(True, None)
        ) as post:
            self.assertEqual(self.agent.process_failed_sessions(now), (2, 2))
            self.assertEqual(post.call_count, 2)
        self.assertFalse(list(self.agent.FAILED_DIR.glob("capture-*.json")))

    def test_debug_image_retention_is_bounded(self):
        self.agent.DEBUG_SAVE_IMAGES = True
        self.agent.DEBUG_RETAIN_IMAGES = 2
        image = Image.new("RGB", (16, 16), "white")
        for index in range(3):
            self.agent.retain_debug_image(image, f"capture-{index}")
        self.assertEqual(len(list(self.agent.DEBUG_DIR.glob("*.jpg"))), 2)

    def test_failed_payload_total_bytes_are_bounded(self):
        self.agent.RETRY_MAX_FILES = 10
        self.agent.RETRY_MAX_BYTES = 1048576
        payload = {"site_id": "large", "cropped_image_base64": "x" * 700000}
        self.agent.save_failed_payload(payload, "offline")
        self.agent.save_failed_payload(payload, "offline")
        records = list(self.agent.FAILED_DIR.glob("capture-*.json"))
        self.assertEqual(len(records), 1)
        self.assertLessEqual(sum(path.stat().st_size for path in records), 1048576)

    def test_success_requires_ninety_percent_of_requested_captures(self):
        self.agent.CAPTURES_PER_SESSION = 10
        self.agent.UPLOAD_ENABLED = True
        self.assertFalse(self.agent.successful_session(0, 0))
        self.assertFalse(self.agent.successful_session(9, 8))
        self.assertTrue(self.agent.successful_session(9, 9))
        self.agent.UPLOAD_ENABLED = False
        self.assertTrue(self.agent.successful_session(9, 0))


if __name__ == "__main__":
    unittest.main()
