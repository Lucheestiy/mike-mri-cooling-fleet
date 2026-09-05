import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "os_upgrade_recovery_watch.py"
SPEC = importlib.util.spec_from_file_location("os_upgrade_recovery_watch", MODULE_PATH)
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)


def evidence(*, physical, active="active", current=True, updated=200):
    configured = ["28-1", "28-2", "28-3", "28-4"]
    baseline = {
        "ready": True,
        "snapshot": {
            "inventory_name": "agcmr2",
            "configured_probe_ids": configured,
        },
        "telemetry": {"last_updated": 100},
    }
    audit = {
        "results": [{
            "inventory_name": "agcmr2",
            "status": "ok",
            "profile": "mri",
            "facts": {
                "sensor_config": {"values": {
                    "PROBE_IN_ID": "28-1",
                    "PROBE_OUT_ID": "28-2",
                    "PROBE_PRIMARY_IN_ID": "28-3",
                    "PROBE_PRIMARY_OUT_ID": "28-4",
                }},
                "one_wire": {"sensor_ids": physical, "count": len(physical)},
                "services": {"mri_sensor": {"active": active}},
            },
        }]
    }
    telemetry = {"current": current, "last_updated": updated}
    return baseline, audit, telemetry


def test_recovery_gate_requires_exact_probes_even_with_active_service():
    baseline, audit, telemetry = evidence(physical=[])
    blockers = watch.recovery_gate(baseline, audit, telemetry)
    assert "exact configured physical probes have not recovered" in blockers
    assert "configured and physical probe mappings differ" in blockers


def test_recovery_gate_requires_current_advancing_telemetry():
    baseline, audit, telemetry = evidence(
        physical=["28-1", "28-2", "28-3", "28-4"],
        current=False,
        updated=100,
    )
    blockers = watch.recovery_gate(baseline, audit, telemetry)
    assert "server telemetry is not current" in blockers
    assert "server telemetry has not advanced beyond the baseline" in blockers


def test_recovery_gate_passes_only_complete_end_to_end_path():
    baseline, audit, telemetry = evidence(
        physical=["28-1", "28-2", "28-3", "28-4"]
    )
    assert watch.recovery_gate(baseline, audit, telemetry) == []
