#!/usr/bin/env python3
from __future__ import annotations

import base64
import copy
import hmac
import json
import math
import os
import re
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


STATIC_DIR = Path(__file__).resolve().parent / "static"
REPORT_DIR = Path(os.getenv("FLEET_REPORT_DIR", "/data/reports"))
EXPECTED_HOSTS = int(os.getenv("FLEET_EXPECTED_HOSTS", "28"))
USERNAME = os.getenv("FLEET_USERNAME", "")
PASSWORD = os.getenv("FLEET_PASSWORD", "")
MRI_SNAPSHOT_URL = os.getenv("MRI_SNAPSHOT_URL", "http://fastapi-api:5000/api/sites/snapshot")
CV_SNAPSHOT_URL = os.getenv("CV_SNAPSHOT_URL", "http://cv-api:5000/api/sites/snapshot")
CAMERA_RECENT_URL = os.getenv(
    "CAMERA_RECENT_URL",
    "http://mri-camera-backend:8001/api/camera/pressure/recent?limit=1000&hours=168",
)
PRODUCTION_RETURN_PRESSURE_URL = os.getenv(
    "PRODUCTION_RETURN_PRESSURE_URL",
    "http://fastapi-api:5000/api/return-pressure/latest-all",
)
BACKUP_COVERAGE_PATH = REPORT_DIR / "backup_coverage.json"
FLEET_TIMEZONE = ZoneInfo(os.getenv("FLEET_TIMEZONE", "America/New_York"))
FLEET_HEALTH_MAX_AGE_SECONDS = int(os.getenv("FLEET_HEALTH_MAX_AGE_SECONDS", "2700"))

MRI_SITE_IDS = {
    "agcmr1": "AGCMR1", "agcmr2": "GMCMR2", "agcmr3": "AGCMR3",
    "oswmr1": "OSWMR1", "oswmr2": "OSWMR2", "svimr1": "SVIMR1",
    "svimr2": "SVIMR2", "gbh": "GBHAera", "shmr": "SHMR",
    "muncymr": "MuncySola", "jsmr": "JerseyShoreMR", "phc": "PHC",
    "phmv": "PHMV", "gr": "GR", "pittstonsola": "PittstonSola",
    "pittstonvida": "PittstonVida", "gcmcsola": "GCMCSola",
    "gcmcmr2": "GCMCMR2", "gswbsola": "GSWBSola", "gwvskyra": "GWVSkyra",
    "vwm1": "VWM1", "vwm2": "VWM2", "vwm3": "VWM3", "glh": "GLH",
}

BACKUP_REPOS = {
    "agcmr1": "agcmr1", "agcmr3": "agcmr3", "oswmr1": "oswmr1",
    "oswmr2": "oswmr2nvme", "svimr1": "svimr1", "svimr2": "svimr2",
    "gbh": "gbh", "shmr": "shmr", "muncymr": "muncymr", "jsmr": "jsmr",
    "gr": "gr", "pittstonsola": "pittston-sola", "pittstonvida": "pittston-vida",
    "gcmcsola": "gcmc-sola", "gswbsola": "gswb-sola", "gwvskyra": "gwv-skyra",
    "gmcir3": "gmcir3", "gmcep3": "gmcep3", "gmcep1and2": "gmcep1and2",
}

PROFILE_BASELINES = {
    "mri": "0d939f88b35ab8167ce1e70d91a8611a14f4a6a9631a30677bbe06bb5234a36f",
    "cv": "a7bb0bc02e548f37993345e54cd664ac4d6e3dc47ba0b5525d7402f3a07717aa",
}

SENSOR_RUNTIME_MINIMUMS = {
    "python-dotenv": (1, 0, 0),
    "requests": (2, 31, 0),
    "w1thermsensor": (2, 0, 0),
}

CAMERA_RUNTIME_MINIMUMS = {
    "numpy": (2, 0, 0),
    "Pillow": (11, 0, 0),
    "python-dotenv": (1, 0, 0),
    "requests": (2, 31, 0),
}
CAMERA_RUNTIME_ALLOWED_MAJORS = {
    "numpy": {2},
    "Pillow": {11, 12},
    "python-dotenv": {1},
    "requests": {2},
}
CAMERA_V3_SOURCE_SHA256 = "56cd4b6e69a472d5b93dedb1f75cbde75817ce41d24e2fc47ad66ee6f690cf04"
CAMERA_V3_RUNTIME_FILES = {
    "scheduled_capture.py",
    "retry_failed_sessions.py",
    "run_scheduled_capture.sh",
    "run_retry_check.sh",
}
CAMERA_V3_RUNTIME_HASHES = {
    "scheduled_capture.py": "56cd4b6e69a472d5b93dedb1f75cbde75817ce41d24e2fc47ad66ee6f690cf04",
    "retry_failed_sessions.py": "ef54f6689342c14f9680b1f38f15eac199edc31700cd71558187c80ca753c16f",
    "run_scheduled_capture.sh": "bc8d39b84fbdc147b08f76ec2b52692dc8f4ca8e8101fb3c3922f90c3595b8ec",
    "run_retry_check.sh": "03d5fce36580cb0a165d0e418766889bf7608f65f0eedc685798b1de59c24120",
}
CAMERA_RAM_LOG_REFERENCE_HOST = "gcmcmr2"
CAMERA_RAM_LOG_USER_CRONTAB_TARGETS = {
    "oswmr1",
    "svimr2",
    "muncymr",
    "jsmr",
    "pittstonsola",
    "pittstonvida",
    "gcmcsola",
    "gswbsola",
}
CAMERA_RAM_LOG_CROND_TARGETS = {"oswmr2"}

SOFTWARE_FAMILIES = {
    "0d939f88b35ab8167ce1e70d91a8611a14f4a6a9631a30677bbe06bb5234a36f": {
        "name": "MRI resilient recovery v2", "state": "approved"
    },
    "a26f04323c2dc121d1ccf268814b2aee2dbf866f5f3caa90aedf5cae0c701eb1": {
        "name": "MRI slow-discovery v1", "state": "compatible"
    },
    "d05922dca653f1d939c82ec8459a20ea66694d18e12425523ef14352a30673cf": {
        "name": "MRI legacy static discovery", "state": "legacy"
    },
    "a7bb0bc02e548f37993345e54cd664ac4d6e3dc47ba0b5525d7402f3a07717aa": {
        "name": "CV flexible 5-probe v2", "state": "approved"
    },
    "50237be542ae964a520103effba8be8bbe1f85be7c0c7ade080dd3c34457d832": {
        "name": "CV EP fixed-probe v1", "state": "compatible"
    },
    "cd47128621c06db282a573599b3eefd963d2505d2f7c11276fe19539666cd0cf": {
        "name": "CV IR fixed-probe v1", "state": "compatible"
    },
}

CAMERA_CONVERGENCE_STATUS = {
    "agcmr1": "v3_production_verified",
    "agcmr2": "blocked_special_local_ocr_contract_review",
    "agcmr3": "v3_production_verified",
    "oswmr1": "eligible_after_primary_pilot_observed_upload_preserved",
    "oswmr2": "eligible_after_primary_pilot",
    "svimr2": "eligible_after_primary_pilot",
    "muncymr": "eligible_after_primary_pilot",
    "jsmr": "eligible_after_primary_pilot",
    "pittstonsola": "eligible_after_primary_pilot",
    "pittstonvida": "eligible_after_primary_pilot",
    "gcmcsola": "eligible_after_primary_pilot",
    "gcmcmr2": "eligible_after_primary_pilot_distinct_optics",
    "gswbsola": "eligible_after_primary_pilot",
    "gwvs": "blocked_commissioning_upload_and_schedule_disabled",
}

COMMON_CAMERA_CROP = {"x": 708, "y": 520, "w": 364, "h": 182}


def camera_target_contract(
    *,
    upload_mode: str,
    shutter_us: int,
    gain: float,
    debug_save_images: bool,
    crop: dict[str, int] | None = None,
    upload_enabled: bool | None = True,
) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "upload_mode": upload_mode,
        "shutter_us": shutter_us,
        "gain": gain,
        "debug_save_images": debug_save_images,
        "crop": dict(crop or COMMON_CAMERA_CROP),
    }
    if upload_enabled is not None:
        contract["upload_enabled"] = upload_enabled
    return contract


CAMERA_TARGET_CONTRACTS = {
    "agcmr1": camera_target_contract(upload_mode="full_and_crop", shutter_us=1500, gain=2.5, debug_save_images=True),
    "agcmr3": camera_target_contract(upload_mode="cropped_only", shutter_us=1000, gain=0.5, debug_save_images=False),
    "oswmr1": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=False),
    "oswmr2": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=False),
    "svimr2": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=False),
    "muncymr": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=False),
    "jsmr": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=True),
    "pittstonsola": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=True),
    "pittstonvida": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=False),
    "gcmcsola": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=False),
    "gcmcmr2": camera_target_contract(upload_mode="cropped_only", shutter_us=2500, gain=1.0, debug_save_images=False, crop={"x": 760, "y": 600, "w": 320, "h": 180}),
    "gswbsola": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=False),
    "gwvs": camera_target_contract(upload_mode="cropped_only", shutter_us=1500, gain=2.5, debug_save_images=True, upload_enabled=False),
}

NEARBY_PILOT_HOSTS = {
    "agcmr1", "agcmr2", "agcmr3", "gmcep1and2", "gmcep3", "gmcir3"
}
OS_PRIMARY_PILOT_HOST = "agcmr3"
OS_RECOVERY_CANARY_HOST = "agcmr2"
HEADLESS_OPTIMIZATION_STATUS = {
    "agcmr1": "reboot_verified_observation",
    "agcmr3": "reboot_verified_observation",
    "gbh": "reboot_verified_observation",
    "gmcep1and2": "reboot_verified_observation",
    "gmcep3": "reboot_verified_observation",
    "gmcir3": "reboot_verified_observation",
    "gwvskyra": "reboot_verified_observation",
    "shmr": "reboot_verified_observation",
    "vwm3": "reboot_verified_observation",
}
RUNTIME_POLICY_EXCEPTIONS = {
    "svimr2": {
        "effective_overrides": {
            "discovery_timeout_seconds": 120,
            "rescan_timeout_seconds": 30,
        },
        "reason": (
            "Approved SVI MR2 recovery exception: longer 120-second discovery "
            "and 30-second rescan bounds are retained for this site's sensors."
        ),
    },
}
WIFI_DIAGNOSTIC_NOTES = {
    "agcmr1": (
        "A reversible nearby power-save A/B test on 2026-07-17 kept 0% packet "
        "loss across all four 30-packet samples, held RSSI at -73/-74 dBm, and "
        "showed no latency benefit; leave power saving unchanged and improve "
        "the physical radio path."
    ),
    "gmcep3": (
        "A reversible nearby power-save A/B test on 2026-07-16 kept 0% packet "
        "loss in both modes, did not improve RSSI, and restored the original "
        "setting; leave power saving unchanged and improve the radio path."
    ),
}
SUDO_COMPAT_SHA256 = "7792b751600eb294f6a40b269bab2d1689aba26655e459577be069b85d57d1d9"
HISTORY_CANARIES = {
    "agcmr1": "AGC MR1",
    "agcmr3": "AGC MR3",
    "gmcir3": "GMC IR3",
    "gmcep3": "GMC EP3",
    "gmcep1and2": "GMC EP1/EP2",
}


def report_is_complete(payload: dict[str, Any]) -> bool:
    results = payload.get("results") or []
    return bool(
        len(results) == EXPECTED_HOSTS
        and all(
            item.get("status") in {"ok", "offline_or_unreachable"}
            for item in results
        )
    )


def load_complete_reports(limit: int = 2) -> list[dict[str, Any]]:
    candidates = sorted(REPORT_DIR.glob("audit_*.json"), reverse=True)
    fallback: dict[str, Any] | None = None
    complete = []
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if fallback is None:
            fallback = payload
        if report_is_complete(payload):
            payload["source_file"] = path.name
            complete.append(payload)
            if len(complete) >= limit:
                return complete
    if complete:
        return complete
    if fallback is not None:
        fallback["source_file"] = candidates[0].name if candidates else ""
        fallback["incomplete_report"] = True
        return [fallback]
    return [{"generated_at": None, "summary": {}, "results": [], "source_file": ""}]


def load_latest_complete_report() -> dict[str, Any]:
    return load_complete_reports(1)[0]


