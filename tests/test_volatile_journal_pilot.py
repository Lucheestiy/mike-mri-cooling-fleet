from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks/volatile_journal_pilot.yml"
ROLLBACK = ROOT / "playbooks/volatile_journal_rollback.yml"


def test_ep1and2_has_exact_cv_journal_contract() -> None:
    play = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]
    variables = play["vars"]
    assert "gmcep1and2" in play["hosts"]
    assert variables["telemetry_site_ids"]["gmcep1and2"] == "EP1and2"
    assert variables["expected_probe_counts"]["gmcep1and2"] == 5
    assert variables["telemetry_required_fields"]["gmcep1and2"] == [
        "room_temp", "helium_in", "helium_out", "primary_in", "primary_out"
    ]
    assert variables["sensor_helper_paths"]["gmcep1and2"].endswith("cv-sensor-service")


def test_journal_transaction_gates_application_identity_and_system_health() -> None:
    text = PLAYBOOK.read_text(encoding="utf-8")
    for evidence in (
        "Require package manager to be idle",
        "Require approved application before journal change",
        "Require non-root site-account sensor service",
        "Require zero current or historical throttle flags",
        "Prove sensor application checksum remained unchanged",
        "Prove every required mapped reading remains numeric",
    ):
        assert evidence in text


def test_profile_aware_rollback_is_one_host_and_self_restoring() -> None:
    play = yaml.safe_load(ROLLBACK.read_text(encoding="utf-8"))[0]
    assert play["hosts"] == "agcmr1:agcmr3:gmcir3:gmcep1and2:gmcep3"
    text = ROLLBACK.read_text(encoding="utf-8")
    assert "ansible_play_hosts_all | length == 1" in text
    assert "Remove only the fleet journald policy" in text
    assert "Require exact probe recovery" in text
    assert "Wait for profile telemetry to advance" in text
    assert "Restore volatile policy after failed rollback verification" in text
