# CoolMRI Pi Fleet Standardization Plan

## Decision

Use one operational baseline with two application profiles:

- **MRI profile**: `mri-sensor.service`, four or five DS18B20 cooling probes,
  optional camera/OCR schedule, production telemetry at `coolmri.com`.
- **CV profile**: `cv-room-sensor.service`, three to five equipment-room probes,
  CV telemetry at `cv.coolmri.com`.

Both profiles share Tailscale, SSH keys, health collection, host naming, package policy,
backup registration, bounded RAM logging, calibration/offset visibility, and the portal.
Application code and per-site sensor IDs remain profile/host-specific.

## Target Baseline

| Area | Fleet target | Rollout rule |
| --- | --- | --- |
| OS | Ubuntu 26.04 LTS, aarch64 | Pilot one MRI and one CV Pi before waves |
| Storage | SSD/NVMe root, ext4, less than 80% used | Never re-image without a verified restore test |
| Logs | Application stdout plus volatile journal capped at 32 MiB | Pilot for seven days; preserve warnings centrally |
| Updates | Monthly controlled package window | Backup, update, health gate, reboot only if required |
| Network | Tailscale active; Wi-Fi better than -67 dBm | External antenna/Ethernet below -75 dBm |
| Sensors | Service active and expected 1-Wire count present | Never overwrite IDs or offsets during OS convergence |
| Backup | Named Restic repo on `mik-EQ` plus verified recent snapshot | Repository existence alone is not proof of recoverability |
| Management | 15-minute read-only audit at `pi.coolmri.com` | Mutating controls remain CLI-only until RBAC exists |

## Current Audit — 2026-07-15

- 27 managed devices: 24 MRI and 3 CV.
- 23 reachable; PHC, PHMV, VWM1, and GLH are unreachable.
- All reachable expected sensor services are active.
- OS distribution: 18 Ubuntu 25.10, 3 Ubuntu 26.04, 1 Ubuntu 25.04,
  and 1 Ubuntu 24.04 LTS.
- AGC MR3's local release upgrader now reports 25.10 unsupported and offers the
  supported 26.04 LTS target. Treat the 18 remaining 25.10 hosts as time-critical,
  but do not bypass restore proof or serial pilot gates.
- AGC MR2 and GCMC MR2 completed their guarded package/kernel promotions. VWM2
  and Jersey Shore remain held by critical/marginal Wi-Fi; GR's boot filesystem
  is read-only and is a separate mutation blocker.
- GR has 266 packages pending. Its FAT filesystem passed a no-write check and a
  no-file-write remount test proved the partition currently supports writable
  operation, but it was returned to read-only and remains held until a controlled
  reboot proves the normal writable mount persists.
- Current routed Wi-Fi field list: VWM2 (-80 dBm), AGC MR1 (-73 dBm), Jersey
  Shore (-71 dBm), and GMC EP3 (-69 dBm). Current interface, band, rates, and
  power-save evidence—not an older weak sample—drive the portal recommendations.
- 24 Restic Pi repositories and configured targets are visible. Nine latest
  snapshots currently pass decrypt-and-restore; 15 older latest snapshots remain
  failed until corrected daily pulls replace their dangling OS-release symlink.
- AGC MR2, GCMC MR2, VWM2, and VWM3 pass the canonical fixed-path export-helper
  check. The helper streams directly to the existing pull workflow and grants only
  its exact no-argument archive action and `check`; hub target setup, root SSH
  authorization, and a successful first snapshot are still required.
- AGC MR1 and AGC MR3 are the two reboot-verified volatile-journald pilots; each
  runtime journal is capped at 32 MiB and prior on-disk archives are retained
  during observation. Both now also run disposable camera logs from bounded
  tmpfs, with historical logs and retry state retained on SSD. Controlled reboots
  verified recreation, schedules, sensor health, and telemetry; MR3's next
  scheduled production capture remains an observation gate.
  Complete no-reboot audit `audit_20260716_132544.json` clears MR3's reboot-only
  unsafe-shutdown delta and reports its camera logs still confined to tmpfs.
- GMC IR3 is the first CV-profile volatile-journald canary. It uses the same
  32 MiB cap and passed a controlled reboot with its non-root service, four-probe
  mapping, canonical program, zero-throttle state, and CV telemetry intact.
