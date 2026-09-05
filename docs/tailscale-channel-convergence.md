# Tailscale channel convergence

The common operational baseline requires Tailscale on every reachable Pi, but a
2026-07-16 read-only comparison found two package channels. Fifteen reachable Pis
use Tailscale's official stable Ubuntu repository; eight use Ubuntu's bundled
package. This explains the four Tailscale versions inside the Ubuntu 25.10 cohort:
routine apt maintenance cannot converge a package beyond the configured channel's
candidate.

AGC MR3 is the nearby, backed, strong-Wi-Fi repository canary. Formal preflight
`preflight_20260716_194923.json` passed backup activity, exact probe mapping,
sensor service, writable storage, package-manager idle state, and current
telemetry. Its existing official key has SHA-256
`3e03dacf222698c60b8e2f990b809ca1b3e104de127767864284e6c228f1fb39`, identical
to nearby AGC MR2, but the stable source is absent.

The repository playbook only adds/removes the release-specific source and refreshes
metadata; it never installs a package or restarts Tailscale. It is restricted to
the named canary/follow-up set, asserts that exactly one host is targeted, and
requires explicit confirmation:

```sh
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/tailscale_stable_repo_canary.yml --limit agcmr3 \
  -e tailscale_repo_confirm=true --check --diff \
  --become-password-file /root/.config/coolmri/ansible-become-password
```

After reviewing the exact candidate, apply the repository canary, rerun the
normal fleet preflight, and use `scripts/fleet_ops.py update --hosts agcmr3` for
the package transaction. That updater retains the backup/local-health/telemetry
gates and post-update recovery proof. Repository rollback is explicit:

```sh
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/tailscale_stable_repo_canary.yml --limit agcmr3 \
  -e tailscale_repo_confirm=true -e tailscale_repo_state=absent \
  --become-password-file /root/.config/coolmri/ansible-become-password
```

A same-OS version spread is evidence for review, not permission to change the
control-plane package on remote, weak-Wi-Fi, unbacked, or storage-held Pis.

## AGC MR3 result

The repository-only canary and guarded update completed successfully on
2026-07-16. The repository change exposed Tailscale 1.98.9 plus four routine
Ubuntu kernel-tool updates (`bpftool`, `linux-libc-dev`, `linux-perf`, and
`linux-tools-common`). The normal updater installed all five without a reboot.

Post-update evidence in `update_20260716_195415.json` proves that Tailscale is
1.98.9 and online, the MRI sensor service remained active with the exact five
probes, the application hash was unchanged, server telemetry advanced, no
packages remain eligible, and no reboot is required. This validates the channel
correction on one nearby Pi; it does not waive the per-device safety gates for a
later wave.

Read-only preflight `preflight_20260716_195710.json` subsequently approved OSW
MR1, SVI MR1, SVI MR2, GBH, and Muncy as the first serial follow-up set. All five
have recent backup evidence, current telemetry, exact probe mappings, healthy
storage and links, and the identical reviewed signing key. AGC MR1 remains out of
scope during its scheduled camera-proof window; Jersey Shore remains excluded by
the remote Wi-Fi gate.

The five-host serial follow-up then completed in reports
`update_20260716_195923.json`, `update_20260716_200024.json`,
`update_20260716_200121.json`, `update_20260716_200226.json`, and
`update_20260716_200325.json`. Every host reached Tailscale 1.98.9, retained its
unchanged MRI application hash and exact five probes, kept the sensor service
active, advanced production telemetry, cleared its eligible package set, and
required no reboot. The stop-on-first-failure sequence did not encounter a
failure.

Complete audit `audit_20260716_200755.json` adds explicit channel inventory:
21/23 reachable Pis now use the signed official stable channel. The two
distribution-channel exceptions are AGC MR1, held through its scheduled camera
proof window, and Jersey Shore, held by its marginal remote Wi-Fi link. The
authenticated public portal publishes both channel counts and exact contributing
host labels alongside the observed versions.

The portal also exposes a distinct Tailscale-channel dispatch lane and per-device
recommendation. AGC MR1 is held through its planned production camera proof;
Jersey Shore is held at the routed remote Wi-Fi gate. This prevents a zero-count
routine package queue from hiding repository-policy drift and prevents channel
work from being mistaken for authorization to bypass normal maintenance checks.

