from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "playbooks" / "camera_ram_logs_pilot.yml"
ROLLBACK = ROOT / "playbooks" / "camera_ram_logs_rollback.yml"


def test_ram_log_pilot_is_restricted_to_one_backed_nearby_host() -> None:
    play = yaml.safe_load(PILOT.read_text(encoding="utf-8"))[0]
    text = PILOT.read_text(encoding="utf-8")
    assert play["hosts"] == "agcmr1:agcmr3"
    assert "ansible_play_hosts_all | length == 1" in text
    assert "inventory_hostname in ['agcmr1', 'agcmr3']" in text
    assert "inventory_hostname in camera_pilot_backup.repositories" in text
    assert "selectattr('repository', 'equalto', inventory_hostname)" in text
    for evidence in (
        "Require package manager to be idle",
        "Capture protected application hashes",
        "Require active MRI sensor service",
        "Count exact 1-Wire probes",
        "Require zero current and historical throttle flags",
        "Capture current MRI telemetry",
        "Wait for MRI telemetry to advance",
        "Prove workload preservation after camera log transition",
    ):
        assert evidence in text


def test_ram_log_rollback_matches_the_pilot_boundary() -> None:
    play = yaml.safe_load(ROLLBACK.read_text(encoding="utf-8"))[0]
    text = ROLLBACK.read_text(encoding="utf-8")
    assert play["hosts"] == "agcmr1:agcmr3"
    assert "ansible_play_hosts_all | length == 1" in text
    assert "inventory_hostname in ['agcmr1', 'agcmr3']" in text


def test_role_supports_exact_crond_schedule_with_auto_resume_watchdog() -> None:
    defaults = (ROOT / "roles/camera_ram_logs/defaults/main.yml").read_text()
    main = (ROOT / "roles/camera_ram_logs/tasks/main.yml").read_text()
    apply = (ROOT / "roles/camera_ram_logs/tasks/apply.yml").read_text()
    pause = (ROOT / "roles/camera_ram_logs/tasks/pause_cron_service.yml").read_text()
    restore = (ROOT / "roles/camera_ram_logs/tasks/restore_cron_service.yml").read_text()
    assert "camera_ram_logs_schedule_strategy: user_crontab" in defaults
    assert "cron_service_watchdog" in main + apply
    assert "systemd-run" in pause
    assert "--on-active=2m" in pause
    assert "systemctl stop" in pause
    assert "argv: [systemctl, start, cron.service]" in restore
    assert "camera_ram_logs_crond_after.stat.checksum == camera_ram_logs_crond_before.stat.checksum" in restore
