from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks/backup_hub_onboard.yml"


def play() -> dict:
    return yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]


def test_hub_onboarding_has_exact_five_prepared_targets() -> None:
    targets = play()["vars"]["backup_hub_target_catalog"]
    assert [item["id"] for item in targets] == [
        "agcmr2",
        "gcmcmr2",
        "vwm2",
        "vwm3",
        "glh",
    ]
    assert len({item["ip"] for item in targets}) == 5
    assert play()["vars"]["backup_hub_onboard_target_ids"] == ["gcmcmr2"]


def test_hub_key_and_export_check_precede_target_mutation() -> None:
    names = [task["name"] for task in play()["tasks"]]
    assert names.index("Prove hub root key and canonical export helper before changing targets") < names.index(
        "Add exact backup target records"
    )
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "sudo\n          - -n\n          - /usr/local/sbin/pi-backup-export\n          - check" in text
    assert "backup-export-ready user=" in text


def test_hub_onboarding_runs_and_verifies_real_snapshots() -> None:
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "Run a real first pull backup for each new target" in text
    assert "snapshots latest --host" in text
    assert "RESTIC_PASSWORD_FILE=/root/.config/restic-backup/password" in text