- GMC EP1/EP2 is the second CV volatile-journald canary after IR3 accumulated nine
  valid low-write samples. It passed a controlled reboot with its canonical
  non-root service, exact five-probe/five-reading contract, zero throttle state,
  and bounded runtime journal preserved.
- AGC MR1 joined AGC MR3 as a reboot-verified headless canary after its real
  scheduled camera workload passed. Both boot to `multi-user.target` with the
  reviewed desktop/peripheral service set inactive while sensor, networking,
  camera scheduling, and management services remain healthy.
- GMC EP3 is the first CV-profile headless canary. Its controlled reboot preserved
  the canonical non-root CV service, exact three-probe contract, all three configured
  readings, networking, and zero-throttle state while the selected desktop and
  peripheral units remained inactive.
- Strong-link GMC IR3 is the second CV-profile headless canary. Preflight
  `preflight_20260716_132715.json`, controlled reboot
  `reboot_20260716_133109.json`, and target audit `audit_20260716_133125.json`
  prove `multi-user.target`, exact four-probe CV recovery, canonical non-root
  service, zero throttling, live telemetry, and the reviewed peripheral services
  inactive. Complete audit `audit_20260716_133742.json` clears the reboot-only
  unsafe-shutdown delta at approximately 416 MiB/day. Marginal-link EP1/EP2
  remains held.
- GMC IR3 is also the first rsyslog-RAM canary. A guarded, reversible play records
  the exact prior service state and disables only rsyslog after proving bounded
  volatile journald, backup, application, probes, throttle, service identity, and
  advancing telemetry. The 13:53 controlled reboot recovered after the command's
  conservative 30-second network window; independent audit at 34 seconds uptime
  proved the workload healthy and retained log files remained unchanged. Complete
  five-minute and consecutive no-reboot audits `audit_20260716_135827.json` and
  `audit_20260716_135907.json` confirm the counter stabilized after that reboot.
- MRI sensor-code wave 1 completed on ten backed-up devices. A complete post-wave
  audit confirmed approved code, active services, five probes, and online telemetry
  on every wave host. The SVI MR2/GBH follow-up and nearby GMC CV convergence
  raised approved software to 20 reachable devices; only three backup-gated MRI
  legacy exceptions remain outside their profile target.
- Controlled package/reboot pilots include AGC MR1/MR3, all three GMC CV systems,
  GBH, SVI MR1, and SVI MR2. The A/B verifier subsequently promoted backed candidates
  on GCMC Sola, GSWB, GWV, and AGC MR1. All recovered their expected services, probes,
  application hashes, and server telemetry.
- AGC MR1 subsequently completed a 44-package security/stability refresh and
  same-kernel A/B promotion. Zero packages remain pending; its sensor, five probes,
  headless profile, volatile journal, camera tmpfs, durable retry state, and live
  production telemetry all survived the controlled reboot.
- Muncy then completed the first follow-on one-host remote security wave: 89
  packages installed, same-kernel A/B assets promoted, and only three normally
  phased kernel meta-packages initially remained. They later became normally
  eligible, installed without being forced, and controlled report
  `reboot_20260716_110238.json` promoted the real 1018-to-1021 kernel candidate.
  Its strong Wi-Fi, canonical service, five readings, zero throttle state,
  telemetry, and SMART health all recovered with zero packages pending.
- GCMC Sola completed the next serial remote wave: 194 packages installed and all
  recovery gates passed. Its initially phased `linux-image-raspi` update later
  became eligible; guarded report `update_20260716_124936.json` and controlled
  reboot `reboot_20260716_125105.json` promoted the real 1011-to-1021 candidate
  with zero packages pending and all application gates healthy.
- GWV Skyra followed serially with 189 installed packages and the same deliberate
  initial hold on its phased 1021 image. Once eligible, guarded report
  `update_20260716_125242.json` and controlled reboot
  `reboot_20260716_125411.json` promoted 1011 to 1021 with zero pending packages
  and healthy application, service, probes, throttle state, and telemetry.
- Pittston Sola then completed a 194-package security wave and controlled
  same-1011 A/B cycle. Complete audit `audit_20260716_111355.json` proves its
  application, site-account service, five probes, strong Wi-Fi, camera software
  and configuration, empty failure queue, durable retry state, and telemetry all
  recovered. Its sole phased 1021 image later became normally eligible and was
  promoted through a second controlled A/B cycle. Complete audit
  `audit_20260716_115350.json` proves it now runs 1021 with zero packages pending
  and no new unsafe-shutdown delta in a five-minute no-reboot interval.
