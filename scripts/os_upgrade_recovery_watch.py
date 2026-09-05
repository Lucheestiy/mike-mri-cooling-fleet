#!/usr/bin/env python3
"""Promote a recovered OS canary only after every strict read-only check passes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import fleet_ops
import os_upgrade_evidence


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def latest_host_report(directory: Path, prefix: str, host: str) -> Path | None:
    for path in sorted(directory.glob(f"{prefix}_*.json"), reverse=True):
        try:
            payload = load_json(path)
            if prefix == "os_upgrade_verification":
                if payload.get("inventory_name") == host:
                    return path
            else:
                os_upgrade_evidence.find_host(payload, host)
                return path
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return None


def recovery_gate(
    baseline: dict[str, Any],
    audit: dict[str, Any],
    telemetry: dict[str, Any],
) -> list[str]:
    before = baseline.get("snapshot") or {}
    host_name = str(before.get("inventory_name") or "")
    host = os_upgrade_evidence.find_host(audit, host_name)
    after = os_upgrade_evidence.evidence_snapshot(host)
    configured = before.get("configured_probe_ids") or []
    blockers: list[str] = []
    if baseline.get("ready") is not True:
        blockers.append("approved pre-upgrade baseline is not ready")
    if host.get("status") != "ok":
        blockers.append("host is not reachable")
    if not configured or after.get("physical_probe_ids") != configured:
        blockers.append("exact configured physical probes have not recovered")
    if not after.get("probe_mapping_complete"):
        blockers.append("configured and physical probe mappings differ")
    if (after.get("sensor_service") or {}).get("active") != "active":
        blockers.append("sensor service is not active")
    if telemetry.get("current") is not True:
        blockers.append("server telemetry is not current")
    before_updated = (baseline.get("telemetry") or {}).get("last_updated")
    after_updated = telemetry.get("last_updated")
    if not (
        isinstance(before_updated, (int, float))
        and isinstance(after_updated, (int, float))
        and after_updated > before_updated
    ):
        blockers.append("server telemetry has not advanced beyond the baseline")
    return blockers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--reports-dir", type=Path, default=ROOT / "reports")
    parser.add_argument("--audit", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline = load_json(args.baseline)
    baseline_host = str((baseline.get("snapshot") or {}).get("inventory_name") or "")
    if baseline_host != args.host:
        raise SystemExit(
            f"baseline host {baseline_host or 'missing'} does not match {args.host}"
        )

    prior_path = latest_host_report(
        args.reports_dir, "os_upgrade_verification", args.host
    )
    if prior_path:
        prior = load_json(prior_path)
        if prior.get("passed") is True:
            print(f"{args.host}: strict OS recovery already verified in {prior_path.name}")
            return 0

    audit_path = args.audit or latest_host_report(args.reports_dir, "audit", args.host)
    if audit_path is None:
        print(f"{args.host}: waiting for an audit containing this host")
        return 0
    audit = load_json(audit_path)
    host = os_upgrade_evidence.find_host(audit, args.host)
    telemetry = fleet_ops.fetch_telemetry(host)
    blockers = recovery_gate(baseline, audit, telemetry)
    if blockers:
        print(f"{args.host}: recovery not yet eligible")
        for blocker in blockers:
            print(f"- {blocker}")
        return 0

    verification = os_upgrade_evidence.verify_upgrade(
        baseline, audit, telemetry, os_upgrade_evidence.dt.datetime.now().astimezone()
    )
    if not verification.get("passed"):
        print(f"{args.host}: recovery gate passed but strict verification still has blockers")
        for item in verification.get("checks") or []:
            if item.get("passed") is not True:
                print(f"- {item.get('name')}")
        return 0

    path = os_upgrade_evidence.write_report(
        verification, "os_upgrade_verification", args.reports_dir
    )
    print(f"{args.host}: strict OS recovery verified")
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
