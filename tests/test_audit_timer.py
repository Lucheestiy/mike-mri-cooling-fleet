from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "systemd" / "coolmri-pi-fleet-audit.service"


def test_scheduled_audit_allows_the_normal_fact_collection_window():
    source = SERVICE.read_text(encoding="utf-8")
    assert "--command-timeout 60" in source
    assert "--command-timeout 25" not in source
    assert "TimeoutStartSec=180" in source


def test_scheduled_audit_checks_mr2_recovery_without_mutating_it():
    source = SERVICE.read_text(encoding="utf-8")
    assert "os_upgrade_recovery_watch.py --host agcmr2" in source
    assert "os_upgrade_readiness_20260717_112357_117411.json" in source
    assert "ExecStartPost=-" in source
