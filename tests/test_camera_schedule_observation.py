import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "camera_schedule_observation.py"
SPEC = importlib.util.spec_from_file_location("camera_schedule_observation", MODULE_PATH)
observation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observation)


def evidence(uptime=100):
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "application_sha256": "app",
        "service": {"active": "active", "enabled": "enabled", "user": "site"},
        "probe_ids": ["28-a", "28-b"],
        "configured_probe_ids": ["28-a", "28-b"],
        "throttle_flags": 0,
        "journald_volatile": True,
        "journald_persistent": False,
        "tmp_tmpfs": True,
        "camera": {
            "installed": True,
            "memory_only": True,
            "logs_target": "/run/camera/site",
            "log_bytes": 100,
            "failed_sessions": 0,
            "retry_state_durable": True,
            "fingerprint": "camera",
            "core_hashes": {"capture.py": "hash"},
            "schedules": [{"schedule": "0 15 * * *"}],
        },
    }


def test_journald_policy_can_require_volatile_or_preserve_persistent_state():
    volatile = evidence()
    persistent = {
        **evidence(),
        "journald_volatile": False,
        "journald_persistent": True,
    }
    assert observation.journald_policy_acceptable(volatile, "volatile")
    assert not observation.journald_policy_acceptable(persistent, "volatile")
    assert observation.journald_policy_acceptable(persistent, "preserve")
    assert observation.journald_policy_preserved(
        persistent, dict(persistent), "preserve"
    )
    changed = {**persistent, "journald_volatile": True, "journald_persistent": False}
    assert not observation.journald_policy_preserved(persistent, changed, "preserve")


def test_camera_log_policy_can_require_ram_or_preserve_disk_state():
    ram = evidence()["camera"]
    disk = {**ram, "memory_only": False, "logs_target": "/srv/camera/logs"}

    assert observation.camera_log_policy_acceptable(ram, "ram")
    assert not observation.camera_log_policy_acceptable(disk, "ram")
    assert observation.camera_log_policy_acceptable(disk, "preserve")
    assert observation.camera_log_policy_preserved(disk, dict(disk), "preserve")
    assert not observation.camera_log_policy_preserved(
        disk, {**disk, "logs_target": "/run/camera/site"}, "preserve"
    )


def test_sessions_are_grouped_by_exact_scheduled_run():
    rows = [
        {"site_id": f"AGCMR3_SCHED_0716_150000_{ordinal:02d}", "timestamp": 200 + ordinal}
        for ordinal in range(1, 11)
    ]
    rows += [
        {"site_id": "AGCMR3_SCHED_0716_090000_01", "timestamp": 100},
        {"site_id": "OTHER_SCHED_0716_150000_01", "timestamp": 250},
    ]
    with mock.patch.object(observation, "fetch_json", return_value={"items": rows}):
        sessions = observation.scheduled_sessions("AGCMR3", 150)
    assert len(sessions) == 1
    assert sessions[0]["count"] == 10
    assert sessions[0]["ordinals"] == list(range(1, 11))


def test_not_before_requires_timezone():
    try:
        observation.parse_not_before("2026-07-16T14:55:00")
    except ValueError as error:
        assert "timezone" in str(error)
    else:
        raise AssertionError("timezone-free observation gate was accepted")


def test_telemetry_uses_sensor_config_site_name_when_inventory_id_is_empty():
    host = {
        "profile": "mri",
        "data_site_id": "",
        "facts": {"sensor_config": {"values": {"SITE_NAME": "AGCMR3"}}},
    }
    with mock.patch.object(
        observation,
        "fetch_json",
        return_value=[{"id": "AGCMR3", "last_updated": 1000, "is_offline": False}],
    ), mock.patch.object(observation.time, "time", return_value=1010):
        result = observation.telemetry(host)
    assert result["site_id"] == "AGCMR3"
    assert result["current"] is True


def test_host_evidence_requires_profile_specific_configured_probe_ids():
    mri = observation.host_evidence({
        "profile": "mri",
        "facts": {
            "sensor_config": {"values": {
                "PROBE_IN_ID": "28-b",
                "PROBE_OUT_ID": "28-a",
                "SITE_NAME": "TEST",
            }},
            "one_wire": {"sensor_ids": ["28-a", "28-b"]},
        },
    })
    cv = observation.host_evidence({
        "profile": "cv",
        "facts": {
            "sensor_config": {"values": {
                "SENSOR_1_ID": "28-c",
                "SENSOR_2_ID": "28-d",
                "PROBE_IN_ID": "ignored",
            }},
            "one_wire": {"sensor_ids": ["28-d", "28-c"]},
        },
    })
    assert mri["configured_probe_ids"] == ["28-a", "28-b"]
    assert mri["probe_ids"] == mri["configured_probe_ids"]
    assert cv["configured_probe_ids"] == ["28-c", "28-d"]
    assert cv["probe_ids"] == cv["configured_probe_ids"]


