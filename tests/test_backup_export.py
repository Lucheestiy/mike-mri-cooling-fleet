from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "roles/backup_export/files/pi-backup-export"
SUDOERS = ROOT / "roles/backup_export/templates/pi-backup-export.sudoers.j2"
DISPATCHER = ROOT / "roles/backup_export/files/pi-backup-ssh-dispatch"
FLEET_OPS = ROOT / "scripts/fleet_ops.py"
HUB_ONBOARD = ROOT / "playbooks/backup_hub_onboard.yml"


def test_backup_export_has_fixed_paths_and_no_dynamic_arguments() -> None:
    text = HELPER.read_text()
    assert '[[ $# -le 1 ]] || usage' in text
    assert '[[ $# -eq 0 || "$1" == "check" ]] || usage' in text
    assert 'paths=("$home_dir")' in text
    assert "for path in /etc /usr/lib/os-release /usr/local /opt /srv /boot/firmware /boot" in text
    assert "eval" not in text


def test_backup_export_keeps_caches_out_and_streams_stdout() -> None:
    text = HELPER.read_text()
    assert "--one-file-system" in text
    assert "--ignore-failed-read" in text
    assert "--exclude='*/.cache'" in text
    assert '-cpf - "${paths[@]}"' in text


def test_backup_export_sudo_rule_is_exact() -> None:
    line = SUDOERS.read_text().strip()
    assert line.endswith(
        "NOPASSWD: /usr/local/sbin/pi-backup-export, /usr/local/sbin/pi-backup-export check"
    )
    assert "*" not in line


def test_hub_key_is_source_and_forced_command_restricted() -> None:
    tasks = (ROOT / "roles/backup_export/tasks/main.yml").read_text(encoding="utf-8")
    dispatcher = DISPATCHER.read_text(encoding="utf-8")
    assert 'from="100.95.120.88"' in tasks
    assert 'command="/usr/local/sbin/pi-backup-ssh-dispatch"' in tasks
    for option in (
        "no-agent-forwarding",
        "no-port-forwarding",
        "no-pty",
        "no-user-rc",
        "no-X11-forwarding",
    ):
        assert option in tasks
    assert "SSH_ORIGINAL_COMMAND" in dispatcher
    assert '"sudo -n /usr/local/sbin/pi-backup-export"' in dispatcher
    assert '"sudo -n /usr/local/sbin/pi-backup-export check"' in dispatcher
    assert "eval" not in dispatcher


def test_fleet_audit_probes_backup_export_without_streaming_archive() -> None:
    text = FLEET_OPS.read_text(encoding="utf-8")
    assert 'def backup_export_helper() -> dict:' in text
    assert 'if not path.is_file() or helper_sha256 != expected_sha256:' in text
    assert '["sudo", "-n", path_text, "check"]' in text
    assert '"pi_backup_export": pi_backup_export' in text


def test_hub_onboarding_defaults_to_the_nearby_gcmc_mr2_canary() -> None:
    text = HUB_ONBOARD.read_text(encoding="utf-8")
    selection = text.split("backup_hub_target_catalog:", 1)[0]
    assert "backup_hub_onboard_target_ids:" in selection
    assert "- gcmcmr2" in selection
    assert "selectattr('id', 'in', backup_hub_onboard_target_ids)" in text
    assert "difference(backup_hub_target_catalog" in text


def test_glh_is_explicitly_mapped_for_export_and_hub_onboarding() -> None:
    prepare = (ROOT / "playbooks/backup_export_prepare.yml").read_text(encoding="utf-8")
    onboard = HUB_ONBOARD.read_text(encoding="utf-8")
    refresh = (ROOT / "playbooks/backup_refresh_restore.yml").read_text(encoding="utf-8")
    assert "glh: GLH" in prepare
    assert "glh: 5" in prepare
    assert "- id: glh" in onboard
    assert "ip: 100.120.102.8" in onboard
    assert "      - glh" in refresh
