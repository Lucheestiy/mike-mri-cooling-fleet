import copy
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"
SPEC = importlib.util.spec_from_file_location("dashboard_app", MODULE_PATH)
dashboard_app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard_app)


class CompleteReportTests(unittest.TestCase):
    def maintenance_host(self, backup):
        return {
            "status": "ok",
            "profile": "mri",
            "backup": backup,
            "facts": {
                "services": {"mri_sensor": {"active": "active"}},
                "disk": {"root_read_only": False, "used_percent": 10},
                "boot_management": {"firmware_mount_options": "rw,relatime"},
                "package_manager": {"busy": False},
                "cpu_temp_c": 40,
                "throttled_flags": 0,
            },
        }

    def maintenance_readiness(self, backup):
        with (
            mock.patch.object(dashboard_app, "assess_sensor_runtime", return_value={"complete": True}),
            mock.patch.object(dashboard_app, "assess_camera_runtime", return_value={"installed": False, "complete": True}),
            mock.patch.object(dashboard_app, "probe_mapping_evidence", return_value={"complete": True, "exact": True}),
            mock.patch.object(dashboard_app, "live_telemetry_evidence", return_value={"backend_available": True, "current": True, "missing_required": [], "alarm": False}),
            mock.patch.object(dashboard_app, "routed_wifi_signal", return_value=-50),
        ):
            return dashboard_app.maintenance_readiness(self.maintenance_host(backup))

    def test_portal_maintenance_requires_batch_or_recent_successful_restore(self):
        failed = self.maintenance_readiness({
            "covered": True,
            "activity_recent": True,
            "batch_success": False,
            "restore_test": {"status": "failure", "recent": False},
        })
        self.assertFalse(failed["ready"])
        self.assertIn(
            "backup batch incomplete and recent decrypt/restore proof unavailable",
            failed["blockers"],
        )
        restored = self.maintenance_readiness({
            "covered": True,
            "activity_recent": True,
            "batch_success": False,
            "restore_test": {"status": "success", "recent": True},
        })
        self.assertTrue(restored["ready"])

    def test_health_requires_current_complete_fleet_evidence(self):
        now = dt.datetime(2026, 7, 16, 23, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
        complete = {
            "generated_at": "2026-07-16T22:50:00-04:00",
            "results": [
                {"status": "ok"} for _ in range(dashboard_app.EXPECTED_HOSTS - 4)
            ] + [
                {"status": "offline_or_unreachable"} for _ in range(4)
            ],
        }
        with mock.patch.object(dashboard_app, "load_latest_complete_report", return_value=complete):
            payload, status = dashboard_app.fleet_health(now)
        self.assertEqual(status, dashboard_app.HTTPStatus.OK)
        self.assertEqual(payload, {"status": "ok", "report_age_seconds": 600})

        stale = copy.deepcopy(complete)
        stale["generated_at"] = "2026-07-16T21:00:00-04:00"
        with mock.patch.object(dashboard_app, "load_latest_complete_report", return_value=stale):
            payload, status = dashboard_app.fleet_health(now)
        self.assertEqual(status, dashboard_app.HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload["status"], "stale")

        incomplete = copy.deepcopy(complete)
        incomplete["results"] = incomplete["results"][:-1]
        with mock.patch.object(dashboard_app, "load_latest_complete_report", return_value=incomplete):
            payload, status = dashboard_app.fleet_health(now)
        self.assertEqual(status, dashboard_app.HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload, {"status": "unavailable"})

    def test_legacy_naive_report_time_uses_fleet_timezone(self):
        parsed = dashboard_app.report_time({"generated_at": "2026-07-16T18:30:00"})
        self.assertEqual(parsed.utcoffset(), dt.timedelta(hours=-4))

    def test_wifi_health_uses_default_route_interface(self):
        facts = {
            "route": "default via 10.0.0.1 dev wlxusb metric 50",
            "wifi": [
                {"interface": "wlan0", "signal_dbm": -81},
                {"interface": "wlxusb", "signal_dbm": -42},
            ],
        }
        self.assertEqual(dashboard_app.routed_wifi_signal(facts), -42)
        self.assertEqual(dashboard_app.signal_grade(dashboard_app.routed_wifi_signal(facts)), "good")

    def test_wifi_health_falls_back_to_best_connected_interface(self):
        facts = {
            "route": "",
            "wifi": [
                {"interface": "wlan0", "signal_dbm": -76},
                {"interface": "wlxusb", "signal_dbm": -55},
            ],
        }
        self.assertEqual(dashboard_app.routed_wifi_signal(facts), -55)

    def test_probe_mapping_uses_exact_configured_cv_ids(self):
        facts = {
            "sensor_config": {
                "values": {f"SENSOR_{index}_ID": f"28-{index}" for index in range(1, 6)}
            },
            "one_wire": {"count": 3, "sensor_ids": ["28-1", "28-2", "28-3"]},
        }
        evidence = dashboard_app.probe_mapping_evidence(facts, "cv")
        self.assertFalse(evidence["complete"])
        self.assertEqual(evidence["expected_count"], 5)
        self.assertEqual(evidence["configured_ids"], ["28-1", "28-2", "28-3", "28-4", "28-5"])
        self.assertEqual(evidence["physical_ids"], ["28-1", "28-2", "28-3"])
        self.assertEqual(evidence["missing"], ["28-4", "28-5"])

    def test_calibration_mapping_accepts_explicit_and_safe_zero_defaults(self):
        facts = {
            "sensor_config": {"values": {
                "PROBE_IN_ID": "28-1",
                "PROBE_OUT_ID": "28-2",
            }},
            "one_wire": {"count": 2, "sensor_ids": ["28-1", "28-2"]},
            "sensor_offsets": {"values": {"28-1": 0.15}},
        }
        evidence = dashboard_app.calibration_mapping_evidence(facts, "mri")
        self.assertTrue(evidence["assessed"])
        self.assertTrue(evidence["aligned"])
        self.assertEqual(evidence["explicit_count"], 1)
        self.assertEqual(evidence["default_zero_ids"], ["28-2"])
        self.assertEqual(evidence["coverage_percent"], 50.0)
        self.assertFalse(evidence["complete_explicit"])

    def test_calibration_mapping_rejects_orphaned_and_invalid_offsets(self):
        facts = {
            "sensor_config": {"values": {"SENSOR_1_ID": "28-1"}},
            "one_wire": {"count": 1, "sensor_ids": ["28-1"]},
            "sensor_offsets": {"values": {"28-1": "bad", "28-old": 0.2}},
        }
        evidence = dashboard_app.calibration_mapping_evidence(facts, "cv")
        self.assertFalse(evidence["aligned"])
        self.assertEqual(evidence["invalid_value_ids"], ["28-1"])
        self.assertEqual(evidence["orphaned_ids"], ["28-old"])

    def test_live_mri_telemetry_preserves_named_channels_and_deltas(self):
        host = {
            "profile": "mri",
            "probe_mapping": {"expected_count": 5},
            "telemetry": {
                "helium_in": 21.125, "helium_out": 22.5,
                "primary_in": 18.0, "primary_out": 19.25,
                "helium_delta": 1.375, "primary_delta": 1.25,
                "last_updated": 990.0,
            },
        }
        with mock.patch.object(dashboard_app.time, "time", return_value=1000.0):
            evidence = dashboard_app.live_telemetry_evidence(host)
        self.assertTrue(evidence["complete"])
        self.assertEqual(evidence["required_count"], 4)
        self.assertEqual(evidence["required_available_count"], 4)
        self.assertEqual(evidence["readings"][0]["label"], "Helium in")
        self.assertEqual(evidence["readings"][0]["value_c"], 21.12)
        self.assertEqual([item["label"] for item in evidence["deltas"]], ["Helium delta", "Primary delta"])

    def test_live_cv_telemetry_uses_numbered_sensor_labels(self):
        host = {
            "profile": "cv",
            "probe_mapping": {"expected_count": 3},
            "telemetry": {
                "helium_in": 1.0, "helium_out": 2.0, "primary_in": 3.0,
                "primary_out": None, "room_temp": None, "last_updated": 995.0,
            },
        }
        with mock.patch.object(dashboard_app.time, "time", return_value=1000.0):
            evidence = dashboard_app.live_telemetry_evidence(host)
        self.assertTrue(evidence["complete"])
        self.assertEqual(evidence["required_count"], 3)
        self.assertEqual(
            [item["label"] for item in evidence["readings"][:3]],
            ["Sensor 1", "Sensor 2", "Sensor 3"],
        )
        self.assertEqual(evidence["deltas"], [])

    def test_live_cv_telemetry_reports_missing_configured_channel(self):
        host = {
            "profile": "cv",
            "probe_mapping": {"expected_count": 4},
            "telemetry": {
                "helium_in": 1.0, "helium_out": 2.0, "primary_in": 3.0,
                "primary_out": None, "last_updated": 999.0,
            },
        }
        with mock.patch.object(dashboard_app.time, "time", return_value=1000.0):
            evidence = dashboard_app.live_telemetry_evidence(host)
        self.assertFalse(evidence["complete"])
        self.assertTrue(evidence["current"])
        self.assertEqual(evidence["missing_required"], ["Sensor 4"])

    def test_live_telemetry_staleness_and_alarm_are_explicit(self):
        host = {
            "profile": "mri",
            "probe_mapping": {"expected_count": 4},
            "telemetry": {
                "helium_in": 1.0, "helium_out": 2.0,
                "primary_in": 3.0, "primary_out": 4.0,
                "helium_alarm": True, "last_updated": 600.0,
            },
        }
        with mock.patch.object(dashboard_app.time, "time", return_value=1000.0):
            evidence = dashboard_app.live_telemetry_evidence(host)
        self.assertFalse(evidence["current"])
        self.assertTrue(evidence["alarm"])
        self.assertEqual(evidence["alarm_fields"], ["helium_alarm"])

    def test_gpio_alignment_accepts_default_gpio4_overlay_and_live_line(self):
        evidence = dashboard_app.gpio_alignment_evidence({
            "gpio": {
                "one_wire_pin": "4",
                "boot_overlays": ["w1-gpio"],
                "pin_state": " 4: ip pn | hi // GPIO4 = input",
            }
        })
        self.assertTrue(evidence["assessed"])
        self.assertTrue(evidence["aligned"])
        self.assertEqual(evidence["configured_pin"], 4)

    def test_gpio_alignment_preserves_explicit_gpio17_exception(self):
        evidence = dashboard_app.gpio_alignment_evidence({
            "gpio": {
                "one_wire_pin": 17,
                "boot_overlays": ["w1-gpio,gpiopin=17"],
                "pin_state": "gpio-586 (GPIO17 | onewire@11) out hi",
            }
        })
        self.assertTrue(evidence["aligned"])
        self.assertEqual(evidence["configured_pin"], 17)

    def test_gpio_alignment_reports_overlay_and_live_pin_mismatch(self):
        evidence = dashboard_app.gpio_alignment_evidence({
            "gpio": {
                "one_wire_pin": 17,
                "boot_overlays": ["w1-gpio"],
                "pin_state": "gpio-586 (GPIO17) out hi",
            }
        })
        self.assertFalse(evidence["aligned"])
        self.assertIn("boot overlay uses GPIO4, audit reports GPIO17", evidence["deviations"])

    def test_approved_mri_runtime_policy_resolves_code_defaults_and_explicit_ram(self):
        facts = {
            "application": {"normalized_sha256": dashboard_app.PROFILE_BASELINES["mri"]},
            "sensor_config": {"values": {
                "POLL_SEC": "10", "AVG_WINDOW": "5", "MEMORY_ONLY_MODE": "true",
                "ENABLE_DUAL_STREAMING": "true",
            }},
        }
        policy = dashboard_app.sensor_runtime_policy(facts, "mri")
        self.assertTrue(policy["matches"])
        self.assertEqual(policy["effective"]["invalid_restart_threshold"], 3)
        self.assertEqual(policy["sources"]["invalid_restart_threshold"], "program default")

    def test_approved_mri_runtime_policy_does_not_infer_ram_mode_when_unset(self):
        facts = {
            "application": {"normalized_sha256": dashboard_app.PROFILE_BASELINES["mri"]},
            "sensor_config": {"values": {
                "POLL_SEC": "10", "AVG_WINDOW": "5", "ENABLE_DUAL_STREAMING": "true",
            }},
        }
        policy = dashboard_app.sensor_runtime_policy(facts, "mri")
        self.assertFalse(policy["matches"])
        self.assertFalse(policy["effective"]["memory_only"])
        self.assertIn("memory only is False, target True", policy["deviations"])

    def test_svi_mr2_exact_longer_recovery_bounds_are_approved_exception(self):
        facts = {
            "application": {"normalized_sha256": dashboard_app.PROFILE_BASELINES["mri"]},
            "sensor_config": {"values": {
                "POLL_SEC": "10", "AVG_WINDOW": "5", "MEMORY_ONLY_MODE": "true",
                "ENABLE_DUAL_STREAMING": "true", "INVALID_SENSOR_RESTART_THRESHOLD": "3",
                "SENSOR_DISCOVERY_TIMEOUT_SEC": "120", "SENSOR_DISCOVERY_INTERVAL_SEC": "5",
                "SENSOR_RESCAN_TIMEOUT_SEC": "30", "SENSOR_RESCAN_INTERVAL_SEC": "5",
            }},
        }
        policy = dashboard_app.sensor_runtime_policy(facts, "mri", "svimr2")
        self.assertFalse(policy["matches"])
        self.assertTrue(policy["approved_exception"])
        self.assertIn("SVI MR2", policy["exception_reason"])
        self.assertFalse(
            dashboard_app.sensor_runtime_policy(facts, "mri", "svimr1")["approved_exception"]
        )

    def test_legacy_mri_runtime_policy_marks_unimplemented_recovery_unknown(self):
        legacy_hash = next(
            digest for digest, family in dashboard_app.SOFTWARE_FAMILIES.items()
            if family["state"] == "legacy"
        )
        facts = {
            "application": {"normalized_sha256": legacy_hash},
            "sensor_config": {"values": {
                "POLL_SEC": "10", "AVG_WINDOW": "5", "MEMORY_ONLY_MODE": "true",
                "ENABLE_DUAL_STREAMING": "true",
            }},
        }
        policy = dashboard_app.sensor_runtime_policy(facts, "mri")
        self.assertFalse(policy["matches"])
        self.assertIsNone(policy["effective"]["invalid_restart_threshold"])
        self.assertIn("lacks the approved runtime policy", policy["deviations"][0])

    def test_approved_cv_runtime_policy_matches_console_profile_defaults(self):
        facts = {
            "application": {"normalized_sha256": dashboard_app.PROFILE_BASELINES["cv"]},
            "sensor_config": {"values": {
                "POLL_SEC": "10", "AVG_WINDOW": "5", "LOG_LEVEL": "INFO",
            }},
        }
        policy = dashboard_app.sensor_runtime_policy(facts, "cv")
        self.assertTrue(policy["matches"])
        self.assertEqual(policy["effective"]["request_timeout_seconds"], 10)
        self.assertEqual(policy["effective"]["logging_mode"], "console")

    def test_os_posture_distinguishes_target_supported_eol_and_offline(self):
        def host(os_name, status="ok"):
            return {"status": status, "facts": {"os": os_name}}

        self.assertEqual(
            dashboard_app.os_posture(host("Ubuntu 26.04 LTS (Resolute Raccoon)"))["state"],
            "target",
        )
        noble = dashboard_app.os_posture(host("Ubuntu 24.04.4 LTS (Noble Numbat)"))
        self.assertEqual(noble["state"], "supported_lts")
        self.assertEqual(noble["standard_support_until"], "2029-05")
        questing = dashboard_app.os_posture(host("Ubuntu 25.10 (Questing Quokka)"))
        self.assertEqual(questing["state"], "eol")
        self.assertEqual(questing["end_of_life"], "2026-07-09")
        self.assertEqual(
            dashboard_app.os_posture(host("", "offline_or_unreachable"))["state"],
            "unknown",
        )

    def test_service_unit_evidence_accepts_profile_paths_and_rejects_warning(self):
        mri = {
            "services": {"mri_sensor": {
                "active": "active", "enabled": "enabled", "user": "site",
                "fragmentpath": "/etc/systemd/system/mri-sensor.service",
                "workingdirectory": "/home/site/mike-mri-cooling",
                "execstart": "/home/site/mike-mri-cooling/src/pi_sensor.py",
                "unit_verify": "",
            }}
        }
        self.assertTrue(dashboard_app.service_unit_evidence(mri, "mri")["aligned"])
        mri["services"]["mri_sensor"]["unit_verify"] = "Assignment outside of section"
        evidence = dashboard_app.service_unit_evidence(mri, "mri")
        self.assertFalse(evidence["aligned"])
        self.assertIn("systemd unit validation reports", evidence["deviations"][0])

        cv = {
            "services": {"cv_sensor": {
                "active": "active", "enabled": "enabled", "user": "cvsite",
                "fragmentpath": "/etc/systemd/system/cv-room-sensor.service",
                "workingdirectory": "/opt/cv-room-monitor",
                "execstart": "/opt/cv-room-monitor/src/cv_room_sensor.py",
                "unit_verify": "",
            }}
        }
        self.assertTrue(dashboard_app.service_unit_evidence(cv, "cv")["aligned"])

    def test_restart_policy_preserves_cv_limit_and_requires_unlimited_mri_recovery(self):
        def facts(profile, delay="15s", interval="0"):
            key = "cv_sensor" if profile == "cv" else "mri_sensor"
            return {"services": {key: {
                "restart": "always", "restartusec": delay,
                "startlimitintervalusec": interval, "startlimitburst": "5",
            }}}

        self.assertTrue(dashboard_app.restart_policy_evidence(facts("mri"), "mri")["aligned"])
        old_mri = dashboard_app.restart_policy_evidence(facts("mri", "100ms", "10s"), "mri")
        self.assertFalse(old_mri["aligned"])
        self.assertEqual(len(old_mri["deviations"]), 2)
        self.assertTrue(dashboard_app.restart_policy_evidence(facts("cv", interval="10s"), "cv")["aligned"])
        self.assertFalse(dashboard_app.restart_policy_evidence({}, "mri")["assessed"])

    def test_restart_recovery_loader_accepts_only_complete_consistent_proof(self):
        valid = {
            "kind": "mri_restart_recovery_verification", "ok": True,
            "inventory_name": "agcmr1", "site_id": "AGCMR1",
            "created_at": "2026-07-16T21:08:59Z", "recovery_elapsed_ms": 15947,
            "before": {"MainPID": "1514"},
            "after": {
                "MainPID": "49593", "ActiveState": "active", "Restart": "always",
                "RestartUSec": "15s", "StartLimitIntervalUSec": "0",
            },
            "application_sha256": dashboard_app.PROFILE_BASELINES["mri"],
            "probe_ids": [f"28-{index}" for index in range(5)],
            "telemetry_before": 100, "telemetry_after": 165,
        }
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            (report_dir / "restart_recovery_20260716_210859.json").write_text(
                json.dumps(valid), encoding="utf-8"
            )
            invalid = copy.deepcopy(valid)
            invalid["inventory_name"] = "bad"
            invalid["after"]["MainPID"] = invalid["before"]["MainPID"]
            (report_dir / "restart_recovery_20260716_210900.json").write_text(
                json.dumps(invalid), encoding="utf-8"
            )
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_restart_recovery_verifications()
        self.assertEqual(list(loaded), ["agcmr1"])
        self.assertEqual(loaded["agcmr1"]["elapsed_seconds"], 15.947)
        self.assertEqual(loaded["agcmr1"]["telemetry_advanced_seconds"], 65)

    def test_complete_report_rejects_fact_or_ssh_failures(self):
        expected = dashboard_app.EXPECTED_HOSTS
        good = {"results": [{"status": "ok"} for _ in range(expected - 4)] + [{"status": "offline_or_unreachable"} for _ in range(4)]}
        self.assertTrue(dashboard_app.report_is_complete(good))
        good["results"][0]["status"] = "fact_collection_failed"
        self.assertFalse(dashboard_app.report_is_complete(good))
        good["results"][0]["status"] = "ssh_failed"
        self.assertFalse(dashboard_app.report_is_complete(good))

    def test_camera_observation_loader_uses_latest_passing_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            (report_dir / "camera_observation_20260716_150100.json").write_text(
                json.dumps({
                    "kind": "camera_schedule_verification",
                    "ok": True,
                    "inventory_name": "agcmr3",
                    "created_at": "2026-07-16T15:01:00-04:00",
                    "checks": {"scheduled_upload_count": True},
                    "camera_session": {
                        "session_id": "AGCMR3_SCHED_0716_150000",
                        "count": 10,
                        "ordinals": list(range(1, 11)),
                        "records": [{"id": value} for value in range(1, 11)],
                        "last_timestamp": 100,
                    },
                    "after": {
                        "camera": {
                            "fingerprint": "camera-v3",
                            "core_hashes": {"scheduled_capture.py": "sha-v3"},
                        }
                    },
                }),
                encoding="utf-8",
            )
            (report_dir / "camera_observation_20260716_150200.json").write_text(
                json.dumps({
                    "kind": "camera_schedule_verification",
                    "ok": False,
                    "inventory_name": "agcmr3",
                }),
                encoding="utf-8",
            )
            (report_dir / "camera_observation_baseline_20260716_145000.json").write_text(
                json.dumps({"ok": True, "inventory_name": "agcmr3"}),
                encoding="utf-8",
            )
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_camera_observations()
        self.assertEqual(loaded["agcmr3"]["upload_count"], 10)
        self.assertEqual(loaded["agcmr3"]["source_file"], "camera_observation_20260716_150100.json")
        self.assertEqual(loaded["agcmr3"]["camera_fingerprint"], "camera-v3")

    def test_camera_proof_must_match_the_current_exact_camera_build(self):
        observation = {
            "passed": True,
            "camera_fingerprint": "camera-v3",
            "camera_core_hashes": {"scheduled_capture.py": "sha-v3"},
        }
        software = {
            "fingerprint": "camera-v3",
            "core_files": {"scheduled_capture.py": {"sha256": "sha-v3"}},
        }
        self.assertTrue(dashboard_app.camera_proof_matches_software(observation, software))
        changed = copy.deepcopy(software)
        changed["core_files"]["scheduled_capture.py"]["sha256"] = "new-sha"
        self.assertFalse(dashboard_app.camera_proof_matches_software(observation, changed))
        self.assertFalse(dashboard_app.camera_proof_matches_software({"passed": True}, software))

    def camera_canary_payload(self):
        hashes = [
            f"{'a' * 64}  /home/oswmr1/mri-cooling-camera/edge/{name}"
            for name in sorted(dashboard_app.CAMERA_V3_RUNTIME_FILES)
        ]
        return {
            "kind": "camera_v3_candidate_canary",
            "schema": 1,
            "passed": True,
            "created_at": "2026-07-18T13:05:00+00:00",
            "inventory_name": "oswmr1",
            "canonical_version": "3.0.0",
            "candidate_source_sha256": dashboard_app.CAMERA_V3_SOURCE_SHA256,
            "site_id": "OSWMR1",
            "sensor_site_id": "OSWMR1",
            "backup_repository": "oswmr1",
            "target_contract": dashboard_app.CAMERA_TARGET_CONTRACTS["oswmr1"],
            "backup": {
                "activity_recent": True,
                "restore_status": "success",
                "restore_recent": True,
                "restore_snapshot_id": "snapshot-1",
            },
            "capture": {
                "requested": 1,
                "captured": 1,
                "uploaded": 0,
                "upload_enabled": False,
                "ram_workspace": "/dev/shm/coolmri-camera-v3-canary-oswmr1",
            },
            "safety": {
                "both_primary_natural_proofs": True,
                "exact_probes_before": True,
                "exact_probes_after": True,
                "sensor_active_before": True,
                "sensor_active_after": True,
                "zero_throttle_before": True,
                "zero_throttle_after": True,
                "production_hashes_unchanged": True,
                "sensor_restarted": False,
                "rebooted": False,
            },
            "production_hashes_before": hashes,
            "production_hashes_after": hashes,
            "telemetry": {
                "before_timestamp": 100,
                "after_timestamp": 112,
                "advanced": True,
                "offline_after": False,
            },
        }

    def test_camera_canary_loader_requires_complete_non_mutating_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            valid = self.camera_canary_payload()
            (report_dir / "camera_v3_candidate_canary_oswmr1_20260718.json").write_text(
                json.dumps(valid), encoding="utf-8"
            )
            invalid = self.camera_canary_payload()
            invalid["inventory_name"] = "oswmr2"
            invalid["target_contract"] = dashboard_app.CAMERA_TARGET_CONTRACTS["oswmr2"]
            invalid["safety"]["rebooted"] = True
            (report_dir / "camera_v3_candidate_canary_oswmr2_20260718.json").write_text(
                json.dumps(invalid), encoding="utf-8"
            )
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_camera_candidate_canaries()
        self.assertEqual(list(loaded), ["oswmr1"])
        self.assertEqual(loaded["oswmr1"]["telemetry_advanced_seconds"], 12)
        self.assertTrue(loaded["oswmr1"]["no_sensor_restart"])

    def test_camera_canary_is_bound_to_unchanged_production_runtime(self):
        canary = {
            "passed": True,
            "production_hashes": {
                name: "a" * 64 for name in dashboard_app.CAMERA_V3_RUNTIME_FILES
            },
        }
        software = {
            "core_files": {
                name: {"sha256": "a" * 64}
                for name in dashboard_app.CAMERA_V3_RUNTIME_FILES
            }
        }
        self.assertTrue(
            dashboard_app.candidate_canary_matches_current_camera(canary, software)
        )
        software["core_files"]["scheduled_capture.py"]["sha256"] = "b" * 64
        self.assertFalse(
            dashboard_app.candidate_canary_matches_current_camera(canary, software)
        )

    def camera_deployment_payload(self):
        return {
            "kind": "camera_v3_candidate_deployment",
            "schema": 1,
            "passed": True,
            "created_at": "2026-07-18T14:00:00+00:00",
            "inventory_name": "oswmr1",
            "canonical_version": "3.0.0",
            "candidate_source_sha256": dashboard_app.CAMERA_V3_SOURCE_SHA256,
            "target_contract": dashboard_app.CAMERA_TARGET_CONTRACTS["oswmr1"],
            "canary_source_file": "camera_v3_candidate_canary_oswmr1_20260718.json",
            "canary_created_at": "2026-07-18T13:00:00+00:00",
            "backup_repository": "oswmr1",
            "restore_snapshot_id": "snapshot-2",
            "installed_hashes": dashboard_app.CAMERA_V3_RUNTIME_HASHES,
            "capture": {
                "requested": 1,
                "captured": 1,
                "uploaded": 0,
                "upload_enabled": False,
                "ram_workspace": "/dev/shm/coolmri-camera-v3-deploy-oswmr1/smoke",
            },
            "safety": {
                "schedule_unchanged": True,
                "exact_probes_after": True,
                "sensor_active_after": True,
                "zero_throttle_after": True,
                "rollback_staged": True,
                "sensor_restarted": False,
                "rebooted": False,
            },
            "telemetry": {
                "before_timestamp": 200,
                "after_timestamp": 215,
                "advanced": True,
            },
            "natural_proof_pending": True,
        }

    def test_camera_deployment_loader_requires_exact_pending_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            valid = self.camera_deployment_payload()
            (report_dir / "camera_v3_candidate_deployment_oswmr1_20260718.json").write_text(
                json.dumps(valid), encoding="utf-8"
            )
            invalid = self.camera_deployment_payload()
            invalid["inventory_name"] = "oswmr2"
            invalid["target_contract"] = dashboard_app.CAMERA_TARGET_CONTRACTS["oswmr2"]
            invalid["safety"]["schedule_unchanged"] = False
            (report_dir / "camera_v3_candidate_deployment_oswmr2_20260718.json").write_text(
                json.dumps(invalid), encoding="utf-8"
            )
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_camera_candidate_deployments()
        self.assertEqual(list(loaded), ["oswmr1"])
        self.assertEqual(loaded["oswmr1"]["telemetry_advanced_seconds"], 15)
        self.assertTrue(loaded["oswmr1"]["natural_proof_pending"])

    def test_camera_deployment_is_bound_to_exact_installed_v3_runtime(self):
        deployment = {
            "passed": True,
            "installed_hashes": dict(dashboard_app.CAMERA_V3_RUNTIME_HASHES),
        }
        software = {
            "core_files": {
                name: {"sha256": digest}
                for name, digest in dashboard_app.CAMERA_V3_RUNTIME_HASHES.items()
            }
        }
        self.assertTrue(
            dashboard_app.candidate_deployment_matches_current_camera(
                deployment, software
            )
        )
        software["core_files"]["run_retry_check.sh"]["sha256"] = "f" * 64
        self.assertFalse(
            dashboard_app.candidate_deployment_matches_current_camera(
                deployment, software
            )
        )

    def test_camera_observation_loader_exposes_valid_pending_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            path = report_dir / "camera_observation_baseline_20260716_145000.json"
            path.write_text(
                json.dumps({
                    "kind": "camera_schedule_baseline",
                    "ok": True,
                    "inventory_name": "agcmr3",
                    "created_at": "2026-07-16T14:50:00-04:00",
                    "not_before": "2026-07-16T14:55:00-04:00",
                    "expected_upload_count": 10,
                    "checks": {"camera_logs_in_ram": True},
                }),
                encoding="utf-8",
            )
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_camera_observations()
        self.assertTrue(loaded["agcmr3"]["pending"])
        self.assertFalse(loaded["agcmr3"]["passed"])
        self.assertEqual(loaded["agcmr3"]["expected_upload_count"], 10)

    def test_camera_observation_loader_exposes_future_plan_and_expires_it(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            path = report_dir / "camera_observation_plan_agcmr1_20260717.json"
            path.write_text(
                json.dumps({
                    "schema": 1,
                    "kind": "camera_schedule_plan",
                    "created_at": "2026-07-16T19:30:00-04:00",
                    "inventory_name": "agcmr1",
                    "baseline_at": "2026-07-17T08:55:00-04:00",
                    "not_before": "2026-07-17T09:00:00-04:00",
                    "complete_at": "2026-07-17T09:03:00-04:00",
                    "expires_at": "2026-07-17T09:30:00-04:00",
                    "expected_upload_count": 10,
                }),
                encoding="utf-8",
            )
            before_expiry = dt.datetime.fromisoformat("2026-07-17T08:00:00-04:00").timestamp()
            with (
                mock.patch.object(dashboard_app, "REPORT_DIR", report_dir),
                mock.patch.object(dashboard_app.time, "time", return_value=before_expiry),
            ):
                planned = dashboard_app.load_camera_observations()["agcmr1"]
            after_expiry = dt.datetime.fromisoformat("2026-07-17T09:31:00-04:00").timestamp()
            with (
                mock.patch.object(dashboard_app, "REPORT_DIR", report_dir),
                mock.patch.object(dashboard_app.time, "time", return_value=after_expiry),
            ):
                expired = dashboard_app.load_camera_observations()["agcmr1"]
        self.assertTrue(planned["planned"])
        self.assertTrue(planned["pending"])
        self.assertFalse(planned["expired"])
        self.assertFalse(expired["pending"])
        self.assertTrue(expired["expired"])

    def test_camera_baseline_supersedes_a_plan_for_the_same_host(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            (report_dir / "camera_observation_plan_agcmr1.json").write_text(
                json.dumps({
                    "schema": 1, "kind": "camera_schedule_plan",
                    "inventory_name": "agcmr1", "expected_upload_count": 10,
                    "baseline_at": "2026-07-17T08:55:00-04:00",
                    "not_before": "2026-07-17T09:00:00-04:00",
                    "complete_at": "2026-07-17T09:03:00-04:00",
                    "expires_at": "2026-07-17T09:30:00-04:00",
                }), encoding="utf-8",
            )
            (report_dir / "camera_observation_baseline_20260717_085500.json").write_text(
                json.dumps({
                    "kind": "camera_schedule_baseline", "ok": True,
                    "inventory_name": "agcmr1", "created_at": "2026-07-17T08:55:00-04:00",
                    "not_before": "2026-07-17T09:00:00-04:00",
                    "expected_upload_count": 10, "checks": {"camera_logs_in_ram": True},
                }), encoding="utf-8",
            )
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_camera_observations()["agcmr1"]
        self.assertTrue(loaded["pending"])
        self.assertNotIn("planned", loaded)

    def test_os_upgrade_readiness_loader_exposes_latest_guarded_result(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            for stamp, ready, blockers in (
                ("150000", True, []),
                ("151000", False, ["production restore proof missing or stale"]),
            ):
                (report_dir / f"os_upgrade_readiness_20260716_{stamp}.json").write_text(
                    json.dumps({
                        "schema": 1,
                        "kind": "os_upgrade_baseline",
                        "created_at": f"2026-07-16T{stamp[:2]}:{stamp[2:4]}:00-04:00",
                        "ready": ready,
                        "blockers": blockers,
                        "target_codename": "resolute",
                        "repository": "agcmr3",
                        "snapshot": {"inventory_name": "agcmr3"},
                    }),
                    encoding="utf-8",
                )
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_os_upgrade_readiness()
        self.assertFalse(loaded["agcmr3"]["ready"])
        self.assertEqual(loaded["agcmr3"]["source_file"], "os_upgrade_readiness_20260716_151000.json")
        self.assertEqual(loaded["agcmr3"]["target_codename"], "resolute")

    def test_os_upgrade_verification_loader_requires_every_strict_check(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            for stamp, passed, checks in (
                ("081000", True, [{"name": "sensor runtime", "passed": True}]),
                ("082000", False, [{"name": "camera runtime", "passed": False}]),
            ):
                (report_dir / f"os_upgrade_verification_20260717_{stamp}.json").write_text(
                    json.dumps({
                        "schema": 1,
                        "kind": "os_upgrade_verification",
                        "created_at": f"2026-07-17T{stamp[:2]}:{stamp[2:4]}:00-04:00",
                        "inventory_name": "agcmr3",
                        "passed": passed,
                        "checks": checks,
                        "after": {
                            "os": "Ubuntu 26.04 LTS (Resolute Raccoon)",
                            "codename": "resolute",
                            "sensor_runtime": {"complete": True},
                            "camera_installed": True,
                            "camera_runtime": {"complete": True},
                        },
                    }), encoding="utf-8",
                )
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_os_upgrade_verifications()
        self.assertTrue(loaded["agcmr3"]["passed"])
        self.assertEqual(loaded["agcmr3"]["source_file"], "os_upgrade_verification_20260717_081000.json")
        self.assertTrue(loaded["agcmr3"]["camera_runtime_complete"])

    def test_maintenance_loader_exposes_only_sanitized_verified_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            update = {
                "action": "update",
                "generated_at": "2026-07-16T10:00:00-04:00",
                "results": [{
                    "inventory_name": "agcmr1",
                    "status": "ok",
                    "mutation_status": "ok",
                    "mutation_output": (
                        "SECRET SHOULD NOT ESCAPE\n"
                        "4 upgraded, 0 newly installed, 0 to remove and 0 not upgraded."
                    ),
                    "post_verification": {
                        "ok": True,
                        "telemetry_advanced": True,
                        "local": {
                            "reboot_observed": True,
                            "application_preserved": True,
                            "service_active": True,
                            "probe_count": 5,
                            "throttle_flags": 0,
                            "pre_kernel": "Linux old",
                            "post_kernel": "Linux old",
                            "kernel_advanced": False,
                            "package_maintenance": {
                                "listed_count": 0,
                                "eligible_count": 0,
                                "deferred_count": 0,
                            },
                        },
                    },
                }],
            }
            failed = copy.deepcopy(update)
            failed["action"] = "reboot"
            failed["generated_at"] = "2026-07-16T11:00:00-04:00"
            failed["results"][0]["mutation_status"] = "verification_failed"
            failed["results"][0]["post_verification"]["ok"] = False
            reboot = copy.deepcopy(update)
            reboot["action"] = "reboot"
            reboot["generated_at"] = "2026-07-16T12:00:00-04:00"
            reboot["results"][0]["inventory_name"] = "agcmr3"
            reboot["results"][0]["post_verification"]["local"].update({
                "reboot_requested": True,
                "reboot_observed": True,
                "kernel_advanced": True,
                "post_kernel": "Linux new",
            })
            (report_dir / "update_20260716_100000.json").write_text(json.dumps(update))
            (report_dir / "reboot_20260716_110000.json").write_text(json.dumps(failed))
            (report_dir / "reboot_20260716_120000.json").write_text(json.dumps(reboot))
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_verified_maintenance_actions()

        self.assertEqual(loaded["agcmr1"]["action"], "update")
        self.assertEqual(loaded["agcmr1"]["packages_changed"]["upgraded"], 4)
        self.assertFalse(loaded["agcmr1"]["reboot_requested"])
        self.assertFalse(loaded["agcmr1"]["reboot_observed"])
        self.assertTrue(loaded["agcmr1"]["telemetry_advanced"])
        self.assertTrue(loaded["agcmr3"]["reboot_observed"])
        self.assertTrue(loaded["agcmr3"]["kernel_advanced"])
        sanitized = json.dumps(loaded)
        self.assertNotIn("SECRET SHOULD NOT ESCAPE", sanitized)
        self.assertNotIn("mutation_output", sanitized)

    def test_maintenance_loader_labels_download_as_cache_only(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            payload = {
                "action": "download",
                "generated_at": "2026-07-17T09:42:00-04:00",
                "results": [{
                    "inventory_name": "gr",
                    "status": "ok",
                    "mutation_status": "ok",
                    "mutation_output": "269 upgraded, 0 newly installed, 0 to remove",
                    "post_verification": {
                        "ok": True,
                        "telemetry_not_required": True,
                        "local": {
                            "service_active": True,
                            "application_preserved": True,
                            "package_maintenance": {
                                "listed_count": 269,
                                "eligible_count": 269,
                                "deferred_count": 0,
                            },
                        },
                    },
                }],
            }
            (report_dir / "download_20260717_094200.json").write_text(json.dumps(payload))
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_verified_maintenance_actions()["gr"]
        self.assertTrue(loaded["packages_cached"])
        self.assertEqual(loaded["cached_eligible"], 269)
        self.assertIsNone(loaded["packages_changed"])
        self.assertTrue(loaded["telemetry_not_required"])

    def test_download_cache_evidence_survives_a_later_update(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            download = {
                "action": "download",
                "generated_at": "2026-07-17T09:42:00-04:00",
                "results": [{
                    "inventory_name": "gmcep1and2",
                    "status": "ok",
                    "mutation_status": "ok",
                    "post_verification": {
                        "ok": True,
                        "local": {"package_maintenance": {
                            "listed_count": 4, "eligible_count": 2, "deferred_count": 2,
                        }},
                    },
                }],
            }
            (report_dir / "download_20260717_094200.json").write_text(json.dumps(download))
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                cached = dashboard_app.load_verified_package_downloads()["gmcep1and2"]
        self.assertTrue(cached["verified"])
        self.assertEqual(cached["eligible"], 2)
        self.assertFalse(cached["installation_performed"])
        self.assertFalse(cached["reboot_performed"])

    def test_current_cache_assessment_refuses_stale_download_claim(self):
        historical = {
            "verified": True,
            "eligible": 213,
            "completed_at": "2026-07-17T09:42:00-04:00",
            "source_file": "download_20260717_094200.json",
        }
        incomplete = dashboard_app.assess_current_package_cache(
            {
                "package_cache": {
                    "assessed": True,
                    "complete": False,
                    "candidate_count": 3,
                    "cached_candidate_count": 2,
                    "missing_candidate_names": ["linux-image-raspi"],
                    "archive_count": 12,
                    "archive_bytes": 1000,
                }
            },
            historical,
        )
        self.assertFalse(incomplete["verified"])
        self.assertTrue(incomplete["download_transaction_verified"])
        self.assertEqual(incomplete["eligible"], 3)
        self.assertEqual(incomplete["missing_candidate_names"], ["linux-image-raspi"])

        complete = dashboard_app.assess_current_package_cache(
            {
                "package_cache": {
                    "assessed": True,
                    "complete": True,
                    "candidate_count": 3,
                    "cached_candidate_count": 3,
                    "missing_candidate_names": [],
                }
            },
            historical,
        )
        self.assertTrue(complete["verified"])
        self.assertEqual(complete["completed_at"], historical["completed_at"])

    def test_last_known_loader_rejects_invalid_and_accepts_sanitized_index(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            path = report_dir / "fleet_last_known.json"
            path.write_text(json.dumps({"kind": "wrong", "schema": 1}), encoding="utf-8")
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                self.assertEqual(dashboard_app.load_last_known_facts()["hosts"], {})
            path.write_text(json.dumps({
                "kind": "fleet_last_known",
                "schema": 1,
                "hosts": {"glh": {"observed_at": "2026-06-08T10:46:19", "facts": {"hostname": "glh"}}},
            }), encoding="utf-8")
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_last_known_facts()
        self.assertEqual(loaded["hosts"]["glh"]["facts"]["hostname"], "glh")

    def test_loader_skips_newer_failed_full_length_report(self):
        expected = dashboard_app.EXPECTED_HOSTS
        with tempfile.TemporaryDirectory() as directory:
            old_dir = dashboard_app.REPORT_DIR
            dashboard_app.REPORT_DIR = Path(directory)
            try:
                good = {"generated_at": "2026-07-16T09:00:00", "results": [{"status": "ok"} for _ in range(expected)]}
                bad = {"generated_at": "2026-07-16T09:15:00", "results": [{"status": "ok"} for _ in range(expected)]}
                bad["results"][0]["status"] = "fact_collection_failed"
                (Path(directory) / "audit_20260716_090000.json").write_text(json.dumps(good))
                (Path(directory) / "audit_20260716_091500.json").write_text(json.dumps(bad))
                loaded = dashboard_app.load_complete_reports(1)
                self.assertEqual(loaded[0]["source_file"], "audit_20260716_090000.json")
            finally:
                dashboard_app.REPORT_DIR = old_dir

    def test_display_loader_uses_newest_full_inventory_even_with_collection_failure(self):
        expected = dashboard_app.EXPECTED_HOSTS
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            good = {
                "generated_at": "2026-07-16T09:00:00",
                "results": [{"status": "ok"} for _ in range(expected)],
            }
            failed = copy.deepcopy(good)
            failed["generated_at"] = "2026-07-16T09:15:00"
            failed["results"][0]["status"] = "ssh_failed"
            (report_dir / "audit_20260716_090000.json").write_text(json.dumps(good))
            (report_dir / "audit_20260716_091500.json").write_text(json.dumps(failed))
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_latest_inventory_report()
        self.assertEqual(loaded["source_file"], "audit_20260716_091500.json")
        self.assertTrue(loaded["incomplete_report"])
        self.assertEqual(loaded["results"][0]["status"], "ssh_failed")

    def test_display_loader_ignores_newer_targeted_report(self):
        expected = dashboard_app.EXPECTED_HOSTS
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            fleet = {
                "generated_at": "2026-07-16T09:00:00",
                "results": [{"status": "ok"} for _ in range(expected)],
            }
            targeted = {
                "generated_at": "2026-07-16T09:15:00",
                "results": [{"status": "ok"}],
            }
            (report_dir / "audit_20260716_090000.json").write_text(json.dumps(fleet))
            (report_dir / "audit_20260716_091500.json").write_text(json.dumps(targeted))
            with mock.patch.object(dashboard_app, "REPORT_DIR", report_dir):
                loaded = dashboard_app.load_latest_inventory_report()
        self.assertEqual(loaded["source_file"], "audit_20260716_090000.json")
        self.assertNotIn("incomplete_report", loaded)

    def test_offline_recommendation_includes_tailscale_last_seen_and_field_action(self):
        host = {
            "status": "offline_or_unreachable",
            "tailscale_peer": {"online": False, "last_seen": "2026-07-15T23:08:10.1Z"},
        }
        recommendation = dashboard_app.recommendations(host)[0]
        self.assertEqual(recommendation["code"], "offline")
        self.assertIn("2026-07-15", recommendation["message"])
        self.assertIn("Check site power", recommendation["message"])

    def test_ssh_failure_discloses_reachable_transport_and_stale_production_data(self):
        host = {
            "status": "ssh_failed",
            "port_22": True,
            "tailscale_peer": {"online": True},
            "live_telemetry": {
                "backend_available": True,
                "current": False,
                "age_seconds": 5.5 * 86400,
            },
            "camera_telemetry": {
                "backend_available": True,
                "matched": True,
                "age_hours": 151.1,
            },
        }
        recommendations = dashboard_app.recommendations(host)
        by_code = {item["code"]: item for item in recommendations}
        self.assertIn("online in Tailscale", by_code["ssh_collection_failed"]["message"])
        self.assertIn("TCP port 22 responds", by_code["ssh_collection_failed"]["message"])
        self.assertIn("132.0 hours old", by_code["sensor_telemetry_stale"]["message"])
        self.assertIn("151.1 hours old", by_code["camera_upload_stale"]["message"])


class FleetHistoryTests(unittest.TestCase):
    def report(self, timestamp, *, uptime, written, online=23, packages=None):
        results = []
        for index in range(dashboard_app.EXPECTED_HOSTS):
            name = "agcmr1" if index == 0 else f"host-{index}"
            status = "ok" if index < online else "offline_or_unreachable"
            item = {"inventory_name": name, "status": status}
            if name == "agcmr1":
                item["facts"] = {
                    "uptime_seconds": uptime,
                    "storage_health": {
                        "root_block_device": "sda",
                        "serial": "SERIAL-1",
                        "bytes_written_since_boot": written,
                        "smart": {"unsafe_shutdowns": 1},
                    },
                    "wifi": [{"signal_dbm": -50}],
                    "package_manager": {"busy": False},
                    "package_maintenance": {
                        "listed_count": packages or 0,
                        "eligible_count": packages or 0,
                        "deferred_count": 0,
                    },
                }
            results.append(item)
        return {"generated_at": timestamp, "results": results}

    def test_history_has_gaps_before_valid_five_minute_sample(self):
        reports = [
            self.report("2026-07-16T10:00:00-04:00", uptime=1000, written=1_000_000_000),
            self.report("2026-07-16T10:10:00-04:00", uptime=1600, written=1_010_485_760),
        ]
        with mock.patch.object(dashboard_app, "load_complete_reports", return_value=list(reversed(reports))):
            history = dashboard_app.fleet_history_payload()
        self.assertEqual(len(history["points"]), 2)
        self.assertIsNone(history["points"][0]["write_mib_per_day"]["agcmr1"])
        self.assertEqual(history["points"][1]["write_mib_per_day"]["agcmr1"], 1440.0)
        self.assertEqual(history["points"][1]["online"], 23)
        self.assertEqual(history["expected_hosts"], dashboard_app.EXPECTED_HOSTS)

    def test_history_keeps_reboot_interval_as_gap(self):
        reports = [
            self.report("2026-07-16T10:00:00-04:00", uptime=1000, written=1_000_000_000),
            self.report("2026-07-16T10:10:00-04:00", uptime=100, written=2_000_000),
        ]
        with mock.patch.object(dashboard_app, "load_complete_reports", return_value=list(reversed(reports))):
            history = dashboard_app.fleet_history_payload()
        self.assertIsNone(history["points"][1]["write_mib_per_day"]["agcmr1"])

    def test_history_uses_later_pilot_evidence_to_gap_crossing_interval(self):
        reports = [
            self.report("2026-07-16T10:00:00-04:00", uptime=1000, written=1_000_000_000),
            self.report("2026-07-16T10:10:00-04:00", uptime=1600, written=1_010_485_760),
            self.report("2026-07-16T10:20:00-04:00", uptime=2200, written=1_020_971_520),
        ]
        applied_epoch = dt.datetime.fromisoformat("2026-07-16T10:05:00-04:00").timestamp()
        reports[-1]["results"][0]["facts"]["ram_optimization"] = {
            "rsyslog_ram_pilot": {"applied_epoch": applied_epoch}
        }
        with mock.patch.object(
            dashboard_app, "load_complete_reports", return_value=list(reversed(reports))
        ):
            history = dashboard_app.fleet_history_payload()
        self.assertIsNone(history["points"][1]["write_mib_per_day"]["agcmr1"])
        self.assertEqual(history["points"][2]["write_mib_per_day"]["agcmr1"], 1440.0)

    def test_history_gaps_interval_with_intermediate_package_state_change(self):
        reports = [
            self.report("2026-07-16T10:00:00-04:00", uptime=1000, written=1_000_000_000),
            self.report("2026-07-16T10:04:00-04:00", uptime=1240, written=1_100_000_000, packages=4),
            self.report("2026-07-16T10:10:00-04:00", uptime=1600, written=1_200_000_000),
        ]
        with mock.patch.object(
            dashboard_app, "load_complete_reports", return_value=list(reversed(reports))
        ):
            history = dashboard_app.fleet_history_payload()
        self.assertIsNone(history["points"][2]["write_mib_per_day"]["agcmr1"])


class MaintenanceWaveTests(unittest.TestCase):
    def host(self, name, *, ready=True, restore=True, signal=-50):
        return {
            "inventory_name": name,
            "label": name.upper(),
            "profile": "mri",
            "status": "ok",
            "maintenance": {
                "ready": ready,
                "blockers": [] if ready else ["backup activity is not recent"],
            },
            "backup": {
                "covered": ready,
                "restore_test": {"recent": restore},
            },
            "software_baseline": {"matches": True, "state": "approved"},
            "camera_convergence": {"status": "not_applicable"},
            "facts": {
                "packages_upgradable": 3,
                "reboot_required": False,
                "os": "Ubuntu 26.04 LTS",
                "wifi": [{"signal_dbm": signal}],
            },
        }

    def waves(self, *hosts):
        return {
            wave["id"]: wave
            for wave in dashboard_app.build_maintenance_waves(list(hosts))
        }

    def test_unbacked_host_never_enters_routine_ready(self):
        waves = self.waves(self.host("agcmr2", ready=False))
        self.assertEqual(waves["routine"]["ready"], [])
        self.assertEqual(waves["routine"]["held"][0]["inventory_name"], "agcmr2")
        self.assertEqual(waves["backup"]["held"][0]["inventory_name"], "agcmr2")

    def test_deferred_packages_do_not_enter_routine_lane(self):
        host = self.host("gmcir3")
        host["facts"]["package_maintenance"] = {
            "listed_count": 2,
            "eligible_count": 0,
            "deferred_count": 2,
        }
        waves = self.waves(host)
        self.assertEqual(waves["routine"]["ready"], [])
        self.assertEqual(waves["routine"]["held"], [])

    def test_tailscale_channel_lane_respects_camera_and_wifi_holds(self):
        camera = self.host("agcmr1")
        camera["facts"]["operational_stack"] = {
            "required_packages": {"tailscale": "1.90.9"},
            "package_channels": {"tailscale": {"channel": "distribution"}},
        }
        camera["camera_observation"] = {"planned": True, "pending": True}
        weak = self.host("jsmr", ready=False, signal=-70)
        weak["maintenance"]["blockers"] = ["remote routed Wi-Fi marginal at -70 dBm"]
        weak["facts"]["operational_stack"] = {
            "required_packages": {"tailscale": "1.92.1"},
            "package_channels": {"tailscale": {"channel": "distribution"}},
        }
        aligned = self.host("agcmr3")
        aligned["facts"]["operational_stack"] = {
            "required_packages": {"tailscale": "1.98.9"},
            "package_channels": {"tailscale": {"channel": "official_stable"}},
        }
        waves = self.waves(aligned, weak, camera)
        self.assertEqual(waves["tailscale"]["ready"], [])
        reasons = {
            item["inventory_name"]: item["reason"]
            for item in waves["tailscale"]["held"]
        }
        self.assertIn("camera proof must complete first", reasons["agcmr1"])
        self.assertIn("remote routed Wi-Fi marginal", reasons["jsmr"])
        self.assertNotIn("agcmr3", reasons)

    def test_tailscale_channel_lane_releases_healthy_distribution_host(self):
        host = self.host("agcmr1")
        host["facts"]["operational_stack"] = {
            "required_packages": {"tailscale": "1.90.9"},
            "package_channels": {"tailscale": {"channel": "distribution"}},
        }
        waves = self.waves(host)
        self.assertEqual(
            [item["inventory_name"] for item in waves["tailscale"]["ready"]],
            ["agcmr1"],
        )

    def test_unbacked_export_ready_host_reports_remaining_hub_work(self):
        host = self.host("agcmr2", ready=False)
        host["facts"]["restricted_helpers"] = {
            "pi_backup_export": {"installed": True, "check": True}
        }
        waves = self.waves(host)
        self.assertIn("hub target/root key", waves["backup"]["held"][0]["reason"])

    def test_nearby_pilots_sort_before_remote_hosts(self):
        waves = self.waves(self.host("vwm2"), self.host("agcmr1"))
        self.assertEqual(
            [item["inventory_name"] for item in waves["routine"]["ready"]],
            ["agcmr1", "vwm2"],
        )
        self.assertTrue(waves["routine"]["ready"][0]["nearby"])

    def test_nvme_controller_resets_enter_field_dispatch(self):
        host = self.host("gr")
        host["facts"]["boot_management"] = {"nvme_controller_resets_since_boot": 4}
        waves = self.waves(host)
        self.assertEqual(waves["network"]["ready"][0]["inventory_name"], "gr")
        self.assertIn("NVMe controller reset 4×", waves["network"]["ready"][0]["reason"])

    def test_unexpected_readonly_boot_enters_field_dispatch(self):
        host = self.host("gr")
        host["facts"]["boot_management"] = {
            "firmware_mount_options": "ro,relatime,errors=remount-ro",
            "firmware_configured_mount_options": "defaults",
            "firmware_source_write_protected_at_boot": True,
        }
        waves = self.waves(host)
        reason = waves["network"]["ready"][0]["reason"]
        self.assertIn("configured rw/defaults", reason)
        self.assertIn("offline FAT check", reason)

    def test_os_lane_requires_restore_proof(self):
        host = self.host("agcmr3", restore=False)
        host["facts"]["os"] = "Ubuntu 25.10 (Questing Quokka)"
        waves = self.waves(host)
        self.assertEqual(waves["os"]["ready"], [])
        self.assertEqual(waves["os"]["held"][0]["reason"], "production restore proof missing")

    def test_os_lane_does_not_treat_restore_proof_as_machine_readiness(self):
        host = self.host("agcmr1", restore=True)
        host["facts"]["os"] = "Ubuntu 25.10 (Questing Quokka)"
        waves = self.waves(host)
        self.assertEqual(waves["os"]["ready"], [])
        self.assertEqual(
            waves["os"]["held"][0]["reason"],
            "restore proof current; machine readiness assessment not completed",
        )

    def test_os_lane_requires_passing_guarded_machine_readiness(self):
        host = self.host("agcmr3", restore=True)
        host["facts"]["os"] = "Ubuntu 25.10 (Questing Quokka)"
        host["os_upgrade_readiness"] = {"ready": True, "blockers": []}
        waves = self.waves(host)
        self.assertEqual(
            [item["inventory_name"] for item in waves["os"]["ready"]],
            ["agcmr3"],
        )
        self.assertIn("attended LTS pilot ready", waves["os"]["ready"][0]["reason"])

    def test_os_lane_holds_later_ready_host_until_primary_pilot_passes(self):
        host = self.host("agcmr1", restore=True)
        host["facts"]["os"] = "Ubuntu 25.10 (Questing Quokka)"
        host["os_upgrade_readiness"] = {"ready": True, "blockers": []}
        waves = self.waves(host)
        self.assertEqual(waves["os"]["ready"], [])
        self.assertEqual(
            waves["os"]["held"][0]["reason"],
            "machine readiness proof current; await AGC MR3 primary pilot outcome",
        )

    def test_os_lane_releases_later_ready_host_after_primary_pilot(self):
        primary = self.host("agcmr3", restore=True)
        primary["facts"]["os"] = "Ubuntu 26.04 LTS (Resolute Raccoon)"
        later = self.host("agcmr1", restore=True)
        later["facts"]["os"] = "Ubuntu 25.10 (Questing Quokka)"
        later["os_upgrade_readiness"] = {"ready": True, "blockers": []}
        waves = self.waves(primary, later)
        self.assertEqual(
            [item["inventory_name"] for item in waves["os"]["ready"]],
            ["agcmr1"],
        )

    def test_failed_recovery_host_does_not_block_other_ready_hosts(self):
        primary = self.host("agcmr3", restore=True)
        primary["facts"]["os"] = "Ubuntu 26.04 LTS (Resolute Raccoon)"
        recovery = self.host("agcmr2", restore=True)
        recovery["facts"]["os"] = "Ubuntu 26.04 LTS (Resolute Raccoon)"
        recovery["maintenance"] = {
            "ready": False,
            "blockers": ["configured probe mapping incomplete"],
        }
        recovery["os_upgrade_verification"] = {"passed": False}
        later = self.host("agcmr1", restore=True)
        later["facts"]["os"] = "Ubuntu 25.10 (Questing Quokka)"
        later["os_upgrade_readiness"] = {"ready": True, "blockers": []}
        waves = self.waves(primary, recovery, later)
        self.assertEqual(
            [item["inventory_name"] for item in waves["os"]["ready"]],
            ["agcmr1"],
        )

    def test_camera_canary_stays_held_without_restore_proof(self):
        host = self.host("agcmr3", restore=False)
        host["facts"]["camera_logging"] = {"installed": True}
        host["camera_convergence"] = {"status": "hardware_canary_passed"}
        waves = self.waves(host)
        self.assertEqual(waves["camera"]["ready"], [])
        self.assertIn("restore proof missing", waves["camera"]["held"][0]["reason"])

    def test_camera_candidate_waits_for_both_primary_natural_proofs(self):
        mr3 = self.host("agcmr3")
        mr3["facts"]["camera_logging"] = {"installed": True}
        mr3["camera_convergence"] = {"status": "v3_production_verified"}
        candidate = self.host("gcmcmr2")
        candidate["facts"]["camera_logging"] = {"installed": True}
        candidate["camera_convergence"] = {
            "status": "eligible_after_primary_pilot_distinct_optics"
        }
        waves = self.waves(mr3, candidate)
        self.assertEqual(waves["camera"]["ready"], [])
        self.assertEqual(
            [item["inventory_name"] for item in waves["camera"]["held"]],
            ["gcmcmr2"],
        )
        self.assertIn("AGC MR1 and MR3", waves["camera"]["held"][0]["reason"])

    def test_camera_candidate_releases_for_upload_disabled_canary_after_primary_proofs(self):
        primary_hosts = []
        for name in ("agcmr1", "agcmr3"):
            host = self.host(name)
            host["facts"]["camera_logging"] = {"installed": True}
            host["camera_convergence"] = {"status": "v3_production_verified"}
            primary_hosts.append(host)
        candidate = self.host("gcmcmr2")
        candidate["facts"]["camera_logging"] = {"installed": True}
        candidate["camera_convergence"] = {
            "status": "eligible_after_primary_pilot_distinct_optics"
        }
        waves = self.waves(*primary_hosts, candidate)
        self.assertEqual(
            [item["inventory_name"] for item in waves["camera"]["ready"]],
            ["gcmcmr2"],
        )
        self.assertIn(
            "upload-disabled hardware canary", waves["camera"]["ready"][0]["reason"]
        )
        self.assertEqual(waves["camera"]["held"], [])

    def test_secondary_production_waits_for_oswmr1_natural_proof(self):
        primary_hosts = []
        for name in ("agcmr1", "agcmr3"):
            host = self.host(name)
            host["facts"]["camera_logging"] = {"installed": True}
            host["camera_convergence"] = {"status": "v3_production_verified"}
            primary_hosts.append(host)
        candidate = self.host("oswmr2", restore=True)
        candidate["facts"]["camera_logging"] = {"installed": True}
        candidate["camera_convergence"] = {"status": "hardware_canary_passed"}
        waves = self.waves(*primary_hosts, candidate)
        self.assertEqual(waves["camera"]["ready"], [])
        self.assertIn("OSW MR1 natural 10/10", waves["camera"]["held"][0]["reason"])

        reference = self.host("oswmr1")
        reference["facts"]["camera_logging"] = {"installed": True}
        reference["camera_convergence"] = {"status": "v3_production_verified"}
        waves = self.waves(*primary_hosts, reference, candidate)
        self.assertEqual(
            [item["inventory_name"] for item in waves["camera"]["ready"]
            ],
            ["oswmr2"],
        )
        self.assertIn("hardware canary", waves["camera"]["ready"][0]["reason"])

    def test_camera_deployment_waits_for_exact_build_natural_proof(self):
        host = self.host("oswmr1")
        host["facts"]["camera_logging"] = {"installed": True}
        host["camera_convergence"] = {
            "status": "v3_smoke_passed_pending_natural_proof"
        }
        waves = self.waves(host)
        self.assertEqual(waves["camera"]["ready"], [])
        self.assertIn("natural 10/10", waves["camera"]["held"][0]["reason"])

    def camera_host(self, name, *, memory_only=False, schedule_source="user"):
        host = self.host(name)
        host["facts"]["camera_logging"] = {
            "installed": True,
            "memory_only": memory_only,
            "software": {"schedules": [{"source": schedule_source}]},
        }
        return host

    def test_camera_ram_lane_waits_for_reference_natural_proof(self):
        reference = self.camera_host("gcmcmr2", memory_only=True)
        candidate = self.camera_host("oswmr1")
        waves = self.waves(reference, candidate)
        self.assertEqual(waves["camera_ram"]["ready"], [])
        self.assertEqual(
            [item["inventory_name"] for item in waves["camera_ram"]["held"]],
            ["oswmr1"],
        )
        self.assertIn("GCMC MR2 natural 10/10", waves["camera_ram"]["held"][0]["reason"])

    def test_camera_ram_lane_releases_exact_user_crontab_candidate(self):
        reference = self.camera_host("gcmcmr2", memory_only=True)
        reference["camera_observation"] = {
            "passed": True,
            "matches_current_camera": True,
        }
        candidate = self.camera_host("oswmr1")
        waves = self.waves(reference, candidate)
        self.assertEqual(
            [item["inventory_name"] for item in waves["camera_ram"]["ready"]],
            ["oswmr1"],
        )
        self.assertEqual(waves["camera_ram"]["held"], [])

    def test_camera_ram_lane_recognizes_crond_watchdog_and_skips_already_ram_hosts(self):
        reference = self.camera_host("gcmcmr2", memory_only=True)
        reference["camera_observation"] = {
            "passed": True,
            "matches_current_camera": True,
        }
        special = self.camera_host("oswmr2", schedule_source="cron.d/mri-cooling-camera")
        already_done = self.camera_host("agcmr1", memory_only=True)
        waves = self.waves(reference, special, already_done)
        self.assertEqual(
            [item["inventory_name"] for item in waves["camera_ram"]["ready"]],
            ["oswmr2"],
        )
        self.assertEqual(waves["camera_ram"]["held"], [])
        self.assertIn("cron.d-preserving", waves["camera_ram"]["ready"][0]["reason"])

    def journal_candidate(self):
        host = self.camera_host("gcmcmr2", memory_only=True)
        host["facts"]["ram_optimization"] = {"persistent_journal": True}
        host["facts"]["operational_stack"] = {
            "background_services": {
                "rsyslog.service": {"active": "active", "enabled": "enabled"}
            }
        }
        host["facts"]["storage_health"] = {
            "write_trend": {"sustained_high": True, "sample_count": 4}
        }
        return host

    def test_journal_lane_requires_exact_camera_workload_proof_first(self):
        candidate = self.journal_candidate()
        waves = self.waves(candidate)
        self.assertEqual(waves["journal"]["ready"], [])
        self.assertEqual(
            [item["inventory_name"] for item in waves["journal"]["held"]],
            ["gcmcmr2"],
        )
        self.assertIn("natural 10/10", waves["journal"]["held"][0]["reason"])

    def test_journal_lane_holds_proven_workload_for_48_hour_canaries(self):
        candidate = self.journal_candidate()
        candidate["camera_observation"] = {
            "passed": True,
            "matches_current_camera": True,
        }
        waves = self.waves(candidate)
        self.assertEqual(waves["journal"]["ready"], [])
        self.assertIn("48-hour", waves["journal"]["held"][0]["reason"])

    def test_journal_lane_releases_only_after_all_independent_gates(self):
        candidate = self.journal_candidate()
        candidate["camera_observation"] = {
            "passed": True,
            "matches_current_camera": True,
        }
        waves = {
            wave["id"]: wave
            for wave in dashboard_app.build_maintenance_waves(
                [candidate], {"cohort_ready": True, "hosts": {}}
            )
        }
        self.assertEqual(
            [item["inventory_name"] for item in waves["journal"]["ready"]],
            ["gcmcmr2"],
        )
        self.assertEqual(waves["journal"]["held"], [])
        self.assertIn("backup, restore, camera", waves["journal"]["ready"][0]["reason"])

    def test_weak_wifi_is_field_ready_not_a_remote_mutation(self):
        waves = self.waves(self.host("vwm2", ready=False, signal=-79))
        self.assertEqual(waves["network"]["ready"][0]["inventory_name"], "vwm2")
        self.assertIn("Ethernet", waves["network"]["ready"][0]["reason"])

    def test_offline_host_enters_field_dispatch_with_last_known_identity(self):
        host = self.host("glh")
        host.update({
            "status": "offline_or_unreachable",
            "tailscale_peer": {"last_seen": "2026-06-08T14:46:19Z"},
            "last_known": {
                "facts": {
                    "tailscale_ips": ["100.120.102.8"],
                    "macs": {"wlan0": "2c:cf:67:f0:24:48"},
                }
            },
        })
        waves = self.waves(host)
        item = waves["network"]["ready"][0]
        self.assertEqual(item["inventory_name"], "glh")
        self.assertIn("OFFLINE", item["reason"])
        self.assertIn("100.120.102.8", item["reason"])
        self.assertIn("2c:cf:67:f0:24:48", item["reason"])

    def test_field_dispatch_deduplicates_wifi_and_storage_actions(self):
        host = self.host("vwm2", signal=-79)
        host["facts"]["storage_health"] = {"smart": {"concerning": True}}
        waves = self.waves(host)
        self.assertEqual(len(waves["network"]["ready"]), 1)
        reason = waves["network"]["ready"][0]["reason"]
        self.assertIn("external-antenna USB Wi-Fi", reason)
        self.assertIn("storage health warning", reason)

    def test_marginal_remote_wifi_does_not_hold_package_and_reboot_lanes(self):
        host = self.host("jsmr", signal=-69)
        host["facts"]["route"] = "default via 10.0.0.1 dev wlan0 metric 600"
        host["facts"]["reboot_required"] = True
        host["maintenance"] = {"ready": True, "blockers": []}
        waves = self.waves(host)
        self.assertEqual(waves["routine"]["ready"][0]["inventory_name"], "jsmr")
        self.assertEqual(waves["reboot"]["ready"][0]["inventory_name"], "jsmr")
        self.assertEqual(waves["routine"]["held"], [])

    def test_marginal_nearby_wifi_does_not_block_pilot_maintenance(self):
        host = self.host("gmcep3", signal=-69)
        host["facts"]["route"] = "default via 10.0.0.1 dev wlan0 metric 600"
        host["maintenance"] = dashboard_app.maintenance_readiness(host)
        self.assertFalse(any("Wi-Fi" in reason for reason in host["maintenance"]["blockers"]))

    def test_operational_drift_uses_normal_maintenance_gate(self):
        ready = self.host("gbh")
        ready["operational_baseline"] = {
            "assessed": True,
            "matches": False,
            "deviations": ["missing base packages: python3-pip"],
        }
        held = self.host("agcmr2", ready=False)
        held["operational_baseline"] = {
            "assessed": True,
            "matches": False,
            "deviations": ["missing base packages: python3-pip"],
        }
        waves = self.waves(ready, held)
        self.assertEqual(waves["operational"]["ready"][0]["inventory_name"], "gbh")
        self.assertEqual(waves["operational"]["held"][0]["inventory_name"], "agcmr2")

    def test_restart_lane_separates_guarded_ready_and_held_mri_hosts(self):
        ready = self.host("oswmr1")
        held = self.host("agcmr2", ready=False)
        cv = self.host("gmcir3")
        cv["profile"] = "cv"
        aligned = self.host("agcmr3")
        for host in (ready, held, cv):
            host["restart_policy"] = {"assessed": True, "aligned": False}
            host["service_unit"] = {"aligned": True}
        aligned["restart_policy"] = {"assessed": True, "aligned": True}
        aligned["service_unit"] = {"aligned": True}
        waves = self.waves(held, ready, cv, aligned)
        self.assertEqual([item["inventory_name"] for item in waves["restart"]["ready"]], ["oswmr1"])
        self.assertEqual([item["inventory_name"] for item in waves["restart"]["held"]], ["agcmr2"])
        self.assertIn("backup activity", waves["restart"]["held"][0]["reason"])

    def test_headless_expansion_waits_for_multi_day_canary_evidence(self):
        pilot = self.host("agcmr3")
        remote = self.host("vwm2")
        for host in (pilot, remote):
            host["facts"]["operational_stack"] = {
                "background_services": {"gdm.service": {"active": "active"}}
            }
        waves = self.waves(remote, pilot)
        self.assertEqual(waves["headless"]["ready"], [])
        reasons = {item["inventory_name"]: item["reason"] for item in waves["headless"]["held"]}
        self.assertIn("48-hour", reasons["agcmr3"])
        self.assertIn("48-hour", reasons["vwm2"])

    def test_reboot_verified_headless_inventory_includes_ir3(self):
        self.assertEqual(
            set(dashboard_app.HEADLESS_OPTIMIZATION_STATUS),
            {"agcmr1", "agcmr3", "gbh", "gmcep1and2", "gmcep3", "gmcir3", "gwvskyra", "shmr", "vwm3"},
        )

    def test_completed_canary_cohort_releases_nearby_then_serial_remote_candidate(self):
        nearby = self.host("gmcep1and2", signal=-60)
        remote = self.host("oswmr1", signal=-50)
        for host in (nearby, remote):
            host["facts"]["operational_stack"] = {
                "background_services": {"gdm.service": {"active": "active"}}
            }
        observation = {"cohort_ready": True, "hosts": {}}
        waves = {
            wave["id"]: wave
            for wave in dashboard_app.build_maintenance_waves([nearby, remote], observation)
        }
        self.assertEqual(
            [item["inventory_name"] for item in waves["headless"]["ready"]],
            ["gmcep1and2", "oswmr1"],
        )
        self.assertEqual(waves["headless"]["held"], [])
        self.assertIn("serial remote expansion", waves["headless"]["ready"][1]["reason"])

    def test_completed_canary_cohort_treats_weak_wifi_as_warning_not_blocker(self):
        nearby = self.host("gmcep1and2", signal=-69)
        nearby["facts"]["operational_stack"] = {
            "background_services": {"gdm.service": {"active": "active"}}
        }
        observation = {"cohort_ready": True, "hosts": {}}
        waves = {
            wave["id"]: wave
            for wave in dashboard_app.build_maintenance_waves([nearby], observation)
        }
        self.assertEqual(waves["headless"]["ready"][0]["inventory_name"], "gmcep1and2")
        self.assertIn("Wi-Fi is weak", waves["headless"]["ready"][0]["reason"])

    def test_accepted_reference_evidence_reports_current_outage_as_real_hold(self):
        remote = self.host("vwm2")
        remote["facts"]["operational_stack"] = {
            "background_services": {"gdm.service": {"active": "active"}}
        }
        observation = {
            "cohort_ready": False,
            "reference_evidence_accepted": True,
            "reference_canaries": ["agcmr1"],
            "hosts": {
                "agcmr1": {
                    "ready": False,
                    "checks": {"reachable": False},
                    "blockers": ["no continuous passing samples"],
                }
            },
        }
        waves = {
            wave["id"]: wave
            for wave in dashboard_app.build_maintenance_waves([remote], observation)
        }
        reason = waves["headless"]["held"][0]["reason"]
        self.assertIn("reference evidence accepted", reason)
        self.assertIn("agcmr1 (unreachable)", reason)
        self.assertNotIn("await 48-hour", reason)

    def test_reboot_verified_offline_host_is_not_described_as_zero_hour_canary(self):
        offline = self.host("agcmr1")
        offline["status"] = "offline_or_unreachable"
        offline["facts"] = {}
        observation = {
            "cohort_ready": False,
            "reference_evidence_accepted": True,
            "reference_canaries": ["agcmr1"],
            "hosts": {
                "agcmr1": {
                    "ready": False,
                    "duration_hours": 0.0,
                    "continuous_samples": 0,
                    "checks": {"reachable": False},
                }
            },
        }
        waves = {
            wave["id"]: wave
            for wave in dashboard_app.build_maintenance_waves([offline], observation)
        }
        reason = waves["headless"]["held"][0]["reason"]
        self.assertIn("currently unreachable", reason)
        self.assertNotIn("0/48", reason)


class OperationalBaselineTests(unittest.TestCase):
    def host(self):
        packages = {
            name: "1.0"
            for name in ("python3", "python3-venv", "python3-pip", "git", "cron", "rsync")
        }
        return {
            "status": "ok",
            "facts": {
                "operational_stack": {
                    "architecture": "arm64",
                    "ntp_synchronized": True,
                    "base_packages": packages,
                },
                "services": {
                    "cron": {"active": "active"},
                    "tailscaled": {"active": "active"},
                },
            },
        }

    def test_aligned_stack_passes(self):
        result = dashboard_app.assess_operational_stack(self.host())
        self.assertTrue(result["assessed"])
        self.assertTrue(result["matches"])
        self.assertEqual(result["deviations"], [])

    def test_missing_package_and_ntp_are_reported(self):
        host = self.host()
        host["facts"]["operational_stack"]["base_packages"]["rsync"] = None
        host["facts"]["operational_stack"]["ntp_synchronized"] = False
        result = dashboard_app.assess_operational_stack(host)
        self.assertFalse(result["matches"])
        self.assertIn("missing required packages: rsync", result["deviations"])
        self.assertIn("system clock is not NTP-synchronized", result["deviations"])

    def test_expanded_required_packages_take_precedence_over_legacy_base_packages(self):
        host = self.host()
        host["facts"]["operational_stack"]["required_packages"] = {
            **host["facts"]["operational_stack"]["base_packages"],
            "curl": None,
        }
        result = dashboard_app.assess_operational_stack(host)
        self.assertFalse(result["matches"])
        self.assertIn("missing required packages: curl", result["deviations"])

    def test_old_audit_is_unknown_not_drift(self):
        result = dashboard_app.assess_operational_stack({"status": "ok", "facts": {}})
        self.assertFalse(result["assessed"])
        self.assertIsNone(result["matches"])

    def test_package_matrix_groups_versions_by_os_without_false_drift(self):
        hosts = []
        for name, codename, version in (
            ("agcmr1", "questing", "1.2-ubuntu1"),
            ("gmcep3", "resolute", "1.3-ubuntu1"),
        ):
            hosts.append({
                "inventory_name": name,
                "label": name.upper(),
                "status": "ok",
                "facts": {"operational_stack": {
                    "version_codename": codename,
                    "required_packages": {"curl": version, "jq": "1.8"},
                }},
            })
        matrix = dashboard_app.operational_package_matrix(hosts)
        by_name = {row["name"]: row for row in matrix["packages"]}
        self.assertEqual(matrix["assessed_hosts"], 2)
        self.assertEqual(matrix["complete_packages"], 2)
        self.assertTrue(by_name["curl"]["complete"])
        self.assertEqual(by_name["curl"]["version_variant_count"], 2)
        self.assertEqual(
            {tuple(item["os_cohorts"]) for item in by_name["curl"]["versions"]},
            {("questing",), ("resolute",)},
        )
        self.assertEqual(by_name["curl"]["same_cohort_spreads"], [])
        self.assertEqual(matrix["packages_with_same_cohort_spread"], 0)

    def test_package_matrix_marks_same_cohort_spread_and_names_variant_hosts(self):
        hosts = [
            {
                "inventory_name": name, "label": label, "status": "ok",
                "facts": {"operational_stack": {
                    "version_codename": "questing",
                    "required_packages": {"tailscale": version},
                }},
            }
            for name, label, version in (
                ("agcmr1", "AGC MR1", "1.90.9"),
                ("agcmr3", "AGC MR3", "1.92.1"),
            )
        ]
        matrix = dashboard_app.operational_package_matrix(hosts)
        row = matrix["packages"][0]
        self.assertEqual(matrix["packages_with_same_cohort_spread"], 1)
        self.assertEqual(row["same_cohort_spreads"], [{
            "os_cohort": "questing", "versions": ["1.90.9", "1.92.1"]
        }])
        self.assertEqual(
            {tuple(item["host_labels"]) for item in row["versions"]},
            {("AGC MR1",), ("AGC MR3",)},
        )

    def test_package_matrix_names_missing_hosts_and_ignores_offline_unknowns(self):
        online = {
            "inventory_name": "agcmr1", "label": "AGC MR1", "status": "ok",
            "facts": {"operational_stack": {
                "version_codename": "questing",
                "required_packages": {"curl": None, "jq": "1.8"},
            }},
        }
        offline = {"inventory_name": "glh", "label": "GLH", "status": "offline_or_unreachable"}
        matrix = dashboard_app.operational_package_matrix([online, offline])
        by_name = {row["name"]: row for row in matrix["packages"]}
        self.assertFalse(by_name["curl"]["complete"])
        self.assertEqual(by_name["curl"]["missing_hosts"], ["AGC MR1"])
        self.assertEqual(by_name["curl"]["expected_count"], 1)

    def test_package_matrix_exposes_tailscale_channels_and_host_labels(self):
        hosts = [
            {
                "inventory_name": name,
                "label": label,
                "status": "ok",
                "facts": {"operational_stack": {
                    "version_codename": "questing",
                    "required_packages": {"tailscale": version},
                    "package_channels": {"tailscale": {"channel": channel}},
                }},
            }
            for name, label, version, channel in (
                ("agcmr3", "AGC MR3", "1.98.9", "official_stable"),
                ("agcmr1", "AGC MR1", "1.90.9", "distribution"),
            )
        ]
        matrix = dashboard_app.operational_package_matrix(hosts)
        self.assertEqual(matrix["tailscale_channels"], [
            {"channel": "distribution", "count": 1, "host_labels": ["AGC MR1"]},
            {"channel": "official_stable", "count": 1, "host_labels": ["AGC MR3"]},
        ])
        self.assertEqual(matrix["packages"][0]["channels"], matrix["tailscale_channels"])

    def test_sensor_runtime_matrix_is_profile_aware_and_names_version_hosts(self):
        hosts = []
        for name, label, profile, python, requests in (
            ("agcmr3", "AGC MR3", "mri", "3.13.7", "2.32.4"),
            ("agcmr2", "AGC MR2", "mri", "3.13.7", "2.31.0"),
            ("gmcep3", "GMC EP3", "cv", "3.14.4", "2.32.3"),
        ):
            hosts.append({
                "inventory_name": name,
                "label": label,
                "profile": profile,
                "status": "ok",
                "facts": {"sensor_runtime": {
                    "complete": True,
                    "executable": "/venv/bin/python",
                    "python_version": python,
                    "direct_dependencies": {
                        "python-dotenv": "1.1.1" if profile == "mri" else "1.0.1",
                        "requests": requests,
                        "w1thermsensor": "2.3.0" if profile == "mri" else "2.0.0",
                    },
                }},
            })
        matrix = dashboard_app.sensor_runtime_matrix(hosts)
        self.assertEqual(matrix["assessed_hosts"], 3)
        self.assertEqual(matrix["complete_hosts"], 3)
        profiles = {item["profile"]: item for item in matrix["profiles"]}
        self.assertEqual(profiles["mri"]["assessed_hosts"], 2)
        requests_row = next(
            item for item in profiles["mri"]["dependencies"]
            if item["name"] == "requests"
        )
        self.assertEqual(requests_row["installed_count"], 2)
        self.assertEqual(
            {tuple(item["host_labels"]) for item in requests_row["versions"]},
            {("AGC MR2",), ("AGC MR3",)},
        )
        self.assertEqual(profiles["cv"]["python_versions"][0]["version"], "3.14.4")

    def test_runtime_matrix_includes_installed_camera_environments_separately(self):
        host = {
            "inventory_name": "agcmr3", "label": "AGC MR3", "profile": "mri", "status": "ok",
            "facts": {
                "sensor_runtime": {
                    "python_version": "3.14.4",
                    "direct_dependencies": {
                        "python-dotenv": "1.1.1", "requests": "2.32.4", "w1thermsensor": "2.3.0",
                    },
                },
                "camera_logging": {
                    "installed": True,
                    "runtime": {
                        "python_version": "3.14.4",
                        "direct_dependencies": {
                            "numpy": "2.3.5", "Pillow": "11.3.0",
                            "python-dotenv": "1.1.1", "requests": "2.32.5",
                        },
                    },
                },
            },
        }
        matrix = dashboard_app.sensor_runtime_matrix([host])
        profiles = {item["profile"]: item for item in matrix["profiles"]}
        self.assertEqual(matrix["camera_assessed_hosts"], 1)
        self.assertEqual(matrix["camera_complete_hosts"], 1)
        self.assertEqual(profiles["camera"]["complete_hosts"], 1)
        self.assertEqual(
            {item["name"] for item in profiles["camera"]["dependencies"]},
            set(dashboard_app.CAMERA_RUNTIME_MINIMUMS),
        )

    def test_broken_installed_camera_runtime_is_critical_and_blocks_maintenance(self):
        host = self.host()
        host.update({"inventory_name": "agcmr3", "profile": "mri"})
        host["facts"]["sensor_runtime"] = {
            "python_version": "3.14.4",
            "direct_dependencies": {
                "python-dotenv": "1.1.1", "requests": "2.32.4", "w1thermsensor": "2.3.0",
            },
        }
        host["facts"]["camera_logging"] = {
            "installed": True,
            "runtime": {
                "python_version": "",
                "direct_dependencies": {
                    "numpy": None, "Pillow": None, "python-dotenv": None, "requests": None,
                },
            },
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "camera_runtime_dependencies"
        )
        self.assertEqual(finding["severity"], "critical")
        self.assertIn("numpy", finding["message"])
        self.assertIn(
            "installed camera Python runtime incomplete",
            dashboard_app.maintenance_readiness(host)["blockers"],
        )

    def test_camera_entrypoint_import_failure_blocks_runtime_even_when_packages_exist(self):
        host = self.host()
        host.update({"inventory_name": "agcmr2", "profile": "mri"})
        host["facts"]["camera_logging"] = {
            "installed": True,
            "runtime": {
                "python_version": "3.14.4",
                "direct_dependencies": {
                    "numpy": "2.3.5",
                    "Pillow": "12.1.1",
                    "python-dotenv": "1.2.2",
                    "requests": "2.32.5",
                },
                "entrypoint_import": {
                    "module": "scheduled_capture",
                    "ok": False,
                    "error": "ModuleNotFoundError: No module named 'pytesseract'",
                },
            },
        }

        assessment = dashboard_app.assess_camera_runtime(host)

        self.assertFalse(assessment["complete"])
        self.assertIn("camera entrypoint import", assessment["missing"])
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "camera_runtime_dependencies"
        )
        self.assertIn("camera entrypoint import", finding["message"])

    def test_missing_sensor_runtime_dependency_is_critical(self):
        host = self.host()
        host.update({"inventory_name": "agcmr3", "profile": "mri"})
        host["facts"]["sensor_runtime"] = {
            "executable": "/venv/bin/python",
            "python_version": "3.13.7",
            "direct_dependencies": {
                "python-dotenv": "1.1.1",
                "requests": None,
                "w1thermsensor": "2.3.0",
            },
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "sensor_runtime_dependencies"
        )
        self.assertEqual(finding["severity"], "critical")
        self.assertIn("requests", finding["message"])

    def test_zero_visible_configured_probes_requires_physical_bus_action(self):
        host = self.host()
        host.update({"inventory_name": "agcmr2", "profile": "mri"})
        host["facts"]["sensor_config"] = {"values": {
            "PROBE_IN_ID": "28-1",
            "PROBE_OUT_ID": "28-2",
            "PROBE_PRIMARY_IN_ID": "28-3",
            "PROBE_PRIMARY_OUT_ID": "28-4",
        }}
        host["facts"]["one_wire"] = {"count": 0, "sensor_ids": []}
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "probe_mapping"
        )
        self.assertEqual(finding["severity"], "critical")
        self.assertIn("None of the 4 configured 1-Wire probes", finding["message"])
        self.assertIn("cold-power-cycle", finding["message"])
        self.assertIn("Three controlled warm reboots", finding["message"])
        self.assertIn("do not repeat warm reboots", finding["message"])

    def test_svi_aera_zero_probe_finding_preserves_external_wifi_diagnosis(self):
        host = self.host()
        host.update({"inventory_name": "svimr1", "profile": "mri"})
        host["facts"]["sensor_config"] = {"values": {
            "PROBE_IN_ID": "28-1",
            "PROBE_OUT_ID": "28-2",
            "PROBE_PRIMARY_IN_ID": "28-3",
            "PROBE_PRIMARY_OUT_ID": "28-4",
            "PROBE_ROOM_ID": "28-5",
        }}
        host["facts"]["one_wire"] = {"count": 0, "sensor_ids": []}
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "probe_mapping"
        )
        self.assertIn("1-Wire driver reload", finding["message"])
        self.assertIn("external USB Wi-Fi route remained healthy", finding["message"])
        self.assertIn("rather than repeating remote reboots", finding["message"])

    def test_sensor_runtime_rejects_below_floor_or_next_major(self):
        host = self.host()
        host["facts"]["sensor_runtime"] = {
            "executable": "/venv/bin/python",
            "python_version": "3.13.7",
            "direct_dependencies": {
                "python-dotenv": "2.0.0",
                "requests": "2.30.9",
                "w1thermsensor": "2.0.0",
            },
        }
        result = dashboard_app.assess_sensor_runtime(host)
        self.assertFalse(result["complete"])
        self.assertEqual(result["incompatible"], ["python-dotenv", "requests"])

    def test_sensor_operational_health_does_not_equate_runtime_with_physical_path(self):
        host = self.host()
        host.update({
            "profile": "mri",
            "sensor_runtime_assessment": {"complete": True},
            "probe_mapping": {"exact": True, "complete": False},
            "live_telemetry": {"current": False, "complete": True},
        })
        host["facts"]["services"]["mri_sensor"] = {"active": "active"}
        result = dashboard_app.sensor_operational_evidence(host)
        self.assertTrue(result["assessed"])
        self.assertFalse(result["operational"])
        self.assertTrue(result["checks"]["software_environment_complete"])
        self.assertFalse(result["checks"]["configured_probes_visible"])
        self.assertFalse(result["checks"]["telemetry_current_complete"])
        self.assertEqual(result["state"], "attention")

    def test_sensor_operational_health_requires_all_end_to_end_checks(self):
        host = self.host()
        host.update({
            "profile": "mri",
            "sensor_runtime_assessment": {"complete": True},
            "probe_mapping": {"exact": True, "complete": True},
            "live_telemetry": {"current": True, "complete": True},
        })
        host["facts"]["services"]["mri_sensor"] = {"active": "active"}
        result = dashboard_app.sensor_operational_evidence(host)
        self.assertTrue(result["operational"])
        self.assertEqual(result["blockers"], [])

    def test_eligible_package_count_prefers_simulated_upgrade_result(self):
        host = {"facts": {
            "packages_upgradable": "9",
            "package_maintenance": {"eligible_count": 3, "deferred_count": 6},
        }}
        self.assertEqual(dashboard_app.eligible_package_count(host), 3)

    def test_eligible_package_count_safely_handles_old_or_invalid_audits(self):
        self.assertEqual(
            dashboard_app.eligible_package_count({"facts": {"packages_upgradable": "4"}}),
            4,
        )
        self.assertEqual(
            dashboard_app.eligible_package_count({"facts": {"packages_upgradable": "unknown"}}),
            0,
        )


class RamBudgetTests(unittest.TestCase):
    def host(self, *, available=82.5, run_used=1.2, filesystem="tmpfs", oom=0):
        return {
            "status": "ok",
            "facts": {
                "ram_budget": {
                    "total_bytes": 8_000_000_000,
                    "available_bytes": 6_600_000_000,
                    "available_percent": available,
                    "swap_total_bytes": 0,
                    "swap_used_bytes": 0,
                    "swap_devices": [],
                    "zram_active": False,
                    "oom_events_since_boot": oom,
                    "run": {
                        "filesystem": filesystem,
                        "used_percent": run_used,
                    },
                },
            },
        }

    def test_healthy_budget_does_not_require_swap(self):
        result = dashboard_app.assess_ram_budget(self.host())
        self.assertTrue(result["assessed"])
        self.assertTrue(result["healthy"])
        self.assertEqual(result["severity"], "healthy")
        self.assertEqual(result["swap_total_bytes"], 0)

    def test_low_headroom_or_run_pressure_blocks_more_ram_rollout(self):
        warning = dashboard_app.assess_ram_budget(self.host(available=19.9, run_used=70))
        self.assertFalse(warning["healthy"])
        self.assertEqual(warning["severity"], "warning")
        critical_host = self.host(available=9.9, run_used=90, oom=1)
        critical = dashboard_app.assess_ram_budget(critical_host)
        self.assertEqual(critical["severity"], "critical")
        finding = next(
            item for item in dashboard_app.recommendations(critical_host)
            if item["code"] == "ram_budget"
        )
        self.assertEqual(finding["severity"], "critical")
        self.assertIn("Hold additional", finding["message"])

    def test_non_tmpfs_run_is_not_treated_as_ram_backed(self):
        result = dashboard_app.assess_ram_budget(self.host(filesystem="ext4"))
        self.assertFalse(result["healthy"])
        self.assertIn("/run is not backed by tmpfs", result["issues"])

    def test_old_audit_is_unassessed_not_unhealthy(self):
        self.assertEqual(
            dashboard_app.assess_ram_budget({"status": "ok", "facts": {}}),
            {"assessed": False, "healthy": None, "severity": None, "issues": []},
        )


class UpdatePolicyTests(unittest.TestCase):
    def host(self, *, reboot="", holds=None, upgrade="1", timers="enabled"):
        return {
            "status": "ok",
            "facts": {
                "update_policy": {
                    "unattended_upgrades_version": "2.12",
                    "apt_daily_timer": {"enabled": timers, "active": "active"},
                    "apt_daily_upgrade_timer": {"enabled": timers, "active": "active"},
                    "update_package_lists": "1",
                    "unattended_upgrade": upgrade,
                    "automatic_reboot": reboot,
                    "held_packages": holds or [],
                },
            },
        }

    def test_safe_policy_allows_default_false_automatic_reboot(self):
        result = dashboard_app.assess_update_policy(self.host())
        self.assertTrue(result["assessed"])
        self.assertTrue(result["aligned"])
        self.assertEqual(result["severity"], "healthy")
        self.assertFalse(result["automatic_reboot"])

    def test_automatic_reboot_is_critical(self):
        host = self.host(reboot="true")
        result = dashboard_app.assess_update_policy(host)
        self.assertFalse(result["aligned"])
        self.assertEqual(result["severity"], "critical")
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "update_policy"
        )
        self.assertEqual(finding["severity"], "critical")
        self.assertIn("automatic reboot", finding["message"])

    def test_disabled_updates_and_holds_are_actionable_drift(self):
        result = dashboard_app.assess_update_policy(
            self.host(upgrade="0", timers="disabled", holds=["linux-image-test"])
        )
        self.assertFalse(result["aligned"])
        self.assertEqual(result["severity"], "warning")
        self.assertIn("linux-image-test", " ".join(result["deviations"]))

    def test_old_audit_is_unassessed(self):
        self.assertFalse(
            dashboard_app.assess_update_policy({"status": "ok", "facts": {}})["assessed"]
        )


class RestoreRecommendationTests(unittest.TestCase):
    def host(self, restore_test=None):
        return {
            "status": "ok",
            "profile": "mri",
            "backup": {
                "covered": True,
                "activity_recent": True,
                "last_snapshot_activity": "2026-07-15T06:00:00-04:00",
                "restore_test": restore_test,
            },
            "facts": {
                "services": {"mri_sensor": {"active": "active", "user": "site"}},
                "wifi": [{"signal_dbm": -50}],
                "disk": {"used_percent": 5, "root_read_only": False},
                "throttled_flags": 0,
                "packages_upgradable": "0",
                "os": "Ubuntu 26.04 LTS",
                "one_wire": {"count": 5},
                "ram_optimization": {"app_memory_only": True},
                "gpio": {"one_wire_pin": "4", "pin_state": "GPIO4 = input"},
            },
        }

    def codes(self, host):
        return {item["code"] for item in dashboard_app.recommendations(host)}

    def test_missing_restore_evidence_is_visible(self):
        self.assertIn("restore_untested", self.codes(self.host()))

    def test_recent_success_clears_restore_finding(self):
        restore = {"status": "success", "recent": True}
        codes = self.codes(self.host(restore))
        self.assertNotIn("restore_untested", codes)
        self.assertNotIn("restore_stale", codes)

    def test_deferred_packages_are_not_reported_as_eligible_updates(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["packages_upgradable"] = "2"
        host["facts"]["package_maintenance"] = {
            "listed_count": 2,
            "eligible_count": 0,
            "deferred_count": 2,
        }
        codes = self.codes(host)
        self.assertIn("updates_deferred", codes)
        self.assertNotIn("updates", codes)

    def test_storage_blocked_packages_are_reported_held_not_ready(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["package_maintenance"] = {
            "listed_count": 272,
            "eligible_count": 272,
            "deferred_count": 0,
            "eligible_names": ["tailscale", "linux-image-raspi"],
        }
        host["facts"]["operational_stack"] = {
            "required_packages": {"tailscale": "1.98.4"},
            "package_channels": {"tailscale": {"channel": "official_stable"}},
        }
        host["facts"]["boot_management"] = {
            "firmware_mount_options": "ro,relatime,errors=remount-ro",
            "nvme_controller_resets_since_boot": 4,
        }
        findings = {item["code"]: item for item in dashboard_app.recommendations(host)}
        self.assertIn("updates_held", findings)
        self.assertNotIn("updates", findings)
        self.assertIn("272", findings["updates_held"]["message"])
        self.assertIn("read-only", findings["updates_held"]["message"])
        self.assertIn("reset 4 times", findings["updates_held"]["message"])
        self.assertIn("tailscale_version_held", findings)
        self.assertIn("Tailscale 1.98.4", findings["tailscale_version_held"]["message"])
        self.assertIn("matching package version", findings["tailscale_version_held"]["message"])

    def test_failed_restore_is_warning(self):
        restore = {"status": "failure", "recent": False}
        self.assertIn("restore_stale", self.codes(self.host(restore)))

    def test_marginal_onboard_wifi_recommends_external_antenna_or_ethernet(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["route"] = "default via 10.0.0.1 dev wlan0 metric 600"
        host["facts"]["wifi"] = [{
            "interface": "wlan0", "driver": "brcmfmac", "signal_dbm": -72,
            "adapter_kind": "onboard", "frequency_mhz": 5240, "power_save": "on",
        }]
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "wifi"
        )
        self.assertIn("external-antenna USB Wi-Fi adapter or Ethernet", finding["message"])
        self.assertIn("below -67 dBm", finding["message"])
        self.assertIn("onboard 5 GHz radio, power save on", finding["message"])

    def test_distribution_tailscale_channel_recommendation_respects_health_hold(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["operational_stack"] = {
            "required_packages": {"tailscale": "1.92.1"},
            "package_channels": {"tailscale": {"channel": "distribution"}},
        }
        host["maintenance"] = {
            "ready": False,
            "blockers": ["remote routed Wi-Fi marginal at -71 dBm"],
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "tailscale_channel"
        )
        self.assertEqual(finding["severity"], "warning")
        self.assertIn("Tailscale 1.92.1 uses the distribution package channel", finding["message"])
        self.assertIn("hold channel convergence until remote routed Wi-Fi marginal", finding["message"])

    def test_distribution_tailscale_channel_recommendation_respects_camera_proof(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["operational_stack"] = {
            "required_packages": {"tailscale": "1.90.9"},
            "package_channels": {"tailscale": {"channel": "distribution"}},
        }
        host["maintenance"] = {"ready": True, "blockers": []}
        host["camera_observation"] = {"planned": True, "pending": True}
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "tailscale_channel"
        )
        self.assertIn("keep it unchanged through the planned production camera proof", finding["message"])

    def test_gmc_ep3_wifi_note_preserves_inconclusive_power_save_setting(self):
        host = self.host({"status": "success", "recent": True})
        host["inventory_name"] = "gmcep3"
        host["facts"]["route"] = "default via 10.0.0.1 dev wlan0 metric 600"
        host["facts"]["wifi"] = [{
            "interface": "wlan0", "driver": "brcmfmac", "signal_dbm": -79,
            "adapter_kind": "onboard", "frequency_mhz": 5180, "power_save": "on",
        }]
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "wifi"
        )
        self.assertIn("0% packet loss in both modes", finding["message"])
        self.assertIn("leave power saving unchanged", finding["message"])

    def test_agcmr1_wifi_note_records_four_sample_power_save_result(self):
        host = self.host({"status": "success", "recent": True})
        host["inventory_name"] = "agcmr1"
        host["facts"]["route"] = "default via 10.0.0.1 dev wlan0 metric 600"
        host["facts"]["wifi"] = [{
            "interface": "wlan0", "driver": "brcmfmac", "signal_dbm": -73,
            "adapter_kind": "onboard", "frequency_mhz": 5805, "power_save": "on",
        }]
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "wifi"
        )
        self.assertIn("all four 30-packet samples", finding["message"])
        self.assertIn("-73/-74 dBm", finding["message"])
        self.assertIn("leave power saving unchanged", finding["message"])

    def test_rsyslog_ram_recommendation_exposes_post_change_boundary(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["ram_optimization"] = {
            "journald_volatile": True,
            "rsyslog_ram_pilot": {"applied_epoch": 1784240311},
        }
        host["facts"]["operational_stack"] = {
            "background_services": {
                "rsyslog.service": {"active": "inactive", "enabled": "disabled"}
            }
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "ram_logging_pilot"
        )
        self.assertIn("post-change window begins", finding["message"])
        self.assertIn("2026-07-16", finding["message"])

    def test_approved_runtime_exception_is_information_not_drift_warning(self):
        host = self.host({"status": "success", "recent": True})
        host["runtime_policy"] = {
            "assessed": True,
            "approved_program": True,
            "matches": False,
            "approved_exception": True,
            "exception_reason": "Approved SVI MR2 recovery exception.",
        }
        findings = dashboard_app.recommendations(host)
        exception = next(
            item for item in findings if item["code"] == "runtime_policy_exception"
        )
        self.assertEqual(exception["severity"], "info")
        self.assertNotIn("runtime_policy", {item["code"] for item in findings})

    def test_invalid_calibration_mapping_is_a_warning(self):
        host = self.host({"status": "success", "recent": True})
        host["calibration_mapping"] = {
            "assessed": True,
            "aligned": False,
            "orphaned_ids": ["28-old"],
            "invalid_value_ids": ["28-bad"],
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "calibration_mapping"
        )
        self.assertEqual(finding["severity"], "warning")
        self.assertIn("28-old", finding["message"])
        self.assertIn("28-bad", finding["message"])

    def test_planned_camera_observation_is_information_not_a_proof(self):
        host = self.host({"status": "success", "recent": True})
        host["camera_observation"] = {
            "planned": True,
            "pending": True,
            "not_before": "2026-07-17T09:00:00-04:00",
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "camera_observation_planned"
        )
        self.assertEqual(finding["severity"], "info")
        self.assertIn("does not trigger an extra capture", finding["message"])

    def test_superseded_camera_proof_requires_the_current_exact_build(self):
        host = self.host({"status": "success", "recent": True})
        host["camera_observation"] = {
            "passed": True,
            "pending": True,
            "superseded_by_current_camera": True,
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "camera_observation_superseded"
        )
        self.assertEqual(finding["severity"], "info")
        self.assertIn("older exact camera build", finding["message"])
        self.assertIn("currently installed fingerprint", finding["message"])

    def test_expired_camera_observation_plan_is_a_warning(self):
        host = self.host({"status": "success", "recent": True})
        host["camera_observation"] = {"planned": True, "expired": True, "pending": False}
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "camera_observation_expired"
        )
        self.assertEqual(finding["severity"], "warning")

    def test_gcmc_mr2_backup_recommendation_shows_nearby_first_hub_gate(self):
        host = self.host()
        host["inventory_name"] = "gcmcmr2"
        host["backup"] = {"covered": False}
        host["facts"]["restricted_helpers"] = {
            "pi_backup_export": {"installed": True, "check": True}
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "backup"
        )
        self.assertIn("Nearby-first backup canary is Pi-ready", finding["message"])
        self.assertIn("separate sudo authorization", finding["message"])

    def test_ubuntu_2510_is_critical(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["os"] = "Ubuntu 25.10 (Questing Quokka)"
        finding = next(
            item for item in dashboard_app.recommendations(host) if item["code"] == "os"
        )
        self.assertEqual(finding["severity"], "critical")

    def test_sustained_unbacked_writer_prioritizes_backup_before_ram_policy(self):
        host = self.host()
        host["backup"] = {"covered": False}
        host["facts"]["storage_health"] = {
            "recent_mib_written_per_day": 6400,
            "write_rate_sample_seconds": 900,
            "write_trend": {
                "sample_count": 4,
                "median_mib_written_per_day": 6450,
                "sustained_high": True,
            },
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "storage_writes"
        )
        self.assertEqual(finding["severity"], "warning")
        self.assertIn("backup first", finding["message"])
        self.assertIn("do not change logging while it is unbacked", finding["message"])

    def test_readonly_boot_and_pending_piboot_are_visible(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["boot_management"] = {
            "firmware_mount_options": "ro,relatime,errors=remount-ro",
            "new_state": "unknown",
        }
        codes = self.codes(host)
        self.assertIn("boot_readonly", codes)
        self.assertIn("boot_candidate", codes)

    def test_nvme_reset_and_writable_block_layer_are_reported(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["boot_management"] = {
            "firmware_mount_options": "ro,relatime,errors=remount-ro",
            "firmware_source_read_only": False,
            "nvme_controller_resets_since_boot": 4,
            "nvme_power_saving_warning": True,
        }
        findings = {item["code"]: item for item in dashboard_app.recommendations(host)}
        self.assertIn("not a permanent hardware lock", findings["boot_readonly"]["message"])
        self.assertIn("reset 4 times", findings["nvme_controller_resets"]["message"])
        self.assertIn("power-saving warning", findings["nvme_controller_resets"]["message"])
        self.assertIn("smart_held", findings)
        self.assertNotIn("smart_unavailable", findings)
        self.assertIn("inspected onsite", findings["smart_held"]["message"])

    def test_unexpected_readonly_boot_is_distinguished_from_policy(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["boot_management"] = {
            "firmware_mount_options": "ro,relatime,errors=remount-ro",
            "firmware_configured_mount_options": "defaults",
            "firmware_source_write_protected_at_boot": True,
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "boot_readonly"
        )
        self.assertIn("configuration requests defaults", finding["message"])
        self.assertIn("not policy", finding["message"])

    def test_concerning_smart_data_is_critical(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["storage_health"] = {
            "smartctl_available": True,
            "smart": {"available": True, "concerning": True},
        }
        finding = next(
            item
            for item in dashboard_app.recommendations(host)
            if item["code"] == "storage_health"
        )
        self.assertEqual(finding["severity"], "critical")

    def test_persistent_camera_logs_are_visible(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["camera_logging"] = {
            "installed": True,
            "memory_only": False,
            "log_bytes": 10 * 1048576,
            "retry_state_durable": True,
        }
        self.assertIn("camera_logs", self.codes(host))

    def test_ram_camera_logs_keep_retry_state_durable(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["camera_logging"] = {
            "installed": True,
            "memory_only": True,
            "retry_state_durable": True,
        }
        codes = self.codes(host)
        self.assertNotIn("camera_logs", codes)
        self.assertNotIn("camera_retry_state", codes)

    def test_observed_legacy_camera_requires_review(self):
        host = self.host({"status": "success", "recent": True})
        host["camera_management"] = "observed_legacy"
        host["facts"]["camera_logging"] = {
            "installed": True,
            "memory_only": False,
            "retry_state_durable": True,
        }
        self.assertIn("camera_legacy", self.codes(host))

    def test_ignored_camera_upload_setting_is_visible(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["camera_logging"] = {
            "installed": True,
            "memory_only": False,
            "retry_state_durable": True,
            "software": {"ignored_safe_config_keys": ["UPLOAD_ENABLED"]},
        }
        self.assertIn("camera_config_ignored", self.codes(host))

    def test_stale_camera_upload_is_visible(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["camera_logging"] = {
            "installed": True,
            "memory_only": True,
            "retry_state_durable": True,
        }
        host["camera_telemetry"] = {
            "backend_available": True,
            "matched": True,
            "age_hours": 40,
        }
        self.assertIn("camera_upload_stale", self.codes(host))

    def test_raw_camera_ingest_does_not_mask_stale_production_posting(self):
        now = 1_800_000_000
        ingest, production = dashboard_app.camera_pipeline_telemetry(
            camera_site_id="AGCMR1",
            production_site_id="AGCMR1",
            camera_backend_available=True,
            production_backend_available=True,
            camera_latest={
                "AGCMR1": {
                    "site_id": "AGCMR1_SCHED_20260723T190001Z_10",
                    "timestamp": now - 12 * 3600,
                    "source": "camera_edge_v3",
                }
            },
            production_latest={
                "AGCMR1": {
                    "site_id": "AGCMR1",
                    "timestamp": now - 7 * 24 * 3600,
                    "return_pressure": 1.14,
                }
            },
            now=now,
        )

        self.assertEqual(ingest["age_hours"], 12)
        self.assertEqual(production["age_hours"], 168)

        host = self.host({"status": "success", "recent": True})
        host["facts"]["camera_logging"] = {
            "installed": True,
            "memory_only": True,
            "retry_state_durable": True,
        }
        host["camera_ingest_telemetry"] = ingest
        host["camera_telemetry"] = production
        finding = next(
            item
            for item in dashboard_app.recommendations(host)
            if item["code"] == "camera_upload_stale"
        )
        self.assertEqual(finding["severity"], "critical")
        self.assertIn("processing/forwarding failure", finding["message"])

    def test_production_pressure_uses_canonical_site_mapping(self):
        ingest, production = dashboard_app.camera_pipeline_telemetry(
            camera_site_id="JSMR",
            production_site_id="JerseyShoreMR",
            camera_backend_available=True,
            production_backend_available=True,
            camera_latest={
                "JSMR": {
                    "site_id": "JSMR_SCHED_0723_153001_10",
                    "timestamp": 1_800_000_000,
                }
            },
            production_latest={
                "JERSEYSHOREMR": {
                    "site_id": "JerseyShoreMR",
                    "timestamp": 1_800_000_000,
                    "return_pressure": 1.17,
                }
            },
            now=1_800_003_600,
        )

        self.assertTrue(ingest["matched"])
        self.assertTrue(production["matched"])
        self.assertEqual(production["site_id"], "JerseyShoreMR")
        self.assertEqual(production["return_pressure"], 1.17)

    def test_camera_backend_failure_is_not_individual_failure(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["camera_logging"] = {
            "installed": True,
            "memory_only": True,
            "retry_state_durable": True,
        }
        host["camera_telemetry"] = {"backend_available": False, "matched": None}
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "camera_backend_unavailable"
        )
        self.assertEqual(finding["severity"], "warning")

    def test_root_service_recommendation_uses_profile(self):
        mri = self.host({"status": "success", "recent": True})
        mri["facts"]["services"]["mri_sensor"]["user"] = "root"
        message = next(
            item["message"] for item in dashboard_app.recommendations(mri)
            if item["code"] == "service_user"
        )
        self.assertIn("MRI pilot", message)
        cv = self.host({"status": "success", "recent": True})
        cv["profile"] = "cv"
        cv["facts"]["services"]["cv_sensor"] = {"active": "active", "user": "root"}
        message = next(
            item["message"] for item in dashboard_app.recommendations(cv)
            if item["code"] == "service_user"
        )
        self.assertIn("CV-profile pilot", message)

    def test_privilege_wrapper_drift_is_a_maintenance_warning(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["restricted_helpers"] = {
            "sudo_compat": {"executable": True, "sha256": "old-build"}
        }
        finding = next(
            item for item in dashboard_app.recommendations(host)
            if item["code"] == "sudo_compat_drift"
        )
        self.assertEqual(finding["severity"], "warning")

    def test_desktop_and_duplicate_logging_are_review_findings(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["operational_stack"] = {
            "background_services": {
                "gdm.service": {"active": "active"},
                "rsyslog.service": {"active": "active"},
            }
        }
        host["facts"]["ram_optimization"] = {
            "app_memory_only": True,
            "persistent_journal": True,
        }
        codes = self.codes(host)
        self.assertIn("desktop_stack", codes)
        self.assertIn("duplicate_logging", codes)

    def test_volatile_journal_reports_rsyslog_disk_writes_or_ram_pilot(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["ram_optimization"] = {"journald_volatile": True}
        host["facts"]["operational_stack"] = {
            "background_services": {
                "rsyslog.service": {"active": "active", "enabled": "enabled"},
            }
        }
        self.assertIn("rsyslog_disk_logging", self.codes(host))

        host["facts"]["operational_stack"]["background_services"]["rsyslog.service"] = {
            "active": "inactive",
            "enabled": "disabled",
        }
        self.assertIn("ram_logging_pilot", self.codes(host))

    def test_unsafe_shutdown_increase_across_reboot_is_observation(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["storage_health"] = {
            "unsafe_shutdowns_delta": 1,
            "unsafe_shutdowns_interval_reboot": True,
            "smart": {"available": True},
        }
        finding = next(item for item in dashboard_app.recommendations(host) if item["code"] == "unsafe_shutdown_increase")
        self.assertEqual(finding["severity"], "info")
        self.assertIn("reboot interval", finding["message"])

    def test_unsafe_shutdown_increase_without_reboot_is_warning(self):
        host = self.host({"status": "success", "recent": True})
        host["facts"]["storage_health"] = {
            "unsafe_shutdowns_delta": 1,
            "unsafe_shutdowns_interval_reboot": False,
            "smart": {"available": True},
        }
        finding = next(item for item in dashboard_app.recommendations(host) if item["code"] == "unsafe_shutdown_increase")
        self.assertEqual(finding["severity"], "warning")
        self.assertIn("without an intervening reboot", finding["message"])


class StorageWriteRateTests(unittest.TestCase):
    def sample(self, byte_count, uptime):
        return {
            "facts": {
                "uptime_seconds": uptime,
                "storage_health": {
                    "root_block_device": "sda",
                    "serial": "SERIAL-1",
                    "bytes_written_since_boot": byte_count,
                    "smart": {"unsafe_shutdowns": 10},
                },
            }
        }

    def report(self, timestamp, byte_count, uptime):
        host = self.sample(byte_count, uptime)
        host.update({"inventory_name": "testpi", "status": "ok"})
        return {"generated_at": timestamp, "results": [host]}

    def test_rate_uses_counter_delta_between_audits(self):
        previous = self.sample(1_000_000_000, 10_000)
        current = self.sample(1_000_000_000 + 1048576, 13_600)
        dashboard_app.add_storage_write_rate(current, previous, 3600)
        storage = current["facts"]["storage_health"]
        self.assertEqual(storage["bytes_written_in_sample"], 1048576)
        self.assertEqual(storage["recent_mib_written_per_day"], 24.0)

    def test_rate_is_omitted_across_reboot(self):
        previous = self.sample(1_000_000_000, 10_000)
        current = self.sample(5_000_000, 120)
        dashboard_app.add_storage_write_rate(current, previous, 3600)
        self.assertNotIn(
            "recent_mib_written_per_day", current["facts"]["storage_health"]
        )

    def test_rate_is_omitted_for_short_noisy_sample(self):
        previous = self.sample(1_000_000_000, 10_000)
        current = self.sample(1_001_000_000, 10_060)
        dashboard_app.add_storage_write_rate(current, previous, 60)
        self.assertNotIn(
            "recent_mib_written_per_day", current["facts"]["storage_health"]
        )

    def test_write_trend_uses_three_non_overlapping_intervals(self):
        mib = 1048576
        reports = [
            self.report("2026-07-16T10:30:00-04:00", 1_000_000_000 + 30 * mib, 11_800),
            self.report("2026-07-16T10:20:00-04:00", 1_000_000_000 + 20 * mib, 11_200),
            self.report("2026-07-16T10:10:00-04:00", 1_000_000_000 + 10 * mib, 10_600),
            self.report("2026-07-16T10:00:00-04:00", 1_000_000_000, 10_000),
        ]
        host = copy.deepcopy(reports[0]["results"][0])
        dashboard_app.add_storage_write_trend(host, reports)
        trend = host["facts"]["storage_health"]["write_trend"]
        self.assertEqual(trend["sample_count"], 3)
        self.assertEqual(trend["median_mib_written_per_day"], 1440.0)
        self.assertTrue(trend["sustained_elevated"])
        self.assertFalse(trend["sustained_high"])

    def test_write_trend_stops_at_rsyslog_configuration_boundary(self):
        mib = 1048576
        reports = [
            self.report("2026-07-16T10:30:00-04:00", 1_000_000_000 + 30 * mib, 11_800),
            self.report("2026-07-16T10:20:00-04:00", 1_000_000_000 + 20 * mib, 11_200),
            self.report("2026-07-16T10:10:00-04:00", 1_000_000_000 + 10 * mib, 10_600),
            self.report("2026-07-16T10:00:00-04:00", 1_000_000_000, 10_000),
        ]
        applied_epoch = dt.datetime.fromisoformat("2026-07-16T10:15:00-04:00").timestamp()
        # Only the latest audit has the marker. Older audits were captured
        # before this public evidence field existed, which matches production.
        reports[0]["results"][0]["facts"]["ram_optimization"] = {
            "rsyslog_ram_pilot": {"applied_epoch": applied_epoch}
        }
        host = copy.deepcopy(reports[0]["results"][0])
        dashboard_app.add_storage_write_trend(host, reports)
        trend = host["facts"]["storage_health"]["write_trend"]
        self.assertEqual(trend["sample_count"], 1)
        self.assertEqual(trend["intervals"][0]["ended_at"], "2026-07-16T10:30:00-04:00")

    def test_write_trend_stops_at_intermediate_package_state_change(self):
        mib = 1048576
        reports = [
            self.report("2026-07-16T10:20:00-04:00", 1_000_000_000 + 20 * mib, 11_200),
            self.report("2026-07-16T10:17:00-04:00", 1_000_000_000 + 17 * mib, 11_020),
            self.report("2026-07-16T10:10:00-04:00", 1_000_000_000 + 10 * mib, 10_600),
        ]
        for index, report in enumerate(reports):
            facts = report["results"][0]["facts"]
            packages = 4 if index == 1 else 0
            facts["package_manager"] = {"busy": False}
            facts["package_maintenance"] = {
                "listed_count": packages,
                "eligible_count": packages,
                "deferred_count": 0,
            }
        host = copy.deepcopy(reports[0]["results"][0])
        dashboard_app.add_storage_write_trend(host, reports)
        self.assertEqual(host["facts"]["storage_health"]["write_trend"]["sample_count"], 0)

    def test_write_trend_skips_explicit_package_activity_window(self):
        mib = 1048576
        reports = [
            self.report("2026-07-16T10:30:00-04:00", 1_000_000_000 + 230 * mib, 11_800),
            self.report("2026-07-16T10:20:00-04:00", 1_000_000_000 + 220 * mib, 11_200),
            self.report("2026-07-16T10:10:00-04:00", 1_000_000_000 + 10 * mib, 10_600),
            self.report("2026-07-16T10:00:00-04:00", 1_000_000_000, 10_000),
        ]
        windows = [(
            dt.datetime.fromisoformat("2026-07-16T10:15:00-04:00"),
            dt.datetime.fromisoformat("2026-07-16T10:25:00-04:00"),
        )]
        host = copy.deepcopy(reports[0]["results"][0])
        dashboard_app.add_storage_write_trend(
            host, reports, maintenance_windows=windows
        )
        trend = host["facts"]["storage_health"]["write_trend"]
        self.assertEqual(trend["sample_count"], 1)
        self.assertEqual(trend["intervals"][0]["ended_at"], "2026-07-16T10:10:00-04:00")
        self.assertEqual(trend["median_mib_written_per_day"], 1440.0)

    def test_package_activity_loader_uses_exact_and_legacy_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            (report_dir / "download_20260717_100000.json").write_text(json.dumps({
                "action": "download",
                "generated_at": "2026-07-17T10:00:00-04:00",
                "results": [{
                    "inventory_name": "jsmr",
                    "action_started_at": "2026-07-17T09:50:00-04:00",
                    "action_finished_at": "2026-07-17T09:59:00-04:00",
                }, {"inventory_name": "gr"}],
            }), encoding="utf-8")
            windows = dashboard_app.load_storage_maintenance_windows(report_dir)
        self.assertEqual(
            windows["jsmr"],
            [(
                dt.datetime.fromisoformat("2026-07-17T09:50:00-04:00"),
                dt.datetime.fromisoformat("2026-07-17T09:59:00-04:00"),
            )],
        )
        self.assertEqual(
            windows["gr"],
            [(
                dt.datetime.fromisoformat("2026-07-17T09:30:00-04:00"),
                dt.datetime.fromisoformat("2026-07-17T10:00:00-04:00"),
            )],
        )

    def test_single_high_interval_is_not_a_sustained_trend(self):
        mib = 1048576
        reports = [
            self.report("2026-07-16T10:10:00-04:00", 1_000_000_000 + 100 * mib, 10_600),
            self.report("2026-07-16T10:00:00-04:00", 1_000_000_000, 10_000),
        ]
        host = copy.deepcopy(reports[0]["results"][0])
        dashboard_app.add_storage_write_trend(host, reports)
        trend = host["facts"]["storage_health"]["write_trend"]
        self.assertEqual(trend["sample_count"], 1)
        self.assertFalse(trend["sustained_high"])

    def test_previous_report_skips_too_close_manual_audit(self):
        reports = [
            {"generated_at": "2026-07-16T00:15:48-04:00"},
            {"generated_at": "2026-07-16T00:15:43-04:00"},
            {"generated_at": "2026-07-16T00:00:22-04:00", "source_file": "valid"},
        ]
        selected = dashboard_app.previous_sample_report(reports)
        self.assertEqual(selected["source_file"], "valid")

    def test_unsafe_shutdown_delta_is_compared_across_same_device(self):
        previous = self.sample(1_000_000_000, 10_000)
        current = self.sample(1_001_000_000, 100)
        current["facts"]["storage_health"]["smart"]["unsafe_shutdowns"] = 11
        dashboard_app.add_storage_unsafe_delta(current, previous)
        self.assertEqual(current["facts"]["storage_health"]["unsafe_shutdowns_delta"], 1)
        self.assertTrue(current["facts"]["storage_health"]["unsafe_shutdowns_interval_reboot"])
        self.assertNotIn("recent_mib_written_per_day", current["facts"]["storage_health"])

    def test_unsafe_shutdown_delta_without_reboot_is_not_marked_reboot_interval(self):
        previous = self.sample(1_000_000_000, 10_000)
        current = self.sample(1_001_000_000, 11_000)
        current["facts"]["storage_health"]["smart"]["unsafe_shutdowns"] = 11
        dashboard_app.add_storage_unsafe_delta(current, previous)
        self.assertFalse(current["facts"]["storage_health"]["unsafe_shutdowns_interval_reboot"])

    def test_unsafe_shutdown_delta_rejects_different_storage(self):
        previous = self.sample(1_000_000_000, 10_000)
        current = self.sample(1_001_000_000, 11_000)
        current["facts"]["storage_health"]["serial"] = "OTHER"
        dashboard_app.add_storage_unsafe_delta(current, previous)
        self.assertNotIn("unsafe_shutdowns_delta", current["facts"]["storage_health"])


if __name__ == "__main__":
    unittest.main()