def test_verify_passes_only_with_complete_session_and_preserved_host(tmp_path):
    before = evidence(100)
    baseline = {
        "ok": True,
        "inventory_name": "agcmr3",
        "camera_site_id": "AGCMR3",
        "not_before_epoch": 200,
        "expected_upload_count": 10,
        "expected_source": "camera_edge_v3",
        "host": before,
        "telemetry": {"last_updated": 1000, "current": True},
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps({"results": [{"inventory_name": "agcmr3"}]}), encoding="utf-8"
    )
    session = {
        "session_id": "AGCMR3_SCHED_0716_150000",
        "count": 10,
        "ordinals": list(range(1, 11)),
        "first_timestamp": 201,
        "last_timestamp": 210,
        "records": [
            {"id": ordinal, "source": "camera_edge_v3", "timestamp": 200 + ordinal}
            for ordinal in range(1, 11)
        ],
    }
    args = SimpleNamespace(baseline=baseline_path, audit=audit_path, report_dir=tmp_path)
    with (
        mock.patch.object(
            observation,
            "host_evidence",
            return_value={
                **evidence(200),
                "camera": {**evidence(200)["camera"], "log_bytes": 200},
            },
        ),
        mock.patch.object(
            observation,
            "telemetry",
            return_value={"last_updated": 1100, "current": True},
        ),
        mock.patch.object(observation, "scheduled_sessions", return_value=[session]),
    ):
        assert observation.verify(args) == 0
    report = next(tmp_path.glob("camera_observation_*.json"))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert all(payload["checks"].values())
    assert payload["expected_upload_count"] == 10
    assert payload["expected_source"] == "camera_edge_v3"
    assert len(payload["baseline_sha256"]) == 64


def test_verify_rejects_records_from_an_unexpected_source(tmp_path):
    before = evidence(100)
    baseline = {
        "ok": True,
        "inventory_name": "agcmr3",
        "camera_site_id": "AGCMR3",
        "not_before_epoch": 200,
        "expected_upload_count": 1,
        "expected_source": "camera_edge_v3",
        "host": before,
        "telemetry": {"last_updated": 1000, "current": True},
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(
        json.dumps({"results": [{"inventory_name": "agcmr3"}]}), encoding="utf-8"
    )
    session = {
        "session_id": "AGCMR3_SCHED_RUN",
        "count": 1,
        "ordinals": [1],
        "first_timestamp": 201,
        "last_timestamp": 201,
        "records": [{"id": 1, "source": "camera_ocr", "timestamp": 201}],
    }
    args = SimpleNamespace(
        baseline=baseline_path, audit=audit_path, report_dir=tmp_path, expected_source=None
    )
    with (
        mock.patch.object(
            observation,
            "host_evidence",
            return_value={
                **evidence(200),
                "camera": {**evidence(200)["camera"], "log_bytes": 200},
            },
        ),
        mock.patch.object(
            observation,
            "telemetry",
            return_value={"last_updated": 1100, "current": True},
        ),
        mock.patch.object(observation, "scheduled_sessions", return_value=[session]),
    ):
        assert observation.verify(args) == 1
    payload = json.loads(next(tmp_path.glob("camera_observation_*.json")).read_text())
    assert payload["checks"]["scheduled_records_complete"] is False


def test_wait_rejects_partial_then_accepts_complete_session(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({
            "camera_site_id": "AGCMR3",
            "not_before_epoch": 200,
            "expected_upload_count": 2,
        }),
        encoding="utf-8",
    )
    partial = {"count": 1, "ordinals": [1], "records": [{}]}
    complete = {
        "session_id": "AGCMR3_SCHED_RUN",
        "count": 2,
        "ordinals": [1, 2],
        "records": [{}, {}],
        "last_timestamp": 220,
    }
    args = SimpleNamespace(baseline=baseline_path, timeout=1, interval=0)
    with mock.patch.object(
        observation,
        "scheduled_sessions",
        side_effect=[[partial], [complete]],
    ):
        assert observation.wait_for_session(args) == 0