- Pittston Vida followed with the same 194-package guarded wave and controlled
  same-1011 A/B cycle. Five-minute follow-up `audit_20260716_112817.json` proves its
  application, site-account service, five probes, camera configuration, durable
  retry state, zero-throttle state, and telemetry recovered. Its phased 1021 image
  later became normally eligible and controlled report `reboot_20260716_121300.json`
  promoted the real 1011-to-1021 candidate with zero packages left pending;
  five-minute audit `audit_20260716_121849.json` reports no new unsafe shutdown.
- GSWB completed the same 194-package guarded wave and controlled same-1011 A/B
  cycle. Its phased 1021 image later became eligible; guarded report
  `update_20260716_130053.json` and controlled reboot
  `reboot_20260716_130228.json` prove real promotion with zero pending packages
  and full sensor, camera, throttle, and telemetry recovery over its marginal link.
- OSW MR1 completed a 241-package guarded wave and controlled same-1011 A/B
  cycle. Complete audit `audit_20260716_121849.json` proves its application,
  site-account service, five probes, camera configuration, durable retry state,
  zero-throttle state, and telemetry recovered while three phased 1021 kernel
  meta-packages initially remained deliberately unforced. They later became
  normally eligible, and controlled report `reboot_20260716_123125.json` promoted
  the real 1011-to-1021 candidate with zero packages left pending.
- OSW MR2 followed with a 230-package guarded wave and controlled same-1011 A/B
  cycle. Its sole phased 1021 image later became eligible; guarded report
  `update_20260716_125533.json` and controlled reboot
  `reboot_20260716_125702.json` prove real promotion with zero pending packages
  and full sensor, camera, throttle, and telemetry recovery.
- Complete no-reboot audit `audit_20260716_130822.json` independently confirms
  GCMC Sola, GWV, GSWB, and OSW MR2 on 1021 with zero pending packages and zero
  new unsafe-shutdown deltas after their reboot intervals closed.
- All 23 reachable devices expose the same checksum-verified read-only status
  helper. All three CV devices also have a profile-specific restricted service
  helper, and all 20 reachable MRI devices share a checksum-verified restricted
  service helper with exact bounded recent-log access. The status helper now falls
  back to the kernel GPIO view, giving GR a live
  GPIO17/1-Wire state without installing a package.
- The Ansible/sudo-rs compatibility wrapper now disables terminal input echo
  before presenting its become prompt and restores it after the child exits. A
  pseudo-terminal regression test proves secrets are absent from output; all 23
  reachable Pis run the same executable checksum and passed a real UID-0 probe.
  Audit `audit_20260716_141214.json` makes this state part of recurring evidence.
- Automated 15-minute audits do not receive the fleet-wide sudo password. Their
  general-sudo field is explicitly unknown/not checked rather than false, while
  restricted helpers remain independently exercised. Credentialed maintenance
  audits distinguish verified access from an actual credential failure.
- All three GMC CV systems now run the same approved flexible sensor program while
  preserving their site-specific five-, three-, and four-probe `.env` mappings.
  The transactional EP3/IR3 wave verified compilation, complete probe matching,
  active services, zero throttling, and advancing mapped CV telemetry.
- All three CV systems also completed the same normally eligible Ubuntu 26.04
  package subset in serial guarded reports `update_20260716_131049.json`,
  `update_20260716_131148.json`, and `update_20260716_131246.json`. Their two
  common phased packages remain deliberately unforced; no reboot was required.
- GMC IR3, EP3, and EP1/EP2 now run that program as their site accounts instead
  of root. All three systemd-hardened units passed exact rollback gates and
  controlled reboot verification, including EP1/EP2 over its marginal Wi-Fi.
- GMC EP3 is now also the fifth reboot-verified volatile-journal canary. It was
  selected from nearby evidence because its persistent journal coincided with
  roughly 2 GiB/day writes while IR3 and EP1/EP2 were near 0.3 GiB/day. Controlled
  report `reboot_20260716_123631.json` proves the 32 MiB cap, canonical CV service,
  three probes, zero throttling, headless profile, and telemetry survived boot.
  Five-minute no-reboot audit `audit_20260716_124218.json` then clears the
  reboot-only unsafe-shutdown delta; longer quiet write observation remains.
