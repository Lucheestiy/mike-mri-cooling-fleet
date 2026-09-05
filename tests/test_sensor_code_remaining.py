from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remaining_wave_targets_only_three_known_legacy_hosts():
    text = (ROOT / "playbooks" / "sensor_code_remaining.yml").read_text(encoding="utf-8")
    assert "sensor_wave_hosts: gcmcmr2:vwm2:vwm3" in text
    assert "import_playbook: sensor_code_wave_1.yml" in text


def test_imported_wave_refuses_unknown_source_programs():
    text = (ROOT / "playbooks" / "sensor_code_wave_1.yml").read_text(encoding="utf-8")
    assert "sensor_allowed_source_sha256:" in text
    assert "e48e6230bb122a3c79bea77a02da75ad63306f97564d1486615ae6759053bee0" in text
    assert "sensor_program.stat.checksum in sensor_allowed_source_sha256" in text
    assert "sensor_site_files_before.results | map(attribute='stat.exists')" in text


def test_shared_wave_preserves_site_state_and_has_automatic_rollback():
    text = (ROOT / "playbooks" / "sensor_code_wave_1.yml").read_text(encoding="utf-8")
    for required in (
        "Enforce successful recent backup gate",
        "Report marginal remote Wi-Fi as an advisory",
        "sensor_wave_wifi_signal.stdout | int <= -67",
        "without blocking maintenance",
        "Capture protected site configuration checksums",
        "Capture exact physical probe set",
        "Prove program convergence without site-state drift",
        "sensor_site_files_after.results",
        "sensor_probes_after.files",
        "Restore the automatic pre-change copy",
        "Wait for server telemetry to advance",
        "serial: 1",
        "max_fail_percentage: 0",
    ):
        assert required in text


def test_shared_wave_pins_the_approved_mri_program_checksum():
    approved = "0d939f88b35ab8167ce1e70d91a8611a14f4a6a9631a30677bbe06bb5234a36f"
    playbook = (ROOT / "playbooks" / "sensor_code_wave_1.yml").read_text(encoding="utf-8")
    source = (ROOT / "roles" / "temp_sensors" / "files" / "pi_sensor.py").read_bytes()
    import hashlib

    assert approved in playbook
    assert hashlib.sha256(source).hexdigest() == approved
