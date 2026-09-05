from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/complete_camera_observation.sh"
STARTER = ROOT / "scripts/start_camera_observation.sh"
LATEST = ROOT / "scripts/complete_latest_camera_observation.sh"
SYSTEMD = ROOT / "systemd"


def test_runner_is_read_only_and_never_prints_credentials():
    text = RUNNER.read_text(encoding="utf-8")
    assert "fleet_ops.py audit" in text
    assert '--hosts "$inventory_name" --no-bootstrap' in text
    assert "camera_schedule_observation.py verify" in text
    assert "camera_schedule_observation.py wait" in text
    assert "source /root/.config/coolmri/pi-fleet.env" not in text
    assert "update --hosts" not in text
    assert "reboot --hosts" not in text
    assert "echo $MRI_PI_PASSWORD" not in text


def test_natural_schedule_wrappers_do_not_trigger_camera_or_mutate_pi():
    starter = STARTER.read_text(encoding="utf-8")
    latest = LATEST.read_text(encoding="utf-8")
    combined = starter + latest
    assert "fleet_ops.py audit" in starter
    assert "camera_schedule_observation.py baseline" in starter
    assert "complete_camera_observation.sh" in latest
    assert "not_before_epoch + 1800" in latest
    for forbidden in ("rpicam", "libcamera", "scheduled_capture.py", "update --hosts", "reboot --hosts"):
        assert forbidden not in combined


def test_agcmr1_v3_one_shot_timers_bracket_next_natural_nine_am_schedule():
    baseline = (SYSTEMD / "coolmri-agcmr1-camera-proof-baseline.timer").read_text()
    completion = (SYSTEMD / "coolmri-agcmr1-camera-proof-complete.timer").read_text()
    baseline_service = (SYSTEMD / "coolmri-agcmr1-camera-proof-baseline.service").read_text()
    completion_service = (SYSTEMD / "coolmri-agcmr1-camera-proof-complete.service").read_text()
    assert "2026-07-18 08:55:00 America/New_York" in baseline
    assert "2026-07-18 09:03:00 America/New_York" in completion
    assert "Persistent=false" in baseline + completion
    assert "AGCMR1 10 2026-07-18T09:00:00-04:00" in baseline_service
    assert "complete_latest_camera_observation.sh agcmr1" in completion_service
    for unit in (baseline_service, completion_service):
        assert "ProtectSystem=strict" in unit
        assert "ReadWritePaths=/home/mlweb/mri-cooling-pi-fleet/reports" in unit


def test_agcmr3_v3_one_shot_timers_bracket_existing_nine_am_schedule():
    prefix = "coolmri-agcmr3-camera-v3-proof"
    baseline = (SYSTEMD / f"{prefix}-baseline.timer").read_text()
    completion = (SYSTEMD / f"{prefix}-complete.timer").read_text()
    baseline_service = (SYSTEMD / f"{prefix}-baseline.service").read_text()
    completion_service = (SYSTEMD / f"{prefix}-complete.service").read_text()
    assert "2026-07-17 08:55:00 America/New_York" in baseline
    assert "2026-07-17 09:03:00 America/New_York" in completion
    assert "Persistent=false" in baseline + completion
    assert "AGCMR3 10 2026-07-17T09:00:00-04:00" in baseline_service
    assert "complete_latest_camera_observation.sh agcmr3" in completion_service
    for unit in (baseline_service, completion_service):
        assert "ProtectSystem=strict" in unit
        assert "ReadWritePaths=/home/mlweb/mri-cooling-pi-fleet/reports" in unit


def test_gcmcmr2_ram_log_proof_timers_observe_only_the_natural_session():
    prefix = "coolmri-gcmcmr2-camera-ram-proof"
    baseline = (SYSTEMD / f"{prefix}-baseline.timer").read_text()
    completion = (SYSTEMD / f"{prefix}-complete.timer").read_text()
    baseline_service = (SYSTEMD / f"{prefix}-baseline.service").read_text()
    completion_service = (SYSTEMD / f"{prefix}-complete.service").read_text()
    assert "2026-07-18 08:55:00 America/New_York" in baseline
    assert "2026-07-18 09:03:00 America/New_York" in completion
    assert "Persistent=false" in baseline + completion
    assert "GCMCMR2 10 2026-07-18T09:00:00-04:00 camera_ocr preserve" in baseline_service
    assert "complete_latest_camera_observation.sh gcmcmr2" in completion_service
    for unit in (baseline_service, completion_service):
        assert "ProtectSystem=strict" in unit
        assert "ReadWritePaths=/home/mlweb/mri-cooling-pi-fleet/reports" in unit
