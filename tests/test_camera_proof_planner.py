import datetime as dt
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "camera_proof_planner.py"
SPEC = importlib.util.spec_from_file_location("camera_proof_planner", MODULE_PATH)
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


def audit_row(name="oswmr1", hashes=None):
    hashes = hashes or planner.CANONICAL_HASHES
    return {
        "inventory_name": name,
        "status": "ok",
        "facts": {
            "camera_logging": {
                "software": {
                    "fingerprint": "v3-fingerprint",
                    "core_files": {
                        filename: {"sha256": digest}
                        for filename, digest in hashes.items()
                    },
                }
            }
        },
    }


def deployment():
    return {
        "kind": "camera_v3_candidate_deployment",
        "schema": 1,
        "passed": True,
        "created_at": "2026-07-18T10:00:00-04:00",
        "inventory_name": "oswmr1",
        "canonical_version": "3.0.0",
        "candidate_source_sha256": planner.CANONICAL_SOURCE_SHA256,
        "target_contract": {"upload_enabled": True},
        "installed_hashes": planner.CANONICAL_HASHES,
        "canary_source_file": "camera_v3_candidate_canary_oswmr1_test.json",
        "restore_snapshot_id": "snapshot",
        "natural_proof_pending": True,
        "capture": {
            "requested": 1,
            "captured": 1,
            "uploaded": 0,
            "upload_enabled": False,
            "ram_workspace": "/dev/shm/test",
        },
        "safety": {
            "schedule_unchanged": True,
            "exact_probes_after": True,
            "sensor_active_after": True,
            "zero_throttle_after": True,
            "rollback_staged": True,
            "sensor_restarted": False,
            "rebooted": False,
        },
        "telemetry": {
            "before_timestamp": 1,
            "after_timestamp": 2,
            "advanced": True,
        },
    }


def test_deployment_requires_exact_contract_and_current_hashes():
    payload = deployment()
    contract = {"status": "eligible_after_primary_pilot", "target": {"upload_enabled": True}}
    row = audit_row()
    assert planner.valid_deployment(payload, contract, row)
    stale = audit_row(hashes={**planner.CANONICAL_HASHES, "scheduled_capture.py": "bad"})
    assert not planner.valid_deployment(payload, contract, stale)
    payload["safety"]["rebooted"] = True
    assert not planner.valid_deployment(payload, contract, row)


def test_next_capture_honors_lead_time_and_site_timezone():
    now = dt.datetime(2026, 7, 18, 8, 56, tzinfo=planner.LOCAL_ZONE)
    selected = planner.next_capture(["09:00", "15:00"], now)
    assert selected == dt.datetime(2026, 7, 18, 15, 0, tzinfo=planner.LOCAL_ZONE)
    plan = planner.plan_payload("oswmr1", "OSWMR1", selected, now)
    assert plan["baseline_at"] == "2026-07-18T14:55:00-04:00"
    assert plan["complete_at"] == "2026-07-18T15:03:00-04:00"
    assert plan["expected_source"] == "camera_edge_v3"


def test_pending_loader_rejects_stale_audited_runtime(tmp_path):
    payload = deployment()
    (tmp_path / "camera_v3_candidate_deployment_oswmr1_test.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    convergence = {
        "hosts": {
            "oswmr1": {
                "status": "eligible_after_primary_pilot",
                "target": {"upload_enabled": True},
            }
        }
    }
    good_audit = {"results": [audit_row()]}
    assert list(planner.pending_deployments(tmp_path, convergence, good_audit)) == ["oswmr1"]
    stale_audit = {"results": [audit_row(hashes={**planner.CANONICAL_HASHES, "run_retry_check.sh": "bad"})]}
    assert planner.pending_deployments(tmp_path, convergence, stale_audit) == {}


def test_planner_and_units_are_read_only_with_respect_to_cameras():
    script = MODULE_PATH.read_text(encoding="utf-8")
    service = (ROOT / "systemd/coolmri-camera-proof-planner.service").read_text()
    timer = (ROOT / "systemd/coolmri-camera-proof-planner.timer").read_text()
    assert "start_camera_observation.sh" in script
    assert "complete_latest_camera_observation.sh" in script
    for forbidden in ("rpicam", "libcamera", "reboot --hosts", "update --hosts"):
        assert forbidden not in script
    assert "User=mlweb" in service
    assert "ProtectSystem=strict" in service
    assert "ReadWritePaths=/home/mlweb/mri-cooling-pi-fleet/reports" in service
    assert "OnCalendar=*-*-* *:*:00" in timer
