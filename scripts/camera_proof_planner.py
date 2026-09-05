#!/usr/bin/env python3
"""Arm and complete read-only natural camera proofs from deployment evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
CONVERGENCE_PATH = ROOT / "inventory" / "camera_convergence.yml"
LOCAL_ZONE = ZoneInfo("America/New_York")
EXPECTED_HOSTS = 28
MINIMUM_BASELINE_LEAD_MINUTES = 6
CANONICAL_VERSION = "3.0.0"
CANONICAL_SOURCE_SHA256 = "56cd4b6e69a472d5b93dedb1f75cbde75817ce41d24e2fc47ad66ee6f690cf04"
CANONICAL_HASHES = {
    "scheduled_capture.py": CANONICAL_SOURCE_SHA256,
    "retry_failed_sessions.py": "ef54f6689342c14f9680b1f38f15eac199edc31700cd71558187c80ca753c16f",
    "run_scheduled_capture.sh": "bc8d39b84fbdc147b08f76ec2b52692dc8f4ca8e8101fb3c3922f90c3595b8ec",
    "run_retry_check.sh": "03d5fce36580cb0a165d0e418766889bf7608f65f0eedc685798b1de59c24120",
}
REQUIRED_SAFETY = {
    "schedule_unchanged",
    "exact_probes_after",
    "sensor_active_after",
    "zero_throttle_after",
    "rollback_staged",
}


def parse_time(value: Any) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    return parsed.astimezone(LOCAL_ZONE) if parsed.tzinfo else None


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def load_convergence(path: Path = CONVERGENCE_PATH) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return payload if isinstance(payload, dict) else {}


def latest_complete_audit(report_dir: Path = REPORT_DIR) -> dict[str, Any]:
    for path in sorted(report_dir.glob("audit_*.json"), reverse=True):
        payload = load_json(path)
        rows = payload.get("results") or []
        if len(rows) == EXPECTED_HOSTS and all(
            row.get("status") in {"ok", "offline_or_unreachable"} for row in rows
        ):
            return payload
    return {}


def audited_camera_hashes(row: dict[str, Any]) -> dict[str, str]:
    files = (
        (((row.get("facts") or {}).get("camera_logging") or {}).get("software") or {})
        .get("core_files")
        or {}
    )
    return {
        name: str((files.get(name) or {}).get("sha256") or "")
        for name in CANONICAL_HASHES
    }


def valid_deployment(
    payload: dict[str, Any],
    contract: dict[str, Any],
    audit_row: dict[str, Any],
) -> bool:
    capture = payload.get("capture") or {}
    safety = payload.get("safety") or {}
    telemetry = payload.get("telemetry") or {}
    created_at = parse_time(payload.get("created_at"))
    return bool(
        payload.get("kind") == "camera_v3_candidate_deployment"
        and payload.get("schema") == 1
        and payload.get("passed") is True
        and created_at
        and audit_row.get("status") == "ok"
        and str(contract.get("status") or "").startswith("eligible_after_primary_pilot")
        and payload.get("canonical_version") == CANONICAL_VERSION
        and payload.get("candidate_source_sha256") == CANONICAL_SOURCE_SHA256
        and payload.get("target_contract") == contract.get("target")
        and payload.get("installed_hashes") == CANONICAL_HASHES
        and audited_camera_hashes(audit_row) == CANONICAL_HASHES
        and str(payload.get("canary_source_file") or "").startswith(
            "camera_v3_candidate_canary_"
        )
        and bool(str(payload.get("restore_snapshot_id") or ""))
        and payload.get("natural_proof_pending") is True
        and capture.get("requested") == 1
        and capture.get("captured") == 1
        and capture.get("uploaded") == 0
        and capture.get("upload_enabled") is False
        and str(capture.get("ram_workspace") or "").startswith("/dev/shm/")
        and REQUIRED_SAFETY.issubset(safety)
        and all(safety.get(name) is True for name in REQUIRED_SAFETY)
        and safety.get("sensor_restarted") is False
        and safety.get("rebooted") is False
        and telemetry.get("advanced") is True
        and isinstance(telemetry.get("before_timestamp"), int)
        and isinstance(telemetry.get("after_timestamp"), int)
        and telemetry["after_timestamp"] > telemetry["before_timestamp"]
    )


def pending_deployments(
    report_dir: Path = REPORT_DIR,
    convergence: dict[str, Any] | None = None,
    audit: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    convergence = convergence or load_convergence()
    audit = audit or latest_complete_audit(report_dir)
    contracts = convergence.get("hosts") or {}
    audit_rows = {
        row.get("inventory_name"): row
        for row in (audit.get("results") or [])
        if row.get("inventory_name")
    }
    pending: dict[str, dict[str, Any]] = {}
    for path in sorted(
        report_dir.glob("camera_v3_candidate_deployment_*.json"), reverse=True
    ):
        payload = load_json(path)
        name = str(payload.get("inventory_name") or "")
        if not name or name in pending:
            continue
        if valid_deployment(payload, contracts.get(name) or {}, audit_rows.get(name) or {}):
            payload["_source_file"] = path.name
            pending[name] = payload
    return pending


def natural_proof_exists(
    inventory_name: str,
    deployment: dict[str, Any],
    audit_row: dict[str, Any],
    report_dir: Path = REPORT_DIR,
) -> bool:
    deployment_time = parse_time(deployment.get("created_at"))
    current_fingerprint = str(
        ((((audit_row.get("facts") or {}).get("camera_logging") or {}).get("software") or {})
         .get("fingerprint")
         or "")
    )
    if not deployment_time or not current_fingerprint:
        return False
    for path in sorted(report_dir.glob("camera_observation_*.json"), reverse=True):
        if "_baseline_" in path.name:
            continue
        payload = load_json(path)
        created_at = parse_time(payload.get("created_at"))
        checks = payload.get("checks") or {}
        session = payload.get("camera_session") or {}
        fingerprint = (((payload.get("after") or {}).get("camera") or {}).get("fingerprint"))
        if (
            payload.get("kind") == "camera_schedule_verification"
            and payload.get("ok") is True
            and payload.get("inventory_name") == inventory_name
            and payload.get("expected_source") == "camera_edge_v3"
            and created_at
            and created_at > deployment_time
            and checks
            and all(value is True for value in checks.values())
            and session.get("count") == 10
            and session.get("ordinals") == list(range(1, 11))
            and len(session.get("records") or []) == 10
            and fingerprint == current_fingerprint
        ):
            return True
    return False


def next_capture(
    capture_times: list[str],
    now: dt.datetime,
    minimum_lead_minutes: int = MINIMUM_BASELINE_LEAD_MINUTES,
) -> dt.datetime:
    local_now = now.astimezone(LOCAL_ZONE)
    threshold = local_now + dt.timedelta(minutes=minimum_lead_minutes)
    candidates: list[dt.datetime] = []
    for day_offset in range(3):
        day = local_now.date() + dt.timedelta(days=day_offset)
        for value in capture_times:
            hour, minute = (int(part) for part in value.split(":", 1))
            candidate = dt.datetime.combine(
                day, dt.time(hour, minute), tzinfo=LOCAL_ZONE
            )
            if candidate >= threshold:
                candidates.append(candidate)
    if not candidates:
        raise ValueError("no valid capture time in the next three days")
    return min(candidates)


def plan_payload(
    inventory_name: str,
    site_id: str,
    schedule: dt.datetime,
    created_at: dt.datetime,
) -> dict[str, Any]:
    return {
        "schema": 1,
        "kind": "camera_schedule_plan",
        "created_at": created_at.isoformat(),
        "inventory_name": inventory_name,
        "camera_site_id": site_id,
        "baseline_at": (schedule - dt.timedelta(minutes=5)).isoformat(),
        "not_before": schedule.isoformat(),
        "complete_at": (schedule + dt.timedelta(minutes=3)).isoformat(),
        "expires_at": (schedule + dt.timedelta(minutes=30)).isoformat(),
        "expected_upload_count": 10,
        "expected_source": "camera_edge_v3",
    }


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o644)
    temporary.replace(path)


def active_plan(inventory_name: str, now: dt.datetime, report_dir: Path) -> dict[str, Any]:
    pointer = report_dir / f"camera_observation_active_{inventory_name}.path"
    for path in sorted(
        report_dir.glob(f"camera_observation_plan_{inventory_name}_*.json"),
        reverse=True,
    ):
        payload = load_json(path)
        not_before = parse_time(payload.get("not_before"))
        expires_at = parse_time(payload.get("expires_at"))
        if (
            payload.get("kind") == "camera_schedule_plan"
            and payload.get("inventory_name") == inventory_name
            and not_before
            and expires_at
            and now < expires_at
            and (now < not_before or pointer.is_file())
        ):
            payload["_path"] = str(path)
            return payload
    return {}


def run_checked(argv: list[str], timeout: int) -> None:
    subprocess.run(argv, cwd=ROOT, check=True, timeout=timeout)


def tick(now: dt.datetime, report_dir: Path = REPORT_DIR, execute: bool = True) -> list[str]:
    convergence = load_convergence()
    audit = latest_complete_audit(report_dir)
    audit_rows = {
        row.get("inventory_name"): row
        for row in (audit.get("results") or [])
        if row.get("inventory_name")
    }
    actions: list[str] = []
    for name, deployment in pending_deployments(report_dir, convergence, audit).items():
        contract = (convergence.get("hosts") or {}).get(name) or {}
        audit_row = audit_rows.get(name) or {}
        if natural_proof_exists(name, deployment, audit_row, report_dir):
            continue
        plan = active_plan(name, now, report_dir)
        if not plan:
            schedule = next_capture(contract.get("capture_times") or [], now)
            plan = plan_payload(name, str(contract.get("site_id") or ""), schedule, now)
            stamp = schedule.strftime("%Y%m%dT%H%M")
            path = report_dir / f"camera_observation_plan_{name}_{stamp}.json"
            if execute:
                write_atomic(path, plan)
            actions.append(f"{name}: planned {schedule.isoformat()}")
        baseline_at = parse_time(plan.get("baseline_at"))
        not_before = parse_time(plan.get("not_before"))
        complete_at = parse_time(plan.get("complete_at"))
        expires_at = parse_time(plan.get("expires_at"))
        pointer = report_dir / f"camera_observation_active_{name}.path"
        if not all((baseline_at, not_before, complete_at, expires_at)):
            continue
        if baseline_at <= now < not_before and not pointer.is_file():
            actions.append(f"{name}: capture read-only baseline")
            if execute:
                run_checked(
                    [
                        str(ROOT / "scripts/start_camera_observation.sh"),
                        name,
                        str(contract["site_id"]),
                        "10",
                        not_before.isoformat(),
                        "camera_edge_v3",
                        "preserve",
                        "preserve",
                    ],
                    timeout=180,
                )
        elif complete_at <= now <= expires_at and pointer.is_file():
            actions.append(f"{name}: verify natural session")
            if execute:
                run_checked(
                    [str(ROOT / "scripts/complete_latest_camera_observation.sh"), name],
                    timeout=600,
                )
    return actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    now = dt.datetime.now(LOCAL_ZONE)
    for action in tick(now, args.report_dir, execute=not args.dry_run):
        print(action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
