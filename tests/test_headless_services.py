from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "playbooks/headless_services_pilot.yml"
ROLLBACK = ROOT / "playbooks/headless_services_rollback.yml"


def test_headless_pilot_has_profile_specific_cv_contract() -> None:
    play = yaml.safe_load(PILOT.read_text(encoding="utf-8"))[0]
    variables = play["vars"]
    assert "gmcep3" in play["hosts"]
    assert variables["headless_pilot_sensor_units"]["gmcep3"] == "cv-room-sensor.service"
    assert variables["headless_pilot_site_ids"]["gmcep3"] == "EP3"
    assert variables["headless_pilot_expected_probes"]["gmcep3"] == 3
    assert variables["headless_pilot_telemetry_urls"]["gmcep3"].startswith("https://cv.coolmri.com/")
    assert variables["headless_pilot_sensor_units"]["gmcir3"] == "cv-room-sensor.service"
    assert variables["headless_pilot_site_ids"]["gmcir3"] == "IR3"
    assert variables["headless_pilot_expected_probes"]["gmcir3"] == 4
    assert variables["headless_pilot_telemetry_urls"]["gmcir3"].startswith("https://cv.coolmri.com/")


def test_headless_pilot_retains_exact_probe_and_advancing_telemetry_gates() -> None:
    text = PILOT.read_text(encoding="utf-8")
    assert "headless_probe_count.stdout | int == headless_pilot_expected_probes[inventory_hostname]" in text
    assert "headless_telemetry_before.last_updated" in text
    assert "headless_telemetry_after_response" in text


def test_headless_pilot_saves_exact_service_states_for_rollback() -> None:
    text = PILOT.read_text(encoding="utf-8")
    assert '"active_state": value(unit, "ActiveState")' in text
    assert '"unit_file_state": value(unit, "UnitFileState")' in text
    assert "'unit_states': headless_unit_states_before" in text
    assert "Restore pre-pilot active state during automatic rollback" in text


def test_rollback_supports_every_active_canary_but_requires_one_limit() -> None:
    play = yaml.safe_load(ROLLBACK.read_text(encoding="utf-8"))[0]
    expected = "agcmr1:agcmr3:gbh:gmcep1and2:gmcep3:gmcir3:gwvskyra:shmr:vwm3"
    assert play["hosts"] == expected
    text = ROLLBACK.read_text(encoding="utf-8")
    assert "ansible_play_hosts_all | length == 1" in text
    assert (
        "inventory_hostname in ['agcmr1', 'agcmr3', 'gbh', 'gmcep1and2', "
        "'gmcep3', 'gmcir3', 'gwvskyra', 'shmr', 'vwm3']"
    ) in text
    assert '"/home/{{ ansible_user }}/.local/bin/sudo-rs-ansible-compat"' in text
    assert "Restore exact saved unit-file states" in text
    assert "Restore exact saved active states" in text
    assert "Restore legacy peripheral defaults when exact state is unavailable" in text
