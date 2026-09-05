from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "camera_v3_candidate_production.yml"


def source() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def test_deployment_is_explicit_candidate_only_and_canary_gated():
    play = yaml.safe_load(source())[0]
    text = source()
    assert play["hosts"] == "{{ camera_v3_deployment_target | default('none') }}"
    assert "camera_v3_deployment_confirm" in text
    assert "^eligible_after_primary_pilot" in text
    assert "camera_v3_candidate_canary_*.json" in text
    assert "camera_canary.production_hashes_before" in text
    assert "Production camera files changed after the hardware canary" in text
    assert "sort(attribute='created_at')" in text


def test_later_secondary_requires_oswmr1_natural_v3_proof():
    text = source()
    for requirement in (
        "Require OSW MR1 natural v3 proof before any later secondary",
        "inventory_hostname == 'oswmr1'",
        "camera_natural_observations",
        "selectattr('inventory_name', 'equalto', 'oswmr1')",
        "selectattr('expected_source', 'equalto', 'camera_edge_v3')",
        "selectattr('camera_session.count', 'equalto', 10)",
    ):
        assert requirement in text


def test_deployment_preserves_contract_backup_restore_schedule_and_sensor_path():
    text = source()
    for requirement in (
        "camera_backup_status.activity_recent",
        "camera_restore_status.recent",
        'test "$configured" = "$physical"',
        "mri-sensor.service",
        "vcgencmd get_throttled",
        "failed_sessions",
        "Capture exact user and cron.d schedule contract",
        "camera_schedule_after.stdout == camera_schedule_before.stdout",
        "Wait for unaffected sensor telemetry to advance",
    ):
        assert requirement in text


def test_deployment_uses_profiled_v3_and_forces_smoke_upload_off():
    text = source()
    for requirement in (
        "UPLOAD_ENABLED={{ camera_target.upload_enabled | ternary('true', 'false') }}",
        "UPLOAD_MODE={{ camera_target.upload_mode }}",
        "OCR_CROP_COORDS={{ camera_target.crop | to_json }}",
        "SHUTTER_SPEED={{ camera_target.shutter_us }}",
        "GAIN={{ camera_target.gain }}",
        'UPLOAD_ENABLED: "false"',
        'TMPDIR: "{{ camera_stage }}/smoke"',
        "captured=1 uploaded=0 requested=1",
    ):
        assert requirement in text


def test_deployment_has_cron_watchdog_byte_exact_rollback_and_atomic_report():
    text = source()
    for requirement in (
        "--on-active=10m",
        "systemctl stop cron.service",
        "Resume cron immediately and disarm watchdog",
        "Capture byte-exact runtime for rollback",
        "Capture environment bytes",
        "Restore byte-exact legacy runtime and environment under lock",
        "Verify byte-exact rollback hashes",
        "Prove byte-exact rollback before stopping",
        "camera_rollback_env.content == camera_env_bytes_before.content",
        "camera_v3_candidate_deployment_",
        "natural_proof_pending",
    ):
        assert requirement in text
    assert "ansible.builtin.reboot" not in text
    assert "systemctl restart" not in text


def test_candidate_hashes_match_canonical_files():
    play = yaml.safe_load(source())[0]
    hashes = play["vars"]["camera_candidate_hashes"]
    import hashlib

    for name, expected in hashes.items():
        path = ROOT / "roles" / "camera_edge" / "files" / "edge" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_deployment_reports_exact_source_bytes_including_final_newline():
    assert "rstrip=false" in source()


def test_deployment_report_timestamp_is_explicit_utc():
    assert "now(utc=true, fmt='%Y-%m-%dT%H:%M:%S.%fZ')" in source()


def test_deployment_report_is_readable_by_hardened_dashboard():
    assert 'mode: "0644"' in source()
