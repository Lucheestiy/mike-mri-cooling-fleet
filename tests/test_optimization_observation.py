import datetime as dt
import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "optimization_observation.py"
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("optimization_observation", MODULE_PATH)
observation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observation)


def host(index=0, *, default_target="multi-user.target", gdm="inactive"):
    probe_ids = [f"28-{value}" for value in range(5)]
    return {
        "inventory_name": "agcmr1",
        "profile": "mri",
        "status": "ok",
        "facts": {
            "operational_stack": {
                "default_target": default_target,
                "background_services": {
                    name: {"active": gdm if name == "gdm.service" else "inactive"}
                    for name in observation.DISABLED_SERVICES
                },
            },
            "ram_optimization": {"journald_volatile": True},
            "services": {"mri_sensor": {"active": "active"}},
            "sensor_config": {
                "values": {f"PROBE_TEST_{i}_ID": value for i, value in enumerate(probe_ids)}
            },
            "one_wire": {"count": 5, "sensor_ids": probe_ids},
            "application": {"normalized_sha256": observation.PROFILE_HASHES["mri"]},
            "throttled_flags": 0,
            "memory_bytes": {"total": 8_000_000_000, "available": 7_000_000_000},
            "ram_budget": {
                "total_bytes": 8_000_000_000,
                "available_bytes": 7_000_000_000,
                "available_percent": 87.5,
                "oom_events_since_boot": 0,
                "run": {"filesystem": "tmpfs", "used_percent": 2.0},
            },
            "uptime_seconds": 10_000 + index * 900,
            "package_manager": {"busy": False},
            "package_maintenance": {
                "listed_count": 0,
                "eligible_count": 0,
                "deferred_count": 0,
            },
            "storage_health": {
                "root_block_device": "sda",
                "bytes_written_since_boot": 1_000_000_000 + index * 1_000_000,
            },
        },
    }


def reports(count=193):
    start = dt.datetime(2026, 7, 16, 14, 0, tzinfo=dt.timezone.utc)
    return [
        {
            "_timestamp": start + dt.timedelta(minutes=15 * index),
            "results": [host(index)],
        }
        for index in range(count)
    ]


def test_old_audit_without_explicit_multi_user_target_cannot_qualify():
    checks = observation.host_checks(host(default_target=None))
    assert checks["multi_user_target"] is False


def test_ram_pressure_or_missing_new_budget_cannot_qualify():
    pressured = host()
    pressured["facts"]["ram_budget"]["run"]["used_percent"] = 70
    pressured["facts"]["ram_budget"]["oom_events_since_boot"] = 1
    checks = observation.host_checks(pressured)
    assert checks["run_tmpfs_headroom"] is False
    assert checks["no_oom_events"] is False


def test_headless_only_expansion_does_not_require_volatile_journal():
    candidate = host()
    candidate["facts"]["ram_optimization"]["journald_volatile"] = False

    assert observation.host_checks(candidate)["volatile_journal"] is False
    assert observation.host_checks(
        candidate, require_volatile_journal=False
    )["volatile_journal"] is True
    legacy = host()
    legacy["facts"].pop("ram_budget")
    checks = observation.host_checks(legacy)
    assert checks["memory_headroom"] is False
    assert checks["run_tmpfs_headroom"] is False
    assert checks["no_oom_events"] is False


def test_full_continuous_window_becomes_ready_with_quiet_writes():
    result = observation.observe_host(
        "agcmr1", reports(), {"current": True, "last_updated": 100}
    )
    assert result["ready"] is True
    assert result["duration_hours"] == 48.0
    assert result["remaining_hours"] == 0.0
    assert observation.parse_time(result["earliest_time_gate_at"]) == reports()[0]["_timestamp"] + dt.timedelta(hours=48)
    assert result["continuous_samples"] == 193
    assert len(result["write_rates_mib_per_day"]) >= 3


def test_failed_service_state_resets_the_continuous_window():
    data = reports()
    data[-2]["results"][0]["facts"]["operational_stack"]["background_services"]["gdm.service"]["active"] = "active"
    result = observation.observe_host(
        "agcmr1", data, {"current": True, "last_updated": 100}
    )
    assert result["ready"] is False
    assert result["continuous_samples"] == 1
    assert result["remaining_hours"] == 48.0
    assert result["observation_start_reason"] == (
        "health gates recovered after: selected services inactive"
    )
    assert "need 48 continuous observation hours" in result["blockers"]


