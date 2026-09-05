from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks/mri_restart_recovery_test.yml"


def source() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def test_recovery_verifier_is_explicitly_one_nearby_host() -> None:
    play = yaml.safe_load(source())[0]
    assert play["hosts"] == "agcmr1"
    text = source()
    assert "mri_restart_recovery_confirm" in text
    assert "ansible_play_batch | length == 1" in text
    assert "when: not ansible_check_mode" in text


def test_recovery_verifier_exercises_only_main_process_and_proves_new_pid() -> None:
    text = source()
    assert "--kill-who=main" in text
    assert "--signal=SIGKILL" in text
    assert "recovery_service_after_map.MainPID != recovery_service_before_map.MainPID" in text
    assert "recovery_elapsed_ms | int >= 12000" in text
    assert "recovery_elapsed_ms | int <= 45000" in text
    assert "reboot" not in text.lower()


def test_recovery_verifier_has_full_safety_and_evidence_gates() -> None:
    text = source()
    for marker in (
        "recovery_backup_status.activity_recent",
        "mri_target_sha256",
        "recovery_probes_before.matched | int == 5",
        "RestartUSec == '15s'",
        "StartLimitIntervalUSec == '0'",
        "recovery_telemetry_after_response",
        "Recover sensor manually only if automatic recovery did not",
        "restart_recovery_",
    ):
        assert marker in text
