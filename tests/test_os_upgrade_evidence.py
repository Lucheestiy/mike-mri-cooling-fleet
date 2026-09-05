import copy
import datetime as dt
import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "os_upgrade_evidence.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("os_upgrade_evidence", MODULE_PATH)
os_upgrade = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(os_upgrade)


class OsUpgradeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 7, 16, 16, 0, tzinfo=dt.timezone.utc)

    def facts(self, codename="questing"):
        ids = ["28-a", "28-b", "28-c", "28-d", "28-e"]
        os_names = {
            "plucky": "Ubuntu 25.04 (Plucky Puffin)",
            "questing": "Ubuntu 25.10 (Questing Quokka)",
            "resolute": "Ubuntu 26.04 LTS (Resolute Raccoon)",
        }
        python_versions = {"plucky": "3.13.3", "questing": "3.13.7", "resolute": "3.14.3"}
        return {
            "os": os_names[codename],
            "application": {"normalized_sha256": "app-hash"},
            "sensor_config": {
                "values": {
                    "SITE_ID": "AGCMR3",
                    **{f"PROBE_TEST_{index}_ID": value for index, value in enumerate(ids, 1)},
                }
            },
            "one_wire": {"count": 5, "sensor_ids": ids},
            "sensor_offsets": {"values": {"28-a": 0.1}},
            "gpio": {"one_wire_pin": 4, "boot_overlays": ["dtoverlay=w1-gpio,gpiopin=4"]},
            "macs": {"eth0": "aa:bb:cc:dd:ee:ff", "lo": "00:00:00:00:00:00"},
            "tailscale_ips": ["100.1.2.3"],
            "services": {
                "mri_sensor": {"active": "active"},
                "cron": {"active": "active"},
                "tailscaled": {"active": "active"},
            },
            "operational_stack": {
                "version_codename": codename,
                "architecture": "arm64",
                "python_version": f"Python {python_versions[codename]}",
                "required_packages": {"python3": "1", "curl": "1"},
                "ntp_synchronized": True,
                "timezone": "America/New_York",
            },
            "throttled_flags": 0,
            "boot_management": {"current_state": "good", "new_state": ""},
            "snap_stack": {
                "assessed": True,
                "installed": True,
                "package_version": "2.72",
                "responding": True,
                "listed_count": 8,
            },
            "disk": {"free_bytes": 900_000_000_000},
            "sensor_runtime": {
                "python_version": python_versions[codename],
                "direct_dependencies": {
                    "python-dotenv": "1.1.1",
                    "requests": "2.32.4",
                    "w1thermsensor": "2.3.0",
                },
                "complete": True,
            },
            "camera_logging": {"installed": False},
        }

    def preflight(self):
        return {
            "generated_at": self.now.isoformat(),
            "results": [
                {
                    "inventory_name": "agcmr3",
                    "label": "AGC MR3",
                    "profile": "mri",
                    "status": "ok",
                    "preflight_status": "ready",
                    "safety_gates": {"telemetry": {"current": True, "last_updated": 100}},
                    "facts": self.facts(),
                }
            ],
        }

    def coverage(self, restore=True):
        return {
            "restore_tests": (
                [{"repository": "agcmr3", "status": "success", "recent": True}]
                if restore
                else []
            )
        }

    def test_missing_restore_proof_blocks_capture(self):
        result = os_upgrade.capture_readiness(
            self.preflight(), self.coverage(False), "agcmr3", self.now
        )
        self.assertFalse(result["ready"])
        self.assertIn("production restore proof missing or stale", result["blockers"])

    def test_complete_gate_produces_approved_baseline(self):
        result = os_upgrade.capture_readiness(
            self.preflight(), self.coverage(), "agcmr3", self.now
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["snapshot"]["configured_probe_ids"], result["snapshot"]["physical_probe_ids"])

    def test_post_upgrade_verifier_checks_identity_and_telemetry(self):
        baseline = os_upgrade.capture_readiness(
            self.preflight(), self.coverage(), "agcmr3", self.now
        )
        post_host = copy.deepcopy(self.preflight()["results"][0])
        post_host["facts"] = self.facts("resolute")
        post = {"generated_at": self.now.isoformat(), "results": [post_host]}
        result = os_upgrade.verify_upgrade(
            baseline,
            post,
            {"current": True, "last_updated": 101},
            self.now,
        )
        self.assertTrue(result["passed"])
        self.assertTrue(all(item["passed"] for item in result["checks"]))

    def test_staged_plucky_to_questing_capture_and_verification(self):
        preflight = self.preflight()
        preflight["results"][0]["facts"] = self.facts("plucky")
        baseline = os_upgrade.capture_readiness(
            preflight,
            self.coverage(),
            "agcmr3",
            self.now,
            source_codename="plucky",
            target_codename="questing",
            target_version="25.10",
        )
        self.assertTrue(baseline["ready"])
        self.assertEqual(baseline["source_codename"], "plucky")
        post_host = copy.deepcopy(preflight["results"][0])
        post_host["facts"] = self.facts("questing")
        result = os_upgrade.verify_upgrade(
            baseline,
            {"generated_at": self.now.isoformat(), "results": [post_host]},
            {"current": True, "last_updated": 101},
            self.now,
        )
        self.assertTrue(result["passed"])
        target = next(item for item in result["checks"] if item["name"] == "Ubuntu 25.10 target")
        self.assertTrue(target["passed"])

    def test_legacy_baseline_defaults_to_resolute_target(self):
        baseline = os_upgrade.capture_readiness(
            self.preflight(), self.coverage(), "agcmr3", self.now
        )
        baseline.pop("target_codename")
        baseline.pop("target_version")
        post_host = copy.deepcopy(self.preflight()["results"][0])
        post_host["facts"] = self.facts("resolute")
        result = os_upgrade.verify_upgrade(
            baseline,
            {"generated_at": self.now.isoformat(), "results": [post_host]},
            {"current": True, "last_updated": 101},
            self.now,
        )
        self.assertTrue(result["passed"])

    def test_changed_probe_and_application_fail_verification(self):
        baseline = os_upgrade.capture_readiness(
            self.preflight(), self.coverage(), "agcmr3", self.now
        )
        post_host = copy.deepcopy(self.preflight()["results"][0])
        post_host["facts"] = self.facts("resolute")
        post_host["facts"]["application"]["normalized_sha256"] = "different"
        post_host["facts"]["one_wire"]["sensor_ids"].pop()
        post = {"generated_at": self.now.isoformat(), "results": [post_host]}
        result = os_upgrade.verify_upgrade(
            baseline,
            post,
            {"current": True, "last_updated": 101},
            self.now,
        )
        failed = {item["name"] for item in result["checks"] if not item["passed"]}
        self.assertFalse(result["passed"])
        self.assertIn("application checksum preserved", failed)
        self.assertIn("physical probe IDs exact", failed)

    def test_broken_python_runtime_blocks_capture(self):
        preflight = self.preflight()
        preflight["results"][0]["facts"]["sensor_runtime"]["complete"] = False
        result = os_upgrade.capture_readiness(
            preflight, self.coverage(), "agcmr3", self.now
        )
        self.assertFalse(result["ready"])
        self.assertIn("sensor Python runtime is incomplete", result["blockers"])

    def test_unresponsive_snap_daemon_blocks_capture(self):
        preflight = self.preflight()
        preflight["results"][0]["facts"]["snap_stack"]["responding"] = False
        result = os_upgrade.capture_readiness(
            preflight, self.coverage(), "agcmr3", self.now
        )
        self.assertFalse(result["ready"])
        self.assertIn("Snap daemon is installed but not responding", result["blockers"])

    def test_snap_daemon_breakage_fails_verification(self):
        baseline = os_upgrade.capture_readiness(
            self.preflight(), self.coverage(), "agcmr3", self.now
        )
        post_host = copy.deepcopy(self.preflight()["results"][0])
        post_host["facts"] = self.facts("resolute")
        post_host["facts"]["snap_stack"]["responding"] = False
        result = os_upgrade.verify_upgrade(
            baseline,
            {"generated_at": self.now.isoformat(), "results": [post_host]},
            {"current": True, "last_updated": 101},
            self.now,
        )
        failed = {item["name"] for item in result["checks"] if not item["passed"]}
        self.assertIn("Snap daemon responding", failed)

    def test_camera_runtime_breakage_fails_verification(self):
        preflight = self.preflight()
        preflight["results"][0]["facts"]["camera_logging"] = {
            "installed": True,
            "software": {"semantic_fingerprint": "camera-hash"},
            "runtime": {"python_version": "3.13.7", "complete": True},
        }
        baseline = os_upgrade.capture_readiness(
            preflight, self.coverage(), "agcmr3", self.now
        )
        post_host = copy.deepcopy(preflight["results"][0])
        post_host["facts"] = self.facts("resolute")
        post_host["facts"]["camera_logging"] = {
            "installed": True,
            "software": {"semantic_fingerprint": "camera-hash"},
            "runtime": {"python_version": "", "complete": False},
        }
        result = os_upgrade.verify_upgrade(
            baseline,
            {"generated_at": self.now.isoformat(), "results": [post_host]},
            {"current": True, "last_updated": 101},
            self.now,
        )
        failed = {item["name"] for item in result["checks"] if not item["passed"]}
        self.assertIn("camera Python runtime complete", failed)


if __name__ == "__main__":
    unittest.main()