def test_rsyslog_change_resets_combined_observation_window():
    data = reports()
    change_time = data[-5]["_timestamp"]
    data[-1]["results"][0]["facts"]["ram_optimization"]["rsyslog_ram_pilot"] = {
        "applied_epoch": change_time.timestamp()
    }
    result = observation.observe_host(
        "agcmr1", data, {"current": True, "last_updated": 100}
    )
    assert result["ready"] is False
    assert result["continuous_samples"] == 5
    assert result["observation_start_reason"] == "rsyslog RAM policy boundary"
    assert observation.parse_time(result["configured_start"]) == change_time.astimezone()


def test_package_state_change_is_excluded_from_quiet_write_rates():
    data = reports(4)
    data[2]["results"][0]["facts"]["package_maintenance"].update({
        "listed_count": 4,
        "eligible_count": 4,
    })
    rates = observation.valid_write_rates([
        (report["_timestamp"], report["results"][0]) for report in data
    ])
    assert rates == []


def test_explicit_maintenance_window_is_excluded_from_write_rates():
    data = reports(8)
    pairs = [(report["_timestamp"], report["results"][0]) for report in data]
    action_time = data[-2]["_timestamp"]
    rates = observation.valid_write_rates(
        pairs,
        maintenance_windows=[
            (action_time - dt.timedelta(minutes=1), action_time + dt.timedelta(minutes=1))
        ],
    )
    assert rates
    assert all(rate < 2048 for rate in rates)


def test_legacy_download_report_gets_conservative_action_window(tmp_path):
    completed = dt.datetime(2026, 7, 17, 9, 42, tzinfo=dt.timezone.utc)
    (tmp_path / "download_20260717_094200.json").write_text(
        __import__("json").dumps({
            "action": "download",
            "generated_at": completed.isoformat(),
            "results": [{"inventory_name": "agcmr1", "mutation_status": "ok"}],
        }),
        encoding="utf-8",
    )
    windows = observation.load_maintenance_windows(tmp_path)["agcmr1"]
    assert windows == [
        (completed.astimezone() - dt.timedelta(minutes=30), completed.astimezone())
    ]


def test_expansion_canary_does_not_revoke_ready_reference_cohort(monkeypatch):
    readiness = {
        "agcmr1": True,
        "agcmr3": True,
        "gbh": False,
        "gmcep3": True,
        "gmcir3": True,
        "gwvskyra": False,
        "gmcep1and2": False,
        "shmr": False,
        "vwm3": False,
    }

    monkeypatch.setattr(
        observation,
        "observe_host",
        lambda inventory_name, *_args, **_kwargs: {"ready": readiness[inventory_name]},
    )
    monkeypatch.setattr(
        observation.fleet_ops,
        "fetch_telemetry",
        lambda _host: {"current": True},
    )
    latest = {
        "results": [
            {"inventory_name": name, "status": "ok", "facts": {}}
            for name in observation.CANARIES
        ]
    }

    result = observation.build_observation([latest])

    assert result["cohort_ready"] is True
    assert result["reference_canaries"] == list(observation.REFERENCE_CANARIES)
    assert result["expansion_canaries"] == [
        "gbh", "gmcep1and2", "gwvskyra", "shmr", "vwm3"
    ]
    assert result["hosts"]["gbh"]["ready"] is False
    assert result["hosts"]["gmcep1and2"]["ready"] is False


def test_reference_canary_failure_keeps_cohort_held(monkeypatch):
    monkeypatch.setattr(
        observation,
        "observe_host",
        lambda inventory_name, *_args, **_kwargs: {
            "ready": inventory_name != "agcmr3"
        },
    )
    monkeypatch.setattr(
        observation.fleet_ops,
        "fetch_telemetry",
        lambda _host: {"current": True},
    )
    latest = {
        "results": [
            {"inventory_name": name, "status": "ok", "facts": {}}
            for name in observation.CANARIES
        ]
    }

    assert observation.build_observation([latest])["cohort_ready"] is False
