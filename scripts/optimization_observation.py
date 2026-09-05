#!/usr/bin/env python3
"""Build a compact, continuous evidence gate for RAM/headless canaries."""

from __future__ import annotations

import datetime as dt
import json
import statistics
from pathlib import Path
from typing import Any

import fleet_ops


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
OUTPUT = REPORT_DIR / "optimization_observation.json"
EXPECTED_HOSTS = 28
MIN_HOURS = 48
MIN_SAMPLES = 24
MAX_GAP_MINUTES = 45
MAX_MEDIAN_MIB_PER_DAY = 2048
LEGACY_ACTION_LOOKBACK_MINUTES = 30
MIN_AVAILABLE_MEMORY_PERCENT = 25
DISABLED_SERVICES = (
    "gdm.service",
    "cups.service",
    "cups-browsed.service",
    "bluetooth.service",
    "ModemManager.service",
    "colord.service",
)
CANARIES = {
    "agcmr1": "2026-07-16T09:28:16-04:00",
    "agcmr3": "2026-07-16T06:49:33-04:00",
    "gbh": "2026-07-21T08:47:24-04:00",
    "gmcep1and2": "2026-07-21T07:58:58-04:00",
    "gmcep3": "2026-07-16T12:36:31-04:00",
    "gmcir3": "2026-07-16T13:31:09-04:00",
    "gwvskyra": "2026-07-21T09:03:32-04:00",
    "shmr": "2026-07-21T08:53:58-04:00",
    "vwm3": "2026-07-21T08:59:00-04:00",
}
# These four hosts are the original, reboot-verified reference cohort.  A later
# expansion canary remains visible in the same report, but its new observation
# clock must not revoke evidence already earned by the reference cohort.
REFERENCE_CANARIES = ("agcmr1", "agcmr3", "gmcep3", "gmcir3")
# Complete report audit_20260721_084327.json independently proves all four
# reference hosts at 68.0 continuous hours / 264 samples with no blockers.
REFERENCE_EVIDENCE_ACCEPTED_AT = "2026-07-21T08:43:27-04:00"
REFERENCE_EVIDENCE_SOURCE = "audit_20260721_084327.json"
HEADLESS_ONLY_CANARIES = {"gbh", "gwvskyra", "shmr", "vwm3"}
PROFILE_HASHES = {
    "mri": "0d939f88b35ab8167ce1e70d91a8611a14f4a6a9631a30677bbe06bb5234a36f",
    "cv": "a7bb0bc02e548f37993345e54cd664ac4d6e3dc47ba0b5525d7402f3a07717aa",
}


