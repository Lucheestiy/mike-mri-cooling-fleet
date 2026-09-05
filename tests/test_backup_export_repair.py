from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "backup_export_repair.yml"


def test_export_repair_is_hard_limited_and_serial():
    play = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]
    assert play["hosts"] == "gbh:muncymr"
    assert play["serial"] == 1
    assert play["max_fail_percentage"] == 0
    assert play["vars"]["backup_export_repair_allowed"] == ["gbh", "muncymr"]


def test_export_repair_preserves_helper_and_sensor_evidence():
    text = PLAYBOOK.read_text(encoding="utf-8")
    for required in (
        "/run/coolmri-pi-backup-export.before",
        "roles/backup_export/files/pi-backup-export",
        "backup-export-ready user=",
        "backup_export_repair_app_after.stat.checksum == backup_export_repair_app_before.stat.checksum",
        "backup_export_repair_probes_after.matched",
        "systemctl, is-active, mri-sensor.service",
        "Wait for production telemetry to advance",
        "Restore legacy helper after failed verification",
    ):
        assert required in text
