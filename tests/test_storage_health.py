import importlib.util
import unittest
from pathlib import Path

import yaml


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "roles"
    / "storage_health"
    / "files"
    / "coolmri_storage_health.py"
)
SPEC = importlib.util.spec_from_file_location("storage_health", MODULE_PATH)
storage_health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(storage_health)

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "playbooks" / "storage_health_pilot.yml"
ROLE = ROOT / "roles" / "storage_health" / "tasks" / "main.yml"


def test_storage_health_wave_is_on_demand_guarded_and_includes_recovered_gr():
    play = yaml.safe_load(PILOT.read_text(encoding="utf-8"))[0]
    source = PILOT.read_text(encoding="utf-8")
    role = ROLE.read_text(encoding="utf-8")
    assert "serial" in play and play["serial"] == 1
    assert "agcmr2" in play["hosts"]
    assert "jsmr" in play["hosts"]
    assert "gcmcmr2" in play["hosts"]
    assert "vwm2" in play["hosts"] and "vwm3" in play["hosts"]
    assert "gr" in play["hosts"].split(":")
    assert "Require writable filesystems and idle package management" in source
    assert "state: stopped" in role and "enabled: false" in role
    assert "Require usable read-only SMART evidence" in role


class SmartParserTests(unittest.TestCase):
    def test_nvme_health_fields(self):
        payload = {
            "model_name": "Fixture NVMe",
            "serial_number": "fixture-serial",
            "device": {"protocol": "NVMe"},
            "smart_status": {"passed": True},
            "temperature": {"current": 41},
            "power_on_time": {"hours": 1234},
            "nvme_smart_health_information_log": {
                "critical_warning": 0,
                "percentage_used": 7,
                "media_errors": 0,
                "unsafe_shutdowns": 2,
            },
        }
        parsed = storage_health.parse_smart(payload, "/dev/nvme0n1", "auto")
        self.assertTrue(parsed["available"])
        self.assertTrue(parsed["passed"])
        self.assertEqual(parsed["percentage_used"], 7)
        self.assertFalse(parsed["concerning"])

    def test_nvme_media_error_is_concerning(self):
        payload = {
            "model_name": "Fixture NVMe",
            "nvme_smart_health_information_log": {
                "critical_warning": 0,
                "media_errors": 1,
            },
        }
        parsed = storage_health.parse_smart(payload, "/dev/nvme0n1", "auto")
        self.assertTrue(parsed["concerning"])

    def test_ata_sector_attributes(self):
        payload = {
            "model_name": "Fixture SATA",
            "smart_status": {"passed": True},
            "ata_smart_attributes": {
                "table": [
                    {"id": 5, "raw": {"value": 0}},
                    {"id": 197, "raw": {"value": 3}},
                    {"id": 198, "raw": {"value": 0}},
                ]
            },
        }
        parsed = storage_health.parse_smart(payload, "/dev/sda", "sat")
        self.assertEqual(parsed["reallocated_sectors"], 0)
        self.assertEqual(parsed["pending_sectors"], 3)
        self.assertEqual(parsed["offline_uncorrectable"], 0)
        self.assertTrue(parsed["concerning"])


if __name__ == "__main__":
    unittest.main()
