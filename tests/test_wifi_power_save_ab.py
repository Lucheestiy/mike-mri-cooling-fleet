from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "wifi_power_save_ab.yml"


def test_wifi_ab_is_nearby_limited_reversible_and_nonpersistent():
    document = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))[0]
    variables = document["vars"]
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert document["hosts"] == "{{ wifi_ab_target | default('agcmr1') }}"
    assert set(variables["wifi_ab_allowed_targets"]) == {"agcmr1", "gmcep3"}
    assert "sudo-rs-ansible-compat" in variables["ansible_become_exe"]
    assert "trap restore EXIT" in text
    assert "sample on\n        sample off\n        sample on\n        sample off" in text
    assert "ping -q -n -c 30 -i 0.2" in text
    assert "nmcli connection modify" not in text
    assert "systemctl is-active" in text
    assert "vcgencmd get_throttled" in text
