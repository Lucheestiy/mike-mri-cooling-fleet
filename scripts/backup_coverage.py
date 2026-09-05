#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path


REPORT_PATH = Path(__file__).resolve().parents[1] / "reports" / "backup_coverage.json"
REMOTE_COMMAND = (
    "find /mnt/t7backup/restic-pi-repos -maxdepth 2 -mindepth 1 "
    "-type d -printf '%P|%T@\\n' 2>/dev/null"
)
TARGETS_COMMAND = "cut -d '|' -f 1,4,5 /etc/restic-pi-backup-targets.psv"
SERVICE_STATUS_COMMAND = (
    "systemctl show restic-pi-pull-backup.service "
    "-p Result -p ExecMainStatus -p ExecMainStartTimestamp -p ExecMainExitTimestamp "
    "-p ActiveState -p SubState --no-pager"
)
TIMER_STATUS_COMMAND = (
    "systemctl show restic-pi-pull-backup.timer "
    "-p ActiveState -p SubState -p LastTriggerUSec -p NextElapseUSecRealtime --no-pager"
)
RESTORE_SWEEP_TIMER_STATUS_COMMAND = (
    "systemctl show coolmri-restic-restore-sweep.timer "
    "-p ActiveState -p UnitFileState -p LastTriggerUSec -p NextElapseUSecRealtime --no-pager"
)
RESTORE_SWEEP_SERVICE_STATUS_COMMAND = (
    "systemctl show coolmri-restic-restore-sweep.service "
    "-p Result -p ExecMainStatus -p ExecMainStartTimestamp -p ExecMainExitTimestamp "
    "-p ActiveState --no-pager"
)
RESTORE_STATUS_COMMAND = (
    "if [ -d /var/lib/coolmri-fleet/restore-tests ]; then "
    "find /var/lib/coolmri-fleet/restore-tests -maxdepth 1 -type f -name '*.json' "
    "-exec cat {} \\; -exec printf '\\n' \\;; fi"
)
BACKUP_STATUS_COMMAND = (
    "if [ -d /var/lib/coolmri-fleet/backup-status ]; then "
    "find /var/lib/coolmri-fleet/backup-status -type f -name '*.json' "
    "-exec cat {} \\; -exec printf '\\n' \\;; fi"
)
RESTORE_HELPER_STATUS_COMMAND = (
    "if [ -x /usr/local/sbin/coolmri-restic-restore-test ]; "
    "then echo installed; else echo absent; fi"
)
RESTORE_AUTHORIZATION_COMMAND = (
    "if sudo -n -l /usr/local/sbin/coolmri-restic-restore-test >/dev/null 2>&1; "
    "then echo authorized; else echo unavailable; fi"
)
MOUNT_STATUS_COMMAND = (
    "if findmnt -rn /mnt/t7backup >/dev/null; then echo mounted; else echo absent; fi"
)
PREPARED_ONBOARDING_TARGETS = ("agcmr2", "gcmcmr2", "vwm2", "vwm3", "glh")
RECENT_ACTIVITY_HOURS = 36
RESTORE_TEST_MAX_AGE_DAYS = 90


def remote(command: str) -> str:
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "mik-eq-backup", command],
        text=True,
        capture_output=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Backup hub command failed ({result.returncode})")
    return result.stdout


def properties(output: str) -> dict[str, str]:
    return {
        key: value
        for line in output.splitlines()
        for key, separator, value in [line.partition("=")]
        if separator and key
    }


def parse_json_stream(output: str) -> list[dict]:
    decoder = json.JSONDecoder()
    items = []
    index = 0
    while index < len(output):
        while index < len(output) and output[index].isspace():
            index += 1
        if index >= len(output):
            break
        try:
            item, index = decoder.raw_decode(output, index)
        except json.JSONDecodeError:
            next_line = output.find("\n", index)
            index = len(output) if next_line < 0 else next_line + 1
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


def parse_restore_tests(output: str, now: dt.datetime) -> list[dict]:
    tests = []
    for item in parse_json_stream(output):
        repository = item.get("repository")
        completed_at = item.get("completed_at")
        if not repository or not completed_at:
            continue
        age_days = None
        try:
            completed = dt.datetime.fromisoformat(completed_at)
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=now.tzinfo)
            age_days = (now - completed.astimezone(now.tzinfo)).total_seconds() / 86400
        except (TypeError, ValueError):
            pass
        item["age_days"] = round(max(0, age_days), 1) if age_days is not None else None
        item["recent"] = bool(
            item.get("status") == "success"
            and age_days is not None
            and 0 <= age_days <= RESTORE_TEST_MAX_AGE_DAYS
        )
        tests.append(item)
    return sorted(tests, key=lambda item: item["repository"])