def parse_time(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return parsed.astimezone()


def complete_report(payload: dict[str, Any]) -> bool:
    results = payload.get("results") or []
    return len(results) == EXPECTED_HOSTS and all(
        item.get("status") in {"ok", "offline_or_unreachable"} for item in results
    )


def load_reports(report_dir: Path = REPORT_DIR) -> list[dict[str, Any]]:
    reports = []
    for path in sorted(report_dir.glob("audit_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        timestamp = parse_time(str(payload.get("generated_at") or ""))
        if timestamp and complete_report(payload):
            payload["_timestamp"] = timestamp
            payload["_source_file"] = path.name
            reports.append(payload)
    return sorted(reports, key=lambda item: item["_timestamp"])


def host_from(report: dict[str, Any], inventory_name: str) -> dict[str, Any]:
    return next(
        (item for item in (report.get("results") or []) if item.get("inventory_name") == inventory_name),
        {},
    )


def host_checks(
    host: dict[str, Any], *, require_volatile_journal: bool = True
) -> dict[str, bool]:
    facts = host.get("facts") or {}
    profile = str(host.get("profile") or "mri")
    operational = facts.get("operational_stack") or {}
    background = operational.get("background_services") or {}
    service_key = "cv_sensor" if profile == "cv" else "mri_sensor"
    ram_budget = facts.get("ram_budget") or {}
    run_budget = ram_budget.get("run") or {}
    memory_percent = ram_budget.get("available_percent")
    return {
        "reachable": host.get("status") == "ok",
        "multi_user_target": operational.get("default_target") == "multi-user.target",
        "selected_services_inactive": bool(background) and all(
            (background.get(name) or {}).get("active") != "active" for name in DISABLED_SERVICES
        ),
        "volatile_journal": (
            not require_volatile_journal
            or (facts.get("ram_optimization") or {}).get("journald_volatile") is True
        ),
        "sensor_service_active": ((facts.get("services") or {}).get(service_key) or {}).get("active") == "active",
        "probe_mapping_complete": fleet_ops.probe_recovery_evidence(facts, profile).get("mapping_complete") is True,
        "approved_application": (facts.get("application") or {}).get("normalized_sha256") == PROFILE_HASHES[profile],
        "no_throttling": facts.get("throttled_flags") == 0,
        "memory_headroom": isinstance(memory_percent, (int, float)) and memory_percent >= MIN_AVAILABLE_MEMORY_PERCENT,
        "run_tmpfs_headroom": (
            run_budget.get("filesystem") == "tmpfs"
            and isinstance(run_budget.get("used_percent"), (int, float))
            and run_budget["used_percent"] < 70
        ),
        "no_oom_events": ram_budget.get("oom_events_since_boot") == 0,
    }


def valid_write_rates(
    observations: list[tuple[dt.datetime, dict[str, Any]]],
    maximum: int = 4,
    maintenance_windows: list[tuple[dt.datetime, dt.datetime]] | None = None,
) -> list[float]:
    rates: list[float] = []
    cursor = len(observations) - 1
    while cursor > 0 and len(rates) < maximum:
        current_time, current_host = observations[cursor]
        older_index = None
        for index in range(cursor - 1, -1, -1):
            if (current_time - observations[index][0]).total_seconds() >= 300:
                older_index = index
                break
        if older_index is None:
            break
        older_time, older_host = observations[older_index]
        maintenance_overlap = any(
            start < current_time and finish > older_time
            for start, finish in (maintenance_windows or [])
        )
        window_hosts = [host for _, host in observations[older_index:cursor + 1]]
        signatures = []
        package_state_known = True
        package_busy = False
        for window_host in window_hosts:
            facts = window_host.get("facts") or {}
            package_busy = package_busy or (
                ((facts.get("package_manager") or {}).get("busy") is True)
            )
            package_maintenance = facts.get("package_maintenance") or {}
            try:
                signature = tuple(
                    int(package_maintenance[name])
                    for name in ("listed_count", "eligible_count", "deferred_count")
                )
            except (KeyError, TypeError, ValueError):
                package_state_known = False
                signature = None
            signatures.append(signature)
        package_window_quiet = bool(
            not package_busy
            and (
                not package_state_known
                or len(set(signatures)) == 1
            )
        )
        if not package_window_quiet:
            break
        if maintenance_overlap:
            cursor = older_index
            continue
        current_facts = current_host.get("facts") or {}
        older_facts = older_host.get("facts") or {}
        current_storage = current_facts.get("storage_health") or {}
        older_storage = older_facts.get("storage_health") or {}
        current_bytes = current_storage.get("bytes_written_since_boot")
        older_bytes = older_storage.get("bytes_written_since_boot")
        current_uptime = current_facts.get("uptime_seconds")
        older_uptime = older_facts.get("uptime_seconds")
        seconds = (current_time - older_time).total_seconds()
        if (
            current_storage.get("root_block_device")
            and current_storage.get("root_block_device") == older_storage.get("root_block_device")
            and isinstance(current_bytes, int)
            and isinstance(older_bytes, int)
            and current_bytes >= older_bytes
            and isinstance(current_uptime, int)
            and isinstance(older_uptime, int)
            and current_uptime > older_uptime
        ):
            rates.append(round((current_bytes - older_bytes) / 1048576 / seconds * 86400, 1))
        cursor = older_index
    return rates


def load_maintenance_windows(
    report_dir: Path = REPORT_DIR,
) -> dict[str, list[tuple[dt.datetime, dt.datetime]]]:
    """Load host-specific APT activity windows without exposing command output.

    Older action reports did not record their start time. For those reports, a
    conservative 30-minute lookback prevents a one-time package transaction from
    being mislabeled as sustained SSD wear.
    """
    windows: dict[str, list[tuple[dt.datetime, dt.datetime]]] = {}
    for pattern in ("update_*.json", "baseline_*.json", "download_*.json"):
        for path in report_dir.glob(pattern):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            completed = parse_time(str(payload.get("generated_at") or ""))
            if completed is None:
                continue
            for result in payload.get("results") or []:
                inventory_name = str(result.get("inventory_name") or "")
                if not inventory_name:
                    continue
                started = parse_time(str(result.get("action_started_at") or ""))
                finished = parse_time(str(result.get("action_finished_at") or ""))
                start = started or completed - dt.timedelta(minutes=LEGACY_ACTION_LOOKBACK_MINUTES)
                finish = finished or completed
                if finish < start:
                    continue
                windows.setdefault(inventory_name, []).append((start, finish))
    return windows


def rsyslog_pilot_start(
    inventory_name: str, reports: list[dict[str, Any]]
) -> dt.datetime | None:
    epochs = []
    for report in reports:
        host = host_from(report, inventory_name)
        value = (
            (((host.get("facts") or {}).get("ram_optimization") or {}).get("rsyslog_ram_pilot") or {})
            .get("applied_epoch")
        )
        if isinstance(value, (int, float)) and value > 0:
            epochs.append(float(value))
    return dt.datetime.fromtimestamp(max(epochs), tz=dt.datetime.now().astimezone().tzinfo) if epochs else None


def observe_host(
    inventory_name: str,
    reports: list[dict[str, Any]],
    telemetry: dict[str, Any],
    maintenance_windows: list[tuple[dt.datetime, dt.datetime]] | None = None,
) -> dict[str, Any]:
    base_start = parse_time(CANARIES[inventory_name])
    pilot_start = rsyslog_pilot_start(inventory_name, reports)
    configured_start = max(
        (value for value in (base_start, pilot_start) if value is not None),
        default=None,
    )
    consecutive: list[tuple[dt.datetime, dict[str, Any]]] = []
    last_time: dt.datetime | None = None
    last_checks: dict[str, bool] = {}
    pending_start_reason = (
        "rsyslog RAM policy boundary"
        if pilot_start is not None and configured_start == pilot_start
        else "first passing audit after canary configuration"
    )
    observation_start_reason = pending_start_reason
    for report in reports:
        timestamp = report["_timestamp"]
        if configured_start and timestamp < configured_start:
            continue
        host = host_from(report, inventory_name)
        checks = host_checks(
            host,
            require_volatile_journal=inventory_name not in HEADLESS_ONLY_CANARIES,
        )
        gap_ok = last_time is None or (timestamp - last_time).total_seconds() <= MAX_GAP_MINUTES * 60
        if all(checks.values()) and gap_ok:
            if not consecutive:
                observation_start_reason = pending_start_reason
            consecutive.append((timestamp, host))
        elif all(checks.values()):
            consecutive = [(timestamp, host)]
            observation_start_reason = (
                f"audit gap exceeded {MAX_GAP_MINUTES} minutes"
            )
        else:
            consecutive = []
            failed_checks = [name.replace("_", " ") for name, passed in checks.items() if not passed]
            pending_start_reason = "health gates recovered after: " + ", ".join(failed_checks)
        last_time = timestamp
        last_checks = checks

    rates = valid_write_rates(consecutive, maintenance_windows=maintenance_windows)
    median_rate = round(statistics.median(rates), 1) if rates else None
    observed_from = consecutive[0][0] if consecutive else None
    observed_to = consecutive[-1][0] if consecutive else None
    duration_hours = (
        (observed_to - observed_from).total_seconds() / 3600
        if observed_from and observed_to
        else 0.0
    )
    earliest_time_gate_at = (
        observed_from + dt.timedelta(hours=MIN_HOURS)
        if observed_from
        else None
    )
    blockers = [name.replace("_", " ") for name, passed in last_checks.items() if not passed]
    if telemetry.get("current") is not True:
        blockers.append("server telemetry not current")
    if len(consecutive) < MIN_SAMPLES:
        blockers.append(f"need {MIN_SAMPLES} continuous audit samples")
    if duration_hours < MIN_HOURS:
        blockers.append(f"need {MIN_HOURS} continuous observation hours")
    if len(rates) < 3:
        blockers.append("need three valid write-rate intervals")
    elif median_rate is not None and median_rate > MAX_MEDIAN_MIB_PER_DAY:
        blockers.append(f"median writes exceed {MAX_MEDIAN_MIB_PER_DAY} MiB/day")
    return {
        "configured_start": configured_start.isoformat(timespec="seconds") if configured_start else None,
        "observed_from": observed_from.isoformat(timespec="seconds") if observed_from else None,
        "observed_to": observed_to.isoformat(timespec="seconds") if observed_to else None,
        "observation_start_reason": observation_start_reason if consecutive else None,
        "duration_hours": round(duration_hours, 1),
        "remaining_hours": round(max(0.0, MIN_HOURS - duration_hours), 1),
        "earliest_time_gate_at": (
            earliest_time_gate_at.isoformat(timespec="seconds")
            if earliest_time_gate_at
            else None
        ),
        "continuous_samples": len(consecutive),
        "checks": last_checks,
        "telemetry": telemetry,
        "write_rates_mib_per_day": rates,
        "median_mib_written_per_day": median_rate,
        "ready": not blockers,
        "blockers": blockers,
    }


def build_observation(
    reports: list[dict[str, Any]],
    maintenance_windows: dict[str, list[tuple[dt.datetime, dt.datetime]]] | None = None,
) -> dict[str, Any]:
    now = dt.datetime.now().astimezone()
    results = {}
    for inventory_name in CANARIES:
        latest_host = host_from(reports[-1], inventory_name) if reports else {}
        telemetry = fleet_ops.fetch_telemetry(latest_host) if latest_host else {"current": False}
        results[inventory_name] = observe_host(
            inventory_name,
            reports,
            telemetry,
            (maintenance_windows or {}).get(inventory_name),
        )
    reference_results = {
        name: results[name] for name in REFERENCE_CANARIES if name in results
    }
    expansion_canaries = [name for name in results if name not in REFERENCE_CANARIES]
    return {
        "schema": 1,
        "kind": "optimization_observation",
        "generated_at": now.isoformat(timespec="seconds"),
        "criteria": {
            "minimum_hours": MIN_HOURS,
            "minimum_samples": MIN_SAMPLES,
            "maximum_gap_minutes": MAX_GAP_MINUTES,
            "maximum_median_mib_per_day": MAX_MEDIAN_MIB_PER_DAY,
            "minimum_available_memory_percent": MIN_AVAILABLE_MEMORY_PERCENT,
            "maximum_run_used_percent_exclusive": 70,
            "require_run_tmpfs": True,
            "require_zero_oom_events_since_boot": True,
        },
        "reference_canaries": list(REFERENCE_CANARIES),
        "reference_evidence_accepted": True,
        "reference_evidence_accepted_at": REFERENCE_EVIDENCE_ACCEPTED_AT,
        "reference_evidence_source": REFERENCE_EVIDENCE_SOURCE,
        "reference_current_healthy": (
            len(reference_results) == len(REFERENCE_CANARIES)
            and all(item["ready"] for item in reference_results.values())
        ),
        "expansion_canaries": expansion_canaries,
        "headless_only_canaries": sorted(HEADLESS_ONLY_CANARIES),
        "cohort_ready": (
            len(reference_results) == len(REFERENCE_CANARIES)
            and all(item["ready"] for item in reference_results.values())
        ),
        "hosts": results,
    }


def main() -> int:
    payload = build_observation(load_reports(), load_maintenance_windows())
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT)
    print(
        "Optimization canaries: "
        + ("ready for nearby expansion" if payload["cohort_ready"] else "observation in progress")
    )
    for name, details in payload["hosts"].items():
        print(f"- {name}: {details['duration_hours']}h / {details['continuous_samples']} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
