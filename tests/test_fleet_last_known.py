import importlib.util
import json
import tempfile
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fleet_last_known.py"
SPEC = importlib.util.spec_from_file_location("fleet_last_known", MODULE_PATH)
last_known = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(last_known)


def report(status, generated_at, hostname):
    results = [
        {
            "inventory_name": f"host{index}",
            "status": "ok",
            "facts": {"hostname": f"host{index}"},
        }
        for index in range(last_known.EXPECTED_HOSTS)
    ]
    results[0] = {
        "inventory_name": "glh",
        "status": status,
        "facts": {"hostname": hostname} if status == "ok" else {},
    }
    return {"generated_at": generated_at, "results": results}


def test_index_uses_latest_successful_facts_when_current_host_is_offline():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "audit_20260716_100000.json").write_text(
            json.dumps(report("ok", "2026-07-16T10:00:00", "glh-good")), encoding="utf-8"
        )
        (root / "audit_20260716_101500.json").write_text(
            json.dumps(report("offline_or_unreachable", "2026-07-16T10:15:00", "")), encoding="utf-8"
        )
        result = last_known.build_index(root)
    assert result["hosts"]["glh"]["facts"]["hostname"] == "glh-good"
    assert result["hosts"]["glh"]["observed_at"] == "2026-07-16T10:00:00"
    assert result["generated_from"] == "2026-07-16T10:15:00"
    assert result["managed_host_count"] == last_known.EXPECTED_HOSTS


def test_incomplete_newer_report_is_ignored():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "audit_20260716_100000.json").write_text(
            json.dumps(report("ok", "2026-07-16T10:00:00", "valid")), encoding="utf-8"
        )
        (root / "audit_20260716_101500.json").write_text(
            json.dumps({"generated_at": "2026-07-16T10:15:00", "results": []}), encoding="utf-8"
        )
        result = last_known.build_index(root)
    assert result["hosts"]["glh"]["facts"]["hostname"] == "valid"
