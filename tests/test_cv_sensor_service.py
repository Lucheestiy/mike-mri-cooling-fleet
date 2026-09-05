from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "roles/cv_sensor_service/templates/cv-room-sensor.service.j2"


def test_cv_unit_runs_as_the_site_account() -> None:
    text = UNIT.read_text()
    assert "User={{ cv_sensor_service_user }}" in text
    assert "Group={{ cv_sensor_service_group }}" in text
    assert "WorkingDirectory=/opt/cv-room-monitor" in text
    assert "ExecStart=/opt/cv-room-monitor/venv/bin/python " in text


def test_cv_unit_has_recovery_and_basic_hardening() -> None:
    text = UNIT.read_text()
    for directive in (
        "Restart=always",
        "NoNewPrivileges=true",
        "PrivateTmp=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "ProtectKernelTunables=true",
        "ProtectKernelModules=true",
        "ProtectControlGroups=true",
        "RestrictSUIDSGID=true",
        "LockPersonality=true",
    ):
        assert directive in text
