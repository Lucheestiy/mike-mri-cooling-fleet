#!/usr/bin/env python3
"""Build a sanitized last-known-good fact index for offline field diagnosis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
OUTPUT = REPORT_DIR / "fleet_last_known.json"
EXPECTED_HOSTS = 28


def complete_report(payload: dict[str, Any]) -> bool:
    results = payload.get("results") or []
    return len(results) == EXPECTED_HOSTS and all(
        item.get("status") in {"ok", "offline_or_unreachable"} for item in results
    )


def build_index(report_dir: Path = REPORT_DIR) -> dict[str, Any]:
    latest: dict[str, dict[str, Any]] = {}
    newest_generated_at = None
    managed_names: set[str] = set()
    for path in sorted(report_dir.glob("audit_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not complete_report(payload):
            continue
        if newest_generated_at is None:
            newest_generated_at = payload.get("generated_at")
            managed_names = {
                str(host.get("inventory_name") or "")
                for host in payload.get("results") or []
                if host.get("inventory_name")
            }
        for host in payload.get("results") or []:
            inventory_name = str(host.get("inventory_name") or "")
            facts = host.get("facts") or {}
            if (
                inventory_name
                and inventory_name in managed_names
                and inventory_name not in latest
                and host.get("status") == "ok"
                and facts
            ):
                latest[inventory_name] = {
                    "observed_at": payload.get("generated_at"),
                    "source_file": path.name,
                    "profile": host.get("profile") or "mri",
                    "facts": facts,
                }
        if managed_names and len(latest) >= len(managed_names):
            break
    return {
        "schema": 1,
        "kind": "fleet_last_known",
        "generated_from": newest_generated_at,
        "managed_host_count": len(managed_names),
        "host_count": len(latest),
        "missing_history": sorted(managed_names - set(latest)),
        "hosts": latest,
        "note": "Historical display context only. These facts never satisfy current health or maintenance gates.",
    }


def main() -> int:
    payload = build_index()
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(f"Last-known-good index: {payload['host_count']} hosts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