AGC MR1's natural production-camera proof subsequently passed on 2026-07-17 in
`camera_observation_20260717_090307.json`: all ten scheduled uploads, canonical
runtime hashes, RAM-only disposable logs, durable retry state, exact probes, and
advancing MRI telemetry were verified. The nearby host is therefore admitted to
the signed repository playbook's explicit one-host allowlist; normal fresh
preflight and post-update verification remain mandatory.

Fresh preflight `preflight_20260717_090641.json` passed after the source-only
change. The guarded updater then installed only Tailscale 1.98.9 and cleared the
eligible package set. `update_20260717_090758.json` proves the official-stable
channel, active Tailscale and MRI services, unchanged approved application,
exact five probes, healthy sensor and camera Python environments, preserved
three-job camera schedule, zero failed camera sessions, advancing telemetry,
and no reboot requirement. Jersey Shore remains the sole reachable distribution-
channel exception and stays held by its remote marginal Wi-Fi/reboot gate.

## Resolute post-upgrade convergence

After the fleet reached Ubuntu 26.04, the 2026-07-18 audit found that Jersey
Shore and VWM2 retained comment-only repository files naming their former
interim releases. The user explicitly made weak Wi-Fi advisory rather than a
maintenance stop. Fresh preflight `preflight_20260718_103634.json` nevertheless
required both hosts to have recent backups, current telemetry, healthy sensors,
and exact probe mappings before changing anything.

The one-host signed-source transaction then replaced only those stale definitions
with the official Resolute stable source after verifying the exact preinstalled
signing key. Jersey Shore's guarded updater advanced Tailscale 1.92.1 to 1.98.9;
`update_20260718_103823.json` proves post-update service, probes, telemetry, and
zero remaining eligible packages without a reboot. VWM2 already ran 1.98.9, so
only its source definition changed. Complete audit `audit_20260718_104017.json`
shows both on `official_stable`, version 1.98.9, with no eligible packages and no
reboot requirement. Fresh encrypted snapshots and real tmpfs restore tests then
passed for both repositories.

The same release-upgrade behavior was then found on 16 additional reachable MRI
Pis: their installed Tailscale was already 1.98.9, but the source file retained
only a comment naming Plucky or Questing. Fifteen passed the complete read-only
maintenance gate in `preflight_20260718_104708.json`; individual check-mode runs
then proved that each transaction changed only the signed source and APT metadata.
All 15 production runs completed serially without installing packages or rebooting.

AGC MR2 was isolated because its boot FAT filesystem and physical 1-Wire bus were
already unhealthy. The sensor exception did not waive storage checks. Its USB SSD
reported writable, the live read-only FAT check passed, and the current boot had
no USB reset, I/O, or FAT errors. A controlled read-write remount plus synced
create/delete probe succeeded, the sensor service remained active, and no new
storage error appeared. Only then was its signed Resolute source corrected; no
package was installed and no reboot was attempted. Complete audit
`audit_20260718_115853.json` proves all 23 reachable Pis now use the official
stable channel. The 22 Ubuntu 26.04 hosts run Tailscale 1.98.9; GR remains on
1.98.4 and is the sole read-only-boot storage hold. Its package candidate is
1.98.9, but the repository version is not permission to write to an NVMe path
that has reset four times during the current boot.

## GR package convergence — 2026-07-18

After the GR FAT partition passed an offline clean check and remounted writable,
guarded report `update_20260718_123717.json` upgraded its supported Ubuntu 24.04
cohort, including Tailscale 1.98.4 to 1.98.9. Controlled reboot
`reboot_20260718_123957.json` returned with a naturally writable boot partition,
zero current-boot NVMe errors, active sensing, five exact probes, and advancing
telemetry. Complete audit `audit_20260718_125026.json` now proves all 23 reachable
Pis use the official stable channel and run Tailscale 1.98.9. No update is
currently eligible; Ubuntu lists six phased/deferred entries across the three GMC
CV Pis, which the policy correctly does not force.
