from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "camera_v3_production_pilot.yml"


def playbook_text() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def test_production_pilot_is_explicitly_profile_limited_and_restore_gated():
    document = yaml.safe_load(playbook_text())[0]
    assert document["hosts"] == "{{ camera_v3_production_target | default('agcmr3') }}"
    text = playbook_text()
    assert set(document["vars"]["camera_v3_profiles"]) == {"agcmr1", "agcmr3"}
    assert "camera_restore_status.recent" in text
    assert "camera_backup_status.activity_recent" in text
    assert "camera_v3_production_confirm" in text


def test_production_profiles_preserve_site_specific_upload_contracts():
    profiles = yaml.safe_load(playbook_text())[0]["vars"]["camera_v3_profiles"]
    assert profiles["agcmr1"]["site_id"] == "AGCMR1"
    assert profiles["agcmr1"]["upload_mode"] == "full_and_crop"
    assert profiles["agcmr1"]["debug_save_images"] == "true"
    assert profiles["agcmr1"]["shutter_speed"] == "1500"
    assert profiles["agcmr1"]["gain"] == "2.5"
    assert profiles["agcmr1"]["crop_json"] == '{"x":708,"y":520,"w":364,"h":182}'
    assert profiles["agcmr3"]["site_id"] == "AGCMR3"
    assert profiles["agcmr3"]["upload_mode"] == "cropped_only"
    assert profiles["agcmr3"]["debug_save_images"] == "false"
    assert profiles["agcmr3"]["shutter_speed"] == "1000"
    assert profiles["agcmr3"]["gain"] == "0.5"
    assert profiles["agcmr3"]["crop_json"] == '{"x":708,"y":520,"w":364,"h":182}'
    text = playbook_text()
    assert "SHUTTER_SPEED={{ camera_v3_profile.shutter_speed }}" in text
    assert "GAIN={{ camera_v3_profile.gain }}" in text
    assert 'SHUTTER_SPEED: "{{ camera_v3_profile.shutter_speed }}"' in text
    assert 'GAIN: "{{ camera_v3_profile.gain }}"' in text
    assert "OCR_CROP_COORDS={{ camera_v3_profile.crop_json }}" in text
    assert 'OCR_CROP_COORDS: "{{ camera_v3_profile.crop_json }}"' in text
    assert text.count('{"x":708,"y":520,"w":364,"h":182}') == 2


def test_production_pilot_preserves_runtime_and_schedule_with_rollback():
    text = playbook_text()
    for requirement in (
        "Capture exact production crontab",
        "Capture current runtime bytes for rollback",
        "Capture current environment bytes for rollback",
        "Atomically replace runtime under the production camera lock",
        "Restore byte-exact prior runtime under the camera lock",
        "camera_crontab_after.stdout == camera_crontab_before.stdout",
    ):
        assert requirement in text


def test_production_pilot_requires_safe_smoke_and_sensor_evidence():
    text = playbook_text()
    for requirement in (
        "UPLOAD_ENABLED: \"false\"",
        "captured=1 uploaded=0 requested=1",
        "mri-sensor.service",
        "camera_expected_probe_count",
        "vcgencmd get_throttled",
        "/run/coolmri-camera-logs/{{ camera_user }}",
        "camera_telemetry_before.last_updated",
    ):
        assert requirement in text


def test_candidate_hashes_cover_only_the_four_reviewed_runtime_files():
    document = yaml.safe_load(playbook_text())[0]
    variables = document["vars"]
    names = {item["name"] for item in variables["camera_runtime_files"]}
    assert names == {
        "scheduled_capture.py",
        "retry_failed_sessions.py",
        "run_scheduled_capture.sh",
        "run_retry_check.sh",
    }
    assert set(variables["camera_candidate_hashes"]) == names
    for profile in variables["camera_v3_profiles"].values():
        assert set(profile["expected_current_modes"]) == names
        assert set(profile["expected_current_hashes"]) == names
        assert all(len(value) == 64 for value in profile["expected_current_hashes"].values())
    assert all(len(value) == 64 for value in variables["camera_candidate_hashes"].values())
