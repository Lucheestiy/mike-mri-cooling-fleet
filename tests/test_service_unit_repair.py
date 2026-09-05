from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks/gr_sensor_unit_header_repair.yml"


def text() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def play() -> dict:
    return yaml.safe_load(text())[0]


def test_unit_repair_is_one_host_confirmed_and_does_not_restart() -> None:
    assert play()["hosts"] == "{{ mri_unit_repair_hosts | default('gr') }}"
    source = text()
    assert "mri_unit_repair_confirm" in source
    assert play()["vars"]["mri_unit_repair_allowed_hosts"] == ["gr", "glh"]
    assert "ansible_play_hosts_all | length == 1" in source
    assert "ansible_play_batch | length == 1" in source
    assert "state: restarted" not in source
    assert "reboot" not in source.lower().replace("does not\n          restart or reboot", "")


def test_gr_unit_repair_removes_only_known_line_and_validates_candidate() -> None:
    source = text()
    assert "regexp: '^Ini, TOML$'" in source
    assert "argv: [systemd-analyze, verify, \"{{ mri_unit_path }}\"]" in source
    assert "mri_service_after.stdout == mri_service_before.stdout" in source
    assert "mri_app_after.stat.checksum == mri_app_before.stat.checksum" in source


def test_gr_unit_repair_requires_backup_probes_service_and_telemetry() -> None:
    source = text()
    assert "mri_backup_status.activity_recent" in source
    assert "mri_restore_status.recent" in source
    assert "mri_probes_before.matched | int == 5" in source
    assert "mri_helper_path" in source
    assert "mri_telemetry_after_response" in source
    assert "Restore exact prior unit" in source
