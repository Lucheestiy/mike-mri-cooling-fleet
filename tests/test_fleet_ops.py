import copy
import datetime as dt
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fleet_ops.py"
SPEC = importlib.util.spec_from_file_location("fleet_ops", MODULE_PATH)
fleet_ops = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fleet_ops)


class SudoCompatibilityTests(unittest.TestCase):
    def test_mutating_commands_use_sudo_rs_compatibility_shim(self):
        expected = '"$HOME/.local/bin/sudo-rs-ansible-compat" -S -p \'\''
        self.assertIn(expected, fleet_ops.UPDATE_SCRIPT)
        self.assertIn(expected, fleet_ops.DOWNLOAD_SCRIPT)
        self.assertIn(expected, fleet_ops.BASELINE_SCRIPT)
        self.assertIn(expected, fleet_ops.REBOOT_SCRIPT)

    def test_update_installs_new_dependencies_without_allowing_removals(self):
        self.assertIn("apt-get -y upgrade --with-new-pkgs", fleet_ops.UPDATE_SCRIPT)
        self.assertNotIn("full-upgrade", fleet_ops.UPDATE_SCRIPT)

    def test_download_only_populates_cache_without_installing(self):
        self.assertIn(" update &&", fleet_ops.DOWNLOAD_SCRIPT)
        self.assertIn("--download-only", fleet_ops.DOWNLOAD_SCRIPT)
        self.assertIn("upgrade --with-new-pkgs", fleet_ops.DOWNLOAD_SCRIPT)
        self.assertIn("Acquire::Retries=3", fleet_ops.DOWNLOAD_SCRIPT)
        self.assertIn("Acquire::https::Timeout=30", fleet_ops.DOWNLOAD_SCRIPT)
        self.assertNotIn("autoremove", fleet_ops.DOWNLOAD_SCRIPT)

    def test_download_gate_only_blocks_low_disk_or_busy_apt(self):
        healthy = {"facts": {"disk": {"free_bytes": 2_000_000_000}, "package_manager": {"busy": False}}}
        self.assertEqual(fleet_ops.download_safety_blockers(healthy), [])
        blocked = {"facts": {"disk": {"free_bytes": 500_000_000}, "package_manager": {"busy": True}}}
        self.assertEqual(
            fleet_ops.download_safety_blockers(blocked),
            ["less than 1 GB root-disk free", "package manager is busy"],
        )

    def test_baseline_covers_the_shared_operational_support_layer(self):
        for package in (
            "ca-certificates",
            "curl",
            "jq",
            "network-manager",
            "openssh-server",
            "rsyslog",
            "tailscale",
        ):
            self.assertIn(package, fleet_ops.BASELINE_SCRIPT)

    def test_baseline_installs_only_missing_packages_without_removals(self):
        self.assertIn("dpkg-query -W", fleet_ops.BASELINE_SCRIPT)
        self.assertIn("operational baseline already aligned", fleet_ops.BASELINE_SCRIPT)
        self.assertIn("apt-get -y --no-remove install", fleet_ops.BASELINE_SCRIPT)
        syntax = subprocess.run(
            ["bash", "-n"],
            input=fleet_ops.BASELINE_BODY,
            text=True,
            capture_output=True,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_audit_separates_required_from_optional_diagnostics(self):
        self.assertIn('"required_packages": required_package_versions', fleet_ops.FACTS_SCRIPT)
        self.assertIn(
            '"optional_diagnostic_packages": optional_diagnostic_versions',
            fleet_ops.FACTS_SCRIPT,
        )
        self.assertNotIn("smartmontools", fleet_ops.BASELINE_SCRIPT)
        self.assertNotIn("nvme-cli", fleet_ops.BASELINE_SCRIPT)

    def test_audit_records_tailscale_channel_without_exposing_source_contents(self):
        self.assertIn('"package_channels": {', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"channel": "official_stable"', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"official_source_configured": bool(', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"pkgs.tailscale.com/stable/"', fleet_ops.FACTS_SCRIPT)
        self.assertNotIn('"source_lines"', fleet_ops.FACTS_SCRIPT)

    def test_audit_tolerates_apt_cache_files_disappearing_during_collection(self):
        self.assertIn("def file_size(path: Path) -> int:", fleet_ops.FACTS_SCRIPT)
        self.assertIn('"archive_bytes": sum(file_size(path)', fleet_ops.FACTS_SCRIPT)

    def test_audit_records_only_direct_sensor_runtime_dependencies(self):
        self.assertIn("def sensor_runtime_details(service: dict)", fleet_ops.FACTS_SCRIPT)
        self.assertIn('"sensor_runtime": sensor_runtime', fleet_ops.FACTS_SCRIPT)
        for package in ("python-dotenv", "requests", "w1thermsensor"):
            self.assertIn(f'"{package}"', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"complete": False', fleet_ops.FACTS_SCRIPT)
        self.assertNotIn('"pip_freeze"', fleet_ops.FACTS_SCRIPT)

    def test_audit_proves_camera_entrypoint_can_import(self):
        self.assertIn("def python_entrypoint_import(", fleet_ops.FACTS_SCRIPT)
        self.assertIn('"scheduled_capture"', fleet_ops.FACTS_SCRIPT)
        self.assertIn('camera_runtime["entrypoint_import"]', fleet_ops.FACTS_SCRIPT)
        self.assertIn("camera_entrypoint.get(\"ok\")", fleet_ops.FACTS_SCRIPT)

    def test_audit_records_bounded_ram_headroom_without_log_contents(self):
        self.assertIn('"ram_budget": {', fleet_ops.FACTS_SCRIPT)
        for field in (
            "available_percent",
            "swap_total_bytes",
            "swap_used_bytes",
            "swap_devices",
            "zram_active",
            "oom_events_since_boot",
        ):
            self.assertIn(f'"{field}"', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"filesystem": sh("findmnt -n -o FSTYPE /run', fleet_ops.FACTS_SCRIPT)
        self.assertIn("Out of memory:", fleet_ops.FACTS_SCRIPT)
        self.assertNotIn('"oom_log"', fleet_ops.FACTS_SCRIPT)

    def test_audit_bounds_long_lived_journal_queries(self):
        self.assertEqual(
            fleet_ops.FACTS_SCRIPT.count(
                "timeout 10s journalctl -k -b --no-pager -n 5000"
            ),
            2,
        )
        self.assertIn(
            "timeout 10s journalctl -b -u boot-firmware.mount "
            "--no-pager -n 5000",
            fleet_ops.FACTS_SCRIPT,
        )

    def test_profile_dependency_manifests_share_compatible_api_floors(self):
        root = Path(fleet_ops.__file__).resolve().parents[1]
        mri = (root / "roles/temp_sensors/files/requirements_pi.txt").read_text()
        cv = (root / "roles/cv_sensor_code/files/requirements_cv.txt").read_text()
        self.assertEqual(mri, cv)
        self.assertEqual(
            mri,
            "python-dotenv>=1.0.0,<2\n"
            "requests>=2.31.0,<3\n"
            "w1thermsensor>=2.0.0,<3\n",
        )

    def test_audit_records_the_default_systemd_target(self):
        self.assertIn('"default_target": sh("systemctl get-default 2>/dev/null")', fleet_ops.FACTS_SCRIPT)

    def test_audit_records_actionable_wifi_radio_evidence(self):
        for field in (
            "bssid",
            "frequency_mhz",
            "rx_bitrate",
            "power_save",
            "adapter_kind",
        ):
            self.assertIn(f'"{field}"', fleet_ops.FACTS_SCRIPT)
        self.assertIn("get power_save", fleet_ops.FACTS_SCRIPT)

    def test_audit_records_rsyslog_pilot_boundary_without_log_contents(self):
        self.assertIn('"rsyslog_ram_pilot": {', fleet_ops.FACTS_SCRIPT)
        self.assertIn("/var/lib/coolmri-fleet/rsyslog-ram-pilot.json", fleet_ops.FACTS_SCRIPT)
        self.assertIn('"applied_epoch": rsyslog_pilot_applied_epoch', fleet_ops.FACTS_SCRIPT)
        self.assertNotIn("rsyslog-ram-pilot-before.json", fleet_ops.FACTS_SCRIPT)

    def test_new_audit_timestamps_include_local_utc_offset(self):
        self.assertIn(
            'dt.datetime.now().astimezone().isoformat(timespec="seconds")',
            Path(fleet_ops.__file__).read_text(encoding="utf-8"),
        )

    def test_audit_records_boot_source_and_nvme_reset_evidence(self):
        for field in (
            "firmware_configured_source",
            "firmware_configured_fstype",
            "firmware_configured_mount_options",
            "firmware_source_read_only",
            "firmware_source_write_protected_at_boot",
            "nvme_controller_resets_since_boot",
            "nvme_power_saving_warning",
        ):
            self.assertIn(f'"{field}"', fleet_ops.FACTS_SCRIPT)
        self.assertIn("controller is down; will reset", fleet_ops.FACTS_SCRIPT)
        self.assertIn("findmnt --fstab --evaluate", fleet_ops.FACTS_SCRIPT)

    def test_audit_collects_privilege_wrapper_checksum_and_mode(self):
        self.assertIn('"sudo_compat": {', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"executable": os.access(', fleet_ops.FACTS_SCRIPT)
        self.assertIn('sudo-rs-ansible-compat', fleet_ops.FACTS_SCRIPT)

    def test_audit_distinguishes_listed_from_eligible_packages(self):
        self.assertIn('"package_maintenance": {', fleet_ops.FACTS_SCRIPT)
        self.assertIn("apt-get -s -o Debug::NoLocking=true upgrade --with-new-pkgs", fleet_ops.FACTS_SCRIPT)
        self.assertIn('"eligible_count": len(eligible_names)', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"deferred_count": len(deferred_names)', fleet_ops.FACTS_SCRIPT)

    def test_audit_records_safe_update_policy_without_config_contents(self):
        self.assertIn('"update_policy": {', fleet_ops.FACTS_SCRIPT)
        for field in (
            "unattended_upgrades_version",
            "apt_daily_timer",
            "apt_daily_upgrade_timer",
            "update_package_lists",
            "unattended_upgrade",
            "automatic_reboot",
            "held_packages",
        ):
            self.assertIn(f'"{field}"', fleet_ops.FACTS_SCRIPT)
        self.assertIn("apt-mark showhold", fleet_ops.FACTS_SCRIPT)
        self.assertNotIn('"apt_config_dump"', fleet_ops.FACTS_SCRIPT)

    def test_camera_audit_recognizes_typed_environment_helpers(self):
        self.assertIn(
            'r"env_(?:bool|int)\\(\\s*[\'\\\"]([A-Z0-9_]+)[\'\\\"]"',
            fleet_ops.FACTS_SCRIPT,
        )

    def test_audit_collects_profile_runtime_policy_keys_without_secrets(self):
        for key in (
            "ENABLE_DUAL_STREAMING",
            "INVALID_SENSOR_RESTART_THRESHOLD",
            "SENSOR_DISCOVERY_TIMEOUT_SEC",
            "SENSOR_DISCOVERY_INTERVAL_SEC",
            "SENSOR_RESCAN_TIMEOUT_SEC",
            "SENSOR_RESCAN_INTERVAL_SEC",
            "REQUEST_TIMEOUT_SEC",
        ):
            self.assertIn(f'"{key}"', fleet_ops.FACTS_SCRIPT)
        for secret in ("PASSWORD", "TOKEN", "SECRET", "API_KEY"):
            self.assertNotIn(f'"{secret}"', fleet_ops.FACTS_SCRIPT)


class AuditSudoEvidenceTests(unittest.TestCase):
    def host(self):
        return {
            "inventory_name": "agcmr3",
            "ansible_host": "100.64.0.1",
            "ansible_user": "agcmr3",
        }

    def args(self):
        return SimpleNamespace(connect_timeout=3, command_timeout=25, no_bootstrap=True)

    def test_unattended_audit_marks_general_sudo_as_not_checked(self):
        with (
            mock.patch.object(fleet_ops, "port_open", return_value=True),
            mock.patch.object(fleet_ops, "try_key_auth", return_value=True),
            mock.patch.object(fleet_ops, "collect_facts", return_value=({"hostname": "agcmr3"}, "")),
        ):
            result = fleet_ops.audit_host(self.host(), None, self.args())
        self.assertIsNone(result["sudo_ok"])
        self.assertEqual(result["sudo_check"], "not_checked_no_credential")

    def test_read_only_preflight_does_not_imply_a_missing_credential(self):
        args = self.args()
        args.action = "preflight"
        with (
            mock.patch.object(fleet_ops, "port_open", return_value=True),
            mock.patch.object(fleet_ops, "try_key_auth", return_value=True),
            mock.patch.object(fleet_ops, "collect_facts", return_value=({"hostname": "agcmr3"}, "")),
        ):
            result = fleet_ops.audit_host(self.host(), None, args)
        self.assertIsNone(result["sudo_ok"])
        self.assertEqual(result["sudo_check"], "not_checked_read_only")

    def test_credentialed_audit_records_verified_sudo(self):
        with (
            mock.patch.object(fleet_ops, "port_open", return_value=True),
            mock.patch.object(fleet_ops, "try_key_auth", return_value=True),
            mock.patch.object(fleet_ops, "collect_facts", return_value=({"hostname": "agcmr3"}, "")),
            mock.patch.object(fleet_ops, "check_sudo", return_value=True),
        ):
            result = fleet_ops.audit_host(self.host(), "secret", self.args())
        self.assertTrue(result["sudo_ok"])
        self.assertEqual(result["sudo_check"], "verified")


class KeyAuthenticationRetryTests(unittest.TestCase):
    def test_transient_key_auth_failure_is_retried(self):
        failed = subprocess.CompletedProcess(["ssh"], 255, "", "connection reset")
        passed = subprocess.CompletedProcess(["ssh"], 0, "", "")
        host = {
            "ansible_host": "100.64.0.10",
            "ansible_ssh_private_key_file": "/tmp/test-key",
        }
        with (
            mock.patch.object(fleet_ops, "run", side_effect=[failed, passed]) as run,
            mock.patch.object(fleet_ops.time, "sleep") as sleep,
        ):
            self.assertTrue(fleet_ops.try_key_auth(host, "pi", 3))
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_parallel_audit_retries_transient_ssh_failure_serially(self):
        host = {
            "inventory_name": "muncymr",
            "mri_label": "Muncy MR",
            "ansible_host": "100.64.0.10",
            "ansible_user": "muncymr",
        }
        failed = {
            "inventory_name": "muncymr",
            "label": "Muncy MR",
            "host": "100.64.0.10",
            "primary_user": "muncymr",
            "bootstrapped_key": False,
            "sudo_check": "not_checked_no_credential",
            "status": "ssh_failed",
        }
        passed = {
            **failed,
            "key_auth": True,
            "login_user": "muncymr",
            "status": "ok",
            "facts": {"hostname": "muncymr"},
        }
        args = SimpleNamespace(connect_timeout=3, command_timeout=60, no_bootstrap=True)
        with (
            mock.patch.object(fleet_ops, "audit_host", side_effect=[failed, passed]) as audit,
            mock.patch.object(fleet_ops, "load_tailscale_peer_status", return_value={}),
        ):
            results = fleet_ops.audit_many([host], None, args)
        self.assertEqual(audit.call_count, 2)
        self.assertEqual(results[0]["status"], "ok")
        self.assertTrue(results[0]["serial_retry_performed"])

    def test_key_auth_stops_after_bounded_attempts(self):
        failed = subprocess.CompletedProcess(["ssh"], 255, "", "denied")
        host = {"ansible_host": "100.64.0.10"}
        with (
            mock.patch.object(fleet_ops, "run", return_value=failed) as run,
            mock.patch.object(fleet_ops.time, "sleep") as sleep,
        ):
            self.assertFalse(fleet_ops.try_key_auth(host, "pi", 3, attempts=2))
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(0.5)


class TailscalePeerStatusTests(unittest.TestCase):
    def test_peer_state_is_keyed_by_every_peer_ip(self):
        payload = {
            "Peer": {
                "node": {
                    "HostName": "vwm1-aera",
                    "DNSName": "vwm1-aera.example.ts.net.",
                    "TailscaleIPs": ["100.93.88.121", "fd7a::1"],
                    "Online": False,
                    "LastSeen": "2026-07-15T23:08:10.1Z",
                    "LastHandshake": "0001-01-01T00:00:00Z",
                    "OS": "linux",
                }
            }
        }
        completed = subprocess.CompletedProcess(
            ["tailscale", "status", "--json"], 0, json.dumps(payload), ""
        )
        with mock.patch.object(fleet_ops, "run", return_value=completed):
            peers = fleet_ops.load_tailscale_peer_status()
        self.assertEqual(peers["100.93.88.121"]["hostname"], "vwm1-aera")
        self.assertFalse(peers["fd7a::1"]["online"])


class MutationSafetyGateTests(unittest.TestCase):
    def setUp(self):
        self.host = {"inventory_name": "agcmr3"}
        self.audit = {
            "profile": "mri",
            "facts": {
                "services": {"mri_sensor": {"active": "active"}},
                "one_wire": {"count": 5},
                "throttled_flags": 0,
                "disk": {"free_bytes": 10_000_000_000},
            },
        }
        self.coverage = {
            "checked_at": dt.datetime.now().astimezone().isoformat(),
            "repositories": ["agcmr3"],
            "configured_targets": [{"repository": "agcmr3"}],
            "repository_status": [
                {"repository": "agcmr3", "activity_recent": True}
            ],
            "batch": {"result": "success"},
        }

    def test_healthy_backed_host_passes(self):
        gates = fleet_ops.mutation_safety_gates(
            self.host, self.audit, self.coverage
        )
        self.assertTrue(gates["backup"]["ok"])
        self.assertTrue(gates["health"]["ok"])

    def test_newly_onboarded_repository_mappings_are_exact(self):
        expected = {
            "agcmr2": "agcmr2",
            "gcmcmr2": "gcmcmr2",
            "vwm2": "vwm2",
            "vwm3": "vwm3",
            "glh": "glh",
        }
        for inventory_name, repository in expected.items():
            with self.subTest(inventory_name=inventory_name):
                self.assertEqual(
                    fleet_ops.BACKUP_REPOSITORIES[inventory_name], repository
                )

    def test_host_without_repository_mapping_is_blocked(self):
        host = {"inventory_name": "unknown-pi"}
        gates = fleet_ops.mutation_safety_gates(host, self.audit, self.coverage)
        self.assertFalse(gates["backup"]["ok"])

    def test_stale_coverage_report_is_blocked(self):
        coverage = copy.deepcopy(self.coverage)
        coverage["checked_at"] = "2026-07-01T00:00:00-04:00"
        gates = fleet_ops.mutation_safety_gates(self.host, self.audit, coverage)
        self.assertFalse(gates["backup"]["coverage_report_recent"])
        self.assertFalse(gates["backup"]["ok"])

    def test_recent_decrypt_restore_can_satisfy_host_gate_during_incomplete_batch(self):
        coverage = copy.deepcopy(self.coverage)
        coverage["batch"] = {"result": "incomplete"}
        coverage["restore_tests"] = [{
            "repository": "agcmr3",
            "status": "success",
            "recent": True,
        }]
        gates = fleet_ops.mutation_safety_gates(self.host, self.audit, coverage)
        self.assertTrue(gates["backup"]["ok"])
        self.assertFalse(gates["backup"]["batch_success"])
        self.assertTrue(gates["backup"]["restore_recent"])
        self.assertEqual(gates["backup"]["evidence_mode"], "recent_decrypt_restore")

    def test_failed_restore_does_not_bypass_incomplete_batch(self):
        coverage = copy.deepcopy(self.coverage)
        coverage["batch"] = {"result": "incomplete"}
        coverage["restore_tests"] = [{
            "repository": "agcmr3",
            "status": "failed",
            "recent": True,
        }]
        gates = fleet_ops.mutation_safety_gates(self.host, self.audit, coverage)
        self.assertFalse(gates["backup"]["ok"])
        self.assertEqual(gates["backup"]["evidence_mode"], "insufficient")

    def test_missing_probes_blocks_health_gate(self):
        audit = copy.deepcopy(self.audit)
        audit["facts"]["one_wire"]["count"] = 3
        gates = fleet_ops.mutation_safety_gates(self.host, audit, self.coverage)
        self.assertFalse(gates["health"]["ok"])
        self.assertEqual(gates["health"]["blockers"], ["only 3 probes; require 4"])

    def test_configured_cv_mapping_requires_all_five_ep_probes(self):
        audit = copy.deepcopy(self.audit)
        audit["profile"] = "cv"
        audit["facts"]["services"] = {"cv_sensor": {"active": "active"}}
        audit["facts"]["sensor_config"] = {
            "values": {f"SENSOR_{index}_ID": f"28-{index}" for index in range(1, 6)}
        }
        audit["facts"]["one_wire"] = {
            "count": 3,
            "sensor_ids": ["28-1", "28-2", "28-3"],
        }
        gates = fleet_ops.mutation_safety_gates(self.host, audit, self.coverage)
        self.assertFalse(gates["health"]["ok"])
        self.assertEqual(gates["health"]["expected_probe_count"], 5)
        self.assertEqual(gates["health"]["missing_probe_ids"], ["28-4", "28-5"])
        self.assertIn("configured probe mapping incomplete", gates["health"]["blockers"][0])

    def test_readonly_boot_partition_blocks_mutation(self):
        audit = copy.deepcopy(self.audit)
        audit["facts"]["boot_management"] = {
            "firmware_mount_options": "ro,relatime,errors=remount-ro"
        }
        gates = fleet_ops.mutation_safety_gates(self.host, audit, self.coverage)
        self.assertFalse(gates["health"]["boot_firmware_writable"])
        self.assertFalse(gates["health"]["ok"])
        self.assertIn("boot firmware filesystem is read-only", gates["health"]["blockers"])

    def test_active_package_manager_blocks_mutation(self):
        audit = copy.deepcopy(self.audit)
        audit["facts"]["package_manager"] = {"busy": True}
        gates = fleet_ops.mutation_safety_gates(self.host, audit, self.coverage)
        self.assertTrue(gates["health"]["package_manager_busy"])
        self.assertFalse(gates["health"]["ok"])

    def test_marginal_remote_wifi_is_reported_but_does_not_block_mutation(self):
        host = {"inventory_name": "jsmr"}
        audit = copy.deepcopy(self.audit)
        audit["facts"]["route"] = "default via 10.0.0.1 dev wlan0 metric 600"
        audit["facts"]["wifi"] = [{"interface": "wlan0", "signal_dbm": -69}]
        gates = fleet_ops.mutation_safety_gates(host, audit, self.coverage)
        self.assertTrue(gates["health"]["ok"])
        self.assertEqual(gates["health"]["routed_wifi_signal_dbm"], -69)
        self.assertFalse(any("Wi-Fi" in reason for reason in gates["health"]["blockers"]))

    def test_marginal_nearby_wifi_remains_pilot_eligible(self):
        host = {"inventory_name": "gmcep3"}
        audit = copy.deepcopy(self.audit)
        audit["facts"]["route"] = "default via 10.0.0.1 dev wlan0 metric 600"
        audit["facts"]["wifi"] = [{"interface": "wlan0", "signal_dbm": -69}]
        gates = fleet_ops.mutation_safety_gates(host, audit, self.coverage)
        self.assertTrue(gates["health"]["ok"])
        self.assertTrue(gates["health"]["nearby_pilot"])

    def test_routed_wifi_ignores_weak_secondary_adapter(self):
        facts = {
            "route": "default via 10.0.0.1 dev wlxusb metric 50",
            "wifi": [
                {"interface": "wlan0", "signal_dbm": -81},
                {"interface": "wlxusb", "signal_dbm": -42},
            ],
        }
        self.assertEqual(fleet_ops.routed_wifi_signal(facts), -42)


class AuditCollectorTests(unittest.TestCase):
    def test_camera_log_size_uses_resolved_target(self):
        self.assertIn(
            "camera_log_bytes = directory_bytes(camera_log_target)",
            fleet_ops.FACTS_SCRIPT,
        )

    def test_fact_collection_timeout_becomes_a_host_result(self):
        host = {
            "ansible_host": "192.0.2.1",
            "ansible_user": "pi",
            "ansible_ssh_private_key_file": "/tmp/key",
        }
        with mock.patch.object(
            fleet_ops,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=45),
        ):
            facts, error = fleet_ops.collect_facts(host, "pi", 3, 45)
        self.assertIsNone(facts)
        self.assertEqual(error, "Fact collection timed out after 45 seconds")

    def test_package_cache_facts_match_exact_candidate_versions(self):
        self.assertIn('"package_cache": {', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"cached_candidate_count": len(cached_candidate_names)', fleet_ops.FACTS_SCRIPT)
        self.assertIn('"missing_candidate_names": missing_cached_candidate_names', fleet_ops.FACTS_SCRIPT)
        self.assertIn('archive_path.name[:-4].rsplit("_", 2)', fleet_ops.FACTS_SCRIPT)
        self.assertIn('unquote(fields[1])', fleet_ops.FACTS_SCRIPT)

    def test_reboot_verifier_requires_a_stability_window(self):
        self.assertEqual(fleet_ops.REBOOT_STABILITY_SECONDS, 30)


class PackageReportTests(unittest.TestCase):
    def test_package_counts_keep_deferred_packages_non_actionable(self):
        facts = {
            "packages_upgradable": "2",
            "package_maintenance": {
                "listed_count": 2,
                "eligible_count": 0,
                "deferred_count": 2,
            },
        }
        self.assertEqual(
            fleet_ops.package_maintenance_counts(facts),
            {"listed": 2, "eligible": 0, "deferred": 2},
        )

    def test_markdown_report_labels_eligible_listed_and_deferred(self):
        result = {
            "label": "GMC EP3",
            "inventory_name": "gmcep3",
            "host": "100.75.242.28",
            "primary_user": "gmcep3",
            "login_user": "gmcep3",
            "profile": "cv",
            "status": "ok",
            "facts": {
                "services": {"cv_sensor": {"active": "active"}},
                "one_wire": {"count": 3},
                "packages_upgradable": "2",
                "package_maintenance": {
                    "listed_count": 2,
                    "eligible_count": 0,
                    "deferred_count": 2,
                },
                "package_cache": {
                    "assessed": True,
                    "complete": True,
                    "candidate_count": 0,
                    "cached_candidate_count": 0,
                    "missing_candidate_names": [],
                },
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(
                report_dir=directory,
                action="audit",
                inventory="/tmp/inventory.yml",
            )
            json_path, markdown_path = fleet_ops.write_report([result], args)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
        self.assertEqual(
            payload["package_maintenance"],
            {"listed": 2, "eligible": 0, "deferred": 2},
        )
        self.assertIn("0 eligible / 2 listed / 2 deferred", markdown)
        self.assertEqual(payload["package_cache"]["complete_hosts"], 1)
        self.assertIn("0/0 exact candidate versions; 1/1 assessed hosts complete", markdown)
        self.assertNotIn("| Updates |", markdown)

    def test_cache_summary_exposes_incomplete_exact_versions(self):
        results = [
            {
                "inventory_name": "jsmr",
                "status": "ok",
                "facts": {"package_cache": {
                    "assessed": True,
                    "complete": False,
                    "candidate_count": 50,
                    "cached_candidate_count": 49,
                    "missing_candidate_names": ["linux-firmware"],
                }},
            },
            {
                "inventory_name": "agcmr3",
                "status": "ok",
                "facts": {"package_cache": {
                    "assessed": True,
                    "complete": True,
                    "candidate_count": 0,
                    "cached_candidate_count": 0,
                    "missing_candidate_names": [],
                }},
            },
            {"inventory_name": "phc", "status": "offline_or_unreachable"},
        ]
        summary = fleet_ops.summarize_package_cache(results)
        self.assertEqual(summary["assessed_hosts"], 2)
        self.assertEqual(summary["complete_hosts"], 1)
        self.assertEqual(summary["candidate_versions"], 50)
        self.assertEqual(summary["cached_candidate_versions"], 49)
        self.assertEqual(summary["incomplete_hosts"][0]["inventory_name"], "jsmr")
        self.assertEqual(
            summary["incomplete_hosts"][0]["missing_candidate_names"],
            ["linux-firmware"],
        )


class RecoveryVerificationTests(unittest.TestCase):
    def audit(self, *, profile="mri", uptime=1000, probes=5, app_hash="approved"):
        service_key = "cv_sensor" if profile == "cv" else "mri_sensor"
        return {
            "status": "ok",
            "profile": profile,
            "facts": {
                "services": {
                    service_key: {"active": "active"},
                    "cron": {"active": "active"},
                    "tailscaled": {"active": "active"},
                },
                "one_wire": {"count": probes},
                "throttled_flags": 0,
                "application": {"normalized_sha256": app_hash},
                "uptime_seconds": uptime,
                "packages_upgradable": "0",
                "reboot_required": False,
                "kernel": "Linux test",
                "operational_stack": {
                    "architecture": "arm64",
                    "ntp_synchronized": True,
                    "base_packages": {
                        name: "1.0"
                        for name in ("python3", "python3-venv", "python3-pip", "git", "cron", "rsync")
                    },
                },
            },
        }

    def test_update_recovery_requires_unchanged_application(self):
        pre = self.audit()
        post = self.audit(uptime=1100)
        state = fleet_ops.local_recovery_state(pre, post, "update")
        self.assertTrue(state["ok"])
        self.assertFalse(state["reboot_requested"])
        self.assertFalse(state["reboot_observed"])
        self.assertTrue(state["reboot_requirement_satisfied"])
        post["facts"]["application"]["normalized_sha256"] = "unexpected"
        self.assertFalse(fleet_ops.local_recovery_state(pre, post, "update")["ok"])

    def test_update_recovery_requires_exact_configured_probe_ids(self):
        pre = self.audit(profile="cv", probes=5)
        pre["facts"]["sensor_config"] = {
            "values": {f"SENSOR_{index}_ID": f"28-{index}" for index in range(1, 6)}
        }
        pre["facts"]["one_wire"]["sensor_ids"] = [f"28-{index}" for index in range(1, 6)]
        post = copy.deepcopy(pre)
        post["facts"]["uptime_seconds"] = 1100
        post["facts"]["one_wire"] = {
            "count": 3,
            "sensor_ids": ["28-1", "28-2", "28-3"],
        }
        state = fleet_ops.local_recovery_state(pre, post, "update")
        self.assertFalse(state["ok"])
        self.assertFalse(state["probe_mapping_complete"])
        self.assertEqual(state["missing_probe_ids"], ["28-4", "28-5"])

    def test_reboot_recovery_requires_new_boot(self):
        pre = self.audit(uptime=50_000)
        post = self.audit(uptime=90)
        state = fleet_ops.local_recovery_state(pre, post, "reboot")
        self.assertTrue(state["reboot_requested"])
        self.assertTrue(state["reboot_observed"])
        self.assertTrue(state["reboot_requirement_satisfied"])
        self.assertTrue(state["ok"])
        not_rebooted = self.audit(uptime=50_100)
        self.assertFalse(
            fleet_ops.local_recovery_state(pre, not_rebooted, "reboot")["ok"]
        )

    def test_reboot_verification_observes_stable_recovery_window(self):
        pre = self.audit(uptime=50_000)
        post = self.audit(uptime=100)
        clock = [0.0]

        def advance(seconds):
            clock[0] += seconds

        args = SimpleNamespace(action="reboot", post_check_timeout=90)
        telemetry = {"current": True, "last_updated": 200}
        with (
            mock.patch.object(fleet_ops, "audit_host", return_value=post) as audited,
            mock.patch.object(fleet_ops, "fetch_telemetry", return_value=telemetry),
            mock.patch.object(fleet_ops.time, "monotonic", side_effect=lambda: clock[0]),
            mock.patch.object(fleet_ops.time, "sleep", side_effect=advance),
        ):
            result = fleet_ops.verify_mutation(
                {"inventory_name": "test"},
                pre,
                {"last_updated": 100},
                "password",
                args,
            )

        self.assertTrue(result["ok"])
        self.assertTrue(result["stability_verified"])
        self.assertEqual(result["stability_required_seconds"], 30)
        self.assertGreaterEqual(audited.call_count, 7)

    def test_pending_piboot_candidate_requires_new_kernel(self):
        pre = self.audit(uptime=50_000)
        pre["facts"]["boot_management"] = {
            "new_state": "unknown",
            "current_kernel_sha256": "old",
            "new_kernel_sha256": "new",
        }
        post = self.audit(uptime=90)
        post["facts"]["boot_management"] = {
            "current_state": "good",
            "new_state": "",
            "old_state": "good",
        }
        state = fleet_ops.local_recovery_state(pre, post, "reboot")
        self.assertTrue(state["reboot_observed"])
        self.assertTrue(state["boot_candidate_pending"])
        self.assertFalse(state["kernel_advanced"])
        self.assertFalse(state["ok"])
        post["facts"]["kernel"] = "Linux newer"
        self.assertTrue(fleet_ops.local_recovery_state(pre, post, "reboot")["ok"])

    def test_same_kernel_initrd_candidate_can_promote(self):
        pre = self.audit(uptime=50_000)
        pre["facts"]["boot_management"] = {
            "new_state": "unknown",
            "current_kernel_sha256": "same",
            "new_kernel_sha256": "same",
        }
        post = self.audit(uptime=90)
        post["facts"]["boot_management"] = {
            "current_state": "good",
            "new_state": "",
            "old_state": "good",
        }
        state = fleet_ops.local_recovery_state(pre, post, "reboot")
        self.assertFalse(state["candidate_kernel_differs"])
        self.assertTrue(state["candidate_promoted"])
        self.assertTrue(state["boot_candidate_verified"])
        self.assertTrue(state["ok"])

    def test_cv_recovery_accepts_three_expected_probes(self):
        pre = self.audit(profile="cv", probes=3)
        post = self.audit(profile="cv", probes=3, uptime=1100)
        self.assertTrue(fleet_ops.local_recovery_state(pre, post, "update")["ok"])

    def test_baseline_recovery_requires_all_core_packages(self):
        pre = self.audit()
        post = self.audit(uptime=1100)
        self.assertTrue(fleet_ops.local_recovery_state(pre, post, "baseline")["ok"])
        post["facts"]["operational_stack"]["base_packages"]["python3-pip"] = None
        state = fleet_ops.local_recovery_state(pre, post, "baseline")
        self.assertFalse(state["baseline_verified"])
        self.assertFalse(state["ok"])

    def test_download_recovery_requires_exact_current_cache(self):
        pre = self.audit()
        post = self.audit(uptime=1100)
        post["facts"]["package_cache"] = {
            "assessed": True,
            "complete": False,
            "candidate_count": 2,
            "cached_candidate_count": 1,
            "missing_candidate_names": ["linux-image-raspi"],
        }
        state = fleet_ops.local_recovery_state(pre, post, "download")
        self.assertFalse(state["ok"])
        self.assertFalse(state["download_cache_verified"])
        post["facts"]["package_cache"].update({
            "complete": True,
            "cached_candidate_count": 2,
            "missing_candidate_names": [],
        })
        state = fleet_ops.local_recovery_state(pre, post, "download")
        self.assertTrue(state["ok"])
        self.assertTrue(state["download_cache_verified"])

    def test_site_id_falls_back_to_sensor_configuration(self):
        audited = {
            "facts": {"sensor_config": {"values": {"SITE_NAME": "GBHAera"}}}
        }
        self.assertEqual(fleet_ops.telemetry_site_id(audited), "GBHAera")

    def test_preflight_summary_uses_gate_status(self):
        summary = fleet_ops.summarize(
            [{"status": "ok", "preflight_status": "ready"},
             {"status": "ok", "preflight_status": "blocked"}]
        )
        self.assertEqual(summary, {"ready": 1, "blocked": 1})


if __name__ == "__main__":
    unittest.main()
