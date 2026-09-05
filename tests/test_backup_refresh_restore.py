from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks/backup_refresh_restore.yml"


def play() -> dict:
    return yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]


def test_refresh_restore_requires_explicit_allowlisted_targets_and_confirmation() -> None:
    source = PLAYBOOK.read_text(encoding="utf-8")
    current = play()
    assert current["hosts"] == "backup_hub"
    assert current["become"] is True
    assert current["vars"]["backup_refresh_restore_targets"] == []
    assert "difference(backup_refresh_restore_allowed_targets)" in source
    assert "ansible_check_mode or backup_refresh_restore_confirm | bool" in source


def test_refresh_restore_runs_bounded_multi_target_backup_then_serial_tmpfs_verifier() -> None:
    source = PLAYBOOK.read_text(encoding="utf-8")
    current = play()
    backup = source.index("/usr/local/sbin/restic-pi-pull-backup")
    restore = source.index("/usr/local/sbin/coolmri-restic-restore-test", backup)
    proof = source.index(".status ==", restore)
    assert backup < restore < proof
    backup_task = next(
        task for task in current["tasks"]
        if task.get("name") == "Create new encrypted snapshots with bounded cross-site concurrency"
    )
    assert backup_task["ansible.builtin.command"]["argv"] == (
        "{{ ['/usr/local/sbin/restic-pi-pull-backup'] + "
        "backup_refresh_restore_targets }}"
    )
    assert "loop" not in backup_task
    restore_task = next(
        task for task in current["tasks"]
        if task.get("name") == "Decrypt and restore-test each new snapshot in tmpfs"
    )
    assert restore_task["loop"] == "{{ backup_refresh_restore_targets }}"
