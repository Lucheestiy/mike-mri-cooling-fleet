#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def attribute_raw(payload: dict[str, Any], attribute_id: int) -> int | None:
    table = ((payload.get("ata_smart_attributes") or {}).get("table") or [])
    for item in table:
        if item.get("id") != attribute_id:
            continue
        raw = (item.get("raw") or {}).get("value")
        return raw if isinstance(raw, int) else None
    return None


def parse_smart(payload: dict[str, Any], device: str, query_type: str) -> dict[str, Any]:
    nvme = payload.get("nvme_smart_health_information_log") or {}
    temperature = payload.get("temperature") or {}
    power_on = payload.get("power_on_time") or {}
    smart_status = payload.get("smart_status") or {}
    critical_warning = nvme.get("critical_warning")
    media_errors = nvme.get("media_errors")
    percentage_used = nvme.get("percentage_used")
    passed = smart_status.get("passed")
    reallocated_sectors = attribute_raw(payload, 5)
    pending_sectors = attribute_raw(payload, 197)
    offline_uncorrectable = attribute_raw(payload, 198)
    concerning = bool(
        passed is False
        or (isinstance(critical_warning, int) and critical_warning != 0)
        or (isinstance(media_errors, int) and media_errors != 0)
        or (isinstance(reallocated_sectors, int) and reallocated_sectors != 0)
        or (isinstance(pending_sectors, int) and pending_sectors != 0)
        or (isinstance(offline_uncorrectable, int) and offline_uncorrectable != 0)
    )
    return {
        "available": True,
        "device": device,
        "query_type": query_type,
        "model": payload.get("model_name") or payload.get("model_family") or "",
        "serial": payload.get("serial_number") or "",
        "protocol": payload.get("device", {}).get("protocol") or "",
        "passed": passed if isinstance(passed, bool) else None,
        "temperature_c": temperature.get("current") if isinstance(temperature.get("current"), int) else nvme.get("temperature"),
        "power_on_hours": power_on.get("hours") if isinstance(power_on.get("hours"), int) else payload.get("power_on_hours"),
        "percentage_used": percentage_used if isinstance(percentage_used, int) else None,
        "critical_warning": critical_warning if isinstance(critical_warning, int) else None,
        "media_errors": media_errors if isinstance(media_errors, int) else None,
        "unsafe_shutdowns": nvme.get("unsafe_shutdowns") if isinstance(nvme.get("unsafe_shutdowns"), int) else None,
        "reallocated_sectors": reallocated_sectors,
        "pending_sectors": pending_sectors,
        "offline_uncorrectable": offline_uncorrectable,
        "concerning": concerning,
    }


def root_device() -> str:
    source = subprocess.run(
        ["findmnt", "-n", "-o", "SOURCE", "/"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    parent = subprocess.run(
        ["lsblk", "-ndo", "PKNAME", source],
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    return f"/dev/{parent}" if parent else f"/dev/{Path(source).name}"


def query(device: str) -> tuple[dict[str, Any] | None, str]:
    attempts = [("auto", ["smartctl", "-j", "-a", device])]
    if Path(device).name.startswith("sd"):
        attempts.extend(
            [
                ("sntrealtek", ["smartctl", "-j", "-a", "-d", "sntrealtek", device]),
                ("sat", ["smartctl", "-j", "-a", "-d", "sat", device]),
            ]
        )
    for query_type, command in attempts:
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=12)
            payload = json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            continue
        if (
            payload.get("smart_status")
            or payload.get("nvme_smart_health_information_log")
            or payload.get("ata_smart_attributes")
        ):
            return payload, query_type
    return None, "unavailable"


def main() -> int:
    if os.geteuid() != 0:
        print(json.dumps({"available": False, "error": "root helper required"}))
        return 77
    if len(sys.argv) != 1:
        print(json.dumps({"available": False, "error": "this helper accepts no arguments"}))
        return 64
    if not Path("/usr/sbin/smartctl").exists() and not Path("/usr/bin/smartctl").exists():
        print(json.dumps({"available": False, "error": "smartctl unavailable"}))
        return 69
    try:
        device = root_device()
    except (OSError, subprocess.CalledProcessError):
        print(json.dumps({"available": False, "error": "root device unavailable"}))
        return 70
    payload, query_type = query(device)
    if payload is None:
        print(json.dumps({"available": False, "device": device, "error": "SMART data unavailable through storage bridge"}))
        return 71
    print(json.dumps(parse_smart(payload, device, query_type), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
