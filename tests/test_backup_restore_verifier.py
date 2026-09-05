import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "roles/backup_restore_test/files/coolmri-restic-restore-test"
SWEEP = ROOT / "roles/backup_restore_test/files/coolmri-restic-restore-sweep"
SWEEP_SERVICE = ROOT / "roles/backup_restore_test/files/coolmri-restic-restore-sweep.service"
SWEEP_TIMER = ROOT / "roles/backup_restore_test/files/coolmri-restic-restore-sweep.timer"


def test_restore_verifier_selects_true_newest_snapshot() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert "snapshots --host \"$target\" --tag pi-pull --json" in text
    assert "--latest 1" not in text
    assert "sort_by(.time) | last | .id" in text
    assert "sort_by(.time) | last | .time" in text


def test_restore_verifier_extracts_os_release_symlink_and_target_in_tmpfs() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert 'mktemp -d "/dev/shm/coolmri-restore-' in text
    assert "etc/os-release" in text
    assert 'if [[ -L "$restored" ]]' in text
    assert "usr/lib/os-release" in text
    assert 'test -s "$restored"' in text
    assert "PRETTY_NAME=" in text
    assert subprocess.run(["bash", "-n", str(HELPER)]).returncode == 0


def test_weekly_sweep_is_serial_and_cannot_overlap_backups() -> None:
    sweep = SWEEP.read_text(encoding="utf-8")
    service = SWEEP_SERVICE.read_text(encoding="utf-8")
    timer = SWEEP_TIMER.read_text(encoding="utf-8")
    assert 'BACKUP_LOCK="${COOLMRI_BACKUP_LOCK:-/run/restic-pi-pull-backup.lock}"' in sweep
    assert "flock -n 8" in sweep
    assert '"$VERIFIER" "$repository"' in sweep
    assert 'GOMAXPROCS="${GOMAXPROCS:-2}"' in sweep
    assert 'GOMEMLIMIT="${GOMEMLIMIT:-2GiB}"' in sweep
    assert " &\n" not in sweep
    assert "ProtectSystem=strict" in service
    assert "NoNewPrivileges=true" in service
    assert "MemoryHigh=3G" in service
    assert "MemoryMax=4G" in service
    assert "OnCalendar=Sun *-*-* 07:00:00" in timer
    assert "Persistent=true" in timer
    assert subprocess.run(["bash", "-n", str(SWEEP)]).returncode == 0
