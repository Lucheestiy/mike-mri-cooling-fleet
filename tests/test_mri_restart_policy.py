from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks/mri_restart_policy_pilot.yml"
DROPIN = ROOT / "roles/temp_sensors/files/mri-sensor-restart-policy.conf"


def source() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def test_restart_policy_matches_canonical_mri_intent() -> None:
    assert DROPIN.read_text(encoding="utf-8") == (
        "[Unit]\nStartLimitIntervalSec=0\n\n"
        "[Service]\nRestart=always\nRestartSec=15s\n"
    )


def test_pilot_is_nearby_one_host_and_never_restarts() -> None:
    play = yaml.safe_load(source())[0]
    assert "mri_restart_policy_hosts" in play["hosts"]
    text = source()
    assert "mri_restart_policy_confirm" in text
    variables = play["vars"]
    assert {"agcmr1", "agcmr2", "agcmr3", "gbh", "jsmr", "gr", "glh"} <= set(variables["mri_site_ids"])
    assert set(variables["mri_site_ids"]) == set(variables["mri_backup_repositories"])
    assert variables["mri_expected_probe_counts"] == {"agcmr2": 4}
    assert variables["mri_initial_restart_policies"]["agcmr2"] == {
        "restart": "on-failure",
        "restart_usec": "5s",
        "start_limit_interval_usec": "10s",
        "start_limit_burst": "5",
    }
    assert "inventory_hostname in mri_site_ids" in text
    assert "ansible_play_hosts_all | length == 1" in text
    assert "ansible_play_batch | length == 1" in text
    assert "state: restarted" not in text
    assert "MainPID == mri_service_before_map.MainPID" in text
    assert "ActiveEnterTimestampMonotonic == mri_service_before_map.ActiveEnterTimestampMonotonic" in text
    assert "mri_service_after_map.ExecStart" in text


def test_pilot_has_backup_application_probe_telemetry_and_rollback_gates() -> None:
    text = source()
    for marker in (
        "mri_backup_status.activity_recent",
        "mri_restore_status.recent",
        "Report marginal remote Wi-Fi as an advisory",
        "Report unavailable Wi-Fi signal tooling as an advisory",
        "command -v iw",
        "mri_restart_wifi_signal.stdout | int <= -67",
        "Require writable root and boot filesystems",
        "Require idle package management",
        "throttled=throttled=0x0",
        "mri_target_sha256",
        "Compute behavior-preserving normalized application checksum",
        "mri_app_normalized_before.stdout == mri_target_sha256",
        "mri_probes_before.matched | int == mri_expected_probe_count | int",
        "mri_service_before_map.Restart == mri_initial_restart_policy.restart",
        "mri_telemetry_after_response",
        "Restore prior restart policy when it existed",
        "Remove newly added restart policy when none existed",
    ):
        assert marker in text


def test_normalized_hash_matches_audit_line_ending_and_trailing_space_rules() -> None:
    play = yaml.safe_load(source())[0]
    code = play["vars"]["mri_normalized_hash_code"]
    assert 'replace(b"\\r\\n", b"\\n").replace(b"\\r", b"\\n")' in code
    assert 'b"\\n".join(line.rstrip()' in code
    assert "mri_app_after.stat.checksum == mri_app_before.stat.checksum" in source()
