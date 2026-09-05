#!/usr/bin/env python3
"""Capture and verify a production camera schedule without changing a Pi."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path


CAMERA_URL = "https://cam.coolmri.com/api/camera/pressure/recent?limit=1000&hours=168"
MRI_URL = "https://api.coolmri.com/api/sites/snapshot"
CV_URL = "https://cv.coolmri.com/api/sites/snapshot"
SESSION_RE = re.compile(r"^(?P<session>.+)_(?P<ordinal>\d{2})$")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": "CoolMRI-Camera-Observation/1.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        return json.load(response)


def audit_host(report: dict, inventory_name: str) -> dict:
    try:
        return next(row for row in report.get("results", []) if row.get("inventory_name") == inventory_name)
    except StopIteration as exc:
        raise ValueError(f"host {inventory_name!r} is absent from audit") from exc


def telemetry(host: dict) -> dict:
    sensor_values = (((host.get("facts") or {}).get("sensor_config") or {}).get("values") or {})
    site_id = str(
        host.get("data_site_id")
        or sensor_values.get("SITE_NAME")
        or sensor_values.get("SITE_ID")
        or sensor_values.get("SCANNER_ID")
        or ""
    )
    url = CV_URL if host.get("profile") == "cv" else MRI_URL
    rows = fetch_json(url)
    row = next((item for item in rows if item.get("id") == site_id), None)
    if row is None:
        return {"site_id": site_id, "current": False, "error": "site absent"}
    updated = row.get("last_updated")
    age = time.time() - updated if isinstance(updated, (int, float)) else None
    return {
        "site_id": site_id,
        "last_updated": updated,
        "age_seconds": round(age, 1) if age is not None else None,
        "is_offline": row.get("is_offline"),
        "current": bool(age is not None and -30 <= age <= 300 and row.get("is_offline") is not True),
    }


def core_hashes(camera: dict) -> dict[str, str]:
    files = ((camera.get("software") or {}).get("core_files") or {})
    return {name: str(details.get("sha256") or "") for name, details in sorted(files.items())}


def host_evidence(host: dict) -> dict:
    facts = host.get("facts") or {}
    camera = facts.get("camera_logging") or {}
    profile = host.get("profile")
    service_key = "cv_sensor" if profile == "cv" else "mri_sensor"
    service = (facts.get("services") or {}).get(service_key) or {}
    sensor_values = ((facts.get("sensor_config") or {}).get("values") or {})
    configured_probe_ids = sorted({
        str(value)
        for key, value in sensor_values.items()
        if value
        and (
            (profile == "cv" and re.fullmatch(r"SENSOR_[1-5]_ID", str(key)))
            or (profile != "cv" and str(key).startswith("PROBE_") and str(key).endswith("_ID"))
        )
    })
    return {
        "status": host.get("status"),
        "uptime_seconds": facts.get("uptime_seconds"),
        "application_sha256": (facts.get("application") or {}).get("sha256"),
        "service": {
            "active": service.get("active"),
            "enabled": service.get("enabled"),
            "user": service.get("user"),
        },
        "probe_ids": sorted((facts.get("one_wire") or {}).get("sensor_ids") or []),
        "configured_probe_ids": configured_probe_ids,
        "throttle_flags": facts.get("throttled_flags"),
        "journald_volatile": (facts.get("ram_optimization") or {}).get("journald_volatile"),
        "journald_persistent": (facts.get("ram_optimization") or {}).get("persistent_journal"),
        "tmp_tmpfs": (facts.get("ram_optimization") or {}).get("tmp_tmpfs"),
        "camera": {
            "installed": camera.get("installed"),
            "memory_only": camera.get("memory_only"),
            "logs_target": camera.get("logs_target"),
            "log_bytes": camera.get("log_bytes"),
            "failed_sessions": camera.get("failed_sessions"),
            "retry_state_durable": camera.get("retry_state_durable"),
            "fingerprint": (camera.get("software") or {}).get("fingerprint"),
            "core_hashes": core_hashes(camera),
            "schedules": (camera.get("software") or {}).get("schedules") or [],
        },
    }


def journald_policy_acceptable(evidence: dict, policy: str) -> bool:
    if policy == "volatile":
        return evidence.get("journald_volatile") is True
    if policy == "preserve":
        return (
            isinstance(evidence.get("journald_volatile"), bool)
            and isinstance(evidence.get("journald_persistent"), bool)
            and evidence["journald_volatile"] != evidence["journald_persistent"]
        )
    return False


def journald_policy_preserved(before: dict, after: dict, policy: str) -> bool:
    return bool(
        journald_policy_acceptable(before, policy)
        and journald_policy_acceptable(after, policy)
        and after.get("journald_volatile") == before.get("journald_volatile")
        and after.get("journald_persistent") == before.get("journald_persistent")
    )


def camera_log_policy_acceptable(camera: dict, policy: str) -> bool:
    if policy == "ram":
        return camera.get("memory_only") is True and str(
            camera.get("logs_target") or ""
        ).startswith("/run/")
    if policy == "preserve":
        return isinstance(camera.get("memory_only"), bool) and bool(
            str(camera.get("logs_target") or "")
        )
    return False


def camera_log_policy_preserved(before: dict, after: dict, policy: str) -> bool:
    return bool(
        camera_log_policy_acceptable(before, policy)
        and camera_log_policy_acceptable(after, policy)
        and after.get("memory_only") == before.get("memory_only")
        and after.get("logs_target") == before.get("logs_target")
    )


def parse_not_before(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("--not-before must include a timezone offset")
    return parsed


def write_report(report_dir: Path, prefix: str, payload: dict) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"{prefix}_{stamp}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def baseline(args: argparse.Namespace) -> int:
    report = load_json(args.audit)
    host = audit_host(report, args.host)
    not_before = parse_not_before(args.not_before)
    evidence = host_evidence(host)
    current_telemetry = telemetry(host)
    camera = evidence["camera"]
    checks = {
        "host_online": evidence["status"] == "ok",
        "sensor_service_active": evidence["service"]["active"] == "active",
        "configured_probes_exact": bool(evidence["configured_probe_ids"])
        and evidence["probe_ids"] == evidence["configured_probe_ids"],
        "zero_throttle": evidence["throttle_flags"] == 0,
        "journald_policy_acceptable": journald_policy_acceptable(
            evidence, args.journald_policy
        ),
        "temporary_capture_storage_in_ram": evidence["tmp_tmpfs"] is True,
        "camera_installed": camera["installed"] is True,
        "camera_log_policy_acceptable": camera_log_policy_acceptable(
            camera, args.camera_log_policy
        ),
        "retry_state_durable": camera["retry_state_durable"] is True,
        "no_failed_sessions": camera["failed_sessions"] == 0,
        "camera_core_fingerprinted": bool(camera["fingerprint"] and camera["core_hashes"]),
        "sensor_telemetry_current": current_telemetry.get("current") is True,
    }
    payload = {
        "kind": "camera_schedule_baseline",
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "audit": args.audit.name,
        "inventory_name": args.host,
        "camera_site_id": args.camera_site_id,
        "expected_source": args.expected_source,
        "journald_policy": args.journald_policy,
        "camera_log_policy": args.camera_log_policy,
        "not_before": not_before.isoformat(),
        "not_before_epoch": not_before.timestamp(),
        "expected_upload_count": args.expected_count,
        "ok": all(checks.values()),
        "checks": checks,
        "host": evidence,
        "telemetry": current_telemetry,
    }
    path = write_report(args.report_dir, "camera_observation_baseline", payload)
    print(path)
    return 0 if payload["ok"] else 1


def scheduled_sessions(site_id: str, not_before_epoch: float) -> list[dict]:
    payload = fetch_json(CAMERA_URL)
    rows = payload.get("items", []) if isinstance(payload, dict) else []
    grouped: dict[str, list[tuple[int, dict]]] = {}
    prefix = f"{site_id.upper()}_SCHED_"
    for row in rows:
        row_site = str(row.get("site_id") or "").upper()
        timestamp = row.get("timestamp")
        match = SESSION_RE.match(row_site)
        if not match or not row_site.startswith(prefix) or not isinstance(timestamp, (int, float)):
            continue
        if timestamp < not_before_epoch:
            continue
        grouped.setdefault(match.group("session"), []).append((int(match.group("ordinal")), row))
    sessions = []
    for session_id, entries in grouped.items():
        ordered = sorted(entries)
        sessions.append({
            "session_id": session_id,
            "count": len(ordered),
            "ordinals": [ordinal for ordinal, _ in ordered],
            "first_timestamp": min(row["timestamp"] for _, row in ordered),
            "last_timestamp": max(row["timestamp"] for _, row in ordered),
            "records": [row for _, row in ordered],
        })
    return sorted(sessions, key=lambda item: item["last_timestamp"], reverse=True)


def wait_for_session(args: argparse.Namespace) -> int:
    before = load_json(args.baseline)
    expected_count = int(before["expected_upload_count"])
    expected_ordinals = list(range(1, expected_count + 1))
    deadline = time.monotonic() + args.timeout
    while True:
        sessions = scheduled_sessions(before["camera_site_id"], before["not_before_epoch"])
        complete = next(
            (
                session for session in sessions
                if session["count"] == expected_count
                and session["ordinals"] == expected_ordinals
                and len(session["records"]) == expected_count
            ),
            None,
        )
        if complete:
            print(json.dumps({
                "session_id": complete["session_id"],
                "count": complete["count"],
                "last_timestamp": complete["last_timestamp"],
            }, sort_keys=True))
            return 0
        if time.monotonic() >= deadline:
            print("scheduled camera session did not complete before timeout", file=sys.stderr)
            return 1
        time.sleep(args.interval)


def verify(args: argparse.Namespace) -> int:
    before = load_json(args.baseline)
    if before.get("ok") is not True:
        raise ValueError("baseline did not pass its pre-schedule safety checks")
    report = load_json(args.audit)
    host = audit_host(report, before["inventory_name"])
    after_host = host_evidence(host)
    after_telemetry = telemetry(host)
    sessions = scheduled_sessions(before["camera_site_id"], before["not_before_epoch"])
    session = sessions[0] if sessions else None
    expected_count = int(before["expected_upload_count"])
    expected_source = str(before.get("expected_source") or args.expected_source or "")
    if not expected_source:
        raise ValueError("baseline has no expected camera record source")
    expected_ordinals = list(range(1, expected_count + 1))
    prior_host = before["host"]
    prior_camera = prior_host["camera"]
    after_camera = after_host["camera"]
    checks = {
        "host_online": after_host["status"] == "ok",
        "uptime_advanced_without_reboot": (
            isinstance(after_host["uptime_seconds"], int)
            and isinstance(prior_host["uptime_seconds"], int)
            and after_host["uptime_seconds"] > prior_host["uptime_seconds"]
        ),
        "application_preserved": after_host["application_sha256"] == prior_host["application_sha256"],
        "sensor_service_preserved": after_host["service"] == prior_host["service"] and after_host["service"]["active"] == "active",
        "configured_probes_preserved_exact": (
            bool(prior_host.get("configured_probe_ids"))
            and after_host.get("configured_probe_ids") == prior_host.get("configured_probe_ids")
            and prior_host["probe_ids"] == prior_host["configured_probe_ids"]
            and after_host["probe_ids"] == after_host["configured_probe_ids"]
        ),
        "zero_throttle": after_host["throttle_flags"] == 0,
        "journald_policy_preserved": journald_policy_preserved(
            prior_host, after_host, str(before.get("journald_policy") or "volatile")
        ),
        "temporary_capture_storage_in_ram": after_host["tmp_tmpfs"] is True,
        "camera_core_preserved": (
            after_camera["fingerprint"] == prior_camera["fingerprint"]
            and after_camera["core_hashes"] == prior_camera["core_hashes"]
        ),
        "camera_log_policy_preserved": camera_log_policy_preserved(
            prior_camera,
            after_camera,
            str(before.get("camera_log_policy") or "ram"),
        ),
        "camera_log_activity_advanced": (
            isinstance(after_camera["log_bytes"], int)
            and isinstance(prior_camera["log_bytes"], int)
            and after_camera["log_bytes"] > prior_camera["log_bytes"]
        ),
        "retry_state_durable": after_camera["retry_state_durable"] is True,
        "no_failed_sessions": after_camera["failed_sessions"] == 0,
        "schedule_preserved": after_camera["schedules"] == prior_camera["schedules"],
        "sensor_telemetry_current": after_telemetry.get("current") is True,
        "sensor_telemetry_advanced": (
            isinstance(after_telemetry.get("last_updated"), (int, float))
            and isinstance(before["telemetry"].get("last_updated"), (int, float))
            and after_telemetry["last_updated"] > before["telemetry"]["last_updated"]
        ),
        "scheduled_session_found": session is not None,
        "scheduled_upload_count": bool(session and session["count"] == expected_count),
        "scheduled_upload_ordinals": bool(session and session["ordinals"] == expected_ordinals),
        "scheduled_records_complete": bool(
            session
            and len(session["records"]) == expected_count
            and all(
                row.get("id") is not None
                and row.get("source") == expected_source
                and isinstance(row.get("timestamp"), (int, float))
                for row in session["records"]
            )
        ),
    }
    ok = all(checks.values())
    payload = {
        "kind": "camera_schedule_verification",
        "created_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "ok": ok,
        "baseline": args.baseline.name,
        "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        "expected_upload_count": expected_count,
        "expected_source": expected_source,
        "audit": args.audit.name,
        "inventory_name": before["inventory_name"],
        "checks": checks,
        "before": prior_host,
        "after": after_host,
        "telemetry_before": before["telemetry"],
        "telemetry_after": after_telemetry,
        "camera_session": session,
    }
    path = write_report(args.report_dir, "camera_observation", payload)
    markdown = path.with_suffix(".md")
    lines = [
        f"# Camera schedule verification — {before['inventory_name']}",
        "",
        f"Result: **{'PASS' if ok else 'FAIL'}**",
        "",
    ] + [f"- {'PASS' if passed else 'FAIL'} — `{name}`" for name, passed in checks.items()]
    markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(path)
    print(markdown)
    return 0 if ok else 1


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="action", required=True)
    baseline_parser = subparsers.add_parser("baseline")
    baseline_parser.add_argument("--audit", type=Path, required=True)
    baseline_parser.add_argument("--host", required=True)
    baseline_parser.add_argument("--camera-site-id", required=True)
    baseline_parser.add_argument("--not-before", required=True)
    baseline_parser.add_argument("--expected-count", type=int, default=10)
    baseline_parser.add_argument("--expected-source", required=True)
    baseline_parser.add_argument(
        "--journald-policy",
        choices=("volatile", "preserve"),
        default="volatile",
        help="Require volatile journald, or preserve the currently audited policy.",
    )
    baseline_parser.add_argument(
        "--camera-log-policy",
        choices=("ram", "preserve"),
        default="ram",
        help="Require camera logs in RAM, or preserve the currently audited policy.",
    )
    baseline_parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    baseline_parser.set_defaults(func=baseline)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--baseline", type=Path, required=True)
    verify_parser.add_argument("--audit", type=Path, required=True)
    verify_parser.add_argument("--expected-source")
    verify_parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    verify_parser.set_defaults(func=verify)
    wait_parser = subparsers.add_parser("wait")
    wait_parser.add_argument("--baseline", type=Path, required=True)
    wait_parser.add_argument("--timeout", type=int, default=300)
    wait_parser.add_argument("--interval", type=int, default=15)
    wait_parser.set_defaults(func=wait_for_session)
    return result


if __name__ == "__main__":
    try:
        arguments = parser().parse_args()
        raise SystemExit(arguments.func(arguments))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"camera observation failed: {error}", file=sys.stderr)
        raise SystemExit(2)
