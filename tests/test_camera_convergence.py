import unittest
from pathlib import Path

import yaml
import importlib.util
import hashlib


ROOT = Path(__file__).resolve().parents[1]


class CameraConvergenceMapTests(unittest.TestCase):
    def setUp(self):
        self.plan = yaml.safe_load(
            (ROOT / "inventory/camera_convergence.yml").read_text(encoding="utf-8")
        )

    def test_all_observed_camera_hosts_are_mapped(self):
        expected = {
            "agcmr1", "agcmr2", "agcmr3", "oswmr1", "oswmr2", "svimr2",
            "muncymr", "jsmr", "pittstonsola", "pittstonvida", "gcmcsola",
            "gcmcmr2", "gswbsola", "gwvs",
        }
        self.assertEqual(set(self.plan["hosts"]), expected)

    def test_special_contract_hosts_keep_explicit_decisions(self):
        self.assertTrue(self.plan["hosts"]["agcmr2"]["status"].startswith("blocked_"))
        osw_mr1 = self.plan["hosts"]["oswmr1"]
        self.assertEqual(
            osw_mr1["status"],
            "eligible_after_primary_pilot_observed_upload_preserved",
        )
        self.assertIs(osw_mr1["target"]["upload_enabled"], True)
        self.assertEqual(osw_mr1["target"]["upload_mode"], "cropped_only")
        gcmc_mr2 = self.plan["hosts"]["gcmcmr2"]
        self.assertEqual(
            gcmc_mr2["status"], "eligible_after_primary_pilot_distinct_optics"
        )
        self.assertEqual(gcmc_mr2["target"]["shutter_us"], 2500)
        self.assertEqual(gcmc_mr2["target"]["gain"], 1.0)
        self.assertEqual(
            gcmc_mr2["target"]["crop"], {"x": 760, "y": 600, "w": 320, "h": 180}
        )

    def test_camera_deployment_is_disabled_by_default(self):
        defaults = yaml.safe_load(
            (ROOT / "inventory/group_vars/all.yml").read_text(encoding="utf-8")
        )
        self.assertIs(defaults["camera_edge_deploy_approved"], False)
        self.assertEqual(self.plan["canonical"]["version"], "3.0.0")
        role = (ROOT / "roles/camera_edge/tasks/main.yml").read_text(encoding="utf-8")
        self.assertIn("Require explicit reviewed camera deployment approval", role)
        self.assertIn("camera_edge_deploy_approved | default(false) | bool", role)

    def test_every_profiled_target_has_explicit_optics_and_debug_contract(self):
        required = {
            "upload_mode", "shutter_us", "gain", "debug_save_images", "crop"
        }
        for name, details in self.plan["hosts"].items():
            target = details.get("target")
            if target is None:
                continue
            self.assertTrue(required.issubset(target), name)
            crop = target["crop"]
            self.assertEqual(set(crop), {"x", "y", "w", "h"}, name)
            self.assertGreaterEqual(crop["x"], 0, name)
            self.assertGreaterEqual(crop["y"], 0, name)
            self.assertGreater(crop["w"], 0, name)
            self.assertGreater(crop["h"], 0, name)
            self.assertLessEqual(crop["x"] + crop["w"], 1920, name)
            self.assertLessEqual(crop["y"] + crop["h"], 1080, name)
            self.assertIsInstance(target["debug_save_images"], bool, name)

    def test_site_role_camera_inputs_cannot_overwrite_reviewed_contracts(self):
        for path in sorted((ROOT / "inventory/host_vars").glob("*.yml")):
            variables = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if "camera_edge" not in (variables.get("mri_modules") or []):
                continue
            name = path.stem
            target = self.plan["hosts"][name]["target"]
            camera = variables["camera_edge"]
            self.assertIs(camera["upload_enabled"], target["upload_enabled"], name)
            self.assertEqual(camera["upload_mode"], target["upload_mode"], name)
            self.assertEqual(camera["shutter_speed"], target["shutter_us"], name)
            self.assertEqual(camera["gain"], target["gain"], name)
            self.assertEqual(camera["debug_save_images"], target["debug_save_images"], name)
            self.assertEqual(camera["ocr_crop_coords"], target["crop"], name)
            self.assertEqual(camera["captures_per_session"], 10, name)

    def test_dashboard_statuses_match_convergence_map(self):
        path = ROOT / "dashboard/app.py"
        spec = importlib.util.spec_from_file_location("dashboard_convergence", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = {name: details["status"] for name, details in self.plan["hosts"].items()}
        self.assertEqual(module.CAMERA_CONVERGENCE_STATUS, expected)
        expected_contracts = {
            name: details["target"]
            for name, details in self.plan["hosts"].items()
            if details.get("target") is not None
        }
        self.assertEqual(module.CAMERA_TARGET_CONTRACTS, expected_contracts)
        source = ROOT / "roles/camera_edge/files/edge/scheduled_capture.py"
        self.assertEqual(
            module.CAMERA_V3_SOURCE_SHA256,
            hashlib.sha256(source.read_bytes()).hexdigest(),
        )
        for name, expected_hash in module.CAMERA_V3_RUNTIME_HASHES.items():
            runtime = ROOT / "roles/camera_edge/files/edge" / name
            self.assertEqual(hashlib.sha256(runtime.read_bytes()).hexdigest(), expected_hash)


if __name__ == "__main__":
    unittest.main()