def parse_successful_backup_history(output: str, now: dt.datetime) -> list[dict]:
    history = []
    for item in parse_json_stream(output):
        repository = item.get("repository")
        completed_at = item.get("completed_at")
        if item.get("status") != "success" or not repository or not completed_at:
            continue
        try:
            completed = dt.datetime.fromisoformat(completed_at)
            if completed.tzinfo is None:
                completed = completed.replace(tzinfo=now.tzinfo)
            completed = completed.astimezone(now.tzinfo)
        except (TypeError, ValueError):
            continue
        history.append({"repository": repository, "completed": completed, "item": item})
    return history


def parse_successful_backup_status(output: str, now: dt.datetime) -> dict[str, dict]:
    statuses = {}
    for status in parse_successful_backup_history(output, now):
        repository = status["repository"]
        existing = statuses.get(repository)
        if existing is None or status["completed"] > existing["completed"]:
            statuses[repository] = {"completed": status["completed"], "item": status["item"]}
    return statuses


def prepared_onboarding_status(
    repositories: set[str], configured_targets: set[str], successful_backups: set[str]
) -> list[dict]:
    return [
        {
            "repository": target,
            "target_configured": target in configured_targets,
            "repository_present": target in repositories,
            "first_backup_verified": target in successful_backups,
            "onboarded": (
                target in configured_targets
                and target in repositories
                and target in successful_backups
            ),
        }
        for target in PREPARED_ONBOARDING_TARGETS
    ]


def restore_verifier_status(installed: bool, authorized: bool) -> str:
    if installed and authorized:
        return "ready"
    if installed:
        return "authorization_missing"
    if authorized:
        return "verifier_missing"
    return "hub_sudo_install_required"


def restore_sweep_status(timer: dict[str, str], service: dict[str, str]) -> str:
    if timer.get("UnitFileState") != "enabled" or timer.get("ActiveState") != "active":
        return "timer_not_ready"
    if service.get("Result") not in {None, "", "success"}:
        return "last_run_failed"
    return "ready"


def parse_systemd_wall_time(value: str | None, timezone: dt.tzinfo) -> dt.datetime | None:
    """Parse systemd's localized weekday/timestamp without trusting its zone label."""

    parts = str(value or "").split()
    if len(parts) < 4 or parts[0].lower() in {"n/a", ""}:
        return None
    try:
        return dt.datetime.strptime(" ".join(parts[1:3]), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone
        )
    except ValueError:
        return None


def batch_completion(
    configured_targets: set[str],
    successful_status: dict[str, dict] | list[dict],
    started_at: str | None,
    finished_at: str | None,
    now: dt.datetime,
) -> dict:
    start = parse_systemd_wall_time(started_at, now.tzinfo)
    finish = parse_systemd_wall_time(finished_at, now.tzinfo)
    candidates = (
        [
            {"repository": repository, **status}
            for repository, status in successful_status.items()
        ]
        if isinstance(successful_status, dict)
        else successful_status
    )
    completed = sorted({
        str(status.get("repository") or "")
        for status in candidates
        if status.get("repository") in configured_targets
        and start is not None
        and finish is not None
        and start <= status["completed"] <= finish + dt.timedelta(seconds=60)
    })
    missing = sorted(configured_targets - set(completed))
    return {
        "expected_count": len(configured_targets),
        "completed_count": len(completed),
        "completed_targets": completed,
        "missing_targets": missing,
        "complete": bool(configured_targets and not missing),
    }


