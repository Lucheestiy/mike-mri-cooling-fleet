from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLAYBOOK = ROOT / "playbooks" / "tailscale_stable_repo_canary.yml"


def source() -> str:
    return PLAYBOOK.read_text(encoding="utf-8")


def test_canary_is_explicitly_confirmed_and_restricted_to_one_nearby_pi() -> None:
    play = yaml.safe_load(source())[0]
    assert play["hosts"] == "{{ tailscale_repo_target | default('agcmr3') }}"
    assert play["serial"] == 1
    assert play["become"] is True
    assert play["vars"]["ansible_become_exe"] == (
        "/home/{{ ansible_user }}/.local/bin/sudo-rs-ansible-compat"
    )
    assert play["vars"]["tailscale_repo_allowed_targets"] == [
        "agcmr3",
        "agcmr1",
        "agcmr2",
        "oswmr1",
        "oswmr2",
        "svimr1",
        "svimr2",
        "gbh",
        "shmr",
        "muncymr",
        "jsmr",
        "pittstonsola",
        "pittstonvida",
        "gcmcsola",
        "gcmcmr2",
        "gswbsola",
        "gwvskyra",
        "vwm2",
        "vwm3",
    ]
    text = source()
    assert "tailscale_repo_confirm | default(false) | bool" in text
    assert "ansible_play_hosts_all | length == 1" in text
    assert "ansible_play_batch | length == 1" in text
    assert "inventory_hostname in tailscale_repo_allowed_targets" in text


def test_canary_requires_the_reviewed_key_and_release_specific_signed_source() -> None:
    text = source()
    assert "3e03dacf222698c60b8e2f990b809ca1b3e104de127767864284e6c228f1fb39" in text
    assert "tailscale_repo_key.stat.checksum == tailscale_repo_key_sha256" in text
    assert "signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg" in text
    assert "https://pkgs.tailscale.com/stable/ubuntu {{ ansible_facts.distribution_release }} main" in text
    assert "ansible_facts.distribution_release in tailscale_repo_allowed_releases" in text


def test_canary_changes_only_repository_metadata_and_supports_explicit_rollback() -> None:
    text = source()
    assert "tailscale_repo_state in ['present', 'absent']" in text
    assert "state: absent" in text
    assert "update_cache: true" in text
    assert "apt-cache policy tailscale" in text
    for forbidden in (
        "state: latest",
        "state: restarted",
        "ansible.builtin.package:",
        "ansible.builtin.service:",
        "tailscale up",
        "tailscale down",
    ):
        assert forbidden not in text
