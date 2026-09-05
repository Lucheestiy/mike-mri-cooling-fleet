from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "playbooks" / "rsyslog_ram_pilot.yml"
ROLLBACK = ROOT / "playbooks" / "rsyslog_ram_rollback.yml"
BACKFILL = ROOT / "playbooks" / "rsyslog_ram_evidence_backfill.yml"


def test_rsyslog_pilot_is_one_host_backed_and_profile_gated() -> None:
    play = yaml.safe_load(PILOT.read_text(encoding="utf-8"))[0]
    text = PILOT.read_text(encoding="utf-8")
    assert play["hosts"] == "gmcir3:agcmr1"
    assert "ansible_play_hosts_all | length == 1" in text
    assert "rsyslog_pilot_backup_status.activity_recent" in text
    for evidence in (
        "Require active bounded volatile journald sink",
        "Require active non-root profile service",
        "Require exact probes and zero throttle flags",
        "Wait for mapped profile telemetry to advance",
        "Restore exact prior rsyslog state",
    ):
        assert evidence in text


def test_rsyslog_rollback_is_exact_and_one_host_only() -> None:
    play = yaml.safe_load(ROLLBACK.read_text(encoding="utf-8"))[0]
    text = ROLLBACK.read_text(encoding="utf-8")
    assert play["hosts"] == "gmcir3:agcmr1"
    assert "ansible_play_hosts_all | length == 1" in text
    assert "Read exact pre-pilot state" in text
    assert "Restore exact prior rsyslog state" in text


def test_rsyslog_pilot_has_exact_mri_and_cv_profile_gates() -> None:
    play = yaml.safe_load(PILOT.read_text(encoding="utf-8"))[0]
    profiles = play["vars"]["rsyslog_pilot_profiles"]
    assert set(profiles) == {"gmcir3", "agcmr1"}
    assert profiles["gmcir3"]["service"] == "cv-room-sensor.service"
    assert profiles["gmcir3"]["expected_probes"] == 4
    assert profiles["agcmr1"]["service"] == "mri-sensor.service"
    assert profiles["agcmr1"]["expected_probes"] == 5
    text = PILOT.read_text(encoding="utf-8")
    assert "Require writable boot storage, safe nearby Wi-Fi, and idle camera" in text
    assert "test \"$signal\" -gt -75" in text


def test_public_evidence_never_contains_root_only_rollback_state() -> None:
    pilot = PILOT.read_text(encoding="utf-8")
    rollback = ROLLBACK.read_text(encoding="utf-8")
    backfill = BACKFILL.read_text(encoding="utf-8")
    for text in (pilot, backfill):
        assert "'kind': 'rsyslog_ram_pilot'" in text
        assert "'applied_epoch':" in text
        assert "rsyslog_pilot_evidence_path" in text
    assert "Remove sanitized active-pilot marker after verified rollback" in rollback
    public_content = backfill.split("Publish original pilot boundary without rollback content", 1)[1]
    assert "rsyslog_pilot_state" not in public_content
