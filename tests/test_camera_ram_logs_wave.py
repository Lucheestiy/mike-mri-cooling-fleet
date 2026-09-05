from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "camera_ram_logs_wave.yml"
CROND_REHEARSAL = ROOT / "playbooks" / "camera_ram_logs_crond_rehearsal.yml"


def source() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def test_wave_is_one_explicit_reviewed_user_crontab_host():
    play = yaml.safe_load(source())[0]
    assert play["hosts"] == "{{ camera_ram_logs_target | default('none') }}"
    assert "ansible_play_hosts_all | length == 1" in source()
    assert "camera_ram_logs_wave_confirm" in source()
    assert "oswmr2" in play["vars"]["camera_ram_logs_allowed_targets"]


def test_wave_requires_current_backup_restore_and_exact_live_sensor_path():
    text = source()
    for requirement in (
        "camera_wave_backup_status.activity_recent",
        "camera_wave_restore_status.recent",
        'test "$configured" = "$physical"',
        "mri-sensor.service",
        "vcgencmd get_throttled",
        "MemAvailable",
        "Require online current sensor telemetry",
        "Wait for sensor telemetry to advance after transition",
    ):
        assert requirement in text


def test_wave_preserves_code_schedule_and_has_automatic_rollback():
    text = source()
    for requirement in (
        "Capture exact protected sensor and camera hashes",
        "Capture exact user camera schedule",
        "camera_wave_hashes_after.stdout == camera_wave_hashes_before.stdout",
        "camera_ram_logs_crontab_after.stdout == camera_wave_crontab_before.stdout",
        "camera_ram_logs_state: rollback",
        "Stop the wave after rollback",
    ):
        assert requirement in text
    assert "ansible.builtin.reboot" not in text
    assert "systemctl restart" not in text


def test_wave_cannot_expand_before_exact_gcmc_reference_proof():
    text = source()
    for requirement in (
        "Require exact natural proof from the first remote RAM-log expansion",
        "gcmcmr2",
        "camera_ocr",
        "camera_session.count', 'equalto', 10",
        "after.camera.fingerprint",
        "camera_wave_reference_audit.facts.camera_logging.software.fingerprint",
    ):
        assert requirement in text


def test_oswmr2_uses_exact_crond_contract_and_auto_resume_strategy():
    text = source()
    for requirement in (
        "cron_service_watchdog",
        "Require the reviewed OSW MR2 cron.d contract",
        "camera_wave_crond_before.stat.mode == '0644'",
        "prune_failed_sessions",
        "camera_ram_logs_schedule_strategy: \"{{ camera_wave_schedule_strategy }}\"",
    ):
        assert requirement in text


def test_crond_strategy_rehearsal_is_hard_limited_to_check_mode():
    play = yaml.safe_load(CROND_REHEARSAL.read_text(encoding="utf-8"))[0]
    rehearsal = CROND_REHEARSAL.read_text(encoding="utf-8")
    assert play["hosts"] == "oswmr2"
    assert "Refuse every non-check-mode invocation" in rehearsal
    assert "- ansible_check_mode" in rehearsal
    assert "camera_ram_logs_schedule_strategy: cron_service_watchdog" in rehearsal
