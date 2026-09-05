from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "backup_status_history_migration.yml"


def test_history_migration_is_confirmed_non_backup_and_rollback_capable() -> None:
    source = PLAYBOOK.read_text(encoding="utf-8")
    document = yaml.safe_load(source)[0]
    assert document["hosts"] == "backup_hub"
    assert "ansible_check_mode or backup_status_history_migration_confirm | bool" in source
    assert "Install reviewed helper without invoking it" in source
    assert "Create a new encrypted snapshot" not in source
    assert 'argv:\n              - "{{ backup_helper_path }}"' not in source
    assert "Restore prior helper after migration failure" in source


def test_history_migration_preserves_the_evidenced_mr1_full_batch_marker() -> None:
    source = PLAYBOOK.read_text(encoding="utf-8")
    variables = yaml.safe_load(source)[0]["vars"]
    marker = variables["historical_agcmr1_marker"]
    assert marker["snapshot_id"] == "8500dba169eae8c11f3518d670705ec1a2233f70ecb7ad2cfb74a655384281fe"
    assert marker["completed_at"] == "2026-07-17T15:57:31-04:00"
    assert "Starting Pi pull backup batch" in source
    assert "Complete agcmr1" in source
    assert "Pi pull backup batch finished" in source