- The portal subsequently identified Muncy as the only root-run MRI exception.
  A recent-backup/checksum/probe/telemetry-gated correction moved it to the
  canonical `muncymr` service identity, giving all 23 reachable devices
  least-privilege site-account sensor services.
- All 23 reachable devices now match the shared operational-core package and
  service baseline. Five package-only deviations were corrected serially with
  preserved application hashes, probes, services, and advancing telemetry.
- The four unreachable exceptions now carry controller-observed Tailscale
  last-seen evidence in every complete audit and on the portal. PHC dates to
  2025-08-05, PHMV to 2026-03-06, GLH to 2026-06-17, and VWM1 to 2026-07-15;
  none responds to Tailscale-layer or SSH probes, so recovery is an on-site
  power/network action followed by a read-only audit.
- Seventeen backed Pis across both MRI and CV profiles now have on-demand,
  no-daemon SMART visibility. Their drives pass with 0% wear, zero media errors,
  no critical warnings, and healthy temperatures; the portal exposes the sanitized
  measurements.
- The read-only portal exposes live dispatch lanes for packages, Tailscale
  channel convergence, reboots, OS upgrades, operational-core alignment, sensor
  convergence, Camera v3, crash recovery, headless optimization, field networking, and backup
  onboarding. It never weakens the underlying per-host gates and sorts the nearby
  AGC pilot group first within each applicable queue.

## Safe Rollout Sequence

The operator selected AGC/GMC MR1, MR2, and MR3 as the nearby pilot group because
they are easiest to reach physically. Changes still proceed serially: MR1, verify and
hold, then MR2, verify and hold, then MR3.

1. Restore-test one MRI and one CV backup; do not treat repository presence as sufficient.
2. Measure longer quiet write windows on both AGC MR1 and MR3. Sensor service,
   telemetry continuity, bounded memory use, and reboot behavior pass on both
   journald pilots; MR1's post-reboot scheduled camera job also passed 10/10
   capture/upload verification with logs remaining in tmpfs.
3. Observe the completed GMC IR3 CV journald and rsyslog-RAM canaries through
   longer quiet write samples before expanding either policy.
4. Upgrade one fully backed-up MRI Pi from 25.10 to 26.04 LTS. Confirm 1-Wire IDs,
   offsets, Tailscale, telemetry, service state, and restricted recovery helpers.
5. Upgrade one CV Pi and apply the same verification gate.
6. Roll out in small site waves, never rebooting all sites simultaneously.
7. Handle Ubuntu 25.04 as a separate upgrade-path exception and keep 24.04 LTS in
   service until the 26.04 baseline has passed the pilots.

## RAM and SSD Guidance

Linux already caches executable pages in RAM, so copying the entire program tree to a
RAM disk adds boot complexity with little benefit. The useful wear reduction is to keep
high-frequency logs and disposable caches in bounded RAM while retaining configuration,
sensor offsets, queued uploads, and retry state on SSD. A full read-only root/overlay
filesystem should only be considered for freshly imaged appliances after recovery testing.

## Remaining Gates

- Perform and record one MRI and one CV restore test; the portal already records the
  authoritative daily batch result, configured targets, and repository activity.
- The tmpfs restore verifier is staged and fixture-tested. Production installation
  and the first `agcmr3`/`gmcep3` tests require backup-hub sudo, not the Pi password.
- Complete backup-hub onboarding and successful first snapshots for AGC MR2,
  GCMC MR2, VWM2, and VWM3 before any mutating maintenance. Their Pi-side export
  helpers are ready, but this is not backup evidence. Offline PHC, PHMV, VWM1, and
  GLH also need backup evidence after recovery.
- Shamokin is the Ubuntu 25.04 exception. Do not release-upgrade it blindly; select
  and run explicit MRI/CV OS-version pilots after restore evidence is available.
- Continue the package wave serially on backed-up units. Jersey Shore still needs
  extra Wi-Fi caution at approximately -69 dBm. Do not touch GR's package backlog
  until its read-only boot filesystem has been diagnosed and a safe recovery path
  is available.
- Add authenticated, role-based actions before exposing update or reboot buttons.
