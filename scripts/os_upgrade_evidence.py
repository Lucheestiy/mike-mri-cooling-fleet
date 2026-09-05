#!/usr/bin/env python3
"""Capture and verify guarded Ubuntu release-upgrade evidence for one Pi."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import fleet_ops


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
MAX_REPORT_AGE_MINUTES = 20
DEFAULT_SOURCE_CODENAME = "questing"
DEFAULT_TARGET_CODENAME = "resolute"
DEFAULT_TARGET_VERSION = "26.04"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def parse_time(value: str, now: dt.datetime) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    return parsed.astimezone(now.tzinfo)


def report_age_minutes(report: dict[str, Any], now: dt.datetime) -> float | None:
    try:
        generated = parse_time(str(report["generated_at"]), now)
    except (KeyError, TypeError, ValueError):
        return None
    return max(0.0, (now - generated).total_seconds() / 60)


def find_host(report: dict[str, Any], inventory_name: str) -> dict[str, Any]:
    for host in report.get("results") or []:
        if host.get("inventory_name") == inventory_name:
            return host
    raise ValueError(f"host {inventory_name!r} is absent from report")


def latest_report(prefix: str, inventory_name: str) -> Path:
    for path in sorted(REPORT_DIR.glob(f"{prefix}_*.json"), reverse=True):
        try:
            find_host(load_json(path), inventory_name)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        return path
    raise ValueError(f"no {prefix} report contains {inventory_name!r}")


def restore_test_for(coverage: dict[str, Any], repository: str) -> dict[str, Any]:
    return next(
        (
            item
            for item in (coverage.get("restore_tests") or [])
            if item.get("repository") == repository
        ),
        {},
    )


def physical_macs(facts: dict[str, Any]) -> dict[str, str]:
    return {
        name: value
        for name, value in sorted((facts.get("macs") or {}).items())
        if value and name not in {"lo", "tailscale0"}
    }


def evidence_snapshot(host: dict[str, Any]) -> dict[str, Any]:
    facts = host.get("facts") or {}
    profile = str(host.get("profile") or "mri")
    probe = fleet_ops.probe_recovery_evidence(facts, profile)
    service_key = "cv_sensor" if profile == "cv" else "mri_sensor"
    operational = facts.get("operational_stack") or {}
    required = operational.get("required_packages") or operational.get("base_packages") or {}
    camera = facts.get("camera_logging") or {}
    return {
        "inventory_name": host.get("inventory_name"),
        "label": host.get("label"),
        "profile": profile,
        "os": facts.get("os"),
        "codename": operational.get("version_codename"),
        "architecture": operational.get("architecture"),
        "os_python_version": operational.get("python_version"),
        "application_normalized_sha256": (facts.get("application") or {}).get("normalized_sha256"),
        "sensor_service": (facts.get("services") or {}).get(service_key) or {},
        "sensor_runtime": facts.get("sensor_runtime") or {},
        "configured_probe_ids": probe.get("configured_probe_ids") or [],
        "physical_probe_ids": probe.get("physical_probe_ids") or [],
        "probe_mapping_complete": probe.get("mapping_complete") is True,
        "sensor_offsets": (facts.get("sensor_offsets") or {}).get("values") or {},
        "sensor_config": (facts.get("sensor_config") or {}).get("values") or {},
        "one_wire_gpio_pin": (facts.get("gpio") or {}).get("one_wire_pin"),
        "boot_overlays": sorted((facts.get("gpio") or {}).get("boot_overlays") or []),
        "physical_macs": physical_macs(facts),
        "tailscale_ips": sorted(facts.get("tailscale_ips") or []),
        "required_packages": required,
        "ntp_synchronized": operational.get("ntp_synchronized"),
        "timezone": operational.get("timezone"),
        "throttled_flags": facts.get("throttled_flags"),
        "boot_management": facts.get("boot_management") or {},
        "snap_stack": facts.get("snap_stack") or {},
        "root_free_bytes": (facts.get("disk") or {}).get("free_bytes"),
        "camera_installed": camera.get("installed") is True,
        "camera_software_sha256": (camera.get("software") or {}).get("semantic_fingerprint"),
        "camera_runtime": camera.get("runtime") or {},
    }


def capture_readiness(
    preflight: dict[str, Any],
    coverage: dict[str, Any],
    inventory_name: str,
    now: dt.datetime,
    source_codename: str = DEFAULT_SOURCE_CODENAME,
    target_codename: str = DEFAULT_TARGET_CODENAME,
    target_version: str = DEFAULT_TARGET_VERSION,
) -> dict[str, Any]:
    host = find_host(preflight, inventory_name)
    snapshot = evidence_snapshot(host)
    repository = fleet_ops.BACKUP_REPOSITORIES.get(inventory_name, "")
    restore = restore_test_for(coverage, repository)
    age_minutes = report_age_minutes(preflight, now)
    blockers: list[str] = []
    if age_minutes is None or age_minutes > MAX_REPORT_AGE_MINUTES:
        blockers.append("preflight report is missing a valid recent timestamp")
    if host.get("status") != "ok" or host.get("preflight_status") != "ready":
        reasons = host.get("preflight_blocked_reasons") or [host.get("status") or "not ready"]
        blockers.append("fleet preflight blocked: " + "; ".join(map(str, reasons)))
    if not repository:
        blockers.append("backup repository is not mapped")
    if restore.get("recent") is not True:
        blockers.append("production restore proof missing or stale")
    if snapshot.get("codename") != source_codename:
        blockers.append(f"source OS codename is not {source_codename}")
    if not snapshot.get("application_normalized_sha256"):
        blockers.append("application checksum is unavailable")
    if (snapshot.get("sensor_runtime") or {}).get("complete") is not True:
        blockers.append("sensor Python runtime is incomplete")
    if snapshot.get("camera_installed") and (snapshot.get("camera_runtime") or {}).get("complete") is not True:
        blockers.append("camera Python runtime is incomplete")
    if not snapshot.get("probe_mapping_complete"):
        blockers.append("configured and physical probe mappings differ")
    if not snapshot.get("configured_probe_ids"):
        blockers.append("exact configured probe IDs are unavailable")
    snap_stack = snapshot.get("snap_stack") or {}
    if (
        snap_stack.get("assessed") is True
        and snap_stack.get("installed") is True
        and snap_stack.get("responding") is not True
    ):
        blockers.append("Snap daemon is installed but not responding")
    required = snapshot.get("required_packages") or {}
    missing = sorted(name for name, version in required.items() if not version)
    if not required or missing:
        blockers.append("required operational packages missing: " + (", ".join(missing) or "inventory unavailable"))
    telemetry = ((host.get("safety_gates") or {}).get("telemetry") or {})
    if telemetry.get("current") is not True:
        blockers.append("server telemetry is not current")
    return {
        "schema": 1,
        "kind": "os_upgrade_baseline",
        "created_at": now.isoformat(timespec="seconds"),
        "preflight_generated_at": preflight.get("generated_at"),
        "preflight_age_minutes": round(age_minutes, 1) if age_minutes is not None else None,
        "source_codename": source_codename,
        "target_codename": target_codename,
        "target_version": target_version,
        "repository": repository,
        "restore_test": restore,
        "telemetry": telemetry,
        "snapshot": snapshot,
        "ready": not blockers,
        "blockers": blockers,
    }


def check(name: str, passed: bool, expected: Any = None, actual: Any = None) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "expected": expected, "actual": actual}


def verify_upgrade(
    baseline: dict[str, Any],
    post_report: dict[str, Any],
    telemetry: dict[str, Any],
    now: dt.datetime,
) -> dict[str, Any]:
    before = baseline.get("snapshot") or {}
    host = find_host(post_report, str(before.get("inventory_name") or ""))
    after = evidence_snapshot(host)
    post_age = report_age_minutes(post_report, now)
    before_telemetry = baseline.get("telemetry") or {}
    target_codename = str(baseline.get("target_codename") or DEFAULT_TARGET_CODENAME)
    target_version = str(baseline.get("target_version") or DEFAULT_TARGET_VERSION)
    checks = [
        check("approved baseline", baseline.get("ready") is True, True, baseline.get("ready")),
        check("fresh post-upgrade audit", post_age is not None and post_age <= MAX_REPORT_AGE_MINUTES, f"<= {MAX_REPORT_AGE_MINUTES} minutes", post_age),
        check("host reachable", host.get("status") == "ok", "ok", host.get("status")),
        check(f"Ubuntu {target_version} target", after.get("codename") == target_codename and target_version in str(after.get("os") or ""), f"Ubuntu {target_version} / {target_codename}", f"{after.get('os')} / {after.get('codename')}"),
        check("architecture preserved", after.get("architecture") == before.get("architecture"), before.get("architecture"), after.get("architecture")),
        check("application checksum preserved", bool(before.get("application_normalized_sha256")) and after.get("application_normalized_sha256") == before.get("application_normalized_sha256"), before.get("application_normalized_sha256"), after.get("application_normalized_sha256")),
        check("configured probe IDs preserved", after.get("configured_probe_ids") == before.get("configured_probe_ids"), before.get("configured_probe_ids"), after.get("configured_probe_ids")),
        check("physical probe IDs exact", after.get("physical_probe_ids") == before.get("configured_probe_ids") and after.get("probe_mapping_complete") is True, before.get("configured_probe_ids"), after.get("physical_probe_ids")),
        check("sensor offsets preserved", after.get("sensor_offsets") == before.get("sensor_offsets"), before.get("sensor_offsets"), after.get("sensor_offsets")),
        check("sensor configuration preserved", after.get("sensor_config") == before.get("sensor_config"), before.get("sensor_config"), after.get("sensor_config")),
        check("1-Wire GPIO preserved", after.get("one_wire_gpio_pin") == before.get("one_wire_gpio_pin"), before.get("one_wire_gpio_pin"), after.get("one_wire_gpio_pin")),
        check("boot overlays preserved", after.get("boot_overlays") == before.get("boot_overlays"), before.get("boot_overlays"), after.get("boot_overlays")),
        check("physical MACs preserved", after.get("physical_macs") == before.get("physical_macs"), before.get("physical_macs"), after.get("physical_macs")),
        check("sensor service active", (after.get("sensor_service") or {}).get("active") == "active", "active", (after.get("sensor_service") or {}).get("active")),
        check("sensor Python runtime complete", (after.get("sensor_runtime") or {}).get("complete") is True, True, after.get("sensor_runtime")),
        check("sensor Python matches OS", bool((after.get("sensor_runtime") or {}).get("python_version")) and str((after.get("sensor_runtime") or {}).get("python_version")).rsplit(".", 1)[0] == str(after.get("os_python_version") or "").replace("Python ", "").rsplit(".", 1)[0], after.get("os_python_version"), (after.get("sensor_runtime") or {}).get("python_version")),
        check("camera installation preserved", "camera_installed" not in before or after.get("camera_installed") == before.get("camera_installed"), before.get("camera_installed"), after.get("camera_installed")),
        check("camera software preserved", not before.get("camera_installed") or (bool(before.get("camera_software_sha256")) and after.get("camera_software_sha256") == before.get("camera_software_sha256")), before.get("camera_software_sha256"), after.get("camera_software_sha256")),
        check("camera Python runtime complete", not before.get("camera_installed") or (after.get("camera_runtime") or {}).get("complete") is True, True, after.get("camera_runtime")),
        check("required packages present", bool(after.get("required_packages")) and all((after.get("required_packages") or {}).values()), "all installed", sorted(name for name, value in (after.get("required_packages") or {}).items() if not value)),
        check("Snap daemon responding", not ((before.get("snap_stack") or {}).get("assessed") is True and (before.get("snap_stack") or {}).get("installed") is True) or (after.get("snap_stack") or {}).get("responding") is True, True, (after.get("snap_stack") or {}).get("responding")),
        check("NTP synchronized", after.get("ntp_synchronized") is True, True, after.get("ntp_synchronized")),
        check("no throttle flags", after.get("throttled_flags") == 0, 0, after.get("throttled_flags")),
        check("boot candidate settled", (after.get("boot_management") or {}).get("current_state") == "good" and not (after.get("boot_management") or {}).get("new_state"), "current=good, new empty", after.get("boot_management")),
        check("server telemetry current", telemetry.get("current") is True, True, telemetry.get("current")),
        check("server telemetry advanced", isinstance(telemetry.get("last_updated"), (int, float)) and isinstance(before_telemetry.get("last_updated"), (int, float)) and telemetry["last_updated"] > before_telemetry["last_updated"], f"> {before_telemetry.get('last_updated')}", telemetry.get("last_updated")),
    ]
    return {
        "schema": 1,
        "kind": "os_upgrade_verification",
        "created_at": now.isoformat(timespec="seconds"),
        "inventory_name": before.get("inventory_name"),
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "before": before,
        "after": after,
        "telemetry": telemetry,
    }


def write_report(payload: dict[str, Any], prefix: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    # Microseconds avoid report collisions when readiness is captured in parallel.
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = output_dir / f"{prefix}_{timestamp}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    capture = subparsers.add_parser("capture", help="Capture a restore-gated pre-upgrade baseline.")
    capture.add_argument("--host", required=True)
    capture.add_argument("--preflight", type=Path)
    capture.add_argument("--backup-coverage", type=Path, default=REPORT_DIR / "backup_coverage.json")
    capture.add_argument("--output-dir", type=Path, default=REPORT_DIR)
    capture.add_argument("--source-codename", default=DEFAULT_SOURCE_CODENAME)
    capture.add_argument("--target-codename", default=DEFAULT_TARGET_CODENAME)
    capture.add_argument("--target-version", default=DEFAULT_TARGET_VERSION)
    verify = subparsers.add_parser("verify", help="Verify a fresh post-upgrade audit against a baseline.")
    verify.add_argument("--baseline", type=Path, required=True)
    verify.add_argument("--audit", type=Path)
    verify.add_argument("--output-dir", type=Path, default=REPORT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = dt.datetime.now().astimezone()
    if args.action == "capture":
        preflight_path = args.preflight or latest_report("preflight", args.host)
        payload = capture_readiness(
            load_json(preflight_path),
            load_json(args.backup_coverage),
            args.host,
            now,
            source_codename=args.source_codename,
            target_codename=args.target_codename,
            target_version=args.target_version,
        )
        path = write_report(payload, "os_upgrade_readiness", args.output_dir)
        print(f"{args.host}: {'ready' if payload['ready'] else 'blocked'}")
        for blocker in payload["blockers"]:
            print(f"- {blocker}")
        print(f"Wrote {path}")
        return 0 if payload["ready"] else 2

    baseline = load_json(args.baseline)
    inventory_name = str((baseline.get("snapshot") or {}).get("inventory_name") or "")
    audit_path = args.audit or latest_report("audit", inventory_name)
    post_report = load_json(audit_path)
    post_host = find_host(post_report, inventory_name)
    telemetry = fleet_ops.fetch_telemetry(post_host)
    payload = verify_upgrade(baseline, post_report, telemetry, now)
    path = write_report(payload, "os_upgrade_verification", args.output_dir)
    print(f"{inventory_name}: {'passed' if payload['passed'] else 'failed'}")
    for item in payload["checks"]:
        print(f"- {'PASS' if item['passed'] else 'FAIL'} {item['name']}")
    print(f"Wrote {path}")
    return 0 if payload["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