def main() -> int:
    try:
        repository_output = remote(REMOTE_COMMAND)
        targets_output = remote(TARGETS_COMMAND)
        service_status = properties(remote(SERVICE_STATUS_COMMAND))
        timer_status = properties(remote(TIMER_STATUS_COMMAND))
        restore_sweep_timer_status = properties(remote(RESTORE_SWEEP_TIMER_STATUS_COMMAND))
        restore_sweep_service_status = properties(remote(RESTORE_SWEEP_SERVICE_STATUS_COMMAND))
        restore_status_output = remote(RESTORE_STATUS_COMMAND)
        backup_status_output = remote(BACKUP_STATUS_COMMAND)
        restore_helper_status = remote(RESTORE_HELPER_STATUS_COMMAND).strip()
        restore_authorization_status = remote(RESTORE_AUTHORIZATION_COMMAND).strip()
        mount_status = remote(MOUNT_STATUS_COMMAND).strip()
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc)) from exc
    repo_names: set[str] = set()
    activity_epochs: dict[str, float] = {}
    for raw_line in repository_output.splitlines():
        path, separator, epoch_text = raw_line.strip().partition("|")
        if not separator or not path:
            continue
        parts = path.split("/")
        if len(parts) == 1:
            repo_names.add(parts[0])
        elif len(parts) == 2 and parts[1] == "snapshots":
            try:
                activity_epochs[parts[0]] = float(epoch_text)
            except ValueError:
                pass

    now = dt.datetime.now().astimezone()
    restore_tests = parse_restore_tests(restore_status_output, now)
    successful_backup_history = parse_successful_backup_history(backup_status_output, now)
    successful_backup_status = parse_successful_backup_status(backup_status_output, now)
    repos = sorted(repo_names)
    configured_targets = []
    for raw_line in targets_output.splitlines():
        target_id, separator, remainder = raw_line.strip().partition("|")
        label, second_separator, reported_host = remainder.partition("|")
        if separator and second_separator and target_id:
            configured_targets.append(
                {"repository": target_id, "label": label, "reported_host": reported_host}
            )
    repository_status = []
    for repo in repos:
        marker = successful_backup_status.get(repo)
        epoch = activity_epochs.get(repo)
        if marker:
            last_activity = marker["completed"]
            activity_evidence = "successful_backup_marker"
        elif repo in PREPARED_ONBOARDING_TARGETS:
            last_activity = None
            activity_evidence = "successful_backup_marker_required"
        else:
            last_activity = dt.datetime.fromtimestamp(epoch, tz=now.tzinfo) if epoch else None
            activity_evidence = "legacy_snapshots_directory_mtime" if last_activity else "none"
        age_hours = (now - last_activity).total_seconds() / 3600 if last_activity else None
        repository_status.append(
            {
                "repository": repo,
                "last_snapshot_activity": last_activity.isoformat(timespec="seconds") if last_activity else None,
                "activity_age_hours": round(age_hours, 1) if age_hours is not None else None,
                "activity_recent": age_hours is not None and age_hours <= RECENT_ACTIVITY_HOURS,
                "activity_evidence": activity_evidence,
            }
        )
    configured_target_ids = {
        item["repository"] for item in configured_targets if item.get("repository")
    }
    completion = batch_completion(
        configured_target_ids,
        successful_backup_history,
        service_status.get("ExecMainStartTimestamp"),
        service_status.get("ExecMainExitTimestamp"),
        now,
    )
    systemd_batch_result = service_status.get("Result")
    reported_batch_result = (
        "incomplete"
        if systemd_batch_result == "success" and not completion["complete"]
        else systemd_batch_result
    )
    prepared_onboarding = prepared_onboarding_status(
        repo_names, configured_target_ids, set(successful_backup_status)
    )
    restore_verifier_installed = restore_helper_status == "installed"
    restore_verifier_authorized = restore_authorization_status == "authorized"
    payload = {
        "checked_at": now.isoformat(timespec="seconds"),
        "hub": "mik-EQ",
        "repository_count": len(repos),
        "repositories": repos,
        "repository_status": repository_status,
        "configured_target_count": len(configured_targets),
        "configured_targets": configured_targets,
        "recent_activity_hours": RECENT_ACTIVITY_HOURS,
        "batch": {
            "result": reported_batch_result,
            "systemd_result": systemd_batch_result,
            "exit_status": service_status.get("ExecMainStatus"),
            "started_at": service_status.get("ExecMainStartTimestamp"),
            "finished_at": service_status.get("ExecMainExitTimestamp"),
            "timer_active": timer_status.get("ActiveState") == "active",
            "last_trigger": timer_status.get("LastTriggerUSec"),
            "next_run": timer_status.get("NextElapseUSecRealtime"),
            **completion,
        },
        "restore_test_max_age_days": RESTORE_TEST_MAX_AGE_DAYS,
        "restore_tests": restore_tests,
        "restore_sweep": {
            "status": restore_sweep_status(
                restore_sweep_timer_status, restore_sweep_service_status
            ),
            "timer_enabled": restore_sweep_timer_status.get("UnitFileState") == "enabled",
            "timer_active": restore_sweep_timer_status.get("ActiveState") == "active",
            "last_trigger": restore_sweep_timer_status.get("LastTriggerUSec"),
            "next_run": restore_sweep_timer_status.get("NextElapseUSecRealtime"),
            "last_result": restore_sweep_service_status.get("Result"),
            "last_exit_status": restore_sweep_service_status.get("ExecMainStatus"),
            "last_started_at": restore_sweep_service_status.get("ExecMainStartTimestamp"),
            "last_finished_at": restore_sweep_service_status.get("ExecMainExitTimestamp"),
        },
        "prepared_onboarding": prepared_onboarding,
        "hub_readiness": {
            "backup_mount_visible": mount_status == "mounted",
            "target_catalog_readable": True,
            "restore_verifier_installed": restore_verifier_installed,
            "restore_verifier_authorized": restore_verifier_authorized,
            "restore_verifier_status": restore_verifier_status(
                restore_verifier_installed, restore_verifier_authorized
            ),
            "prepared_count": len(prepared_onboarding),
            "prepared_onboarded": sum(item["onboarded"] for item in prepared_onboarding),
        },
        "note": "The systemd result confirms the configured batch outcome. Newly onboarded repositories require an atomic successful-backup marker written only after Restic completes; repository creation time is never accepted as backup evidence. Existing repositories retain their legacy snapshots-directory timestamp until their next marked run. Restore-test status appears only after the hub helper has decrypted a snapshot and restored etc/os-release into tmpfs. Weekly restore-sweep status is collected directly from its systemd timer and service.",
    }
    temporary = REPORT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(REPORT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
