import hashlib
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SOURCE = Path(__file__).parents[1] / "roles/cv_sensor_code/files/cv_room_sensor.py"
EXPECTED_SHA256 = "a7bb0bc02e548f37993345e54cd664ac4d6e3dc47ba0b5525d7402f3a07717aa"


def load_sensor_module():
    requests = types.ModuleType("requests")
    requests.post = lambda *args, **kwargs: None
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    w1 = types.ModuleType("w1thermsensor")
    w1.W1ThermSensor = type("W1ThermSensor", (), {"get_available_sensors": staticmethod(lambda: [])})
    with patch.dict(sys.modules, {"requests": requests, "dotenv": dotenv, "w1thermsensor": w1}):
        spec = importlib.util.spec_from_file_location("cv_sensor_under_test", SOURCE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class CvSensorCodeTests(unittest.TestCase):
    def test_canonical_source_checksum(self):
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), EXPECTED_SHA256)

    def test_blank_optional_probe_is_excluded(self):
        module = load_sensor_module()
        env = {
            "SENSOR_1_ID": "28-one",
            "SENSOR_2_ID": "28-two",
            "SENSOR_3_ID": "28-three",
            "SENSOR_4_ID": "",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                module.configured_sensor_ids(),
                {"temp_1": "28-one", "temp_2": "28-two", "temp_3": "28-three"},
            )

    def test_payload_preserves_optional_fourth_and_fifth_probe_mapping(self):
        module = load_sensor_module()
        with patch.object(module, "get_pi_ip", return_value="192.0.2.1"):
            payload = module.build_payload(
                {"temp_1": 1.0, "temp_2": 2.0, "temp_3": 3.0, "temp_4": 4.0, "temp_5": 5.0}
            )
        self.assertEqual(payload["helium_in"], 1.0)
        self.assertEqual(payload["helium_out"], 2.0)
        self.assertEqual(payload["primary_in"], 3.0)
        self.assertEqual(payload["primary_out"], 4.0)
        self.assertEqual(payload["room_temp"], 5.0)