def load_latest_inventory_report() -> dict[str, Any]:
    """Load the newest report that accounts for every inventory host.

    Collection failures must remain visible on the fleet page instead of causing
    it to silently fall back to an older complete report.  Strict consumers such
    as health checks and history continue to use ``load_complete_reports``.
    """

    for path in sorted(REPORT_DIR.glob("audit_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if len(payload.get("results") or []) != EXPECTED_HOSTS:
            continue
        payload["source_file"] = path.name
        if not report_is_complete(payload):
            payload["incomplete_report"] = True
        return payload
    return load_latest_complete_report()


def load_restart_recovery_verifications() -> dict[str, dict[str, Any]]:
    """Load only complete, internally consistent automatic-recovery proofs."""

    verified: dict[str, dict[str, Any]] = {}
    for path in sorted(REPORT_DIR.glob("restart_recovery_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        inventory_name = str(payload.get("inventory_name") or "")
        before = payload.get("before") or {}
        after = payload.get("after") or {}
        elapsed = payload.get("recovery_elapsed_ms")
        probe_ids = payload.get("probe_ids") or []
        if (
            payload.get("kind") != "mri_restart_recovery_verification"
            or payload.get("ok") is not True
            or not inventory_name
            or inventory_name in verified
            or not isinstance(elapsed, int)
            or not 12000 <= elapsed <= 45000
            or before.get("MainPID") == after.get("MainPID")
            or not str(before.get("MainPID") or "").isdigit()
            or not str(after.get("MainPID") or "").isdigit()
            or after.get("ActiveState") != "active"
            or after.get("Restart") != "always"
            or after.get("RestartUSec") != "15s"
            or after.get("StartLimitIntervalUSec") != "0"
            or payload.get("application_sha256") != PROFILE_BASELINES["mri"]
            or len(probe_ids) != 5
            or len(set(probe_ids)) != 5
            or int(payload.get("telemetry_after") or 0) <= int(payload.get("telemetry_before") or 0)
        ):
            continue
        verified[inventory_name] = {
            "verified": True,
            "created_at": payload.get("created_at"),
            "elapsed_seconds": round(elapsed / 1000, 3),
            "old_pid": int(before["MainPID"]),
            "new_pid": int(after["MainPID"]),
            "probe_count": len(probe_ids),
            "telemetry_advanced_seconds": int(payload["telemetry_after"]) - int(payload["telemetry_before"]),
            "source_file": path.name,
        }
    return verified


def load_verified_maintenance_actions() -> dict[str, dict[str, Any]]:
    """Load only sanitized, successfully verified package/cache/reboot actions."""

    candidates: list[tuple[datetime, Path, dict[str, Any], dict[str, Any]]] = []
    for pattern in ("update_*.json", "download_*.json", "baseline_*.json", "reboot_*.json"):
        for path in REPORT_DIR.glob(pattern):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            action = str(payload.get("action") or "")
            completed_at = report_time(payload)
            if action not in {"update", "download", "baseline", "reboot"} or completed_at is None:
                continue
            for result in payload.get("results") or []:
                verification = result.get("post_verification") or {}
                inventory_name = str(result.get("inventory_name") or "")
                if (
                    not inventory_name
                    or result.get("status") != "ok"
                    or result.get("mutation_status") != "ok"
                    or verification.get("ok") is not True
                ):
                    continue
                candidates.append((completed_at, path, payload, result))

    verified: dict[str, dict[str, Any]] = {}
    for completed_at, path, payload, result in sorted(candidates, reverse=True, key=lambda item: item[0]):
        inventory_name = str(result["inventory_name"])
        if inventory_name in verified:
            continue
        action = str(payload["action"])
        verification = result.get("post_verification") or {}
        local = verification.get("local") or {}
        package_maintenance = local.get("package_maintenance") or {}
        package_match = re.search(
            r"(\d+) upgraded, (\d+) newly installed, (\d+) to remove",
            str(result.get("mutation_output") or ""),
        )
        package_counts = (
            {
                "upgraded": int(package_match.group(1)),
                "newly_installed": int(package_match.group(2)),
                "removed": int(package_match.group(3)),
            }
            if package_match and action != "download"
            else None
        )
        cached_eligible = (
            package_maintenance.get("eligible_count")
            if action == "download"
            else None
        )
        reboot_requested = (
            local.get("reboot_requested") is True
            if "reboot_requested" in local
            else action == "reboot"
        )
        # Older no-reboot update reports used reboot_observed as a requirement-
        # satisfied flag. Only a reboot action can be literal reboot evidence.
        reboot_observed = bool(reboot_requested and local.get("reboot_observed") is True)
        verified[inventory_name] = {
            "action": action,
            "completed_at": completed_at.isoformat(),
            "source_file": path.name,
            "packages_changed": package_counts,
            "packages_cached": action == "download",
            "cached_eligible": cached_eligible,
            "packages_remaining": {
                "listed": package_maintenance.get("listed_count"),
                "eligible": package_maintenance.get("eligible_count"),
                "deferred": package_maintenance.get("deferred_count"),
            },
            "reboot_requested": reboot_requested,
            "reboot_observed": reboot_observed,
            "kernel_before": local.get("pre_kernel"),
            "kernel_after": local.get("post_kernel") or local.get("kernel"),
            "kernel_advanced": local.get("kernel_advanced") is True,
            "application_preserved": local.get("application_preserved") is True,
            "probe_count": local.get("probe_count"),
            "service_active": local.get("service_active") is True,
            "throttle_flags": local.get("throttle_flags"),
            "telemetry_advanced": verification.get("telemetry_advanced") is True,
            "telemetry_not_required": verification.get("telemetry_not_required") is True,
        }
    return verified


def load_verified_package_downloads() -> dict[str, dict[str, Any]]:
    """Keep cache evidence independent from a later install/reboot action."""
    cached: dict[str, dict[str, Any]] = {}
    for path in sorted(REPORT_DIR.glob("download_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        completed_at = report_time(payload)
        if payload.get("action") != "download" or completed_at is None:
            continue
        for result in payload.get("results") or []:
            inventory_name = str(result.get("inventory_name") or "")
            verification = result.get("post_verification") or {}
            if (
                not inventory_name
                or inventory_name in cached
                or result.get("status") != "ok"
                or result.get("mutation_status") != "ok"
                or verification.get("ok") is not True
            ):
                continue
            package_maintenance = (verification.get("local") or {}).get("package_maintenance") or {}
            cached[inventory_name] = {
                "verified": True,
                "completed_at": completed_at.isoformat(),
                "source_file": path.name,
                "eligible": package_maintenance.get("eligible_count"),
                "listed": package_maintenance.get("listed_count"),
                "deferred": package_maintenance.get("deferred_count"),
                "installation_performed": False,
                "reboot_performed": False,
            }
    return cached


def assess_current_package_cache(
    facts: dict[str, Any],
    download_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind historical download evidence to the cache observed in this audit."""

    observed = facts.get("package_cache") or {}
    candidate_count = int(observed.get("candidate_count") or 0)
    cached_count = int(observed.get("cached_candidate_count") or 0)
    missing = sorted(str(name) for name in (observed.get("missing_candidate_names") or []))
    verified = bool(
        observed.get("assessed") is True
        and observed.get("complete") is True
        and cached_count == candidate_count
        and not missing
    )
    evidence = download_evidence or {}
    return {
        "verified": verified,
        "assessed": observed.get("assessed") is True,
        "eligible": candidate_count,
        "cached_eligible": cached_count,
        "missing_candidate_names": missing,
        "archive_count": int(observed.get("archive_count") or 0),
        "archive_bytes": int(observed.get("archive_bytes") or 0),
        "completed_at": evidence.get("completed_at"),
        "source_file": evidence.get("source_file"),
        "download_transaction_verified": evidence.get("verified") is True,
        "installation_performed": False,
        "reboot_performed": False,
    }


def load_camera_observations() -> dict[str, dict[str, Any]]:
    """Load the newest passing production-schedule proof for each camera host."""

    observations: dict[str, dict[str, Any]] = {}
    for path in sorted(REPORT_DIR.glob("camera_observation_*.json"), reverse=True):
        if "_baseline_" in path.name:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        inventory_name = str(payload.get("inventory_name") or "")
        checks = payload.get("checks") or {}
        session = payload.get("camera_session") or {}
        upload_count = session.get("count")
        if (
            payload.get("kind") != "camera_schedule_verification"
            or payload.get("ok") is not True
            or not checks
            or not all(value is True for value in checks.values())
            or not isinstance(upload_count, int)
            or upload_count <= 0
            or session.get("ordinals") != list(range(1, upload_count + 1))
            or len(session.get("records") or []) != upload_count
            or not inventory_name
            or inventory_name in observations
        ):
            continue
        observations[inventory_name] = {
            "passed": True,
            "created_at": payload.get("created_at"),
            "source_file": path.name,
            "session_id": session.get("session_id"),
            "upload_count": upload_count,
            "last_timestamp": session.get("last_timestamp"),
            "expected_source": payload.get("expected_source"),
            "camera_fingerprint": ((payload.get("after") or {}).get("camera") or {}).get("fingerprint"),
            "camera_core_hashes": ((payload.get("after") or {}).get("camera") or {}).get("core_hashes") or {},
        }
    for path in sorted(REPORT_DIR.glob("camera_observation_baseline_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        inventory_name = str(payload.get("inventory_name") or "")
        checks = payload.get("checks") or {}
        if (
            payload.get("kind") != "camera_schedule_baseline"
            or payload.get("ok") is not True
            or not checks
            or not all(value is True for value in checks.values())
            or not inventory_name
            or inventory_name in observations
        ):
            continue
        observations[inventory_name] = {
            "passed": False,
            "pending": True,
            "created_at": payload.get("created_at"),
            "source_file": path.name,
            "not_before": payload.get("not_before"),
            "expected_upload_count": payload.get("expected_upload_count"),
        }
    for path in sorted(REPORT_DIR.glob("camera_observation_plan_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            baseline_at = datetime.fromisoformat(str(payload.get("baseline_at") or ""))
            not_before = datetime.fromisoformat(str(payload.get("not_before") or ""))
            complete_at = datetime.fromisoformat(str(payload.get("complete_at") or ""))
            expires_at = datetime.fromisoformat(str(payload.get("expires_at") or ""))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        inventory_name = str(payload.get("inventory_name") or "")
        expected_count = payload.get("expected_upload_count")
        if (
            payload.get("kind") != "camera_schedule_plan"
            or payload.get("schema") != 1
            or not inventory_name
            or inventory_name in observations
            or not isinstance(expected_count, int)
            or expected_count <= 0
            or any(value.tzinfo is None for value in (baseline_at, not_before, complete_at, expires_at))
            or not baseline_at < not_before < complete_at < expires_at
        ):
            continue
        expired = time.time() > expires_at.timestamp()
        observations[inventory_name] = {
            "passed": False,
            "planned": True,
            "pending": not expired,
            "expired": expired,
            "created_at": payload.get("created_at"),
            "source_file": path.name,
            "baseline_at": baseline_at.isoformat(),
            "not_before": not_before.isoformat(),
            "complete_at": complete_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "expected_upload_count": expected_count,
        }
    return observations


def camera_hash_lines(lines: Any) -> dict[str, str]:
    """Parse the bounded sha256sum evidence emitted by the camera canary."""

    if not isinstance(lines, list):
        return {}
    hashes: dict[str, str] = {}
    for line in lines:
        fields = str(line).split(maxsplit=1)
        if len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{64}", fields[0]):
            return {}
        name = Path(fields[1].lstrip("* ")).name
        if name in hashes:
            return {}
        hashes[name] = fields[0]
    return hashes


def load_camera_candidate_canaries() -> dict[str, dict[str, Any]]:
    """Load only complete, contract-bound, non-mutating camera canary proofs."""

    canaries: dict[str, dict[str, Any]] = {}
    required_safety = {
        "both_primary_natural_proofs",
        "exact_probes_before",
        "exact_probes_after",
        "sensor_active_before",
        "sensor_active_after",
        "zero_throttle_before",
        "zero_throttle_after",
        "production_hashes_unchanged",
    }
    for path in sorted(REPORT_DIR.glob("camera_v3_candidate_canary_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(str(payload.get("created_at") or ""))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        inventory_name = str(payload.get("inventory_name") or "")
        safety = payload.get("safety") or {}
        capture = payload.get("capture") or {}
        backup = payload.get("backup") or {}
        telemetry = payload.get("telemetry") or {}
        before_hashes = camera_hash_lines(payload.get("production_hashes_before"))
        after_hashes = camera_hash_lines(payload.get("production_hashes_after"))
        expected_contract = CAMERA_TARGET_CONTRACTS.get(inventory_name)
        base_status = CAMERA_CONVERGENCE_STATUS.get(inventory_name, "")
        if (
            payload.get("kind") != "camera_v3_candidate_canary"
            or payload.get("schema") != 1
            or payload.get("passed") is not True
            or created_at.tzinfo is None
            or not base_status.startswith("eligible_after_primary_pilot")
            or inventory_name in canaries
            or payload.get("canonical_version") != "3.0.0"
            or payload.get("candidate_source_sha256") != CAMERA_V3_SOURCE_SHA256
            or not expected_contract
            or payload.get("target_contract") != expected_contract
            or capture.get("requested") != 1
            or capture.get("captured") != 1
            or capture.get("uploaded") != 0
            or capture.get("upload_enabled") is not False
            or not str(capture.get("ram_workspace") or "").startswith("/dev/shm/")
            or not required_safety.issubset(safety)
            or not all(safety.get(key) is True for key in required_safety)
            or safety.get("sensor_restarted") is not False
            or safety.get("rebooted") is not False
            or backup.get("activity_recent") is not True
            or backup.get("restore_status") != "success"
            or backup.get("restore_recent") is not True
            or not str(backup.get("restore_snapshot_id") or "")
            or set(before_hashes) != CAMERA_V3_RUNTIME_FILES
            or before_hashes != after_hashes
            or telemetry.get("advanced") is not True
            or telemetry.get("offline_after") is not False
            or not isinstance(telemetry.get("before_timestamp"), int)
            or not isinstance(telemetry.get("after_timestamp"), int)
            or telemetry["after_timestamp"] <= telemetry["before_timestamp"]
        ):
            continue
        canaries[inventory_name] = {
            "passed": True,
            "created_at": created_at.isoformat(),
            "source_file": path.name,
            "candidate_source_sha256": payload["candidate_source_sha256"],
            "target_contract": expected_contract,
            "backup_repository": payload.get("backup_repository"),
            "restore_snapshot_id": backup["restore_snapshot_id"],
            "production_hashes": before_hashes,
            "telemetry_advanced_seconds": (
                telemetry["after_timestamp"] - telemetry["before_timestamp"]
            ),
            "no_sensor_restart": True,
            "no_reboot": True,
        }
    return canaries


def candidate_canary_matches_current_camera(
    canary: dict[str, Any], software: dict[str, Any]
) -> bool:
    """Reject a canary after any of the four production runtime files changes."""

    current_hashes = {
        name: str(((software.get("core_files") or {}).get(name) or {}).get("sha256") or "")
        for name in CAMERA_V3_RUNTIME_FILES
    }
    return bool(
        canary.get("passed") is True
        and canary.get("production_hashes") == current_hashes
        and all(current_hashes.values())
    )


def load_camera_candidate_deployments() -> dict[str, dict[str, Any]]:
    """Load successful v3 installs that still require a natural schedule proof."""

    deployments: dict[str, dict[str, Any]] = {}
    required_safety = {
        "schedule_unchanged",
        "exact_probes_after",
        "sensor_active_after",
        "zero_throttle_after",
        "rollback_staged",
    }
    for path in sorted(
        REPORT_DIR.glob("camera_v3_candidate_deployment_*.json"), reverse=True
    ):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            created_at = datetime.fromisoformat(str(payload.get("created_at") or ""))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        inventory_name = str(payload.get("inventory_name") or "")
        base_status = CAMERA_CONVERGENCE_STATUS.get(inventory_name, "")
        expected_contract = CAMERA_TARGET_CONTRACTS.get(inventory_name)
        capture = payload.get("capture") or {}
        safety = payload.get("safety") or {}
        telemetry = payload.get("telemetry") or {}
        if (
            payload.get("kind") != "camera_v3_candidate_deployment"
            or payload.get("schema") != 1
            or payload.get("passed") is not True
            or created_at.tzinfo is None
            or not base_status.startswith("eligible_after_primary_pilot")
            or inventory_name in deployments
            or payload.get("canonical_version") != "3.0.0"
            or payload.get("candidate_source_sha256") != CAMERA_V3_SOURCE_SHA256
            or not expected_contract
            or payload.get("target_contract") != expected_contract
            or payload.get("installed_hashes") != CAMERA_V3_RUNTIME_HASHES
            or not str(payload.get("canary_source_file") or "").startswith(
                "camera_v3_candidate_canary_"
            )
            or not str(payload.get("restore_snapshot_id") or "")
            or payload.get("natural_proof_pending") is not True
            or capture.get("requested") != 1
            or capture.get("captured") != 1
            or capture.get("uploaded") != 0
            or capture.get("upload_enabled") is not False
            or not str(capture.get("ram_workspace") or "").startswith("/dev/shm/")
            or not required_safety.issubset(safety)
            or not all(safety.get(key) is True for key in required_safety)
            or safety.get("sensor_restarted") is not False
            or safety.get("rebooted") is not False
            or telemetry.get("advanced") is not True
            or not isinstance(telemetry.get("before_timestamp"), int)
            or not isinstance(telemetry.get("after_timestamp"), int)
            or telemetry["after_timestamp"] <= telemetry["before_timestamp"]
        ):
            continue
        deployments[inventory_name] = {
            "passed": True,
            "natural_proof_pending": True,
            "created_at": created_at.isoformat(),
            "source_file": path.name,
            "canary_source_file": payload["canary_source_file"],
            "candidate_source_sha256": payload["candidate_source_sha256"],
            "target_contract": expected_contract,
            "installed_hashes": dict(CAMERA_V3_RUNTIME_HASHES),
            "backup_repository": payload.get("backup_repository"),
            "restore_snapshot_id": payload["restore_snapshot_id"],
            "telemetry_advanced_seconds": (
                telemetry["after_timestamp"] - telemetry["before_timestamp"]
            ),
            "schedule_unchanged": True,
            "no_sensor_restart": True,
            "no_reboot": True,
        }
    return deployments


def candidate_deployment_matches_current_camera(
    deployment: dict[str, Any], software: dict[str, Any]
) -> bool:
    """Bind pending-natural-proof state to the exact installed v3 files."""

    current_hashes = {
        name: str(((software.get("core_files") or {}).get(name) or {}).get("sha256") or "")
        for name in CAMERA_V3_RUNTIME_FILES
    }
    return bool(
        deployment.get("passed") is True
        and deployment.get("installed_hashes") == current_hashes
        and current_hashes == CAMERA_V3_RUNTIME_HASHES
    )


def camera_proof_matches_software(observation: dict[str, Any], software: dict[str, Any]) -> bool:
    """Bind a schedule proof to the exact camera build currently audited."""

    proof_fingerprint = str(observation.get("camera_fingerprint") or "")
    current_fingerprint = str(software.get("fingerprint") or "")
    proof_hashes = observation.get("camera_core_hashes") or {}
    current_hashes = {
        str(name): str(details.get("sha256") or "")
        for name, details in (software.get("core_files") or {}).items()
        if details.get("sha256")
    }
    return bool(
        observation.get("passed") is True
        and proof_fingerprint
        and proof_fingerprint == current_fingerprint
        and proof_hashes
        and proof_hashes == current_hashes
    )


def load_os_upgrade_readiness() -> dict[str, dict[str, Any]]:
    """Load the newest guarded OS-upgrade readiness record for each host."""

    readiness: dict[str, dict[str, Any]] = {}
    for path in sorted(REPORT_DIR.glob("os_upgrade_readiness_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        snapshot = payload.get("snapshot") or {}
        inventory_name = str(snapshot.get("inventory_name") or "")
        if (
            payload.get("kind") != "os_upgrade_baseline"
            or payload.get("schema") != 1
            or not inventory_name
            or inventory_name in readiness
        ):
            continue
        readiness[inventory_name] = {
            "ready": payload.get("ready") is True,
            "blockers": payload.get("blockers") or [],
            "created_at": payload.get("created_at"),
            "target_codename": payload.get("target_codename"),
            "repository": payload.get("repository"),
            "restore_test": payload.get("restore_test") or {},
            "preflight_age_minutes": payload.get("preflight_age_minutes"),
            "source_file": path.name,
            "sensor_runtime_complete": (snapshot.get("sensor_runtime") or {}).get("complete"),
            "camera_installed": snapshot.get("camera_installed"),
            "camera_runtime_complete": (snapshot.get("camera_runtime") or {}).get("complete"),
        }
    return readiness


def load_os_upgrade_verifications() -> dict[str, dict[str, Any]]:
    """Load the newest passing strict release-upgrade proof for each host."""

    verified: dict[str, dict[str, Any]] = {}
    for path in sorted(REPORT_DIR.glob("os_upgrade_verification_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        inventory_name = str(payload.get("inventory_name") or "")
        checks = payload.get("checks") or []
        if (
            payload.get("kind") != "os_upgrade_verification"
            or payload.get("schema") != 1
            or payload.get("passed") is not True
            or not inventory_name
            or inventory_name in verified
            or not checks
            or not all(item.get("passed") is True for item in checks)
        ):
            continue
        after = payload.get("after") or {}
        verified[inventory_name] = {
            "passed": True,
            "created_at": payload.get("created_at"),
            "source_file": path.name,
            "check_count": len(checks),
            "os": after.get("os"),
            "codename": after.get("codename"),
            "sensor_runtime_complete": (after.get("sensor_runtime") or {}).get("complete"),
            "camera_installed": after.get("camera_installed"),
            "camera_runtime_complete": (after.get("camera_runtime") or {}).get("complete"),
        }
    return verified


def load_optimization_observation() -> dict[str, Any]:
    path = REPORT_DIR / "optimization_observation.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"cohort_ready": False, "hosts": {}, "note": "optimization evidence unavailable"}
    if payload.get("kind") != "optimization_observation" or payload.get("schema") != 1:
        return {"cohort_ready": False, "hosts": {}, "note": "optimization evidence invalid"}
    return payload


def load_last_known_facts() -> dict[str, Any]:
    path = REPORT_DIR / "fleet_last_known.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"hosts": {}, "note": "historical context unavailable"}
    if payload.get("kind") != "fleet_last_known" or payload.get("schema") != 1:
        return {"hosts": {}, "note": "historical context invalid"}
    return payload


def report_time(payload: dict[str, Any]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(payload.get("generated_at"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=FLEET_TIMEZONE) if parsed.tzinfo is None else parsed


def load_storage_maintenance_windows(
    report_dir: Path = REPORT_DIR,
) -> dict[str, list[tuple[datetime, datetime]]]:
    """Load host-specific package activity windows for SSD-rate filtering."""

    windows: dict[str, list[tuple[datetime, datetime]]] = {}
    for pattern in ("update_*.json", "baseline_*.json", "download_*.json"):
        for path in report_dir.glob(pattern):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            completed = report_time(payload)
            if completed is None:
                continue
            for result in payload.get("results") or []:
                inventory_name = str(result.get("inventory_name") or "")
                if not inventory_name:
                    continue
                started = report_time({"generated_at": result.get("action_started_at")})
                finished = report_time({"generated_at": result.get("action_finished_at")})
                start = started or completed - timedelta(minutes=30)
                finish = finished or completed
                if finish >= start:
                    windows.setdefault(inventory_name, []).append((start, finish))
    return windows


def interval_overlaps_maintenance(
    older_time: datetime | None,
    current_time: datetime | None,
    windows: list[tuple[datetime, datetime]] | None,
) -> bool:
    return bool(
        older_time is not None
        and current_time is not None
        and any(start < current_time and finish > older_time for start, finish in (windows or []))
    )


def fleet_health(now: datetime | None = None) -> tuple[dict[str, Any], HTTPStatus]:
    """Report controller health only when complete fleet evidence is current."""

    report = load_latest_complete_report()
    generated_at = report_time(report)
    if report.get("incomplete_report") or not report_is_complete(report) or generated_at is None:
        return {"status": "unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=FLEET_TIMEZONE)
    age_seconds = max(0, int((current - generated_at).total_seconds()))
    if age_seconds > FLEET_HEALTH_MAX_AGE_SECONDS:
        return {
            "status": "stale",
            "report_age_seconds": age_seconds,
        }, HTTPStatus.SERVICE_UNAVAILABLE
    return {
        "status": "ok",
        "report_age_seconds": age_seconds,
    }, HTTPStatus.OK


def previous_sample_report(
    reports: list[dict[str, Any]], minimum_seconds: int = 300
) -> dict[str, Any]:
    """Return the nearest report far enough back for a meaningful rate sample."""

    if not reports:
        return {}
    current_time = report_time(reports[0])
    if current_time is None:
        return {}
    for candidate in reports[1:]:
        candidate_time = report_time(candidate)
        if candidate_time and (current_time - candidate_time).total_seconds() >= minimum_seconds:
            return candidate
    return {}


def add_storage_write_rate(host: dict[str, Any], previous: dict[str, Any], sample_seconds: float | None) -> None:
    storage = (host.get("facts") or {}).get("storage_health") or {}
    previous_storage = ((previous.get("facts") or {}).get("storage_health") or {})
    current_bytes = storage.get("bytes_written_since_boot")
    previous_bytes = previous_storage.get("bytes_written_since_boot")
    current_uptime = (host.get("facts") or {}).get("uptime_seconds")
    previous_uptime = (previous.get("facts") or {}).get("uptime_seconds")
    if (
        sample_seconds
        and sample_seconds >= 300
        and storage.get("root_block_device") == previous_storage.get("root_block_device")
        and isinstance(current_bytes, int)
        and isinstance(previous_bytes, int)
        and current_bytes >= previous_bytes
        and isinstance(current_uptime, int)
        and isinstance(previous_uptime, int)
        and current_uptime > previous_uptime
    ):
        delta_bytes = current_bytes - previous_bytes
        storage["write_rate_sample_seconds"] = round(sample_seconds)
        storage["bytes_written_in_sample"] = delta_bytes
        storage["recent_mib_written_per_day"] = round(
            delta_bytes / 1048576 / sample_seconds * 86400, 1
        )


def package_state_signature(host: dict[str, Any]) -> tuple[int, int, int] | None:
    package_maintenance = (host.get("facts") or {}).get("package_maintenance") or {}
    if not package_maintenance:
        return None
    try:
        return tuple(
            int(package_maintenance.get(name, 0))
            for name in ("listed_count", "eligible_count", "deferred_count")
        )
    except (TypeError, ValueError):
        return None


def quiet_write_window(hosts: list[dict[str, Any]]) -> bool:
    """Reject package refresh/upgrade activity from SSD-wear observations."""

    if any(
        (((host.get("facts") or {}).get("package_manager") or {}).get("busy") is True)
        for host in hosts
    ):
        return False
    signatures = [package_state_signature(host) for host in hosts]
    known = [signature for signature in signatures if signature is not None]
    # Preserve compatibility with older audits that predate package-state facts.
    if not known:
        return True
    return len(known) == len(hosts) and len(set(known)) == 1


def report_window_hosts(
    reports: list[dict[str, Any]], inventory_name: str, start: int, stop: int
) -> list[dict[str, Any]]:
    return [
        host
        for report in reports[start:stop]
        for host in (report.get("results") or [])
        if host.get("inventory_name") == inventory_name
    ]


def rsyslog_pilot_epoch(host: dict[str, Any]) -> float | None:
    value = (
        (((host.get("facts") or {}).get("ram_optimization") or {}).get("rsyslog_ram_pilot") or {})
        .get("applied_epoch")
    )
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def interval_after_rsyslog_change(
    current_host: dict[str, Any], older_time: datetime | None
) -> bool:
    """Reject an interval whose older endpoint predates the active pilot."""

    applied_epoch = rsyslog_pilot_epoch(current_host)
    return not (
        applied_epoch is not None
        and older_time is not None
        and older_time.timestamp() < applied_epoch
    )


def interval_crosses_epoch(
    older_time: datetime | None,
    current_time: datetime | None,
    applied_epoch: float | None,
) -> bool:
    return bool(
        older_time is not None
        and current_time is not None
        and applied_epoch is not None
        and older_time.timestamp() < applied_epoch <= current_time.timestamp()
    )


def add_storage_write_trend(
    host: dict[str, Any],
    reports: list[dict[str, Any]],
    max_samples: int = 4,
    maintenance_windows: list[tuple[datetime, datetime]] | None = None,
) -> None:
    """Attach non-overlapping valid write intervals for one host.

    Each sample uses two complete audits at least five minutes apart, then moves
    the cursor to the older audit so a burst is not counted repeatedly through
    overlapping cumulative windows.
    """

    inventory_name = host.get("inventory_name")
    active_rsyslog_boundary = rsyslog_pilot_epoch(host)
    rates: list[float] = []
    intervals: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(reports) - 1 and len(rates) < max_samples:
        current_report = reports[cursor]
        current_time = report_time(current_report)
        if current_time is None:
            cursor += 1
            continue
        older_index = None
        older_time = None
        for index in range(cursor + 1, len(reports)):
            candidate_time = report_time(reports[index])
            if candidate_time and (current_time - candidate_time).total_seconds() >= 300:
                older_index = index
                older_time = candidate_time
                break
        if older_index is None or older_time is None:
            break
        if (
            active_rsyslog_boundary is not None
            and older_time.timestamp() < active_rsyslog_boundary
        ):
            break
        if not quiet_write_window(
            report_window_hosts(reports, str(inventory_name or ""), cursor, older_index + 1)
        ):
            break
        if interval_overlaps_maintenance(older_time, current_time, maintenance_windows):
            cursor = older_index
            continue
        current_host = next(
            (item for item in (current_report.get("results") or []) if item.get("inventory_name") == inventory_name),
            None,
        )
        older_host = next(
            (item for item in (reports[older_index].get("results") or []) if item.get("inventory_name") == inventory_name),
            None,
        )
        if current_host and older_host:
            sample_host = copy.deepcopy(current_host)
            sample_seconds = (current_time - older_time).total_seconds()
            add_storage_write_rate(sample_host, older_host, sample_seconds)
            rate = (((sample_host.get("facts") or {}).get("storage_health") or {}).get("recent_mib_written_per_day"))
            if isinstance(rate, (int, float)):
                rates.append(float(rate))
                intervals.append({
                    "ended_at": current_time.isoformat(),
                    "sample_seconds": round(sample_seconds),
                    "mib_written_per_day": rate,
                })
        cursor = older_index

    storage = (host.get("facts") or {}).get("storage_health") or {}
    median_rate = round(statistics.median(rates), 1) if rates else None
    storage["write_trend"] = {
        "sample_count": len(rates),
        "median_mib_written_per_day": median_rate,
        "sustained_elevated": bool(len(rates) >= 3 and median_rate is not None and median_rate >= 1024),
        "sustained_high": bool(len(rates) >= 3 and median_rate is not None and median_rate >= 5120),
        "intervals": intervals,
    }


def add_storage_unsafe_delta(host: dict[str, Any], previous: dict[str, Any]) -> None:
    """Compare the cumulative unsafe-shutdown counter to the nearest audit.

    Unlike write-rate evidence, this counter needs no minimum time interval. Using
    the nearest complete report lets a clean post-reboot audit clear the observation
    instead of carrying it until an older five-minute rate baseline ages out.
    """

    storage = (host.get("facts") or {}).get("storage_health") or {}
    previous_storage = ((previous.get("facts") or {}).get("storage_health") or {})
    current_smart = storage.get("smart") or {}
    previous_smart = previous_storage.get("smart") or {}
    current_unsafe = current_smart.get("unsafe_shutdowns")
    previous_unsafe = previous_smart.get("unsafe_shutdowns")
    current_uptime = (host.get("facts") or {}).get("uptime_seconds")
    previous_uptime = (previous.get("facts") or {}).get("uptime_seconds")
    if (
        storage.get("serial")
        and storage.get("serial") == previous_storage.get("serial")
        and isinstance(current_unsafe, int)
        and isinstance(previous_unsafe, int)
        and current_unsafe >= previous_unsafe
    ):
        storage["unsafe_shutdowns_delta"] = current_unsafe - previous_unsafe
        storage["unsafe_shutdowns_interval_reboot"] = bool(
            isinstance(current_uptime, int)
            and isinstance(previous_uptime, int)
            and current_uptime < previous_uptime
        )


def fleet_history_payload(limit: int = 96) -> dict[str, Any]:
    reports = list(reversed(load_complete_reports(limit)))
    if not reports or reports[0].get("incomplete_report"):
        return {
            "points": [],
            "canaries": HISTORY_CANARIES,
            "sample_count": 0,
            "expected_hosts": EXPECTED_HOSTS,
        }

    maintenance_windows = load_storage_maintenance_windows()
    rsyslog_boundaries: dict[str, float] = {}
    for report in reports:
        for host in report.get("results") or []:
            name = str(host.get("inventory_name") or "")
            epoch = rsyslog_pilot_epoch(host)
            if name and epoch is not None:
                rsyslog_boundaries[name] = max(epoch, rsyslog_boundaries.get(name, 0))

    points = []
    for index, report in enumerate(reports):
        timestamp = report_time(report)
        if timestamp is None:
            continue
        current_hosts = {
            item.get("inventory_name"): item for item in (report.get("results") or [])
        }
        previous = None
        previous_index = None
        previous_timestamp = None
        for candidate_index in range(index - 1, -1, -1):
            candidate = reports[candidate_index]
            candidate_timestamp = report_time(candidate)
            if candidate_timestamp and (timestamp - candidate_timestamp).total_seconds() >= 300:
                previous = candidate
                previous_index = candidate_index
                previous_timestamp = candidate_timestamp
                break
        previous_hosts = {
            item.get("inventory_name"): item for item in ((previous or {}).get("results") or [])
        }
        sample_seconds = (
            (timestamp - previous_timestamp).total_seconds()
            if previous_timestamp is not None
            else None
        )
        rates: dict[str, float | None] = {}
        for name in HISTORY_CANARIES:
            current_host = current_hosts.get(name)
            previous_host = previous_hosts.get(name)
            if not current_host or not previous_host:
                rates[name] = None
                continue
            sample_host = copy.deepcopy(current_host)
            if not interval_crosses_epoch(
                previous_timestamp,
                timestamp,
                rsyslog_boundaries.get(name),
            ) and not interval_overlaps_maintenance(
                previous_timestamp,
                timestamp,
                maintenance_windows.get(name),
            ) and previous_index is not None and quiet_write_window(
                report_window_hosts(reports, name, previous_index, index + 1)
            ):
                add_storage_write_rate(sample_host, previous_host, sample_seconds)
            rate = (((sample_host.get("facts") or {}).get("storage_health") or {}).get("recent_mib_written_per_day"))
            rates[name] = rate if isinstance(rate, (int, float)) else None

        signals = []
        for host in current_hosts.values():
            if host.get("status") != "ok":
                continue
            signal = routed_wifi_signal(host.get("facts") or {})
            if signal is not None:
                signals.append(signal)
        points.append({
            "timestamp": timestamp.isoformat(),
            "online": sum(item.get("status") == "ok" for item in current_hosts.values()),
            "offline": sum(item.get("status") != "ok" for item in current_hosts.values()),
            "wifi_critical": sum(value <= -75 for value in signals),
            "wifi_marginal": sum(-75 < value <= -67 for value in signals),
            "sample_seconds": round(sample_seconds) if sample_seconds is not None else None,
            "write_mib_per_day": rates,
            "source_file": report.get("source_file", ""),
        })

    return {
        "points": points,
        "canaries": HISTORY_CANARIES,
        "sample_count": sum(
            value is not None
            for point in points
            for value in point["write_mib_per_day"].values()
        ),
        "first_at": points[0]["timestamp"] if points else None,
        "last_at": points[-1]["timestamp"] if points else None,
        "retention": min(limit, 96),
        "expected_hosts": EXPECTED_HOSTS,
        "note": "Write rates use same-device monotonic counters, increasing uptime, and samples of at least five minutes. Missing or reboot-crossing intervals are gaps, not zeroes.",
    }


def fetch_json(url: str) -> Any:
    try:
        with urllib.request.urlopen(url, timeout=4) as response:
            return json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []


def latest_camera_ingest_by_site(payload: Any) -> dict[str, dict[str, Any]]:
    """Index the newest raw camera-server record for each camera base site."""

    latest: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return latest
    for item in payload["items"]:
        if not isinstance(item, dict):
            continue
        site_id = str(item.get("site_id") or "")
        base_site = site_id.split("_", 1)[0].upper()
        timestamp = item.get("timestamp")
        if not base_site or not isinstance(timestamp, (int, float)):
            continue
        current = latest.get(base_site)
        if current is None or timestamp > current.get("timestamp", 0):
            latest[base_site] = item
    return latest


def production_pressure_by_site(payload: Any) -> dict[str, dict[str, Any]]:
    """Index production website pressure records by canonical site id."""

    if not isinstance(payload, list):
        return {}
    return {
        str(item.get("site_id") or "").upper(): item
        for item in payload
        if isinstance(item, dict) and item.get("site_id")
    }


def camera_pipeline_telemetry(
    *,
    camera_site_id: str,
    production_site_id: str,
    camera_backend_available: bool,
    production_backend_available: bool,
    camera_latest: dict[str, dict[str, Any]],
    production_latest: dict[str, dict[str, Any]],
    now: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep raw image ingestion separate from successful production posting."""

    current_time = time.time() if now is None else now
    ingest_item = camera_latest.get(camera_site_id.upper())
    ingest_timestamp = ingest_item.get("timestamp") if ingest_item else None
    ingest_matched = isinstance(ingest_timestamp, (int, float))
    ingest = {
        "backend_available": camera_backend_available,
        "matched": ingest_matched if camera_backend_available else None,
        "site_id": ingest_item.get("site_id") if ingest_item else camera_site_id,
        "timestamp": ingest_timestamp,
        "age_hours": (
            round(max(0, current_time - ingest_timestamp) / 3600, 1)
            if ingest_matched
            else None
        ),
        "source": ingest_item.get("source") if ingest_item else None,
        "status_text": ingest_item.get("status_text") if ingest_item else None,
        "return_pressure": ingest_item.get("return_pressure") if ingest_item else None,
    }

    production_item = production_latest.get(production_site_id.upper())
    production_timestamp = (
        production_item.get("timestamp") if production_item else None
    )
    production_matched = isinstance(production_timestamp, (int, float))
    production = {
        "backend_available": production_backend_available,
        "matched": production_matched if production_backend_available else None,
        "site_id": (
            production_item.get("site_id") if production_item else production_site_id
        ),
        "timestamp": production_timestamp,
        "age_hours": (
            round(max(0, current_time - production_timestamp) / 3600, 1)
            if production_matched
            else None
        ),
        "received_at": (
            production_item.get("received_at") if production_item else None
        ),
        "source": "production_return_pressure",
        "return_pressure": (
            production_item.get("return_pressure") if production_item else None
        ),
        "array_lowest_pressure": (
            production_item.get("array_lowest_pressure")
            if production_item
            else None
        ),
    }
    return ingest, production


def signal_grade(signal: float | None) -> str:
    if signal is None:
        return "unknown"
    if signal <= -75:
        return "critical"
    if signal <= -67:
        return "weak"
    return "good"


def routed_wifi_details(facts: dict[str, Any]) -> dict[str, Any] | None:
    """Return details for the Wi-Fi interface carrying the default route."""

    wifi = facts.get("wifi") or []
    route = str(facts.get("route") or "")
    match = re.search(r"^default\b.*\bdev\s+(\S+)", route, re.M)
    if match:
        interface = match.group(1)
        routed = next(
            (
                item for item in wifi
                if item.get("interface") == interface
                and item.get("signal_dbm") is not None
            ),
            None,
        )
        if routed is not None:
            return routed
    connected = [item for item in wifi if item.get("signal_dbm") is not None]
    return max(connected, key=lambda item: item["signal_dbm"]) if connected else None


def routed_wifi_signal(facts: dict[str, Any]) -> float | None:
    details = routed_wifi_details(facts)
    return details.get("signal_dbm") if details else None


def probe_mapping_evidence(facts: dict[str, Any], profile: str) -> dict[str, Any]:
    values = ((facts.get("sensor_config") or {}).get("values") or {})
    pattern = re.compile(r"^SENSOR_\d+_ID$" if profile == "cv" else r"^PROBE_.+_ID$")
    expected_ids = sorted({
        str(value).strip()
        for key, value in values.items()
        if pattern.match(str(key)) and str(value).strip()
    })
    sensors = facts.get("one_wire") or {}
    physical_ids = sorted(set(sensors.get("sensor_ids") or []))
    count = int(sensors.get("count") or len(physical_ids))
    minimum = 3 if profile == "cv" else 4
    exact = bool(expected_ids)
    complete = set(expected_ids) == set(physical_ids) if exact else count >= minimum
    return {
        "complete": complete,
        "exact": exact,
        "count": count,
        "expected_count": len(expected_ids) if exact else minimum,
        "configured_ids": expected_ids,
        "physical_ids": physical_ids,
        "missing": sorted(set(expected_ids) - set(physical_ids)) if exact else [],
        "unexpected": sorted(set(physical_ids) - set(expected_ids)) if exact else [],
    }


def calibration_mapping_evidence(facts: dict[str, Any], profile: str) -> dict[str, Any]:
    """Validate stored offsets without treating the supported zero default as drift."""

    probe_mapping = probe_mapping_evidence(facts, profile)
    configured_ids = set(probe_mapping.get("configured_ids") or [])
    physical_ids = set(probe_mapping.get("physical_ids") or [])
    known_ids = configured_ids or physical_ids
    raw_offsets = (facts.get("sensor_offsets") or {}).get("values")
    offsets = raw_offsets if isinstance(raw_offsets, dict) else {}
    offset_ids = set(str(sensor_id) for sensor_id in offsets)
    invalid_values = sorted(
        str(sensor_id)
        for sensor_id, value in offsets.items()
        if isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    )
    orphaned = sorted(offset_ids - known_ids) if known_ids else sorted(offset_ids)
    explicit_ids = sorted(offset_ids & known_ids)
    default_zero_ids = sorted(known_ids - offset_ids)
    assessed = bool(known_ids and isinstance(raw_offsets, dict))
    aligned = bool(assessed and not invalid_values and not orphaned)
    configured_count = len(known_ids)
    explicit_count = len(explicit_ids)
    return {
        "assessed": assessed,
        "aligned": aligned if assessed else None,
        "configured_count": configured_count,
        "explicit_count": explicit_count,
        "default_zero_count": len(default_zero_ids),
        "coverage_percent": round(explicit_count / configured_count * 100, 1)
        if configured_count
        else None,
        "explicit_ids": explicit_ids,
        "default_zero_ids": default_zero_ids,
        "orphaned_ids": orphaned,
        "invalid_value_ids": invalid_values,
        "complete_explicit": bool(assessed and not default_zero_ids),
    }


def live_telemetry_evidence(host: dict[str, Any]) -> dict[str, Any]:
    """Normalize backend readings without erasing MRI/CV channel semantics."""

    profile = str(host.get("profile") or "mri").lower()
    telemetry = host.get("telemetry")
    snapshot = telemetry if isinstance(telemetry, dict) else {}
    configured_count = int(
        (host.get("probe_mapping") or {}).get("expected_count")
        or (host.get("probe_mapping") or {}).get("count")
        or 0
    )
    fields = [
        ("helium_in", "Helium in"),
        ("helium_out", "Helium out"),
        ("primary_in", "Primary in"),
        ("primary_out", "Primary out"),
        ("room_temp", "Room"),
    ]
    if profile == "cv":
        fields = [(key, f"Sensor {index}") for index, (key, _) in enumerate(fields, 1)]
        required_count = min(max(configured_count, 3), len(fields))
    else:
        # MRI room probes are supported but optional in the server snapshot.
        required_count = min(max(configured_count, 4), 4)

    readings = []
    for index, (key, label) in enumerate(fields):
        raw_value = snapshot.get(key)
        valid = (
            isinstance(raw_value, (int, float))
            and not isinstance(raw_value, bool)
            and math.isfinite(float(raw_value))
        )
        readings.append({
            "key": key,
            "label": label,
            "value_c": round(float(raw_value), 2) if valid else None,
            "required": index < required_count,
            "available": valid,
        })

    deltas = []
    if profile == "mri":
        for key, label in (("helium_delta", "Helium delta"), ("primary_delta", "Primary delta")):
            raw_value = snapshot.get(key)
            if (
                isinstance(raw_value, (int, float))
                and not isinstance(raw_value, bool)
                and math.isfinite(float(raw_value))
            ):
                deltas.append({"key": key, "label": label, "value_c": round(float(raw_value), 2)})

    last_updated = snapshot.get("last_updated")
    age_seconds = (
        max(0, round(time.time() - float(last_updated)))
        if isinstance(last_updated, (int, float))
        and not isinstance(last_updated, bool)
        and math.isfinite(float(last_updated))
        else None
    )
    current = bool(
        snapshot
        and snapshot.get("is_offline") is not True
        and age_seconds is not None
        and age_seconds <= 300
    )
    missing = [item["label"] for item in readings if item["required"] and not item["available"]]
    alarm_fields = sorted(
        key for key, value in snapshot.items()
        if (key.endswith("_alarm") or key in {"alarm", "in_alarm"}) and value is True
    )
    return {
        "profile": profile,
        "backend_available": bool(snapshot),
        "current": current,
        "complete": bool(current and not missing),
        "last_updated": last_updated if isinstance(last_updated, (int, float)) else None,
        "age_seconds": age_seconds,
        "required_count": required_count,
        "available_count": sum(item["available"] for item in readings),
        "required_available_count": sum(
            item["available"] for item in readings if item["required"]
        ),
        "missing_required": missing,
        "readings": readings,
        "deltas": deltas,
        "alarm": bool(alarm_fields),
        "alarm_fields": alarm_fields,
    }


def gpio_alignment_evidence(facts: dict[str, Any]) -> dict[str, Any]:
    """Normalize boot overlay, reported 1-Wire pin, and live GPIO evidence."""

    gpio = facts.get("gpio") or {}
    overlays = [
        str(item).strip()
        for item in (gpio.get("boot_overlays") or [])
        if str(item).strip().startswith("w1-gpio")
    ]
    configured_pins: set[int] = set()
    for overlay in overlays:
        match = re.search(r"(?:^|,)gpiopin=(\d+)(?:,|$)", overlay)
        configured_pins.add(int(match.group(1)) if match else 4)
    try:
        reported_pin = int(gpio.get("one_wire_pin"))
    except (TypeError, ValueError):
        reported_pin = None
    configured_pin = next(iter(configured_pins)) if len(configured_pins) == 1 else None
    pin_state = str(gpio.get("pin_state") or "")
    live_seen = bool(
        configured_pin is not None
        and re.search(
            rf"(?:GPIO\s*{configured_pin}\b|GPIO{configured_pin}\b|^\s*{configured_pin}:)",
            pin_state,
            re.I | re.M,
        )
    )
    assessed = bool(overlays and reported_pin is not None and pin_state)
    aligned = bool(
        assessed
        and configured_pin is not None
        and reported_pin == configured_pin
        and live_seen
    )
    deviations = []
    if assessed and configured_pin is None:
        deviations.append("multiple 1-Wire GPIO pins are configured")
    if assessed and configured_pin is not None and reported_pin != configured_pin:
        deviations.append(f"boot overlay uses GPIO{configured_pin}, audit reports GPIO{reported_pin}")
    if assessed and not live_seen:
        deviations.append(f"live GPIO{configured_pin} line was not found")
    return {
        "assessed": assessed,
        "aligned": aligned if assessed else None,
        "configured_pin": configured_pin,
        "reported_pin": reported_pin,
        "live_seen": live_seen,
        "overlays": overlays,
        "deviations": deviations,
    }


def sensor_runtime_policy(
    facts: dict[str, Any], profile: str, inventory_name: str = ""
) -> dict[str, Any]:
    """Resolve explicit settings and approved-program defaults into behavior."""

    values = ((facts.get("sensor_config") or {}).get("values") or {})
    application_hash = (facts.get("application") or {}).get("normalized_sha256")
    approved_program = application_hash == PROFILE_BASELINES.get(profile)

    def integer(key: str, program_default: int) -> tuple[int | None, str]:
        raw = values.get(key)
        if raw in (None, ""):
            return (program_default, "program default") if approved_program else (None, "unknown on legacy program")
        try:
            return int(raw), "explicit"
        except (TypeError, ValueError):
            return None, "invalid"

    def boolean(key: str, program_default: bool) -> tuple[bool | None, str]:
        raw = values.get(key)
        if raw in (None, ""):
            return (program_default, "program default") if approved_program else (None, "unknown on legacy program")
        normalized = str(raw).strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True, "explicit"
        if normalized in {"false", "0", "no", "off"}:
            return False, "explicit"
        return None, "invalid"

    effective: dict[str, Any] = {}
    sources: dict[str, str] = {}
    targets: dict[str, Any]
    fields: list[tuple[str, str, str, Any]]
    if profile == "cv":
        fields = [
            ("poll_seconds", "POLL_SEC", "int", 10),
            ("average_window", "AVG_WINDOW", "int", 5),
            ("request_timeout_seconds", "REQUEST_TIMEOUT_SEC", "int", 10),
        ]
        log_level = str(values.get("LOG_LEVEL") or ("INFO" if approved_program else "")).upper() or None
        effective["log_level"] = log_level
        sources["log_level"] = "explicit" if values.get("LOG_LEVEL") else ("program default" if approved_program else "unknown on legacy program")
        effective["logging_mode"] = "console"
        sources["logging_mode"] = "approved program"
        targets = {
            "poll_seconds": 10,
            "average_window": 5,
            "request_timeout_seconds": 10,
            "log_level": "INFO",
            "logging_mode": "console",
        }
    else:
        fields = [
            ("poll_seconds", "POLL_SEC", "int", 10),
            ("average_window", "AVG_WINDOW", "int", 5),
            # The approved program defaults to disk logging. RAM-only is an
            # explicit fleet policy and must never be inferred when absent.
            ("memory_only", "MEMORY_ONLY_MODE", "bool", False),
            ("dual_streaming", "ENABLE_DUAL_STREAMING", "bool", False),
            ("invalid_restart_threshold", "INVALID_SENSOR_RESTART_THRESHOLD", "int", 3),
            ("discovery_timeout_seconds", "SENSOR_DISCOVERY_TIMEOUT_SEC", "int", 90),
            ("discovery_interval_seconds", "SENSOR_DISCOVERY_INTERVAL_SEC", "int", 5),
            ("rescan_timeout_seconds", "SENSOR_RESCAN_TIMEOUT_SEC", "int", 20),
            ("rescan_interval_seconds", "SENSOR_RESCAN_INTERVAL_SEC", "int", 5),
        ]
        targets = {
            "poll_seconds": 10,
            "average_window": 5,
            "memory_only": True,
            "dual_streaming": True,
            "invalid_restart_threshold": 3,
            "discovery_timeout_seconds": 90,
            "discovery_interval_seconds": 5,
            "rescan_timeout_seconds": 20,
            "rescan_interval_seconds": 5,
        }
    for name, env_key, kind, default in fields:
        value, source = boolean(env_key, default) if kind == "bool" else integer(env_key, default)
        effective[name] = value
        sources[name] = source

    deviations = [
        f"{name.replace('_', ' ')} is {effective.get(name)!r}, target {target!r}"
        for name, target in targets.items()
        if effective.get(name) != target
    ]
    if not approved_program:
        deviations.insert(0, "profile program lacks the approved runtime policy implementation")
    exception = RUNTIME_POLICY_EXCEPTIONS.get(inventory_name) or {}
    exception_targets = {
        **targets,
        **(exception.get("effective_overrides") or {}),
    }
    approved_exception = bool(
        values
        and approved_program
        and exception
        and all(effective.get(name) == target for name, target in exception_targets.items())
    )
    return {
        "assessed": bool(values and application_hash),
        "matches": bool(values and approved_program and not deviations),
        "profile": profile,
        "approved_program": approved_program,
        "approved_exception": approved_exception,
        "exception_reason": exception.get("reason") if approved_exception else None,
        "effective": effective,
        "sources": sources,
        "targets": targets,
        "deviations": deviations,
    }


def assess_operational_stack(host: dict[str, Any]) -> dict[str, Any]:
    """Assess common support tooling without conflating MRI and CV applications."""

    if host.get("status") != "ok":
        return {"assessed": False, "matches": None, "deviations": ["host unreachable"]}
    facts = host.get("facts") or {}
    stack = facts.get("operational_stack") or {}
    packages = stack.get("required_packages") or stack.get("base_packages") or {}
    if not stack or not packages:
        return {
            "assessed": False,
            "matches": None,
            "deviations": ["awaiting operational-stack audit"],
        }

    deviations = []
    missing = sorted(name for name, version in packages.items() if not version)
    if missing:
        deviations.append("missing required packages: " + ", ".join(missing))
    architecture = str(stack.get("architecture") or "")
    if architecture not in {"arm64", "aarch64"}:
        deviations.append(f"unexpected architecture: {architecture or 'unknown'}")
    if stack.get("ntp_synchronized") is not True:
        deviations.append("system clock is not NTP-synchronized")
    services = facts.get("services") or {}
    for key, label in (("cron", "cron"), ("tailscaled", "Tailscale")):
        if (services.get(key) or {}).get("active") != "active":
            deviations.append(f"{label} service is not active")
    return {"assessed": True, "matches": not deviations, "deviations": deviations}


def operational_package_matrix(hosts: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare required support packages without demanding cross-release versions."""

    assessed = []
    for host in hosts:
        stack = ((host.get("facts") or {}).get("operational_stack") or {})
        packages = stack.get("required_packages")
        if host.get("status") == "ok" and isinstance(packages, dict) and packages:
            assessed.append((host, stack, packages))
    names = sorted({name for _, _, packages in assessed for name in packages})
    rows = []
    for name in names:
        variants: dict[str, dict[str, Any]] = {}
        cohort_versions: dict[str, set[str]] = {}
        channels: dict[str, dict[str, Any]] = {}
        missing = []
        for host, stack, packages in assessed:
            version = packages.get(name)
            if not version:
                missing.append(str(host.get("label") or host.get("inventory_name") or "unknown"))
                continue
            version_text = str(version)
            variant = variants.setdefault(
                version_text, {"count": 0, "os_cohorts": set(), "host_labels": []}
            )
            variant["count"] += 1
            cohort = str(stack.get("version_codename") or (host.get("facts") or {}).get("os") or "unknown")
            variant["os_cohorts"].add(cohort)
            variant["host_labels"].append(
                str(host.get("label") or host.get("inventory_name") or "unknown")
            )
            cohort_versions.setdefault(cohort, set()).add(version_text)
            if name == "tailscale":
                channel = str(
                    (((stack.get("package_channels") or {}).get("tailscale") or {}).get("channel"))
                    or "unknown"
                )
                channel_row = channels.setdefault(channel, {"count": 0, "host_labels": []})
                channel_row["count"] += 1
                channel_row["host_labels"].append(
                    str(host.get("label") or host.get("inventory_name") or "unknown")
                )
        version_rows = [
            {
                "version": version,
                "count": details["count"],
                "os_cohorts": sorted(details["os_cohorts"]),
                "host_labels": sorted(details["host_labels"]),
            }
            for version, details in sorted(variants.items())
        ]
        same_cohort_spreads = [
            {"os_cohort": cohort, "versions": sorted(versions)}
            for cohort, versions in sorted(cohort_versions.items())
            if len(versions) > 1
        ]
        rows.append({
            "name": name,
            "installed_count": len(assessed) - len(missing),
            "expected_count": len(assessed),
            "complete": not missing,
            "missing_hosts": sorted(missing),
            "version_variant_count": len(version_rows),
            "versions": version_rows,
            "same_cohort_spreads": same_cohort_spreads,
            "channels": [
                {
                    "channel": channel,
                    "count": details["count"],
                    "host_labels": sorted(details["host_labels"]),
                }
                for channel, details in sorted(channels.items())
            ],
        })
    return {
        "assessed_hosts": len(assessed),
        "package_count": len(rows),
        "complete_packages": sum(row["complete"] for row in rows),
        "packages_with_same_cohort_spread": sum(
            bool(row["same_cohort_spreads"]) for row in rows
        ),
        "tailscale_channels": next(
            (row["channels"] for row in rows if row["name"] == "tailscale"), []
        ),
        "packages": rows,
        "note": "Version differences are grouped by observed OS cohort and are not treated as drift when every host has the required package.",
    }


def assess_python_runtime(
    runtime: dict[str, Any],
    minimums: dict[str, tuple[int, int, int]],
    allowed_majors: dict[str, set[int]] | None = None,
) -> dict[str, Any]:
    dependencies = runtime.get("direct_dependencies")
    if not isinstance(dependencies, dict):
        return {"assessed": False, "complete": None, "missing": []}
    required = tuple(minimums)
    missing = [name for name in required if not dependencies.get(name)]
    incompatible = []
    for name, minimum in minimums.items():
        version = str(dependencies.get(name) or "")
        parts = tuple(int(value) for value in re.findall(r"\d+", version)[:3])
        normalized = parts + (0,) * (3 - len(parts))
        accepted_majors = (allowed_majors or {}).get(name, {minimum[0]})
        if version and (not parts or normalized[0] not in accepted_majors or normalized < minimum):
            incompatible.append(name)
    return {
        "assessed": True,
        "complete": bool(runtime.get("python_version")) and not missing and not incompatible,
        "missing": missing,
        "incompatible": incompatible,
        "python_version": str(runtime.get("python_version") or ""),
        "executable": str(runtime.get("executable") or ""),
        "direct_dependencies": {name: dependencies.get(name) for name in required},
    }


def assess_sensor_runtime(host: dict[str, Any]) -> dict[str, Any]:
    if host.get("status") != "ok":
        return {"assessed": False, "complete": None, "missing": []}
    runtime = (host.get("facts") or {}).get("sensor_runtime") or {}
    return assess_python_runtime(runtime, SENSOR_RUNTIME_MINIMUMS)


def assess_camera_runtime(host: dict[str, Any]) -> dict[str, Any]:
    if host.get("status") != "ok":
        return {"installed": None, "assessed": False, "complete": None, "missing": []}
    camera = (host.get("facts") or {}).get("camera_logging") or {}
    if camera.get("installed") is not True:
        return {"installed": False, "assessed": False, "complete": None, "missing": []}
    runtime = camera.get("runtime") or {}
    assessment = assess_python_runtime(
        runtime,
        CAMERA_RUNTIME_MINIMUMS,
        CAMERA_RUNTIME_ALLOWED_MAJORS,
    )
    entrypoint = runtime.get("entrypoint_import")
    if isinstance(entrypoint, dict):
        assessment["entrypoint_import"] = entrypoint
        if entrypoint.get("ok") is not True:
            assessment["complete"] = False
            assessment["missing"] = [
                *assessment.get("missing", []),
                "camera entrypoint import",
            ]
    assessment["installed"] = True
    return assessment


def assess_ram_budget(host: dict[str, Any]) -> dict[str, Any]:
    """Assess RAM-backed workload headroom without requiring swap."""

    budget = (host.get("facts") or {}).get("ram_budget") or {}
    run = budget.get("run") or {}
    available = budget.get("available_percent")
    run_used = run.get("used_percent")
    total = budget.get("total_bytes")
    if (
        host.get("status") != "ok"
        or not isinstance(total, (int, float))
        or total <= 0
        or not isinstance(available, (int, float))
        or not isinstance(run_used, (int, float))
    ):
        return {"assessed": False, "healthy": None, "severity": None, "issues": []}

    warning_issues = []
    critical_issues = []
    oom_events = budget.get("oom_events_since_boot")
    if isinstance(oom_events, (int, float)) and oom_events > 0:
        critical_issues.append(f"{int(oom_events)} kernel OOM event(s) since boot")
    if available < 10:
        critical_issues.append(f"only {available:g}% memory available")
    elif available < 20:
        warning_issues.append(f"only {available:g}% memory available")
    if run_used >= 90:
        critical_issues.append(f"/run is {run_used:g}% full")
    elif run_used >= 70:
        warning_issues.append(f"/run is {run_used:g}% full")
    if str(run.get("filesystem") or "").lower() != "tmpfs":
        warning_issues.append("/run is not backed by tmpfs")

    issues = critical_issues + warning_issues
    severity = "critical" if critical_issues else "warning" if warning_issues else "healthy"
    return {
        "assessed": True,
        "healthy": not issues,
        "severity": severity,
        "issues": issues,
        "available_percent": available,
        "run_used_percent": run_used,
        "oom_events_since_boot": int(oom_events or 0),
        "swap_total_bytes": int(budget.get("swap_total_bytes") or 0),
        "swap_used_bytes": int(budget.get("swap_used_bytes") or 0),
        "zram_active": budget.get("zram_active") is True,
    }


def assess_update_policy(host: dict[str, Any]) -> dict[str, Any]:
    """Assess safe automatic security updates without permitting auto-reboots."""

    policy = (host.get("facts") or {}).get("update_policy") or {}
    if host.get("status") != "ok" or not policy:
        return {
            "assessed": False,
            "aligned": None,
            "severity": None,
            "deviations": [],
            "held_packages": [],
        }
    deviations = []
    critical = []
    if not policy.get("unattended_upgrades_version"):
        deviations.append("unattended-upgrades is not installed")
    for key, label in (
        ("apt_daily_timer", "apt-daily.timer"),
        ("apt_daily_upgrade_timer", "apt-daily-upgrade.timer"),
    ):
        timer = policy.get(key) or {}
        if timer.get("enabled") != "enabled":
            deviations.append(f"{label} is not enabled")
        if timer.get("active") != "active":
            deviations.append(f"{label} is not active")
    if str(policy.get("update_package_lists") or "") != "1":
        deviations.append("daily package-list refresh is not enabled")
    if str(policy.get("unattended_upgrade") or "") != "1":
        deviations.append("daily unattended upgrades are not enabled")
    automatic_reboot = str(policy.get("automatic_reboot") or "").lower()
    if automatic_reboot in {"1", "true", "yes"}:
        critical.append("automatic reboot is enabled")
    held_packages = sorted(
        str(name) for name in (policy.get("held_packages") or []) if name
    )
    if held_packages:
        deviations.append("held packages require review: " + ", ".join(held_packages))
    all_deviations = critical + deviations
    return {
        "assessed": True,
        "aligned": not all_deviations,
        "severity": "critical" if critical else "warning" if deviations else "healthy",
        "deviations": all_deviations,
        "held_packages": held_packages,
        "automatic_reboot": automatic_reboot in {"1", "true", "yes"},
    }


def sensor_runtime_matrix(hosts: list[dict[str, Any]]) -> dict[str, Any]:
    """Group sensor profiles plus the optional camera workload runtimes."""

    profile_rows = []
    assessed_total = 0
    complete_total = 0
    for profile in ("mri", "cv"):
        entries = []
        for host in hosts:
            if host.get("profile") != profile:
                continue
            assessment = host.get("sensor_runtime_assessment") or assess_sensor_runtime(host)
            if assessment.get("assessed") is not True:
                continue
            entries.append((host, assessment))
        if not entries:
            continue
        assessed_total += len(entries)
        profile_complete = sum(item[1].get("complete") is True for item in entries)
        complete_total += profile_complete

        python_variants: dict[str, list[str]] = {}
        dependency_variants: dict[str, dict[str, list[str]]] = {
            name: {} for name in ("python-dotenv", "requests", "w1thermsensor")
        }
        for host, assessment in entries:
            label = str(host.get("label") or host.get("inventory_name") or "unknown")
            python_version = str(assessment.get("python_version") or "missing")
            python_variants.setdefault(python_version, []).append(label)
            for name, version in (assessment.get("direct_dependencies") or {}).items():
                version_text = str(version or "missing")
                dependency_variants[name].setdefault(version_text, []).append(label)

        profile_rows.append({
            "profile": profile,
            "assessed_hosts": len(entries),
            "complete_hosts": profile_complete,
            "python_versions": [
                {"version": version, "count": len(labels), "host_labels": sorted(labels)}
                for version, labels in sorted(python_variants.items())
            ],
            "dependencies": [
                {
                    "name": name,
                    "installed_count": sum(
                        len(labels)
                        for version, labels in versions.items()
                        if version != "missing"
                    ),
                    "expected_count": len(entries),
                    "versions": [
                        {"version": version, "count": len(labels), "host_labels": sorted(labels)}
                        for version, labels in sorted(versions.items())
                    ],
                }
                for name, versions in dependency_variants.items()
            ],
        })

    camera_entries = []
    for host in hosts:
        assessment = host.get("camera_runtime_assessment") or assess_camera_runtime(host)
        if assessment.get("installed") is True and assessment.get("assessed") is True:
            camera_entries.append((host, assessment))
    camera_complete = sum(item[1].get("complete") is True for item in camera_entries)
    if camera_entries:
        python_variants: dict[str, list[str]] = {}
        dependency_variants: dict[str, dict[str, list[str]]] = {
            name: {} for name in CAMERA_RUNTIME_MINIMUMS
        }
        for host, assessment in camera_entries:
            label = str(host.get("label") or host.get("inventory_name") or "unknown")
            python_version = str(assessment.get("python_version") or "missing")
            python_variants.setdefault(python_version, []).append(label)
            for name, version in (assessment.get("direct_dependencies") or {}).items():
                dependency_variants[name].setdefault(str(version or "missing"), []).append(label)
        profile_rows.append({
            "profile": "camera",
            "assessed_hosts": len(camera_entries),
            "complete_hosts": camera_complete,
            "python_versions": [
                {"version": version, "count": len(labels), "host_labels": sorted(labels)}
                for version, labels in sorted(python_variants.items())
            ],
            "dependencies": [
                {
                    "name": name,
                    "installed_count": sum(
                        len(labels) for version, labels in versions.items() if version != "missing"
                    ),
                    "expected_count": len(camera_entries),
                    "versions": [
                        {"version": version, "count": len(labels), "host_labels": sorted(labels)}
                        for version, labels in sorted(versions.items())
                    ],
                }
                for name, versions in dependency_variants.items()
            ],
        })
    return {
        "assessed_hosts": assessed_total,
        "complete_hosts": complete_total,
        "camera_assessed_hosts": len(camera_entries),
        "camera_complete_hosts": camera_complete,
        "profiles": profile_rows,
        "note": "MRI and CV sensors remain separate profiles; installed camera workloads are assessed independently. Missing or incompatible direct imports are drift.",
    }


def eligible_package_count(host: dict[str, Any]) -> int:
    """Return the apt-simulated eligible count, preserving old-audit fallback."""

    facts = host.get("facts") or {}
    package_maintenance = facts.get("package_maintenance") or {}
    raw = package_maintenance.get("eligible_count", facts.get("packages_upgradable") or 0)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def os_posture(host: dict[str, Any]) -> dict[str, Any]:
    """Classify only currently observed Ubuntu releases; never infer offline state."""

    if host.get("status") != "ok":
        return {"assessed": False, "state": "unknown", "label": "offline / unassessed"}
    os_name = str((host.get("facts") or {}).get("os") or "")
    if "Ubuntu 26.04" in os_name:
        return {
            "assessed": True,
            "state": "target",
            "label": "fleet target LTS",
            "standard_support_until": "2031-05",
        }
    if "Ubuntu 24.04" in os_name:
        return {
            "assessed": True,
            "state": "supported_lts",
            "label": "supported LTS exception",
            "standard_support_until": "2029-05",
        }
    if "Ubuntu 25.10" in os_name:
        return {
            "assessed": True,
            "state": "eol",
            "label": "end of life",
            "end_of_life": "2026-07-09",
            "upgrade_path": "26.04 LTS",
        }
    if "Ubuntu 25.04" in os_name:
        return {
            "assessed": True,
            "state": "eol",
            "label": "end of life",
            "end_of_life": "2026-01-15",
            "upgrade_path": "staged path to 26.04 LTS",
        }
    return {"assessed": bool(os_name), "state": "unknown", "label": "unclassified release"}


def service_unit_evidence(facts: dict[str, Any], profile: str) -> dict[str, Any]:
    """Assess active profile service structure without equating MRI and CV paths."""

    key = "cv_sensor" if profile == "cv" else "mri_sensor"
    service = (facts.get("services") or {}).get(key) or {}
    if not service:
        return {"assessed": False, "aligned": None, "deviations": ["service facts unavailable"]}
    user = str(service.get("user") or "")
    fragment = str(service.get("fragmentpath") or "")
    working_directory = str(service.get("workingdirectory") or "")
    exec_start = str(service.get("execstart") or "")
    expected_fragment = "/etc/systemd/system/cv-room-sensor.service" if profile == "cv" else "/etc/systemd/system/mri-sensor.service"
    expected_working_directory = "/opt/cv-room-monitor" if profile == "cv" else (f"/home/{user}/mike-mri-cooling" if user else "")
    expected_program = "/opt/cv-room-monitor/src/cv_room_sensor.py" if profile == "cv" else (f"/home/{user}/mike-mri-cooling/src/pi_sensor.py" if user else "")
    deviations = []
    if service.get("active") != "active":
        deviations.append(f"service is {service.get('active') or 'unknown'}")
    if service.get("enabled") != "enabled":
        deviations.append(f"service is {service.get('enabled') or 'not enabled'} at boot")
    if not user or user == "root":
        deviations.append("service does not run as a site account")
    if fragment != expected_fragment:
        deviations.append(f"unit path is {fragment or 'unknown'}")
    if expected_working_directory and working_directory != expected_working_directory:
        deviations.append(f"working directory is {working_directory or 'unknown'}")
    if expected_program and expected_program not in exec_start:
        deviations.append("effective executable does not use the profile program")
    verify_warning = str(service.get("unit_verify") or "").strip()
    if verify_warning:
        deviations.append("systemd unit validation reports: " + verify_warning.splitlines()[0])
    return {
        "assessed": True,
        "aligned": not deviations,
        "profile": profile,
        "user": user,
        "fragment": fragment,
        "working_directory": working_directory,
        "deviations": deviations,
    }


def sensor_operational_evidence(host: dict[str, Any]) -> dict[str, Any]:
    """Separate an installed runtime from a working end-to-end sensor path."""
    if host.get("status") != "ok":
        return {
            "assessed": False,
            "operational": False,
            "state": "offline",
            "checks": {},
            "blockers": ["host is offline"],
        }

    profile = host.get("profile", "mri")
    service_key = "cv_sensor" if profile == "cv" else "mri_sensor"
    service = ((((host.get("facts") or {}).get("services") or {}).get(service_key)) or {})
    checks = {
        "software_environment_complete": (
            (host.get("sensor_runtime_assessment") or {}).get("complete") is True
        ),
        "configured_probes_visible": (
            (host.get("probe_mapping") or {}).get("exact") is True
            and (host.get("probe_mapping") or {}).get("complete") is True
        ),
        "service_active": service.get("active") == "active",
        "telemetry_current_complete": (
            (host.get("live_telemetry") or {}).get("current") is True
            and (host.get("live_telemetry") or {}).get("complete") is True
        ),
    }
    labels = {
        "software_environment_complete": "sensor software environment incomplete",
        "configured_probes_visible": "configured physical probes are not all visible",
        "service_active": "sensor service is not active",
        "telemetry_current_complete": "sensor telemetry is stale or incomplete",
    }
    blockers = [labels[name] for name, passed in checks.items() if not passed]
    return {
        "assessed": True,
        "operational": not blockers,
        "state": "operational" if not blockers else "attention",
        "checks": checks,
        "blockers": blockers,
    }


def restart_policy_evidence(facts: dict[str, Any], profile: str) -> dict[str, Any]:
    """Assess crash recovery while preserving intentional MRI/CV differences."""

    key = "cv_sensor" if profile == "cv" else "mri_sensor"
    service = (facts.get("services") or {}).get(key) or {}
    required = ("restart", "restartusec", "startlimitintervalusec")
    if not service or not all(field in service for field in required):
        return {
            "assessed": False,
            "aligned": None,
            "deviations": ["effective restart properties unavailable"],
        }

    restart = str(service.get("restart") or "")
    delay = str(service.get("restartusec") or "")
    interval = str(service.get("startlimitintervalusec") or "")
    burst = str(service.get("startlimitburst") or "")
    deviations = []
    if restart != "always":
        deviations.append(f"restart mode is {restart or 'unknown'}, target always")
    if delay != "15s":
        deviations.append(f"restart delay is {delay or 'unknown'}, target 15s")
    # CV keeps its profile-specific start-limit. MRI disables the finite window so
    # repeated failures cannot exhaust the limit and leave a room sensor stopped.
    if profile == "mri" and interval != "0":
        deviations.append(f"finite start-limit interval is {interval or 'unknown'}, target disabled")
    return {
        "assessed": True,
        "aligned": not deviations,
        "profile": profile,
        "restart": restart,
        "delay": delay,
        "start_limit_interval": interval,
        "start_limit_burst": burst,
        "deviations": deviations,
    }


def build_maintenance_waves(
    hosts: list[dict[str, Any]],
    optimization_observation: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build read-only action lanes without weakening per-host safety gates."""

    def weakest_signal(host: dict[str, Any]) -> float | None:
        return routed_wifi_signal(host.get("facts") or {})

    def ref(host: dict[str, Any], reason: str, priority: int = 50) -> dict[str, Any]:
        name = host.get("inventory_name", "")
        return {
            "inventory_name": name,
            "label": host.get("label") or name,
            "profile": host.get("profile", "mri"),
            "nearby": name in NEARBY_PILOT_HOSTS,
            "reason": reason,
            "priority": priority,
        }

    def ordered(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(items, key=lambda item: (item.get("priority", 50), not item["nearby"], item["label"].lower()))

    def lane(
        lane_id: str,
        title: str,
        description: str,
        ready: list[dict[str, Any]],
        held: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "id": lane_id,
            "title": title,
            "description": description,
            "state": "ready" if ready else "hold",
            "ready": ordered(ready),
            "held": ordered(held),
        }

    primary_os_pilot_complete = any(
        host.get("status") == "ok"
        and host.get("inventory_name") == OS_PRIMARY_PILOT_HOST
        and "Ubuntu 26.04" in str((host.get("facts") or {}).get("os") or "")
        for host in hosts
    )
    camera_primary_pilot_complete = all(
        any(
            host.get("status") == "ok"
            and host.get("inventory_name") == pilot
            and (host.get("camera_convergence") or {}).get("status")
            == "v3_production_verified"
            for host in hosts
        )
        for pilot in ("agcmr1", "agcmr3")
    )
    camera_secondary_reference_complete = any(
        host.get("status") == "ok"
        and host.get("inventory_name") == "oswmr1"
        and (host.get("camera_convergence") or {}).get("status")
        == "v3_production_verified"
        for host in hosts
    )
    camera_ram_log_reference_complete = any(
        host.get("status") == "ok"
        and host.get("inventory_name") == CAMERA_RAM_LOG_REFERENCE_HOST
        and (((host.get("facts") or {}).get("camera_logging") or {}).get("memory_only") is True)
        and (host.get("camera_observation") or {}).get("passed") is True
        and (host.get("camera_observation") or {}).get("matches_current_camera") is True
        for host in hosts
    )

    routine_ready, routine_held = [], []
    tailscale_ready, tailscale_held = [], []
    reboot_ready, reboot_held = [], []
    os_ready, os_held = [], []
    operational_ready, operational_held = [], []
    software_ready, software_held = [], []
    restart_ready, restart_held = [], []
    camera_ready, camera_held = [], []
    camera_ram_ready, camera_ram_held = [], []
    journal_ready, journal_held = [], []
    headless_ready, headless_held = [], []
    network_ready = []
    backup_held = []

    optimization_observation = optimization_observation or {}
    optimization_hosts = optimization_observation.get("hosts") or {}
    optimization_cohort_ready = optimization_observation.get("cohort_ready") is True
    optimization_reference_accepted = (
        optimization_observation.get("reference_evidence_accepted") is True
    )
    reference_names = optimization_observation.get("reference_canaries") or []
    host_labels = {
        str(host.get("inventory_name") or ""): str(host.get("label") or host.get("inventory_name") or "")
        for host in hosts
    }
    degraded_references = []
    for name in reference_names:
        evidence = optimization_hosts.get(name) or {}
        if evidence.get("ready") is True:
            continue
        checks = evidence.get("checks") or {}
        if checks.get("reachable") is False:
            detail = "unreachable"
        else:
            detail = ", ".join(evidence.get("blockers") or []) or "health gate not passing"
        degraded_references.append(f"{host_labels.get(name, name)} ({detail})")
    optimization_hold_reason = (
        "reference evidence accepted; current reference health degraded: "
        + "; ".join(degraded_references)
        if optimization_reference_accepted and degraded_references
        else "await 48-hour nearby RAM/write canary evidence"
    )

    for host in hosts:
        facts = host.get("facts") or {}
        maintenance = host.get("maintenance") or {}
        blockers = maintenance.get("blockers") or []
        hold_reason = "; ".join(blockers) or "maintenance gate unavailable"
        package_maintenance = facts.get("package_maintenance") or {}
        updates = int(package_maintenance.get("eligible_count", facts.get("packages_upgradable") or 0))

        if host.get("status") == "ok" and updates:
            item = ref(host, f"{updates} package{'s' if updates != 1 else ''} pending")
            (routine_ready if maintenance.get("ready") else routine_held).append(
                item if maintenance.get("ready") else ref(host, hold_reason)
            )

        tailscale_channel = (
            (((facts.get("operational_stack") or {}).get("package_channels") or {}).get("tailscale") or {})
            .get("channel")
        )
        if host.get("status") == "ok" and tailscale_channel == "distribution":
            tailscale_version = (
                (((facts.get("operational_stack") or {}).get("required_packages") or {}).get("tailscale"))
                or "unknown"
            )
            camera_observation = host.get("camera_observation") or {}
            if camera_observation.get("planned") and camera_observation.get("pending"):
                tailscale_held.append(ref(
                    host,
                    f"distribution channel {tailscale_version}; planned production camera proof must complete first",
                ))
            elif maintenance.get("ready"):
                tailscale_ready.append(ref(
                    host,
                    f"distribution channel {tailscale_version}; signed official-stable one-host preflight ready",
                ))
            else:
                tailscale_held.append(ref(
                    host,
                    f"distribution channel {tailscale_version}; {hold_reason}",
                ))

        if host.get("status") == "ok" and facts.get("reboot_required"):
            item = ref(host, "installed updates require reboot")
            (reboot_ready if maintenance.get("ready") else reboot_held).append(
                item if maintenance.get("ready") else ref(host, hold_reason)
            )

        os_name = str(facts.get("os") or "")
        if host.get("status") == "ok" and ("Ubuntu 25.10" in os_name or "Ubuntu 25.04" in os_name):
            restore = ((host.get("backup") or {}).get("restore_test") or {})
            readiness = host.get("os_upgrade_readiness") or {}
            os_gate = bool(
                maintenance.get("ready")
                and restore.get("recent") is True
                and readiness.get("ready") is True
                and (
                    host.get("inventory_name") == OS_PRIMARY_PILOT_HOST
                    or primary_os_pilot_complete
                )
            )
            if os_gate:
                reason = "restore and machine-readiness proofs current; attended LTS pilot ready"
            elif restore.get("recent") is not True:
                reason = "production restore proof missing"
            elif not maintenance.get("ready"):
                reason = hold_reason
            elif not readiness:
                reason = "restore proof current; machine readiness assessment not completed"
            elif readiness.get("ready") is True and not primary_os_pilot_complete:
                reason = "machine readiness proof current; await AGC MR3 primary pilot outcome"
            else:
                blockers = readiness.get("blockers") or []
                reason = "machine readiness blocked: " + (
                    "; ".join(str(item) for item in blockers) or "guarded readiness proof did not pass"
                )
            (os_ready if os_gate else os_held).append(ref(host, reason))

        baseline = host.get("software_baseline") or {}
        if host.get("status") == "ok" and baseline and not baseline.get("matches"):
            helpers = facts.get("restricted_helpers") or {}
            helper_ready = helpers.get("sensor_service_control") is True
            software_gate = bool(maintenance.get("ready") and helper_ready)
            reason = (
                f"known {baseline.get('state', 'drift')} family; restart helper available"
                if software_gate
                else ("restricted restart helper missing" if not helper_ready else hold_reason)
            )
            (software_ready if software_gate else software_held).append(ref(host, reason))

        restart_policy = host.get("restart_policy") or {}
        if (
            host.get("status") == "ok"
            and host.get("profile") == "mri"
            and restart_policy.get("assessed") is True
            and restart_policy.get("aligned") is False
        ):
            unit_aligned = (host.get("service_unit") or {}).get("aligned") is True
            restart_gate = bool(
                maintenance.get("ready")
                and baseline.get("matches") is True
                and unit_aligned
            )
            if restart_gate:
                reason = "backed, healthy no-restart drop-in candidate"
            elif baseline.get("matches") is not True:
                reason = "approved MRI application required before policy convergence"
            elif not unit_aligned:
                reason = "service-unit structure must align before policy convergence"
            else:
                reason = hold_reason
            (restart_ready if restart_gate else restart_held).append(ref(host, reason))

        operational = host.get("operational_baseline") or {}
        if operational.get("assessed") and not operational.get("matches"):
            reason = "; ".join(operational.get("deviations") or [])
            (operational_ready if maintenance.get("ready") else operational_held).append(
                ref(host, reason if maintenance.get("ready") else hold_reason)
            )

        camera = (facts.get("camera_logging") or {}).get("installed") is True
        convergence = (host.get("camera_convergence") or {}).get("status", "unmapped")
        if camera and convergence != "v3_production_verified":
            restore = ((host.get("backup") or {}).get("restore_test") or {})
            canary_candidate = convergence.startswith("eligible_after_primary_pilot")
            camera_gate = bool(
                (
                    (
                        convergence == "hardware_canary_passed"
                        and camera_secondary_reference_complete
                    )
                    or (canary_candidate and camera_primary_pilot_complete)
                )
                and maintenance.get("ready")
                and restore.get("recent") is True
            )
            if camera_gate and convergence == "hardware_canary_passed":
                reason = "hardware canary and restore proof complete"
            elif camera_gate:
                reason = "primary v3 proofs complete; ready for upload-disabled hardware canary"
            elif convergence == "hardware_canary_passed" and restore.get("recent") is not True:
                reason = "hardware canary passed; production restore proof missing"
            elif convergence == "hardware_canary_passed" and not camera_secondary_reference_complete:
                reason = "hardware canary passed; await OSW MR1 natural 10/10 v3 proof before production deployment"
            elif canary_candidate and not camera_primary_pilot_complete:
                reason = "await AGC MR1 and MR3 natural v3 production proofs"
            elif convergence == "v3_smoke_passed_pending_natural_proof":
                reason = "v3 installed and upload-disabled smoke passed; await exact-build natural 10/10 proof"
            elif convergence != "hardware_canary_passed":
                reason = convergence.replace("_", " ")
            else:
                reason = hold_reason
            (camera_ready if camera_gate else camera_held).append(ref(host, reason))

        camera_logging = facts.get("camera_logging") or {}
        if camera and camera_logging.get("memory_only") is not True:
            inventory_name = host.get("inventory_name", "")
            restore = ((host.get("backup") or {}).get("restore_test") or {})
            schedules = ((camera_logging.get("software") or {}).get("schedules") or [])
            user_crontab_exact = bool(schedules) and all(
                item.get("source") == "user" for item in schedules
            )
            cron_d_exact = bool(schedules) and all(
                item.get("source") == "cron.d/mri-cooling-camera" for item in schedules
            )
            schedule_approved = (
                inventory_name in CAMERA_RAM_LOG_USER_CRONTAB_TARGETS
                and user_crontab_exact
            ) or (
                inventory_name in CAMERA_RAM_LOG_CROND_TARGETS
                and cron_d_exact
            )
            ram_log_gate = bool(
                schedule_approved
                and camera_ram_log_reference_complete
                and maintenance.get("ready")
                and restore.get("recent") is True
            )
            if inventory_name == "agcmr2":
                reason = "recover the older four-probe sensor bus before a dedicated nearby local-OCR transition"
            elif not schedule_approved:
                reason = "camera schedule contract is not approved for the user-crontab RAM-log wave"
            elif not camera_ram_log_reference_complete:
                reason = (
                    "cron-service watchdog prepared; await GCMC MR2 natural 10/10 proof"
                    if inventory_name == "oswmr2"
                    else "await GCMC MR2 natural 10/10 proof after its RAM-log transition"
                )
            elif restore.get("recent") is not True:
                reason = "exact production restore proof missing"
            elif not maintenance.get("ready"):
                reason = hold_reason
            else:
                reason = (
                    "GCMC proof complete; cron.d-preserving watchdog transition ready"
                    if inventory_name == "oswmr2"
                    else "GCMC proof complete; exact-schedule one-host RAM-log transition ready"
                )
            (camera_ram_ready if ram_log_gate else camera_ram_held).append(
                ref(host, reason)
            )

        ram_optimization = facts.get("ram_optimization") or {}
        background = ((facts.get("operational_stack") or {}).get("background_services") or {})
        write_trend = (facts.get("storage_health") or {}).get("write_trend") or {}
        if (
            host.get("status") == "ok"
            and ram_optimization.get("persistent_journal") is True
            and (background.get("rsyslog.service") or {}).get("active") == "active"
            and write_trend.get("sustained_high") is True
        ):
            restore = ((host.get("backup") or {}).get("restore_test") or {})
            camera_proof_ready = bool(
                camera_logging.get("installed") is not True
                or (
                    camera_logging.get("memory_only") is True
                    and (host.get("camera_observation") or {}).get("passed") is True
                    and (host.get("camera_observation") or {}).get("matches_current_camera") is True
                )
            )
            journal_gate = bool(
                optimization_cohort_ready
                and restore.get("recent") is True
                and maintenance.get("ready") is True
                and camera_proof_ready
            )
            if not camera_proof_ready:
                reason = "await this exact camera build's natural 10/10 RAM-log proof"
            elif not optimization_cohort_ready:
                reason = optimization_hold_reason
            elif restore.get("recent") is not True:
                reason = "exact production restore proof missing"
            elif not maintenance.get("ready"):
                reason = hold_reason
            else:
                reason = "sustained clean write evidence; backup, restore, camera, and 48-hour canary gates complete"
            (journal_ready if journal_gate else journal_held).append(ref(host, reason))

        headless_status = HEADLESS_OPTIMIZATION_STATUS.get(host.get("inventory_name"))
        canary_observation = optimization_hosts.get(host.get("inventory_name")) or {}
        if headless_status == "reboot_verified_observation" and (background.get("gdm.service") or {}).get("active") != "active":
            if canary_observation.get("ready") is not True:
                duration = canary_observation.get("duration_hours")
                samples = canary_observation.get("continuous_samples")
                if host.get("status") != "ok":
                    reason = "reboot verified; host currently unreachable, so live observation is paused"
                else:
                    reason = (
                        f"reboot verified; {duration:g}/48 observation hours · {samples}/24 samples"
                        if isinstance(duration, (int, float)) and isinstance(samples, int)
                        else "reboot verified; multi-day quiet write observation in progress"
                    )
                headless_held.append(ref(host, reason))
        elif (background.get("gdm.service") or {}).get("active") == "active":
            signal = routed_wifi_signal(facts)
            if not maintenance.get("ready"):
                reason = hold_reason
            elif not optimization_cohort_ready:
                reason = optimization_hold_reason
            elif isinstance(signal, (int, float)) and signal <= -67:
                reason = (
                    f"canary evidence complete; routed Wi-Fi is weak ({signal:g} dBm), "
                    "so proceed serially with recovery verification"
                )
            elif host.get("inventory_name") in NEARBY_PILOT_HOSTS:
                reason = (
                    "48-hour canary evidence complete; nearby reversible expansion ready"
                )
            else:
                reason = "48-hour canary evidence complete; serial remote expansion ready"
            if optimization_cohort_ready and maintenance.get("ready"):
                priority = 20 if host.get("inventory_name") in NEARBY_PILOT_HOSTS else 40
                if isinstance(signal, (int, float)) and signal <= -67:
                    priority += 20
                headless_ready.append(ref(host, reason, priority))
            else:
                headless_held.append(ref(host, reason))

        signal = weakest_signal(host)
        if host.get("status") != "ok":
            peer = host.get("tailscale_peer") or {}
            last_seen = str(peer.get("last_seen") or "")
            historical = host.get("last_known") or {}
            historical_facts = historical.get("facts") or {}
            prior_ips = historical_facts.get("tailscale_ips") or []
            prior_macs = historical_facts.get("macs") or {}
            identity_parts = []
            if prior_ips:
                identity_parts.append(f"last IP {prior_ips[0]}")
            preferred_mac = prior_macs.get("wlan0") or prior_macs.get("eth0")
            if preferred_mac:
                identity_parts.append(f"MAC {preferred_mac}")
            seen_text = f"last Tailscale contact {last_seen[:10]}" if last_seen else "last contact unknown"
            identity_text = " · " + " / ".join(identity_parts) if identity_parts else ""
            network_ready.append(ref(
                host,
                f"OFFLINE · {seen_text}{identity_text} · check site power, status LEDs, and network; audit before maintenance",
                priority=0,
            ))
        else:
            field_actions = []
            field_priority = 50
            if isinstance(signal, (int, float)) and signal <= -67:
                wifi_details = routed_wifi_details(facts) or {}
                interface = wifi_details.get("interface") or "unknown interface"
                driver = wifi_details.get("driver") or "unknown driver"
                onboard = driver == "brcmfmac" and interface == "wlan0"
                external_adapter = interface.startswith("wlx") or driver not in {"brcmfmac", "unknown driver"}
                recommendation = (
                    "add external-antenna USB Wi-Fi or Ethernet"
                    if signal <= -75 and not external_adapter
                    else "reposition antenna/Pi, then remeasure"
                )
                frequency = wifi_details.get("frequency_mhz")
                band = (
                    "5 GHz" if isinstance(frequency, (int, float)) and frequency >= 5000
                    else "2.4 GHz" if isinstance(frequency, (int, float)) and frequency >= 2400
                    else "unknown band"
                )
                adapter = wifi_details.get("adapter_kind") or (
                    "onboard" if onboard else "external" if external_adapter else "unknown adapter"
                )
                field_actions.append(
                    f"{signal:g} dBm via {interface}/{driver} ({adapter}, {band}) · {recommendation}"
                )
                diagnostic_note = WIFI_DIAGNOSTIC_NOTES.get(host.get("inventory_name", ""))
                if diagnostic_note:
                    field_actions.append(diagnostic_note)
                field_priority = min(field_priority, 1 if signal <= -75 else 2)
            smart = ((facts.get("storage_health") or {}).get("smart") or {})
            if smart.get("concerning") is True:
                field_actions.append("storage health warning · verify backup, cabling, and replacement drive")
                field_priority = min(field_priority, 0)
            if facts.get("throttled_flags") not in (None, 0):
                field_actions.append("power/thermal throttling · inspect supply, USB-C cable, and enclosure airflow")
                field_priority = min(field_priority, 1)
            boot = facts.get("boot_management") or {}
            boot_options = str(boot.get("firmware_mount_options") or "").split(",")
            configured_boot_options = str(
                boot.get("firmware_configured_mount_options") or ""
            ).split(",")
            if "ro" in boot_options:
                if (
                    "ro" not in configured_boot_options
                    and boot.get("firmware_source_write_protected_at_boot") is True
                ):
                    field_actions.append(
                        "boot firmware configured rw/defaults but source appeared write-protected at boot · inspect power/PCIe path and run an offline FAT check before updates"
                    )
                else:
                    field_actions.append(
                        "boot firmware is read-only · verify intended mount policy and FAT health before updates"
                    )
                field_priority = min(field_priority, 1)
            nvme_resets = int(boot.get("nvme_controller_resets_since_boot") or 0)
            if nvme_resets:
                field_actions.append(
                    f"NVMe controller reset {nvme_resets}× since boot · inspect power, PCIe connection, and drive health before firmware writes"
                )
                field_priority = min(field_priority, 1)
            if field_actions:
                network_ready.append(ref(host, " · ".join(field_actions), priority=field_priority))

        backup = host.get("backup") or {}
        if backup.get("covered") is not True:
            export_ready = (((facts.get("restricted_helpers") or {}).get("pi_backup_export") or {}).get("check") is True)
            if host.get("status") != "ok":
                reason = "offline and repository missing"
            elif export_ready:
                reason = "Pi export ready; hub target/root key and first backup remain"
            else:
                reason = "repository/target missing"
            backup_held.append(ref(host, reason))

    return [
        lane("routine", "Package maintenance", "Backed, healthy hosts with pending operating-system packages.", routine_ready, routine_held),
        lane("tailscale", "Tailscale channel", "Align the control-plane package source only through the signed, serial one-host workflow.", tailscale_ready, tailscale_held),
        lane("reboot", "Required reboots", "Hosts that need a verified restart to finish installed updates.", reboot_ready, reboot_held),
        lane("os", "Ubuntu 26.04 LTS", "Unsupported interim releases; every move requires current restore and machine-readiness proofs, healthy nearby canaries, and an attended window.", os_ready, os_held),
        lane("operational", "Operational core", "Common support packages, clock discipline, cron, and Tailscale across both profiles.", operational_ready, operational_held),
        lane("software", "Sensor convergence", "Known MRI/CV software drift, preserving the two distinct profiles.", software_ready, software_held),
        lane("restart", "Crash recovery policy", "Serial MRI metadata-only convergence after the exercised nearby proof; CV retains its profile-specific limit.", restart_ready, restart_held),
        lane("camera", "Camera v3", "Candidates first receive an upload-disabled hardware canary; upload-enabled rollout requires primary production proof, backup, restore, and maintenance gates.", camera_ready, camera_held),
        lane("camera_ram", "Camera logs to RAM", "Move only disposable camera logs to bounded tmpfs while preserving exact code, schedules, historical logs, retry state, backup, restore, probes, service, and telemetry.", camera_ram_ready, camera_ram_held),
        lane("journal", "Persistent journal to RAM", "Consider a reversible one-host journald/rsyslog transition only for clean sustained writers after backup, exact restore, workload proof, and the 48-hour nearby canary gate.", journal_ready, journal_held),
        lane("headless", "Headless optimization", "Remove unused desktop/peripheral services only after a reversible nearby canary.", headless_ready, headless_held),
        lane("network", "Field dispatch", "On-site recovery for offline, connectivity, storage, power, or thermal findings; no remote mutation implied.", network_ready, []),
        lane("backup", "Backup onboarding", "Create missing targets before allowing package, code, or OS mutations.", [], backup_held),
    ]


def maintenance_readiness(host: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if host.get("status") != "ok":
        blockers.append("SSH/Tailscale unreachable")
        return {"ready": False, "blockers": blockers}

    facts = host.get("facts") or {}
    profile = host.get("profile", "mri")
    sudo_compat = ((facts.get("restricted_helpers") or {}).get("sudo_compat") or {})
    if sudo_compat and (
        sudo_compat.get("executable") is not True
        or sudo_compat.get("sha256") != SUDO_COMPAT_SHA256
    ):
        blockers.append("privilege wrapper differs from security baseline")
    service_name = "cv_sensor" if profile == "cv" else "mri_sensor"
    if ((facts.get("services") or {}).get(service_name) or {}).get("active") != "active":
        blockers.append("sensor service inactive")
    sensor_runtime = host.get("sensor_runtime_assessment") or assess_sensor_runtime(host)
    if sensor_runtime.get("complete") is not True:
        blockers.append("sensor Python runtime incomplete")
    camera_runtime = host.get("camera_runtime_assessment") or assess_camera_runtime(host)
    if camera_runtime.get("installed") is True and camera_runtime.get("complete") is not True:
        blockers.append("installed camera Python runtime incomplete")
    probe_evidence = probe_mapping_evidence(facts, profile)
    if not probe_evidence["complete"]:
        if probe_evidence["exact"]:
            details = []
            if probe_evidence["missing"]:
                details.append("missing " + ", ".join(probe_evidence["missing"]))
            if probe_evidence["unexpected"]:
                details.append("unexpected " + ", ".join(probe_evidence["unexpected"]))
            blockers.append("configured probe mapping incomplete: " + "; ".join(details))
        else:
            blockers.append(
                f"only {probe_evidence['count']} probes; require {probe_evidence['expected_count']}"
            )

    telemetry = host.get("live_telemetry") or live_telemetry_evidence(host)
    if telemetry.get("backend_available") is not True:
        blockers.append("server telemetry unavailable")
    elif telemetry.get("current") is not True:
        blockers.append("server telemetry older than 5 minutes")
    elif telemetry.get("missing_required"):
        blockers.append(
            "server telemetry missing required channels: "
            + ", ".join(telemetry["missing_required"])
        )
    if telemetry.get("alarm") is True:
        blockers.append("server telemetry alarm active")

    backup = host.get("backup") or {}
    if not backup.get("covered"):
        blockers.append("backup target/repository missing")
    elif backup.get("activity_recent") is not True:
        blockers.append("recent repository activity unconfirmed")
    else:
        restore = backup.get("restore_test") or {}
        restore_recent = bool(
            restore.get("status") == "success" and restore.get("recent") is True
        )
        if backup.get("batch_success") is not True and not restore_recent:
            blockers.append("backup batch incomplete and recent decrypt/restore proof unavailable")

    disk = facts.get("disk") or {}
    if disk.get("root_read_only"):
        blockers.append("root filesystem read-only")
    if (disk.get("used_percent") or 0) >= 85:
        blockers.append("root disk at least 85% full")
    boot_options = str(
        ((facts.get("boot_management") or {}).get("firmware_mount_options") or "")
    )
    if "ro" in boot_options.split(","):
        blockers.append("firmware boot partition read-only")
    if (facts.get("package_manager") or {}).get("busy") is True:
        blockers.append("package manager or unattended upgrades active")

    cpu_temp = facts.get("cpu_temp_c")
    if isinstance(cpu_temp, (int, float)) and cpu_temp >= 75:
        blockers.append("CPU temperature at least 75 °C")
    if facts.get("throttled_flags") not in (None, 0):
        blockers.append("power/thermal throttling recorded")

    return {"ready": not blockers, "blockers": blockers}


def recommendations(host: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if host.get("status") != "ok":
        status = str(host.get("status") or "")
        peer = host.get("tailscale_peer") or {}
        peer_online = peer.get("online") is True
        port_22 = host.get("port_22") is True
        last_seen = str(peer.get("last_seen") or "")
        seen_text = ""
        try:
            seen_at = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
            if seen_at.year > 2000:
                seen_text = f" Tailscale last saw it on {seen_at.astimezone().date().isoformat()}."
        except ValueError:
            pass
        if status == "ssh_failed" and peer_online and port_22:
            message = (
                "Pi is online in Tailscale and TCP port 22 responds, but SSH "
                "session setup fails before host facts can be collected. Restart "
                "sshd locally or perform a controlled reboot/power cycle, then "
                "audit it before maintenance."
            )
            code = "ssh_collection_failed"
        elif status == "ssh_failed" and peer_online:
            message = (
                "Pi is online in Tailscale, but SSH port 22 is unavailable and "
                "host facts cannot be collected. Check sshd locally, then audit "
                "it before maintenance."
            )
            code = "ssh_collection_failed"
        elif status == "fact_collection_failed":
            message = (
                "SSH reached the Pi, but fact collection failed; current service, "
                "probe, storage, and package state is unverified. Review the "
                "collector failure and repeat a full audit before maintenance."
            )
            code = "fact_collection_failed"
        else:
            message = (
                "Pi is absent from both Tailscale and SSH."
                + seen_text
                + " Check site power, Ethernet/Wi-Fi, and the Pi status LEDs; audit it before any maintenance after it returns."
            )
            code = "offline"
        items.append({
            "severity": "critical",
            "code": code,
            "message": message,
        })

        telemetry = host.get("live_telemetry") or {}
        telemetry_age = telemetry.get("age_seconds")
        if telemetry.get("backend_available") is True and telemetry.get("current") is not True:
            age_text = (
                f" ({telemetry_age / 3600:.1f} hours old)"
                if isinstance(telemetry_age, (int, float))
                else ""
            )
            items.append({
                "severity": "critical",
                "code": "sensor_telemetry_stale",
                "message": (
                    f"Production sensor telemetry is stale{age_text}; website "
                    "temperatures are historical until Pi reporting resumes."
                ),
            })

        camera = host.get("camera_telemetry") or {}
        camera_age = camera.get("age_hours")
        if (
            camera.get("backend_available") is True
            and camera.get("matched") is True
            and isinstance(camera_age, (int, float))
            and camera_age > 36
        ):
            items.append({
                "severity": "critical",
                "code": "camera_upload_stale",
                "message": (
                    f"Latest production camera-pressure reading is {camera_age:.1f} "
                    "hours old; the website is showing historical camera data."
                ),
            })
        return items

    facts = host.get("facts") or {}
    gpio_alignment = host.get("gpio_alignment") or gpio_alignment_evidence(facts)
    profile = host.get("profile", "mri")
    sudo_compat = ((facts.get("restricted_helpers") or {}).get("sudo_compat") or {})
    if sudo_compat and (
        sudo_compat.get("executable") is not True
        or sudo_compat.get("sha256") != SUDO_COMPAT_SHA256
    ):
        items.append({
            "severity": "warning",
            "code": "sudo_compat_drift",
            "message": "The fleet privilege wrapper is missing, non-executable, or differs from the no-echo security baseline; repair it before privileged maintenance.",
        })
    operational = host.get("operational_baseline") or assess_operational_stack(host)
    if operational.get("assessed") and not operational.get("matches"):
        items.append({
            "severity": "warning",
            "code": "operational_baseline",
            "message": "Shared operational baseline differs: "
            + "; ".join(operational.get("deviations") or []),
        })
    sensor_runtime = host.get("sensor_runtime_assessment") or assess_sensor_runtime(host)
    if sensor_runtime.get("assessed") and sensor_runtime.get("complete") is not True:
        issues = []
        if sensor_runtime.get("missing"):
            issues.append("missing " + ", ".join(sensor_runtime["missing"]))
        if sensor_runtime.get("incompatible"):
            issues.append("outside the compatible baseline: " + ", ".join(sensor_runtime["incompatible"]))
        items.append({
            "severity": "critical",
            "code": "sensor_runtime_dependencies",
            "message": (
                "The active sensor virtual environment has direct dependency drift: "
                + "; ".join(issues or ["unknown"])
                + "; repair the profile environment and prove service/telemetry recovery before other maintenance."
            ),
        })
    probe_mapping = host.get("probe_mapping") or probe_mapping_evidence(facts, profile)
    if probe_mapping.get("complete") is not True:
        physical_count = int(probe_mapping.get("count") or 0)
        expected_count = int(probe_mapping.get("expected_count") or 0)
        missing = [str(item) for item in probe_mapping.get("missing") or []]
        unexpected = [str(item) for item in probe_mapping.get("unexpected") or []]
        if expected_count and physical_count == 0:
            message = (
                f"None of the {expected_count} configured 1-Wire probes is visible. "
                "Check the shared sensor-bus 3.3 V, ground, GPIO data connector, and pull-up; "
                "then cold-power-cycle the Pi and verify exact probe IDs before other maintenance."
            )
            if host.get("inventory_name") == "agcmr2":
                message += (
                    " Three controlled warm reboots with full recovery windows on 2026-07-17 "
                    "already failed to restore this bus; do not repeat warm reboots as the next action."
                )
            elif host.get("inventory_name") == "svimr1":
                message += (
                    " A sensor-only 1-Wire driver reload and one controlled warm reboot on "
                    "2026-07-21 already failed while the external USB Wi-Fi route remained "
                    "healthy; inspect the shared bus onsite rather than repeating remote reboots."
                )
        else:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            message = (
                f"Physical 1-Wire probe mapping is incomplete ({physical_count}/{expected_count or 'required'} visible)"
                + (": " + "; ".join(details) if details else "")
                + ". Check the sensor bus and require exact probe recovery before maintenance."
            )
        items.append({
            "severity": "critical",
            "code": "probe_mapping",
            "message": message,
        })
    camera_runtime = host.get("camera_runtime_assessment") or assess_camera_runtime(host)
    if camera_runtime.get("installed") is True and camera_runtime.get("complete") is not True:
        issues = []
        if camera_runtime.get("missing"):
            issues.append("missing " + ", ".join(camera_runtime["missing"]))
        if camera_runtime.get("incompatible"):
            issues.append(
                "outside the compatible baseline: "
                + ", ".join(camera_runtime["incompatible"])
            )
        items.append({
            "severity": "critical",
            "code": "camera_runtime_dependencies",
            "message": (
                "The installed camera virtual environment cannot satisfy its direct runtime contract: "
                + "; ".join(issues or ["interpreter or dependency evidence unavailable"])
                + "; rebuild it atomically and complete an upload-disabled camera smoke test."
            ),
        })
    ram_budget = host.get("ram_budget_assessment") or assess_ram_budget(host)
    if ram_budget.get("assessed") and ram_budget.get("healthy") is not True:
        items.append({
            "severity": str(ram_budget.get("severity") or "warning"),
            "code": "ram_budget",
            "message": (
                "RAM-backed workload safety gate is not healthy: "
                + "; ".join(str(issue) for issue in ram_budget.get("issues") or ["unknown pressure"])
                + ". Hold additional volatile-log or RAM-workload rollout until a clean audit confirms recovery."
            ),
        })
    update_policy = host.get("update_policy_assessment") or assess_update_policy(host)
    if update_policy.get("assessed") and update_policy.get("aligned") is not True:
        items.append({
            "severity": str(update_policy.get("severity") or "warning"),
            "code": "update_policy",
            "message": (
                "Operating-system update policy differs from the safe fleet contract: "
                + "; ".join(
                    str(item) for item in update_policy.get("deviations") or ["unknown drift"]
                )
                + ". Keep changes serial and prove sensor/telemetry recovery."
            ),
        })
    operational_stack = facts.get("operational_stack") or {}
    tailscale_channel = (
        ((operational_stack.get("package_channels") or {}).get("tailscale") or {})
        .get("channel")
    )
    if tailscale_channel == "distribution":
        tailscale_version = (
            (operational_stack.get("required_packages") or {}).get("tailscale")
            or "unknown version"
        )
        maintenance_blockers = (host.get("maintenance") or {}).get("blockers") or []
        camera_observation = host.get("camera_observation") or {}
        if camera_observation.get("planned") and camera_observation.get("pending"):
            action = (
                "keep it unchanged through the planned production camera proof, "
                "then rerun preflight and use the signed official-stable one-host wave"
            )
        elif maintenance_blockers:
            action = (
                "hold channel convergence until "
                + "; ".join(str(item) for item in maintenance_blockers)
                + ", then rerun the signed official-stable one-host wave"
            )
        else:
            action = "use the signed official-stable one-host wave after a fresh preflight"
        items.append({
            "severity": "warning",
            "code": "tailscale_channel",
            "message": (
                f"Tailscale {tailscale_version} uses the distribution package channel; "
                f"{action}."
            ),
        })
    background = ((facts.get("operational_stack") or {}).get("background_services") or {})
    active_background = sorted(
        name.removesuffix(".service")
        for name, details in background.items()
        if (details or {}).get("active") == "active"
    )
    if "gdm" in active_background:
        items.append({
            "severity": "info",
            "code": "desktop_stack",
            "message": "A graphical desktop service is active on this sensor Pi; confirm no local-display dependency, then use a backed nearby pilot before disabling desktop/peripheral services.",
        })
    ram_optimization = facts.get("ram_optimization") or {}
    if "rsyslog" in active_background and ram_optimization.get("persistent_journal"):
        items.append({
            "severity": "info",
            "code": "duplicate_logging",
            "message": "Both persistent journald and rsyslog are active; review duplicate SSD logging during the RAM-journal pilot.",
        })
    elif "rsyslog" in active_background and ram_optimization.get("journald_volatile"):
        items.append({
            "severity": "info",
            "code": "rsyslog_disk_logging",
            "message": "Journald is volatile, but rsyslog still writes syslog, kernel, and authentication logs to the SSD; use a backed one-host pilot before disabling it.",
        })
    elif (
        ram_optimization.get("journald_volatile")
        and (background.get("rsyslog.service") or {}).get("active") == "inactive"
        and (background.get("rsyslog.service") or {}).get("enabled") == "disabled"
    ):
        pilot_epoch = ((ram_optimization.get("rsyslog_ram_pilot") or {}).get("applied_epoch"))
        boundary_text = (
            " The measured post-change window begins at "
            + datetime.fromtimestamp(pilot_epoch, tz=FLEET_TIMEZONE).isoformat(timespec="seconds")
            + "."
            if isinstance(pilot_epoch, (int, float)) and pilot_epoch > 0
            else ""
        )
        items.append({
            "severity": "info",
            "code": "ram_logging_pilot",
            "message": "Persistent rsyslog writes are disabled; bounded journald remains active in RAM while historical log files are retained." + boundary_text,
        })
    weakest = routed_wifi_signal(facts)
    routed_wifi = routed_wifi_details(facts) or {}
    using_onboard_wifi = (
        routed_wifi.get("interface") == "wlan0"
        and routed_wifi.get("driver") == "brcmfmac"
    )
    grade = signal_grade(weakest)
    frequency = routed_wifi.get("frequency_mhz")
    band = (
        "5 GHz" if isinstance(frequency, (int, float)) and frequency >= 5000
        else "2.4 GHz" if isinstance(frequency, (int, float)) and frequency >= 2400
        else "unknown band"
    )
    adapter_kind = routed_wifi.get("adapter_kind") or (
        "onboard" if using_onboard_wifi else "external or unknown"
    )
    radio_context = (
        f"{adapter_kind} {band} radio, power save {routed_wifi.get('power_save', 'unknown')}"
    )
    diagnostic_note = WIFI_DIAGNOSTIC_NOTES.get(host.get("inventory_name", ""), "")
    if grade == "critical":
        action = (
            "install a quality USB Wi-Fi adapter with an external antenna or provide Ethernet"
            if using_onboard_wifi
            else "reposition the active adapter/antenna or provide Ethernet"
        )
        message = f"Wi-Fi is very weak ({weakest:g} dBm via {routed_wifi.get('interface', 'the routed interface')}; {radio_context}); {action}."
        if diagnostic_note:
            message += " " + diagnostic_note
        items.append({"severity": "critical", "code": "wifi", "message": message})
    elif grade == "weak":
        action = (
            "reposition the Pi and remeasure; if it remains below -67 dBm, install a quality external-antenna USB Wi-Fi adapter or Ethernet"
            if using_onboard_wifi
            else "reposition the active USB adapter/antenna and remeasure before remote maintenance"
        )
        message = f"Wi-Fi is marginal ({weakest:g} dBm via {routed_wifi.get('interface', 'the routed interface')}; {radio_context}); {action}."
        if diagnostic_note:
            message += " " + diagnostic_note
        items.append({"severity": "warning", "code": "wifi", "message": message})
    elif weakest is None:
        items.append({"severity": "info", "code": "wifi_unknown", "message": "Wi-Fi signal was not reported; verify the active network interface."})

    if gpio_alignment.get("assessed") and gpio_alignment.get("aligned") is not True:
        items.append({
            "severity": "warning",
            "code": "gpio_alignment",
            "message": "1-Wire GPIO evidence differs: " + "; ".join(gpio_alignment.get("deviations") or ["review boot overlay and live pin state"]),
        })

    calibration = host.get("calibration_mapping") or {}
    if calibration.get("assessed") and calibration.get("aligned") is not True:
        details = []
        if calibration.get("orphaned_ids"):
            details.append("offsets reference unknown IDs: " + ", ".join(calibration["orphaned_ids"]))
        if calibration.get("invalid_value_ids"):
            details.append("non-numeric offsets: " + ", ".join(calibration["invalid_value_ids"]))
        items.append({
            "severity": "warning",
            "code": "calibration_mapping",
            "message": "Calibration mapping differs: " + "; ".join(details or ["review stored offsets"]),
        })

    live_telemetry = host.get("live_telemetry") or live_telemetry_evidence(host)
    if live_telemetry.get("backend_available") is not True:
        items.append({
            "severity": "warning",
            "code": "live_telemetry_unavailable",
            "message": "No matching server telemetry snapshot is available for this Pi; verify its site identifier and data path before maintenance.",
        })
    elif live_telemetry.get("current") is not True:
        age_seconds = live_telemetry.get("age_seconds")
        age_text = (
            f" ({round(age_seconds / 60)} minutes old)"
            if isinstance(age_seconds, (int, float))
            else ""
        )
        items.append({
            "severity": "warning",
            "code": "live_telemetry_stale",
            "message": "Server telemetry is not current" + age_text + "; verify the sensor service and network path.",
        })
    if live_telemetry.get("missing_required"):
        items.append({
            "severity": "warning",
            "code": "live_telemetry_missing",
            "message": "Required live readings are missing: "
            + ", ".join(live_telemetry["missing_required"])
            + ". Check probe mapping and service logs before maintenance.",
        })
    if live_telemetry.get("alarm") is True:
        items.append({
            "severity": "critical",
            "code": "live_telemetry_alarm",
            "message": "The server reports an active sensor alarm: "
            + ", ".join(live_telemetry.get("alarm_fields") or ["unspecified alarm"])
            + ". Review temperatures before changing the Pi.",
        })

    runtime_policy = host.get("runtime_policy") or {}
    if runtime_policy.get("approved_exception") is True:
        items.append({
            "severity": "info",
            "code": "runtime_policy_exception",
            "message": runtime_policy.get("exception_reason")
            or "Approved site-specific runtime-policy exception.",
        })
    elif (
        runtime_policy.get("assessed")
        and runtime_policy.get("approved_program")
        and runtime_policy.get("matches") is not True
    ):
        items.append({
            "severity": "warning",
            "code": "runtime_policy",
            "message": "Sensor runtime policy differs: "
            + "; ".join(runtime_policy.get("deviations") or ["review effective settings"]),
        })

    service_name = "cv_sensor" if profile == "cv" else "mri_sensor"
    service_details = (facts.get("services") or {}).get(service_name) or {}
    service = service_details.get("active")
    if service != "active":
        items.append({"severity": "critical", "code": "service", "message": f"Expected {profile.upper()} sensor service is {service or 'unknown'}."})
    service_user = service_details.get("user", "")
    if service == "active" and service_user in {"", "root"}:
        pilot_text = "a nearby CV-profile pilot" if profile == "cv" else "a backed-up nearby MRI pilot"
        items.append({"severity": "warning", "code": "service_user", "message": f"Sensor service runs as root; migrate it to the site account after {pilot_text}."})
    if service_details.get("unit_verify"):
        first_warning = service_details["unit_verify"].splitlines()[0]
        items.append({"severity": "warning", "code": "unit", "message": f"Systemd unit validation warning: {first_warning}"})

    disk = facts.get("disk") or {}
    if (disk.get("used_percent") or 0) >= 85:
        items.append({"severity": "critical", "code": "disk", "message": f"Root disk is {disk['used_percent']}% full."})
    if disk.get("root_read_only"):
        items.append({"severity": "critical", "code": "readonly", "message": "Root filesystem is read-only."})

    storage = facts.get("storage_health") or {}
    write_rate = storage.get("recent_mib_written_per_day")
    sample_seconds = storage.get("write_rate_sample_seconds") or 0
    write_trend = storage.get("write_trend") or {}
    trend_samples = int(write_trend.get("sample_count") or 0)
    median_write_rate = write_trend.get("median_mib_written_per_day")
    ram_policy = facts.get("ram_optimization") or {}
    rsyslog_state = ((((facts.get("operational_stack") or {}).get("background_services") or {}).get("rsyslog.service") or {}))
    if sample_seconds >= 300 and isinstance(write_rate, (int, float)):
        if write_trend.get("sustained_high") and isinstance(median_write_rate, (int, float)):
            if (host.get("backup") or {}).get("covered") is not True:
                action = "onboard and verify its backup first, then use the rollback-capable volatile-journal pilot; do not change logging while it is unbacked"
            elif ram_policy.get("persistent_journal"):
                action = "persistent journald and rsyslog remain active; schedule a rollback-capable volatile-journal pilot after current canary evidence is accepted"
            else:
                action = "correlate package activity and logging before changing SSD policy"
            items.append({"severity": "warning", "code": "storage_writes", "message": f"Root-device writes are repeatedly high: {median_write_rate / 1024:.1f} GiB/day median across {trend_samples} non-overlapping intervals; {action}."})
        elif write_rate >= 5120:
            items.append({"severity": "info", "code": "storage_write_burst", "message": f"One valid interval extrapolates to {write_rate / 1024:.1f} GiB/day, but the multi-sample trend is not yet high; recheck before treating this as sustained wear."})
        elif write_rate >= 1024:
            if ram_policy.get("journald_volatile") and rsyslog_state.get("active") == "inactive":
                context = "continue observing the journald/rsyslog RAM canary"
            elif ram_policy.get("journald_volatile"):
                context = "continue observing the volatile-journal canary and duplicate persistent logging"
            else:
                context = "collect repeated intervals before selecting a backed RAM-journal pilot"
            items.append({"severity": "info", "code": "storage_writes", "message": f"Recent root-device writes extrapolate to {write_rate / 1024:.1f} GiB/day; {context}."})
    smart = storage.get("smart") or {}
    unsafe_delta = storage.get("unsafe_shutdowns_delta")
    if isinstance(unsafe_delta, int) and unsafe_delta > 0:
        across_reboot = storage.get("unsafe_shutdowns_interval_reboot") is True
        severity = "info" if across_reboot else ("critical" if unsafe_delta >= 2 else "warning")
        message = (
            f"Root storage's unsafe-shutdown counter increased by {unsafe_delta} across a reboot interval; some USB/NVMe bridges count orderly Pi restarts, so recheck the next no-reboot audit and investigate power only if it rises again."
            if across_reboot
            else f"Root storage recorded {unsafe_delta} new unsafe shutdown{'s' if unsafe_delta != 1 else ''} without an intervening reboot; inspect Pi power, cabling, and abrupt power loss before maintenance."
        )
        items.append({
            "severity": severity,
            "code": "unsafe_shutdown_increase",
            "message": message,
        })
    if smart.get("concerning") is True:
        items.append({"severity": "critical", "code": "storage_health", "message": "SMART/NVMe reports a failed-health flag, media error, or non-zero bad/pending sector count; verify the backup and plan drive replacement."})
    elif smart.get("available") is True:
        temperature = smart.get("temperature_c")
        percentage_used = smart.get("percentage_used")
        if isinstance(temperature, (int, float)) and temperature >= 70:
            items.append({"severity": "warning", "code": "storage_temperature", "message": f"Root storage temperature is high ({temperature:g} °C); inspect enclosure airflow."})
        if isinstance(percentage_used, (int, float)) and percentage_used >= 80:
            items.append({"severity": "warning", "code": "storage_wear", "message": f"NVMe reports {percentage_used:g}% endurance used; prepare a replacement and confirm restore evidence."})
    elif not storage.get("smartctl_available"):
        storage_boot = facts.get("boot_management") or {}
        storage_mount_options = str(storage_boot.get("firmware_mount_options") or "").split(",")
        storage_nvme_resets = int(storage_boot.get("nvme_controller_resets_since_boot") or 0)
        if "ro" in storage_mount_options or storage_nvme_resets:
            items.append({
                "severity": "info",
                "code": "smart_held",
                "message": (
                    "SMART/NVMe tooling is intentionally held on this host until its native "
                    "storage/power path is inspected onsite and a stable writable boot is proven; "
                    "the guarded USB-storage wave is complete on the other reachable Pis."
                ),
            })
        else:
            items.append({"severity": "info", "code": "smart_unavailable", "message": "Capacity and write counters are available, but SMART/NVMe media-health data is not; use the guarded on-demand smartmontools wave after current backup and bridge compatibility are verified."})
    else:
        items.append({"severity": "warning", "code": "smart_bridge", "message": "smartmontools is installed but the root-storage bridge did not return usable health data; keep capacity/write monitoring and review bridge compatibility."})

    cpu_temp = facts.get("cpu_temp_c")
    if cpu_temp is not None and cpu_temp >= 75:
        items.append({"severity": "critical", "code": "temperature", "message": f"CPU temperature is high ({cpu_temp:g} °C); inspect enclosure airflow."})
    if facts.get("throttled_flags") not in (None, 0):
        items.append({"severity": "warning", "code": "throttle", "message": "Power or thermal throttling has been recorded."})

    gpio = facts.get("gpio") or {}
    pin_state = str(gpio.get("pin_state") or "").strip()
    if not pin_state or pin_state.lower() == "unavailable":
        pin = gpio.get("one_wire_pin") or "configured 1-Wire pin"
        items.append({
            "severity": "info",
            "code": "pin_state",
            "message": f"Live state for GPIO{pin} is unavailable through both the pin utilities and the kernel GPIO view; verify debugfs access before electrical troubleshooting.",
        })

    package_maintenance = facts.get("package_maintenance") or {}
    listed_updates = int(package_maintenance.get("listed_count", facts.get("packages_upgradable") or 0))
    eligible_updates = int(package_maintenance.get("eligible_count", listed_updates))
    deferred_updates = int(package_maintenance.get("deferred_count", max(0, listed_updates - eligible_updates)))
    boot = facts.get("boot_management") or {}
    boot_mount_options = str(boot.get("firmware_mount_options") or "").split(",")
    nvme_resets = int(boot.get("nvme_controller_resets_since_boot") or 0)
    storage_holds_updates = "ro" in boot_mount_options or nvme_resets > 0
    if eligible_updates and storage_holds_updates:
        reasons = []
        if "ro" in boot_mount_options:
            reasons.append("the boot firmware partition is read-only")
        if nvme_resets:
            reasons.append(f"the NVMe controller reset {nvme_resets} times")
        items.append({
            "severity": "warning",
            "code": "updates_held",
            "message": (
                f"{eligible_updates} operating-system packages are eligible but held because "
                + " and ".join(reasons)
                + "; inspect the storage/power path and prove a stable writable boot before package changes."
            ),
        })
        eligible_names = {
            str(name) for name in (package_maintenance.get("eligible_names") or [])
        }
        if tailscale_channel == "official_stable" and "tailscale" in eligible_names:
            tailscale_version = (
                (operational_stack.get("required_packages") or {}).get("tailscale")
                or "unknown version"
            )
            items.append({
                "severity": "info",
                "code": "tailscale_version_held",
                "message": (
                    f"Tailscale {tailscale_version} already uses the signed official-stable "
                    "channel, but the package itself is among the storage-held updates; "
                    "matching repository policy must not be reported as matching package "
                    "version until the storage hold is cleared."
                ),
            })
    elif eligible_updates >= 50:
        items.append({"severity": "warning", "code": "updates", "message": f"{eligible_updates} operating-system packages are eligible now; schedule a controlled update."})
    elif eligible_updates:
        items.append({"severity": "info", "code": "updates", "message": f"{eligible_updates} packages are eligible now."})
    elif deferred_updates:
        items.append({"severity": "info", "code": "updates_deferred", "message": f"{deferred_updates} packages are listed but phased or otherwise deferred; apt currently offers no eligible upgrade, so do not force them."})
    if facts.get("reboot_required"):
        items.append({"severity": "warning", "code": "reboot", "message": "A reboot is required to finish installed updates."})

    os_name = facts.get("os", "")
    posture = host.get("os_posture") or os_posture(host)
    if posture.get("state") == "eol" and "Ubuntu 25.04" in os_name:
        items.append({"severity": "critical", "code": "os", "message": "Ubuntu 25.04 reached end of life on 2026-01-15; use its reviewed staged path to Ubuntu 26.04 LTS only after production restore proof."})
    elif posture.get("state") == "eol":
        items.append({"severity": "critical", "code": "os", "message": "Ubuntu 25.10 reached end of life on 2026-07-09; prioritize a controlled move to Ubuntu 26.04 LTS after production restore proof."})
    elif posture.get("state") == "supported_lts":
        items.append({"severity": "info", "code": "os", "message": "Ubuntu 24.04 LTS remains in standard support through May 2029; upgrade after the 26.04 LTS pilot is proven."})
    elif posture.get("state") == "unknown" and os_name:
        items.append({"severity": "warning", "code": "os_unknown", "message": "The observed operating-system release is not classified in the fleet lifecycle policy; review it before maintenance."})

    boot = facts.get("boot_management") or {}
    mount_options = str(boot.get("firmware_mount_options") or "")
    if "ro" in mount_options.split(","):
        source_writable = boot.get("firmware_source_read_only") is False
        source_text = " The block layer is currently writable, so this is not a permanent hardware lock." if source_writable else ""
        configured_options = str(boot.get("firmware_configured_mount_options") or "")
        unexpected_text = ""
        if (
            "ro" not in configured_options.split(",")
            and boot.get("firmware_source_write_protected_at_boot") is True
        ):
            configured_text = configured_options or "rw/defaults"
            unexpected_text = (
                f" Persistent configuration requests {configured_text}, but the source appeared write-protected during boot; treat this as an unexpected storage or power-path condition, not policy."
            )
        items.append({
            "severity": "warning",
            "code": "boot_readonly",
            "message": "The firmware boot partition is read-only; kernel/initramfs package configuration can fail until filesystem health and mount state are verified." + source_text + unexpected_text,
        })
    nvme_resets = int(boot.get("nvme_controller_resets_since_boot") or 0)
    if nvme_resets:
        power_text = " The kernel also logged the NVMe power-saving warning." if boot.get("nvme_power_saving_warning") else ""
        items.append({
            "severity": "warning",
            "code": "nvme_controller_resets",
            "message": (
                f"The NVMe controller reset {nvme_resets} times during the current boot."
                + power_text
                + " Keep firmware writes and package changes held until power/PCIe inspection, drive-health evidence, and a controlled recovery window are available."
            ),
        })
    if boot.get("new_state") == "unknown":
        items.append({
            "severity": "warning",
            "code": "boot_candidate",
            "message": "Untested Raspberry Pi A/B boot assets are staged; use the verified piboot-try path and require candidate promotion, with a kernel change when the staged kernel image differs.",
        })
    elif boot.get("new_state") == "bad":
        items.append({
            "severity": "critical",
            "code": "boot_candidate_bad",
            "message": "Raspberry Pi A/B boot assets are marked bad after fallback; retain the known-good current kernel and review before retrying.",
        })

    probe_evidence = probe_mapping_evidence(facts, profile)
    if not probe_evidence["complete"]:
        if probe_evidence["exact"]:
            details = []
            if probe_evidence["missing"]:
                details.append("missing " + ", ".join(probe_evidence["missing"]))
            if probe_evidence["unexpected"]:
                details.append("unexpected " + ", ".join(probe_evidence["unexpected"]))
            message = "Configured 1-Wire probe mapping is incomplete: " + "; ".join(details) + "."
        else:
            message = f"Only {probe_evidence['count']} 1-Wire sensors are visible (expected at least {probe_evidence['expected_count']})."
        items.append({"severity": "warning", "code": "sensors", "message": message})

    ram = facts.get("ram_optimization") or {}
    if not ram.get("app_memory_only"):
        items.append({"severity": "warning", "code": "wear", "message": "Sensor application still writes log files; enable its RAM/stdout-only logging mode."})
    elif ram.get("persistent_journal"):
        usage = ram.get("journal_disk_usage") or "persistent journal enabled"
        items.append({"severity": "info", "code": "wear", "message": f"Sensor logging is RAM/stdout-only, but journald persists to SSD ({usage}); pilot a 32 MiB volatile journal cap."})
    elif ram.get("journald_volatile") and ram.get("persistent_journal_directory"):
        cap = ram.get("journal_runtime_max_use") or "bounded RAM"
        items.append({"severity": "info", "code": "wear_pilot", "message": f"SSD-write pilot active: journald is volatile and capped at {cap}; the prior on-disk archive is retained until the pilot completes."})
    camera_logging = facts.get("camera_logging") or {}
    if camera_logging.get("installed") and not camera_logging.get("memory_only"):
        log_bytes = camera_logging.get("log_bytes")
        size_text = f" ({log_bytes / 1048576:.1f} MiB retained)" if isinstance(log_bytes, (int, float)) else ""
        items.append({"severity": "info", "code": "camera_logs", "message": f"Camera retry/capture logs still write to SSD{size_text}; use the nearby RAM-log pilot while keeping failed-session data durable."})
    if camera_logging.get("memory_only") and camera_logging.get("retry_state_durable") is not True:
        items.append({"severity": "critical", "code": "camera_retry_state", "message": "Camera logs are in RAM but failed-session retry state is not confirmed durable; restore durable retry storage before relying on captures."})
    if camera_logging.get("installed") and host.get("camera_management") == "observed_legacy":
        items.append({"severity": "warning", "code": "camera_legacy", "message": "Camera agent is inventoried as an observed legacy build, not role-managed; compare its fingerprint and schedule before approving convergence."})
    camera_software = camera_logging.get("software") or {}
    ignored_camera_keys = camera_software.get("ignored_safe_config_keys") or []
    ignored_behavior_keys = sorted(set(ignored_camera_keys) & {"UPLOAD_ENABLED", "UPLOAD_MODE"})
    if ignored_behavior_keys:
        items.append({"severity": "warning", "code": "camera_config_ignored", "message": f"Camera environment declares {', '.join(ignored_behavior_keys)}, but the installed capture program does not read those settings; treat observed runtime behavior as authoritative."})
    if camera_logging.get("installed"):
        camera_telemetry = host.get("camera_telemetry") or {}
        camera_ingest = host.get("camera_ingest_telemetry") or {}
        if camera_telemetry.get("backend_available") is False:
            items.append({"severity": "warning", "code": "camera_backend_unavailable", "message": "Production camera-pressure recency is unavailable because the production API could not be queried; raw image arrival alone does not prove website posting."})
        elif camera_telemetry.get("matched") is False:
            ingest_age = camera_ingest.get("age_hours")
            if isinstance(ingest_age, (int, float)) and ingest_age <= 36:
                message = (
                    f"A raw camera image arrived {ingest_age:.0f} hours ago, but no "
                    "production return-pressure reading exists; inspect batch parsing "
                    "and production forwarding."
                )
                severity = "critical"
            else:
                message = (
                    "No production return-pressure reading exists and no recent raw "
                    "camera image proves capture; inspect the Pi schedule, upload path, "
                    "batch processing, and production forwarding."
                )
                severity = "warning"
            items.append({"severity": severity, "code": "camera_upload_missing", "message": message})
        else:
            camera_age = camera_telemetry.get("age_hours")
            if isinstance(camera_age, (int, float)) and camera_age > 72:
                ingest_age = camera_ingest.get("age_hours")
                pipeline_note = (
                    f" Raw images are current ({ingest_age:.0f} hours old), so this is a processing/forwarding failure rather than a Pi capture outage."
                    if isinstance(ingest_age, (int, float)) and ingest_age <= 36
                    else ""
                )
                items.append({"severity": "critical", "code": "camera_upload_stale", "message": f"Latest production camera-pressure reading is {camera_age:.0f} hours old.{pipeline_note}"})
            elif isinstance(camera_age, (int, float)) and camera_age > 36:
                ingest_age = camera_ingest.get("age_hours")
                pipeline_note = (
                    f" Raw images are current ({ingest_age:.0f} hours old), so inspect batch processing and production forwarding."
                    if isinstance(ingest_age, (int, float)) and ingest_age <= 36
                    else " The twice-daily capture or upload schedule has likely missed multiple runs."
                )
                items.append({"severity": "warning", "code": "camera_upload_stale", "message": f"Latest production camera-pressure reading is {camera_age:.0f} hours old.{pipeline_note}"})
    camera_observation = host.get("camera_observation") or {}
    if camera_observation.get("superseded_by_current_camera") is True:
        items.append({
            "severity": "info",
            "code": "camera_observation_superseded",
            "message": (
                "The last successful natural camera proof belongs to an older exact camera build; "
                "require a new scheduled proof matching the currently installed fingerprint before rollout approval."
            ),
        })
    elif camera_observation.get("planned") is True and camera_observation.get("pending") is True:
        items.append({
            "severity": "info",
            "code": "camera_observation_planned",
            "message": (
                "A read-only machine proof is scheduled around the natural camera job at "
                + str(camera_observation.get("not_before") or "the planned time")
                + "; it does not trigger an extra capture."
            ),
        })
    elif camera_observation.get("expired") is True:
        items.append({
            "severity": "warning",
            "code": "camera_observation_expired",
            "message": "The planned camera proof expired without a passing verification; review the controller timer and baseline evidence before rescheduling.",
        })
    backup = host.get("backup") or {}
    if not backup.get("covered"):
        export_ready = (((facts.get("restricted_helpers") or {}).get("pi_backup_export") or {}).get("check") is True)
        if export_ready and host.get("inventory_name") == "gcmcmr2":
            message = (
                "Nearby-first backup canary is Pi-ready (check mode changed=0); "
                "the Restic hub still needs its separate sudo authorization, "
                "target record, root pull-key check, and successful first snapshot."
            )
        elif export_ready and host.get("inventory_name") in {"agcmr2", "vwm2", "vwm3"}:
            message = (
                "Pi export helper is ready; queue this host after the nearby GCMC MR2 "
                "backup canary, then require the hub target/root-key check and a successful first snapshot."
            )
        elif export_ready:
            message = "Pi export helper is ready; the Restic hub still needs its target/root SSH authorization and a successful first backup."
        else:
            message = "No matching Pi repository is registered on the Restic backup hub."
        items.append({"severity": "warning", "code": "backup", "message": message})
    elif backup.get("activity_recent") is False:
        age = backup.get("activity_age_hours")
        age_text = f" ({age:.0f} hours old)" if isinstance(age, (int, float)) else ""
        items.append({"severity": "warning", "code": "backup_stale", "message": f"Restic repository activity is stale{age_text}; verify the backup job before maintenance."})
    elif not backup.get("last_snapshot_activity"):
        items.append({"severity": "info", "code": "backup_unknown", "message": "Restic repository exists, but recent snapshot-directory activity could not be confirmed."})
    restore_test = backup.get("restore_test") or {}
    if backup.get("covered") and not restore_test:
        items.append({"severity": "info", "code": "restore_untested", "message": "No recorded decrypt-and-restore test exists; complete one before an OS-version upgrade."})
    elif restore_test and restore_test.get("recent") is not True:
        status = restore_test.get("status") or "unknown"
        items.append({"severity": "warning", "code": "restore_stale", "message": f"Latest restore test is {status} or older than the 90-day evidence window."})
    rank = {"critical": 0, "warning": 1, "info": 2}
    return sorted(items, key=lambda item: rank.get(item["severity"], 3))


def fleet_payload() -> dict[str, Any]:
    trusted_reports = load_complete_reports(12)
    report = load_latest_inventory_report()
    reports = [report] + [
        candidate
        for candidate in trusted_reports
        if candidate.get("source_file") != report.get("source_file")
    ]
    immediate_previous_report = reports[1] if len(reports) > 1 else {}
    previous_report = previous_sample_report(reports)
    previous_report_index = next(
        (index for index, candidate in enumerate(reports) if candidate is previous_report),
        None,
    )
    immediate_previous_hosts = {
        row.get("inventory_name"): row
        for row in (immediate_previous_report.get("results") or [])
        if row.get("inventory_name")
    }
    previous_hosts = {
        row.get("inventory_name"): row
        for row in (previous_report.get("results") or [])
        if row.get("inventory_name")
    }
    current_time = report_time(report)
    previous_time = report_time(previous_report)
    report_delta_seconds = (
        (current_time - previous_time).total_seconds()
        if current_time and previous_time
        else None
    )
    camera_observations = load_camera_observations()
    camera_candidate_canaries = load_camera_candidate_canaries()
    camera_candidate_deployments = load_camera_candidate_deployments()
    restart_recovery_verifications = load_restart_recovery_verifications()
    maintenance_actions = load_verified_maintenance_actions()
    package_downloads = load_verified_package_downloads()
    os_upgrade_readiness = load_os_upgrade_readiness()
    os_upgrade_verifications = load_os_upgrade_verifications()
    optimization_observation = load_optimization_observation()
    storage_maintenance_windows = load_storage_maintenance_windows()
    last_known_index = load_last_known_facts()
    mri_snapshot = {row.get("id"): row for row in (fetch_json(MRI_SNAPSHOT_URL) or [])}
    cv_snapshot = {row.get("id"): row for row in (fetch_json(CV_SNAPSHOT_URL) or [])}
    camera_recent_payload = fetch_json(CAMERA_RECENT_URL)
    camera_backend_available = bool(
        isinstance(camera_recent_payload, dict)
        and isinstance(camera_recent_payload.get("items"), list)
    )
    camera_latest = latest_camera_ingest_by_site(camera_recent_payload)
    production_pressure_payload = fetch_json(PRODUCTION_RETURN_PRESSURE_URL)
    production_backend_available = bool(
        isinstance(production_pressure_payload, list)
        and production_pressure_payload
    )
    production_latest = production_pressure_by_site(production_pressure_payload)
    try:
        backup_coverage = json.loads(BACKUP_COVERAGE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        backup_coverage = {"repositories": [], "checked_at": None, "note": "Backup coverage unavailable."}
    backup_repositories = set(backup_coverage.get("repositories") or [])
    backup_targets = {
        row.get("repository")
        for row in (backup_coverage.get("configured_targets") or [])
        if row.get("repository")
    }
    backup_status = {
        row.get("repository"): row
        for row in (backup_coverage.get("repository_status") or [])
        if row.get("repository")
    }
    restore_status = {
        row.get("repository"): row
        for row in (backup_coverage.get("restore_tests") or [])
        if row.get("repository")
    }
    hosts = []
    for raw in report.get("results") or []:
        host = dict(raw)
        profile = host.get("profile", "mri")
        data_site_id = host.get("data_site_id") or MRI_SITE_IDS.get(host.get("inventory_name", ""), "")
        host["profile"] = profile
        host["data_site_id"] = data_site_id
        host["telemetry"] = (cv_snapshot if profile == "cv" else mri_snapshot).get(data_site_id)
        inventory_name = host.get("inventory_name", "")
        if host.get("status") != "ok":
            historical = (last_known_index.get("hosts") or {}).get(inventory_name)
            if historical:
                historical = dict(historical)
                historical["gpio_alignment"] = gpio_alignment_evidence(historical.get("facts") or {})
            host["last_known"] = historical
        backup_repo = BACKUP_REPOS.get(inventory_name, inventory_name)
        repo_status = backup_status.get(backup_repo, {})
        host["backup"] = {
            "repository": backup_repo,
            "configured": bool(backup_repo and backup_repo in backup_targets),
            "covered": bool(backup_repo and backup_repo in backup_repositories),
            "checked_at": backup_coverage.get("checked_at"),
            "last_snapshot_activity": repo_status.get("last_snapshot_activity"),
            "activity_age_hours": repo_status.get("activity_age_hours"),
            "activity_recent": repo_status.get("activity_recent"),
            "batch_success": (backup_coverage.get("batch") or {}).get("result") == "success",
            "restore_test": restore_status.get(backup_repo),
        }
        add_storage_unsafe_delta(host, immediate_previous_hosts.get(inventory_name) or {})
        previous = previous_hosts.get(inventory_name) or {}
        rate_window_hosts = (
            report_window_hosts(reports, inventory_name, 0, previous_report_index + 1)
            if previous_report_index is not None
            else []
        )
        if (
            interval_after_rsyslog_change(host, previous_time)
            and not interval_overlaps_maintenance(
                previous_time,
                current_time,
                storage_maintenance_windows.get(inventory_name),
            )
            and quiet_write_window(rate_window_hosts)
        ):
            add_storage_write_rate(host, previous, report_delta_seconds)
        add_storage_write_trend(
            host, reports, maintenance_windows=storage_maintenance_windows.get(inventory_name)
        )
        camera_installed = (((host.get("facts") or {}).get("camera_logging") or {}).get("installed") is True)
        camera_config = ((((host.get("facts") or {}).get("camera_logging") or {}).get("software") or {}).get("safe_config") or {})
        camera_site_id = str(camera_config.get("SITE_ID") or "").upper()
        camera_ingest, camera_production = camera_pipeline_telemetry(
            camera_site_id=camera_site_id,
            production_site_id=data_site_id,
            camera_backend_available=camera_backend_available,
            production_backend_available=production_backend_available,
            camera_latest=camera_latest,
            production_latest=production_latest,
        )
        host["camera_ingest_telemetry"] = camera_ingest
        host["camera_telemetry"] = camera_production
        host["camera_observation"] = camera_observations.get(inventory_name)
        camera_software = (((host.get("facts") or {}).get("camera_logging") or {}).get("software") or {})
        host["camera_canary"] = camera_candidate_canaries.get(inventory_name)
        if host["camera_canary"]:
            host["camera_canary"]["matches_current_camera"] = (
                candidate_canary_matches_current_camera(
                    host["camera_canary"], camera_software
                )
            )
        host["camera_deployment"] = camera_candidate_deployments.get(inventory_name)
        if host["camera_deployment"]:
            host["camera_deployment"]["matches_current_camera"] = (
                candidate_deployment_matches_current_camera(
                    host["camera_deployment"], camera_software
                )
            )
        if host["camera_observation"]:
            host["camera_observation"]["matches_current_camera"] = camera_proof_matches_software(
                host["camera_observation"], camera_software
            )
            if (
                host["camera_observation"].get("passed") is True
                and host["camera_observation"]["matches_current_camera"] is not True
            ):
                host["camera_observation"]["superseded_by_current_camera"] = True
                host["camera_observation"]["pending"] = True
        camera_version = (
            camera_software
            .get("core_files", {})
            .get("scheduled_capture.py", {})
            .get("reported_version")
        )
        camera_proven = bool(
            camera_version == "3.0.0"
            and (host.get("camera_observation") or {}).get("matches_current_camera") is True
        )
        camera_canary_proven = bool(
            (host.get("camera_canary") or {}).get("matches_current_camera") is True
        )
        camera_deployment_current = bool(
            (host.get("camera_deployment") or {}).get("matches_current_camera") is True
        )
        host["camera_convergence"] = {
            "target_version": "3.0.0" if camera_installed else None,
            "target_contract": CAMERA_TARGET_CONTRACTS.get(inventory_name),
            "status": (
                "v3_production_verified"
                if camera_proven
                else "v3_smoke_passed_pending_natural_proof"
                if camera_deployment_current
                else "hardware_canary_passed"
                if camera_canary_proven
                else CAMERA_CONVERGENCE_STATUS.get(inventory_name, "not_applicable")
            ),
        }
        host["os_upgrade_readiness"] = os_upgrade_readiness.get(inventory_name)
        host["os_upgrade_verification"] = os_upgrade_verifications.get(inventory_name)
        host["os_posture"] = os_posture(host)
        host["operational_baseline"] = assess_operational_stack(host)
        host["sensor_runtime_assessment"] = assess_sensor_runtime(host)
        host["camera_runtime_assessment"] = assess_camera_runtime(host)
        host["ram_budget_assessment"] = assess_ram_budget(host)
        host["update_policy_assessment"] = assess_update_policy(host)
        host["headless_optimization"] = {
            "status": HEADLESS_OPTIMIZATION_STATUS.get(inventory_name, "not_started"),
            "observation": (optimization_observation.get("hosts") or {}).get(inventory_name),
        }
        host["probe_mapping"] = probe_mapping_evidence(host.get("facts") or {}, profile)
        host["calibration_mapping"] = calibration_mapping_evidence(
            host.get("facts") or {}, profile
        )
        host["live_telemetry"] = live_telemetry_evidence(host)
        host["gpio_alignment"] = gpio_alignment_evidence(host.get("facts") or {})
        host["runtime_policy"] = sensor_runtime_policy(
            host.get("facts") or {}, profile, inventory_name
        )
        host["service_unit"] = service_unit_evidence(host.get("facts") or {}, profile)
        host["restart_policy"] = restart_policy_evidence(host.get("facts") or {}, profile)
        host["sensor_operational"] = sensor_operational_evidence(host)
        host["restart_recovery"] = restart_recovery_verifications.get(inventory_name)
        host["last_maintenance_action"] = maintenance_actions.get(inventory_name)
        host["package_cache"] = assess_current_package_cache(
            host.get("facts") or {}, package_downloads.get(inventory_name)
        )
        host["maintenance"] = maintenance_readiness(host)
        host["recommendations"] = recommendations(host)
        hosts.append(host)

    rank = {"critical": 0, "warning": 1, "info": 2}
    for host in hosts:
        application = ((host.get("facts") or {}).get("application") or {})
        digest = application.get("normalized_sha256") or application.get("sha256", "")
        target = PROFILE_BASELINES.get(host.get("profile", "mri"), "")
        family = SOFTWARE_FAMILIES.get(digest, {"name": "Unknown sensor build", "state": "unknown"})
        host["software_baseline"] = {
            "current": digest,
            "target": target,
            "matches": bool(digest and digest == target),
            "family": family["name"],
            "state": family["state"],
        }
        if digest and target and digest != target:
            if family["state"] == "legacy":
                message = f"{family['name']} lacks the approved runtime-recovery behavior; converge after a verified backup."
            elif family["state"] == "compatible":
                message = f"{family['name']} is a known working variant; converge to the approved {host.get('profile', 'mri').upper()} build in a controlled wave."
            else:
                message = "Unknown sensor program differs from the approved profile build; review before maintenance."
            host["recommendations"].append({"severity": "warning", "code": "software", "message": message})
            host["recommendations"].sort(key=lambda item: rank.get(item["severity"], 3))

    concerns = sum(
        any(item["severity"] in {"critical", "warning"} for item in host["recommendations"])
        for host in hosts
    )
    critical = sum(any(item["severity"] == "critical" for item in host["recommendations"]) for host in hosts)
    status_helper_hashes = {
        str((((host.get("facts") or {}).get("restricted_helpers") or {}).get("pi_status_sha256") or ""))
        for host in hosts
        if host.get("status") == "ok"
        and (((host.get("facts") or {}).get("restricted_helpers") or {}).get("pi_status_sha256"))
    }
    mri_helper_hashes = {
        str((((((host.get("facts") or {}).get("restricted_helpers") or {}).get("mri_sensor_service") or {}).get("sha256")) or ""))
        for host in hosts
        if host.get("status") == "ok"
        and host.get("profile") == "mri"
        and (((((host.get("facts") or {}).get("restricted_helpers") or {}).get("mri_sensor_service") or {}).get("sha256")))
    }
    sudo_compat_hashes = {
        str((((host.get("facts") or {}).get("restricted_helpers") or {}).get("sudo_compat") or {}).get("sha256") or "")
        for host in hosts
        if host.get("status") == "ok"
        and ((((host.get("facts") or {}).get("restricted_helpers") or {}).get("sudo_compat") or {}).get("sha256"))
    }
    maintenance_waves = build_maintenance_waves(hosts, optimization_observation)
    package_matrix = operational_package_matrix(hosts)
    runtime_matrix = sensor_runtime_matrix(hosts)
    eligible_packages = {
        host.get("inventory_name", ""): eligible_package_count(host)
        for host in hosts if host.get("status") == "ok"
    }
    return {
        "generated_at": report.get("generated_at"),
        "served_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_file": report.get("source_file"),
        "expected_hosts": EXPECTED_HOSTS,
        "backup": backup_coverage,
        "optimization_observation": optimization_observation,
        "incomplete_report": report.get("incomplete_report", False),
        "maintenance_waves": maintenance_waves,
        "operational_package_matrix": package_matrix,
        "sensor_runtime_matrix": runtime_matrix,
        "summary": {
            "total": len(hosts),
            "online": sum(host.get("status") == "ok" for host in hosts),
            "offline": sum(host.get("status") != "ok" for host in hosts),
            "sensor_runtime_assessed": runtime_matrix["assessed_hosts"],
            "sensor_runtime_complete": runtime_matrix["complete_hosts"],
            "sensor_operational_assessed": sum(
                (host.get("sensor_operational") or {}).get("assessed") is True
                for host in hosts
            ),
            "sensor_operational": sum(
                (host.get("sensor_operational") or {}).get("operational") is True
                for host in hosts
            ),
            "camera_runtime_assessed": runtime_matrix["camera_assessed_hosts"],
            "camera_runtime_complete": runtime_matrix["camera_complete_hosts"],
            "ram_budget_assessed": sum(
                (host.get("ram_budget_assessment") or {}).get("assessed") is True
                for host in hosts
            ),
            "ram_budget_healthy": sum(
                (host.get("ram_budget_assessment") or {}).get("healthy") is True
                for host in hosts
            ),
            "update_policy_assessed": sum(
                (host.get("update_policy_assessment") or {}).get("assessed") is True
                for host in hosts
            ),
            "update_policy_aligned": sum(
                (host.get("update_policy_assessment") or {}).get("aligned") is True
                for host in hosts
            ),
            "offline_history_available": sum(
                host.get("status") != "ok" and bool(host.get("last_known"))
                for host in hosts
            ),
            "packages_listed": sum(
                int(((host.get("facts") or {}).get("package_maintenance") or {}).get(
                    "listed_count", (host.get("facts") or {}).get("packages_upgradable") or 0
                ))
                for host in hosts if host.get("status") == "ok"
            ),
            "packages_eligible": sum(eligible_packages.values()),
            "package_hosts_eligible": sum(count > 0 for count in eligible_packages.values()),
            "packages_eligible_ready": sum(
                eligible_packages.get(host.get("inventory_name", ""), 0)
                for host in hosts
                if host.get("status") == "ok"
                and (host.get("maintenance") or {}).get("ready") is True
            ),
            "packages_eligible_held": sum(
                eligible_packages.get(host.get("inventory_name", ""), 0)
                for host in hosts
                if host.get("status") == "ok"
                and (host.get("maintenance") or {}).get("ready") is not True
            ),
            "packages_deferred": sum(
                int(((host.get("facts") or {}).get("package_maintenance") or {}).get("deferred_count", 0))
                for host in hosts if host.get("status") == "ok"
            ),
            "wifi_critical": sum(
                signal_grade(routed_wifi_signal(host.get("facts") or {})) == "critical"
                for host in hosts if host.get("status") == "ok"
            ),
            "wifi_marginal": sum(
                signal_grade(routed_wifi_signal(host.get("facts") or {})) == "weak"
                for host in hosts if host.get("status") == "ok"
            ),
            "new_unsafe_shutdowns": sum(
                int((((host.get("facts") or {}).get("storage_health") or {}).get("unsafe_shutdowns_delta") or 0))
                for host in hosts
            ),
            "field_priority": sum(
                host.get("status") != "ok"
                or (
                    isinstance(routed_wifi_signal(host.get("facts") or {}), (int, float))
                    and routed_wifi_signal(host.get("facts") or {}) <= -67
                )
                or (((((host.get("facts") or {}).get("storage_health") or {}).get("smart") or {}).get("concerning") is True))
                or int((((host.get("facts") or {}).get("boot_management") or {}).get("nvme_controller_resets_since_boot") or 0)) > 0
                or (host.get("facts") or {}).get("throttled_flags") not in (None, 0)
                for host in hosts
            ),
            "concerns": concerns,
            "critical": critical,
            "mri": sum(host.get("profile") == "mri" for host in hosts),
            "cv": sum(host.get("profile") == "cv" for host in hosts),
            "software_drift": sum(not host.get("software_baseline", {}).get("matches", False) for host in hosts if host.get("status") == "ok"),
            "software_approved": sum(host.get("software_baseline", {}).get("matches", False) for host in hosts if host.get("status") == "ok"),
            "backup_covered": sum((host.get("backup") or {}).get("covered", False) for host in hosts),
            "backup_recent": sum((host.get("backup") or {}).get("activity_recent") is True for host in hosts),
            "backup_export_ready": sum(
                (((host.get("facts") or {}).get("restricted_helpers") or {}).get("pi_backup_export") or {}).get("check") is True
                for host in hosts
            ),
            "backup_batch_success": (backup_coverage.get("batch") or {}).get("result") == "success",
            "backup_batch_result": (backup_coverage.get("batch") or {}).get("result") or "unknown",
            "backup_batch_completed_targets": (backup_coverage.get("batch") or {}).get("completed_count"),
            "backup_batch_expected_targets": (backup_coverage.get("batch") or {}).get("expected_count"),
            "backup_onboarding_prepared": len(backup_coverage.get("prepared_onboarding") or []),
            "backup_onboarding_complete": sum(
                item.get("onboarded") is True
                for item in (backup_coverage.get("prepared_onboarding") or [])
            ),
            "backup_restore_verifier_installed": (
                (backup_coverage.get("hub_readiness") or {}).get("restore_verifier_installed") is True
            ),
            "backup_restore_verifier_status": (
                (backup_coverage.get("hub_readiness") or {}).get("restore_verifier_status")
                or "unknown"
            ),
            "backup_restore_sweep_status": (
                (backup_coverage.get("restore_sweep") or {}).get("status")
                or "unknown"
            ),
            "backup_restore_sweep_next_run": (
                (backup_coverage.get("restore_sweep") or {}).get("next_run")
            ),
            "restore_tested": sum(
                item.get("status") == "success" and item.get("recent") is True
                for item in (backup_coverage.get("restore_tests") or [])
            ),
            "backup_restore_failed_repositories": sum(
                item.get("status") == "failure"
                for item in (backup_coverage.get("restore_tests") or [])
            ),
            "os_pilot_ready": sum(
                (host.get("os_upgrade_readiness") or {}).get("ready") is True
                for host in hosts
            ),
            "os_pilot_blocked": sum(
                bool(host.get("os_upgrade_readiness"))
                and (host.get("os_upgrade_readiness") or {}).get("ready") is not True
                for host in hosts
            ),
            "os_upgrade_verified": sum(
                (host.get("os_upgrade_verification") or {}).get("passed") is True
                for host in hosts
            ),
            "os_assessed": sum((host.get("os_posture") or {}).get("assessed") is True for host in hosts),
            "os_target": sum((host.get("os_posture") or {}).get("state") == "target" for host in hosts),
            "os_supported_lts": sum((host.get("os_posture") or {}).get("state") == "supported_lts" for host in hosts),
            "os_supported_total": sum((host.get("os_posture") or {}).get("state") in {"target", "supported_lts"} for host in hosts),
            "os_eol": sum((host.get("os_posture") or {}).get("state") == "eol" for host in hosts),
            "os_unknown": sum((host.get("os_posture") or {}).get("state") == "unknown" for host in hosts),
            "maintenance_ready": sum((host.get("maintenance") or {}).get("ready") is True for host in hosts),
            "live_telemetry_current": sum(
                (host.get("live_telemetry") or {}).get("current") is True
                for host in hosts
            ),
            "live_telemetry_complete": sum(
                (host.get("live_telemetry") or {}).get("complete") is True
                for host in hosts
            ),
            "live_telemetry_alarm": sum(
                (host.get("live_telemetry") or {}).get("alarm") is True
                for host in hosts
            ),
            "probe_mappings_assessed": sum(
                (host.get("probe_mapping") or {}).get("exact") is True
                for host in hosts if host.get("status") == "ok"
            ),
            "probe_mappings_aligned": sum(
                (host.get("probe_mapping") or {}).get("exact") is True
                and (host.get("probe_mapping") or {}).get("complete") is True
                for host in hosts if host.get("status") == "ok"
            ),
            "calibration_maps_assessed": sum(
                (host.get("calibration_mapping") or {}).get("assessed") is True
                for host in hosts if host.get("status") == "ok"
            ),
            "calibration_maps_aligned": sum(
                (host.get("calibration_mapping") or {}).get("aligned") is True
                for host in hosts if host.get("status") == "ok"
            ),
            "calibration_explicit_complete": sum(
                (host.get("calibration_mapping") or {}).get("complete_explicit") is True
                for host in hosts if host.get("status") == "ok"
            ),
            "calibration_default_zero_hosts": sum(
                int((host.get("calibration_mapping") or {}).get("default_zero_count") or 0) > 0
                for host in hosts if host.get("status") == "ok"
            ),
            "gpio_mappings_assessed": sum(
                (host.get("gpio_alignment") or {}).get("assessed") is True
                for host in hosts
            ),
            "gpio_mappings_aligned": sum(
                (host.get("gpio_alignment") or {}).get("aligned") is True
                for host in hosts
            ),
            "runtime_policies_assessed": sum(
                (host.get("runtime_policy") or {}).get("assessed") is True
                for host in hosts
            ),
            "runtime_policies_aligned": sum(
                (host.get("runtime_policy") or {}).get("matches") is True
                for host in hosts
            ),
            "runtime_policy_exceptions": sum(
                (host.get("runtime_policy") or {}).get("approved_exception") is True
                for host in hosts
            ),
            "ops_core_assessed": sum(
                (host.get("operational_baseline") or {}).get("assessed") is True
                for host in hosts
            ),
            "ops_core_aligned": sum(
                (host.get("operational_baseline") or {}).get("matches") is True
                for host in hosts
            ),
            "status_helpers_readable": sum(
                (((host.get("facts") or {}).get("restricted_helpers") or {}).get("pi_status_readable") is True)
                for host in hosts
            ),
            "status_helper_variants": len(status_helper_hashes),
            "sudo_compat_aligned": sum(
                (((host.get("facts") or {}).get("restricted_helpers") or {}).get("sudo_compat") or {}).get("sha256") == SUDO_COMPAT_SHA256
                and (((host.get("facts") or {}).get("restricted_helpers") or {}).get("sudo_compat") or {}).get("executable") is True
                for host in hosts
                if host.get("status") == "ok"
            ),
            "sudo_compat_variants": len(sudo_compat_hashes),
            "mri_helpers_control": sum(
                (((host.get("facts") or {}).get("restricted_helpers") or {}).get("mri_sensor_service") or {}).get("control") is True
                for host in hosts
                if host.get("status") == "ok" and host.get("profile") == "mri"
            ),
            "mri_helpers_logs": sum(
                (((host.get("facts") or {}).get("restricted_helpers") or {}).get("mri_sensor_service") or {}).get("logs") is True
                for host in hosts
                if host.get("status") == "ok" and host.get("profile") == "mri"
            ),
            "mri_helper_variants": len(mri_helper_hashes),
            "cv_services_nonroot": sum(
                str(((((host.get("facts") or {}).get("services") or {}).get("cv_sensor") or {}).get("user") or ""))
                not in {"", "root"}
                for host in hosts
                if host.get("status") == "ok" and host.get("profile") == "cv"
            ),
            "sensor_services_nonroot": sum(
                str((((((host.get("facts") or {}).get("services") or {}).get(
                    "cv_sensor" if host.get("profile") == "cv" else "mri_sensor"
                ) or {}).get("user")) or "")) not in {"", "root"}
                for host in hosts
                if host.get("status") == "ok"
            ),
            "service_units_assessed": sum(
                (host.get("service_unit") or {}).get("assessed") is True for host in hosts
            ),
            "service_units_aligned": sum(
                (host.get("service_unit") or {}).get("aligned") is True for host in hosts
            ),
            "restart_policies_assessed": sum(
                (host.get("restart_policy") or {}).get("assessed") is True for host in hosts
            ),
            "restart_policies_aligned": sum(
                (host.get("restart_policy") or {}).get("aligned") is True for host in hosts
            ),
            "restart_recovery_verified": sum(
                (host.get("restart_recovery") or {}).get("verified") is True for host in hosts
            ),
            "maintenance_history_available": sum(
                bool(host.get("last_maintenance_action")) for host in hosts
            ),
            "package_cache_verified_hosts": sum(
                (host.get("package_cache") or {}).get("verified") is True
                for host in hosts
            ),
            "package_cache_verified_eligible": sum(
                int((host.get("package_cache") or {}).get("eligible") or 0)
                for host in hosts
                if (host.get("package_cache") or {}).get("verified") is True
            ),
            "headless_canary_active": sum(
                (host.get("headless_optimization") or {}).get("status") == "reboot_verified_observation"
                and (((host.get("facts") or {}).get("operational_stack") or {}).get("background_services") or {}).get("gdm.service", {}).get("active") != "active"
                for host in hosts
            ),
            "optimization_canaries_ready": sum(
                (item or {}).get("ready") is True
                for item in (optimization_observation.get("hosts") or {}).values()
            ),
            "rsyslog_ram_pilots": sum(
                ((host.get("facts") or {}).get("ram_optimization") or {}).get("journald_volatile") is True
                and (((host.get("facts") or {}).get("operational_stack") or {}).get("background_services") or {}).get("rsyslog.service", {}).get("active") == "inactive"
                and (((host.get("facts") or {}).get("operational_stack") or {}).get("background_services") or {}).get("rsyslog.service", {}).get("enabled") == "disabled"
                for host in hosts
                if host.get("status") == "ok"
            ),
            "boot_firmware_readonly": sum(
                "ro" in str(((host.get("facts") or {}).get("boot_management") or {}).get("firmware_mount_options") or "").split(",")
                for host in hosts
            ),
            "boot_candidates_pending": sum(
                ((host.get("facts") or {}).get("boot_management") or {}).get("new_state") == "unknown"
                for host in hosts
            ),
            "high_write_rate": sum(
                ((((host.get("facts") or {}).get("storage_health") or {}).get("write_trend") or {}).get("sustained_high") is True)
                for host in hosts
            ),
            "high_write_bursts": sum(
                (((host.get("facts") or {}).get("storage_health") or {}).get("recent_mib_written_per_day") or 0) >= 5120
                and ((((host.get("facts") or {}).get("storage_health") or {}).get("write_trend") or {}).get("sustained_high") is not True)
                for host in hosts
            ),
            "smart_visible": sum(
                ((((host.get("facts") or {}).get("storage_health") or {}).get("smart") or {}).get("available") is True)
                for host in hosts
            ),
            "camera_enabled": sum(
                ((host.get("facts") or {}).get("camera_logging") or {}).get("installed") is True
                for host in hosts
            ),
            "camera_ram_logs": sum(
                ((host.get("facts") or {}).get("camera_logging") or {}).get("memory_only") is True
                for host in hosts
            ),
            "camera_ram_workload_verified": sum(
                ((host.get("facts") or {}).get("camera_logging") or {}).get("memory_only") is True
                and (host.get("camera_observation") or {}).get("matches_current_camera") is True
                for host in hosts
            ),
            "camera_observations_pending": sum(
                (host.get("camera_observation") or {}).get("pending") is True
                for host in hosts
            ),
            "camera_observations_planned": sum(
                (host.get("camera_observation") or {}).get("planned") is True
                and (host.get("camera_observation") or {}).get("pending") is True
                for host in hosts
            ),
            "camera_observations_expired": sum(
                (host.get("camera_observation") or {}).get("expired") is True
                for host in hosts
            ),
            "volatile_journal_pilots": sum(
                ((host.get("facts") or {}).get("ram_optimization") or {}).get("journald_volatile") is True
                for host in hosts
            ),
            "camera_legacy": sum(
                host.get("camera_management") == "observed_legacy"
                and ((host.get("facts") or {}).get("camera_logging") or {}).get("installed") is True
                for host in hosts
            ),
            "camera_config_ignored": sum(
                bool(set(((((host.get("facts") or {}).get("camera_logging") or {}).get("software") or {}).get("ignored_safe_config_keys") or [])) & {"UPLOAD_ENABLED", "UPLOAD_MODE"})
                for host in hosts
            ),
            "camera_v3_canary_passed": sum(
                (host.get("camera_convergence") or {}).get("status") == "hardware_canary_passed"
                for host in hosts
            ),
            "camera_v3_pending_natural_proof": sum(
                (host.get("camera_convergence") or {}).get("status")
                == "v3_smoke_passed_pending_natural_proof"
                for host in hosts
            ),
            "camera_v3_blocked": sum(
                str((host.get("camera_convergence") or {}).get("status", "")).startswith("blocked_")
                or (host.get("camera_convergence") or {}).get("status") == "operator_decision_required"
                for host in hosts
            ),
            "camera_upload_recent": sum(
                isinstance((host.get("camera_telemetry") or {}).get("age_hours"), (int, float))
                and (host.get("camera_telemetry") or {}).get("age_hours") <= 36
                for host in hosts
            ),
            "camera_upload_stale": sum(
                isinstance((host.get("camera_telemetry") or {}).get("age_hours"), (int, float))
                and (host.get("camera_telemetry") or {}).get("age_hours") > 36
                for host in hosts
            ),
            "camera_ingest_recent": sum(
                isinstance((host.get("camera_ingest_telemetry") or {}).get("age_hours"), (int, float))
                and (host.get("camera_ingest_telemetry") or {}).get("age_hours") <= 36
                for host in hosts
            ),
        },
        "hosts": hosts,
    }


class Handler(SimpleHTTPRequestHandler):
    SECURITY_HEADERS = {
        "Cache-Control": "no-store",
        "Content-Security-Policy": (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        ),
        "Cross-Origin-Opener-Policy": "same-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Referrer-Policy": "no-referrer",
        "Strict-Transport-Security": "max-age=31536000",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-Robots-Tag": "noindex, nofollow",
    }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self) -> None:
        for name, value in self.SECURITY_HEADERS.items():
            self.send_header(name, value)
        super().end_headers()

    def authenticated(self) -> bool:
        if not USERNAME or not PASSWORD:
            return False
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:]).decode("utf-8")
            supplied_user, supplied_password = decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            return False
        return hmac.compare_digest(supplied_user, USERNAME) and hmac.compare_digest(supplied_password, PASSWORD)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            payload, status = fleet_health()
            self.send_json(payload, status)
            return
        if not self.authenticated():
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", 'Basic realm="CoolMRI Fleet"')
            self.end_headers()
            return
        if self.path == "/api/fleet":
            self.send_json(fleet_payload())
            return
        if self.path == "/api/history":
            self.send_json(fleet_history_payload())
            return
        super().do_GET()

    def send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} {format % args}", flush=True)


if __name__ == "__main__":
    if not USERNAME or not PASSWORD:
        raise SystemExit("FLEET_USERNAME and FLEET_PASSWORD are required")
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    print("CoolMRI Fleet listening on :8080", flush=True)
    server.serve_forever()
