from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "camera_v3_candidate_canary.yml"


def source() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def test_canary_is_explicitly_targeted_and_limited_to_reviewed_candidates():
    play = yaml.safe_load(source())[0]
    assert play["hosts"] == "{{ camera_v3_candidate_target | default('none') }}"
    text = source()
    assert "camera_v3_candidate_confirm" in text
    assert "^eligible_after_primary_pilot" in text
    assert "camera_convergence.yml" in text


def test_canary_requires_both_natural_primary_v3_proofs():
    text = source()
    for requirement in (
        "agcmr1",
        "agcmr3",
        "expected_source', 'equalto', 'camera_edge_v3'",
        "camera_session.count', 'equalto', 10",
        "camera_observation_*.json",
    ):
        assert requirement in text


def test_canary_requires_backup_restore_and_live_sensor_path():
    text = source()
    for requirement in (
        "camera_backup_status.activity_recent",
        "camera_restore_status.recent",
        "mri-sensor.service",
        "PROBE_.*_ID",
        'test "$configured" = "$physical"',
        "vcgencmd get_throttled",
        "camera_telemetry_before.last_updated",
        "Wait for advancing sensor telemetry after the canary",
    ):
        assert requirement in text
    assert "ansible.builtin.reboot" not in text
    assert "shutdown -r" not in text
    assert "systemctl restart" not in text.lower()


def test_canary_allows_a_full_averaged_sensor_publish_window():
    play = yaml.safe_load(source())[0]
    wait = next(
        task
        for task in play["tasks"]
        if task.get("name") == "Wait for advancing sensor telemetry after the canary"
    )
    assert wait["retries"] == 12
    assert wait["delay"] == 10


def test_canary_check_mode_finishes_after_preflight_without_running_capture():
    play = yaml.safe_load(source())[0]
    finish = next(
        task
        for task in play["pre_tasks"]
        if task.get("name")
        == "Finish successful dry-run after validating every canary gate"
    )
    assert finish["ansible.builtin.meta"] == "end_play"
    assert finish["when"] == "ansible_check_mode"


def test_canary_hashes_the_exact_source_bytes_including_final_newline():
    assert "lookup('ansible.builtin.file', camera_canary_source, rstrip=false)" in source()


def test_canary_report_is_dashboard_readable_and_timestamped_explicit_utc():
    assert 'mode: "0644"' in source()
    assert "now(utc=true, fmt='%Y-%m-%dT%H:%M:%S.%fZ')" in source()


def test_canary_is_ram_only_upload_disabled_and_profile_driven():
    text = source()
    for requirement in (
        "/dev/shm/coolmri-camera-v3-canary-",
        'TMPDIR: "{{ camera_canary_base }}"',
        'UPLOAD_ENABLED: "false"',
        'UPLOAD_MODE: "{{ camera_target.upload_mode }}"',
        'OCR_CROP_COORDS: "{{ camera_target.crop | to_json }}"',
        'SHUTTER_SPEED: "{{ camera_target.shutter_us }}"',
        'GAIN: "{{ camera_target.gain }}"',
        "captured=1 uploaded=0 requested=1",
        "camera_production_hashes_after.stdout == camera_production_hashes_before.stdout",
    ):
        assert requirement in text


def test_every_candidate_has_explicit_sensor_and_backup_identity():
    plan = yaml.safe_load(
        (ROOT / "inventory" / "camera_convergence.yml").read_text(encoding="utf-8")
    )
    for name, details in plan["hosts"].items():
        if not details["status"].startswith("eligible_after_primary_pilot"):
            continue
        assert details["sensor_site_id"], name
        assert details["backup_repository"], name
