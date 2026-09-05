import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "roles/backup_hub/files/restic-pi-pull-backup"
STATUS_REFRESH = ROOT / "roles/backup_hub/files/restic-pi-backup-status-refresh"
PLAYBOOK = ROOT / "playbooks/backup_hub_pull_helper.yml"


def test_hub_helper_supports_restricted_and_legacy_exports() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert "sudo -n /usr/local/sbin/pi-backup-export check" in text
    assert "Using restricted canonical export" in text
    assert "Using reviewed legacy export fallback" in text
    assert "/usr/lib/os-release" in text
    assert "bash -s --" in text
    assert "eval" not in text
    assert subprocess.run(["bash", "-n", str(HELPER)]).returncode == 0


def test_target_catalog_cannot_be_consumed_by_ssh_or_legacy_heredoc() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert 'read -r -u 3 id user ip label reported_host port' in text
    assert 'done 3< "$TARGETS"' in text
    assert 'ssh -n "${target_ssh_options[@]}" "$user@$ip" sudo -n /usr/local/sbin/pi-backup-export check' in text
    assert 'ssh -n "${target_ssh_options[@]}" "$user@$ip" sudo -n /usr/local/sbin/pi-backup-export \\' in text
    assert 'done < "$TARGETS"' not in text


def test_helper_bounds_parallel_repositories_and_attributes_worker_failures() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert 'CONCURRENCY="${COOLMRI_BACKUP_CONCURRENCY:-4}"' in text
    assert '[[ ! "$CONCURRENCY" =~ ^[1-8]$ ]]' in text
    assert 'backup_target "$id" "$user" "$ip" "$label" "${port:-22}" &' in text
    assert 'if ((${#group_pids[@]} >= CONCURRENCY)); then' in text
    assert 'wait "$pid"' in text
    assert 'failures+=("$id:$reason")' in text
    assert 'printf \'%s\\n\' "$reason" >"$BATCH_STATE_DIR/$id.failure"' in text


def test_helper_supports_a_backward_compatible_per_target_ssh_port() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert 'port="${5:-22}"' in text
    assert 'target_ssh_options=("${ssh_options[@]}" -p "$port")' in text
    assert '((port < 1 || port > 65535))' in text


def test_helper_canary_rolls_back_and_verifies_snapshot() -> None:
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "backup_hub_pull_helper_confirm" in text
    assert "backup: true" in text
    assert "Restore the prior hub pull helper" in text
    assert "Run four real repository canaries in one helper invocation" in text
    assert "backup_hub_canary_ids" in text
    assert "sort_by(.time) | last | .id" in text
    assert "coolmri-restic-restore-test" in text
    assert "Require restore reports to match the exact new markers" in text
    assert "--tag pi-pull" in text
    assert "restic-pi-backup-status-refresh" in text


def test_successful_backup_markers_require_real_restic_snapshots() -> None:
    helper = HELPER.read_text(encoding="utf-8")
    refresher = STATUS_REFRESH.read_text(encoding="utf-8")
    for text in (helper, refresher):
        assert "sort_by(.time) | last" in text
        assert 'status: "success"' in text
        assert "snapshot_id" in text
        assert "snapshots --host" in text
    assert "STATUS_DIR=/var/lib/coolmri-fleet/backup-status" in helper
    assert "HISTORY_DIR=$STATUS_DIR/history" in helper
    assert '"$HISTORY_DIR/$id/$snapshot_id.json"' in helper
    assert subprocess.run(["bash", "-n", str(STATUS_REFRESH)]).returncode == 0
