from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "diagnose_writes.sh"


def test_read_only_diagnostic_tolerates_unreadable_or_disappearing_proc_entries() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "if [[ -n \"$value\" ]]" in text
    assert "return 0" in text


def test_read_only_diagnostic_tolerates_head_closing_metadata_pipelines() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "head -25 || true" in text
    assert "done || true" in text
