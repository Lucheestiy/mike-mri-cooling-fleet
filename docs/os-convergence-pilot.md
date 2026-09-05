# Ubuntu 26.04 LTS convergence pilot

## Supported paths

Canonical's release lifecycle lists Ubuntu 26.04 LTS for arm64 with standard
security maintenance through 2031. The 26.04 release notes identify Ubuntu 25.10
as the direct interim-release upgrade source. Ubuntu's server guide recommends
`do-release-upgrade`, a fully updated source release, adequate free space, review
of third-party repositories, an interactive maintenance window, and a verified
backup.

Primary references:

- https://ubuntu.com/about/release-cycle
- https://documentation.ubuntu.com/release-notes/26.04/
- https://documentation.ubuntu.com/server/how-to/software/upgrade-your-release/

Canonical's Ubuntu Security announcement confirms that 25.10 reached end of
life on 2026-07-09, and the release announcement confirms that 25.04 reached end
of life on 2026-01-15:

- https://lists.ubuntu.com/archives/ubuntu-security-announce/2026-June/010741.html
- https://lists.ubuntu.com/archives/ubuntu-announce/2026-January/000320.html

## Live OS posture — 2026-07-16

Complete audit `audit_20260716_164309.json` classifies current observations rather
than stale offline history. Of 23 reachable Pis, three CV systems already run the
Ubuntu 26.04 LTS target, GR runs supported Ubuntu 24.04 LTS, and 19 MRI systems
run end-of-life interim releases: 18 on 25.10 and Shamokin on 25.04. Four offline
systems remain unknown. Thus 4/23 reachable systems are on a supported LTS and
3/23 are on the exact fleet target. The portal exposes target, supported-exception,
end-of-life, and unknown counts separately; it does not call an offline system
compliant using historical facts.

## MRI pilot selection

AGC MR3 is the preferred first MRI pilot because it is physically close to the
office, backed up, already on the approved MRI application family, and passed the
package/reboot pilot. A read-only check on 2026-07-15 confirmed:

- Ubuntu 25.10 with `Prompt=normal` and `do-release-upgrade` installed;
- the upgrader advertises Ubuntu 26.04 LTS and reports 25.10 unsupported;
- only official `ports.ubuntu.com` Questing sources, with no detected PPA;
- zero pending packages and no reboot flag;
- 861 GiB free on `/` and 276 MiB free on `/boot/firmware`;
- active Tailscale and MRI sensor services; and
- five visible probes and current server telemetry.

This was readiness evidence rather than authorization to begin. The production
AGC MR3 restore test was the final recovery gate and subsequently succeeded.

Fresh preflight `preflight_20260716_143338.json` reconfirmed the same state on
July 16: the upgrader still offers 26.04 LTS directly, no third-party apt source
was detected, zero packages are pending, no reboot is required, `/` has about
923.5 GB free, `/boot/firmware` has about 289 MB free, and Tailscale, the MRI
sensor service, five probes, zero throttling, current server telemetry, recent
repository activity, and the successful daily backup batch all pass. The restore
test list is still empty, so the portal correctly keeps the upgrade on hold.

The newer guarded evidence workflow makes this gate machine-verifiable:

```bash
python3 scripts/fleet_ops.py preflight --hosts agcmr3
python3 scripts/os_upgrade_evidence.py capture --host agcmr3
```

`os_upgrade_readiness_20260716_154951.json` captured the live application hash,
five configured and physical probe IDs, five offsets, GPIO 4 and its boot
overlay, physical MACs, all 13 required operational packages, synchronized
clock, boot state, free space, and current server telemetry. Every readiness
check passed except the production restore proof, so the command intentionally
exited blocked and the portal exposed that exact evidence rather than only a
manual note. After the production restore succeeded, fresh preflight
`preflight_20260716_214804.json` and readiness report
`os_upgrade_readiness_20260716_214807.json` passed every machine gate. The pilot
is now ready for an attended interactive maintenance window; it is not appropriate
to launch the whole-OS upgrade unattended.

After final backup onboarding and fleet convergence, fresh preflight
`preflight_20260716_224642.json` and readiness report
`os_upgrade_readiness_20260716_224646.json` again returned `ready` against the
authoritative successful-snapshot markers and production restore proof.

## Guarded procedure

1. Install the hub restore verifier and run the `agcmr3` production test. Confirm
   the portal shows a recent successful restore.
2. Capture a fresh full audit, backup activity, application hash, sensor IDs,
   offsets, GPIO state, network interfaces, MAC addresses, routes, systemd unit,
   and telemetry timestamp.
3. Apply the complete current-release update recommended by Ubuntu, including
   phased updates, and reboot if required. Re-run fleet preflight.
4. Start `do-release-upgrade` interactively during an attended window. Review its
   package-removal summary and every configuration-file prompt. Preserve custom
   SSH, netplan, Tailscale, boot overlay, and sensor-service configuration unless
   a reviewed diff proves replacement is required.
5. Reboot only when the upgrader completes. Do not advance to another Pi until
   SSH/Tailscale, Ubuntu 26.04, the expected kernel, service, five probes, unchanged
   application hash, offsets, GPIO, Wi-Fi, and advancing server telemetry all pass.
6. Hold the MRI pilot for observation before any broader OS wave.

After the reboot, take a fresh audit and run the strict comparator:

```bash
python3 scripts/fleet_ops.py audit --no-bootstrap --hosts agcmr3
python3 scripts/os_upgrade_evidence.py verify \
  --baseline reports/os_upgrade_readiness_<approved>.json \
  --audit reports/audit_<post-upgrade>.json
```

Verification refuses an unapproved baseline and requires Ubuntu 26.04, the same
architecture, application checksum, configured sensors, physical sensor set,
offsets, safe sensor configuration, GPIO/overlays, physical MACs, active sensor
service, complete operational packages, NTP, zero throttle flags, a settled A/B
boot state, and telemetry newer than the pre-upgrade baseline.

There is no supported in-place downgrade. Recovery is the tested Restic restore or
physical SSD replacement, which is why repository activity alone is insufficient.

## CV and exception handling

All three reachable CV devices already run Ubuntu 26.04, so GMC EP3 is the nearby
CV reference rather than a release-upgrade candidate. Its service and fixed-probe
CV application must remain profile-specific.

Shamokin's Ubuntu 25.04 installation is a separate staged exception. Canonical's
documented path requires reaching 25.10 before 26.04, but both interim releases
are now end-of-life and may require archived repository handling. Do not attempt
that path until production restore proof and the AGC MR3 direct 25.10-to-26.04
pilot succeed. GR can remain on supported Ubuntu 24.04 LTS until the pilot is
proven; it should not be upgraded merely to make the version count look uniform.

## AGC MR3 result — 2026-07-17

The attended AGC MR3 upgrade completed successfully. It now runs Ubuntu 26.04
LTS with the Resolute Raspberry Pi kernel, zero pending package upgrades, active
Tailscale and sensor services, the exact five configured probes, and advancing
server telemetry. Strict evidence passed after recovery in
`os_upgrade_verification_20260717_081659.json`.

The release changed the system Python ABI from 3.13 to 3.14. Both the sensor and
optional camera virtual environments referenced the old interpreter and were
rebuilt without changing application code or configuration. Fleet facts now
record sensor and camera interpreter/dependency health, and guarded verification
requires the sensor runtime plus any installed camera runtime to be complete.
The recovery playbook preserves the prior venv, replaces it atomically, and is
both host-limited and explicitly confirmed:

```bash
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/post_upgrade_python_recovery.yml --limit <host> \
  -e python_recovery_confirm=true \
  --become-password-file /root/.config/coolmri/ansible-become-password
```

Because hospitals have separate local links, parallel package downloads are
normally appropriate and a one-time roughly 3 GB SSD write is not a meaningful
wear concern. Downloads may be staged concurrently after readiness gates pass;
interactive release upgrades and post-reboot verification remain a controlled
wave so a newly discovered boot or runtime issue is not repeated fleet-wide.

## GMC MR2 result — 2026-07-17

GMC MR2 was selected as the second nearby MRI canary because its routed Wi-Fi was
about -43 dBm, it had 864 GiB free, zero normal package updates, a current
machine-specific decrypt-and-restore proof, and a fully passing guarded baseline
in `os_upgrade_readiness_20260717_112357_117411.json`. The attended 25.10 to
26.04 transaction completed, staged and promoted kernel `7.0.0-1014-raspi`, and
preserved the application checksum, four configured probe IDs, four offsets,
GPIO4 overlay, physical MACs, service unit, and camera software. Both Python 3.13
virtual environments were atomically rebuilt for Python 3.14; their sensor and
camera dependency contracts pass.

This canary is not a successful sensor upgrade yet. After the reboot, the 1-Wire
master exposed zero of the four configured physical probes and the sensor service
could not complete startup. The GPIO4 overlay, live pin, kernel modules, pull-up
state, and device-tree node match the working GMC MR3 reference. Loading and
reloading the 1-Wire drivers, directly addressing a known sensor ID, and holding
the dedicated GPIO4 bus low for a controlled reset did not recover a device. A
piboot diagnostic boot into the retained `6.17.0-1021-raspi` kernel produced the
same zero-device result, ruling out the 7.0 kernel; the promoted 7.0 boot set was
then restored and settled.

Final strict report `os_upgrade_verification_20260717_135358_713266.json` passes
the target OS, architecture, application, configured IDs, offsets, sensor
configuration, GPIO/overlays, MACs, both Python runtimes, shared packages, NTP,
throttling, and boot-set checks. It intentionally fails physical-probe equality,
active sensor service, and current telemetry. The portal therefore publishes a
critical GMC MR2 field action: cold-power-cycle the Pi and check the common
sensor-bus 3.3 V, ground, GPIO4 data connector, and pull-up, then require all four
exact IDs plus advancing telemetry before this canary is accepted or another OS
wave starts. A fresh encrypted post-upgrade snapshot was subsequently created,
decrypted, and restore-tested successfully, so both the pre-upgrade recovery
point and the current 26.04 disk state are available while the physical bus is
repaired.

The operator subsequently clarified that this older MR2 sensor-bus setup has
occasionally required several boots before its probes enumerate. After a new
24-target backup and exact restore sweep, three additional controlled warm
reboots were therefore attempted with full three-minute recovery windows. Reports
`reboot_20260717_163035.json`, `reboot_20260717_163351.json`, and
`reboot_20260717_163704.json` each prove a new boot on kernel 7.0.0-1014, normal
SSH/Tailscale return, and zero throttling, but all three still found zero of four
physical probes and no advancing telemetry. Target audit
`audit_20260717_163718.json` confirms the final state. Normal reboot repetition is
now exhausted for this incident; remove power long enough for the Pi and sensor
bus to discharge, then restore power and require the four exact configured IDs.
The operator also noted that many later field installations use an upgraded
sensor setup that does not normally exhibit this reboot-enumeration problem; the
MR2 behavior must therefore remain a host-specific hardware exception rather
than a fleet-wide expectation.

The controller's existing 15-minute read-only fleet audit now runs
`scripts/os_upgrade_recovery_watch.py` after fact collection. It does not reboot,
restart, or configure MR2. It waits for the exact four baseline probe IDs, a
complete mapping, an active service, and current telemetry newer than the
pre-upgrade baseline; only then does it execute the complete 25-check comparison
and publish a passing OS verification. A failed or partial cold-start therefore
cannot mark MR2 healthy or release maintenance on MR2 itself.

## GMC MR1 refreshed readiness — 2026-07-17

Read-only preflight `preflight_20260717_165017.json` and readiness record
`os_upgrade_readiness_20260717_165022_850350.json` refresh MR1's eventual upgrade
baseline after its camera-v3 deployment. The record passes with no blockers and
binds the current MRI application, exact five configured/physical probes,
offsets, GPIO state, active service and telemetry, writable USB boot partition,
settled piboot state, zero throttling, current v3 camera semantic hash and Python
runtime, plus the exact successful 16:23 restore of snapshot
`8500dba169eae8c11f3518d670705ec1a2233f70ecb7ad2cfb74a655384281fe`.

The operator subsequently authorized continuing updates elsewhere and will repair
MR2's older sensor bus later if necessary. MR2 therefore remains individually
held until its four exact probes, service, and telemetry recover, but it is no
longer a fleet-wide gate. Because the successful MR3 primary pilot is complete,
MR1 can become the next attended nearby candidate using its own current backup,
restore, machine-readiness, sensor, camera-runtime, and telemetry proofs.

## GMC MR1 result — 2026-07-17

The next serial wave completed successfully after the operator directed that
MR2's host-specific hardware fault must not block healthy Pis. MR1 received a
fresh encrypted snapshot and exact decrypt/restore test, passed current-release
package maintenance with zero pending packages, and captured a new approved
baseline in `os_upgrade_readiness_20260717_192012_000197.json`.

The supervised 25.10-to-26.04 transaction exited zero. Before reboot, the sensor
and camera virtual environments were atomically rebuilt for Python 3.14 while
retaining their prior environments. The guarded piboot restart promoted kernel
`7.0.0-1014-raspi` and returned with all five exact configured probes, the active
sensor service, and advancing telemetry. Strict report
`os_upgrade_verification_20260717_195915_167102.json` passed all 25 checks,
including unchanged application/camera fingerprints, offsets, sensor settings,
GPIO/overlays, physical MACs, complete Python runtimes, operational packages,
NTP, throttle state, and a settled boot candidate.

A new post-upgrade encrypted snapshot was then created and the exact snapshot ID
was decrypted and restore-tested successfully. MR1 is therefore a complete
nearby 26.04 reference independent of MR2's pending physical repair. The next
remote wave remains serial and selects only a host with its own fresh backup,
restore, strong routed link, exact probe/service/telemetry health, and approved
machine baseline.

## GBH Snap preflight repair — 2026-07-17

GBH was selected for the first remote wave because it had the strongest routed
signal among ready remote hosts (about -38 dBm), five exact probes, an active
sensor with current telemetry, no camera runtime, 208 GiB free, and current
backup/restore proof. Its first release-upgrade invocation stopped before package
mutation when the upgrader's Snap connectivity check timed out. Although the
wrapper exited zero, `main.log` recorded the abort; release-upgrade success must
therefore be proven by a `cache.commit()` milestone and post-upgrade state, not
the process exit code alone.

Investigation found `snapd.service` failed and `/var/lib/snapd/state.json` was
entirely NUL-filled while the snap images, sequence files, and mounts remained.
The corrupt state was retained root-only, snapd reconstructed its state from the
installed snaps, seeding and all tracked refreshes completed, and `snap debug
connectivity` passed. A fresh encrypted snapshot and exact decrypt/restore test
then captured the repaired pre-upgrade state.

Fleet fact collection now records only whether installed snapd responds to a
bounded `snap list` probe, its package version, and installed-snap count; it does
not copy Snap state or error contents. Guarded OS readiness blocks an installed
but unresponsive daemon, and strict post-upgrade verification requires it to
remain responsive. This closes the preflight gap that allowed GBH's first,
non-mutating attempt to start.

## GBH result — 2026-07-17

After the Snap repair, GBH passed a refreshed guarded baseline in
`os_upgrade_readiness_20260717_202443_056403.json`. The supervised upgrader
downloaded about 2.9 GiB, recorded `cache.commit()` at 20:33, completed package
configuration and PostUpgrade cleanup, and exited successfully. SSH was briefly
unavailable while OpenSSH/system packages were replaced, but the Pi remained
directly reachable over Tailscale and the local systemd transaction continued
without intervention.

GBH's service uses `/home/gbh/mike-mri-cooling/venv`, not the newer `/opt`
layout. The first generic recovery invocation therefore failed before creating
or replacing a venv and its rescue handler restarted the service. Inventory now
records GBH's real runtime path; the rerun atomically retained its prior venv,
built a Python 3.14 replacement, passed all dependency imports, and returned the
sensor service to active state.

Guarded reboot report `reboot_20260717_210148.json` promoted kernel
`7.0.0-1014-raspi`. Strict report
`os_upgrade_verification_20260717_210203_219643.json` passes all 26 checks,
including Ubuntu 26.04, settled boot state, unchanged application/site/probe
configuration/offsets/GPIO/MACs, all five exact physical probes, active Python
3.14 sensor runtime, advancing telemetry, required packages, responsive Snap,
NTP, and zero throttling. A fresh encrypted post-upgrade snapshot was then
created; exact snapshot `6f878092431ecc8723cdde94cae8ebd55d9ae66bcff7703a46069f9e71f0e5ee`
was decrypted and restore-tested successfully. GBH is the first complete remote
26.04 wave.

## SVI MR1 result — 2026-07-17

SVI MR1 was selected next with approximately -39 dBm routed Wi-Fi, five exact
probes, no camera runtime, 861 GiB free, and fresh backup/restore evidence. Its
ordinary 25.10 maintenance completed first, followed by approved baseline
`os_upgrade_readiness_20260717_210827_828751.json`. The release transaction
recorded `cache.commit()`, installed kernel `7.0.0-1014-raspi`, completed cleanup,
and exited successfully. SSH was temporarily refused while OpenSSH packages were
replaced, but direct Tailscale reachability remained and the persistent local
unit continued without interruption.

Inventory now records SVI MR1's legacy runtime path at
`/home/svimr1/mike-mri-cooling/venv`. Its prior environment was retained and an
atomic Python 3.14 replacement passed all imports before the guarded reboot.
Report `reboot_20260717_214259.json` proves recovery on the promoted kernel, and
`os_upgrade_verification_20260717_214317_373513.json` passes all 26 strict
checks, including five exact probes, active sensor, advancing telemetry, Snap,
NTP, unchanged identity/configuration, and settled boot state. Exact encrypted
snapshot `0ce62d3383b4df0cc10d54e76d6ad2e50dfc9525c6469586b6b0ef3b0d8c8520`
was then decrypted and restore-tested successfully. SVI MR1 is the second
complete remote 26.04 wave.

## VWM3 result — 2026-07-17

VWM3 entered the next serial wave with five exact probes, no camera runtime,
approximately -46 dBm routed Wi-Fi, and fresh backup/restore proof. Ordinary
25.10 maintenance passed first, followed by approved baseline
`os_upgrade_readiness_20260717_214848_174191.json`. The persistent release unit
passed Snap checks, recorded `cache.commit()`, installed the 26.04 package set,
and completed successfully. A roughly ten-minute OpenSSH replacement window did
not interrupt the locally running transaction; direct Tailscale reachability
remained throughout.

The retained sensor venv was atomically replaced with a dependency-complete
Python 3.14 runtime. Guarded reboot `reboot_20260717_222310.json` promoted kernel
`7.0.0-1014-raspi`; strict report
`os_upgrade_verification_20260717_222330_521149.json` passes all 26 checks,
including unchanged identity/application/configuration, five exact probes,
active service, advancing telemetry, Snap, NTP, zero throttling, and settled
boot state. Post-upgrade encrypted snapshot
`2a7d2afa8cef667bba6b85008947c41aa90001c6747b0c5320fa949d1435066f`
was decrypted and restore-tested successfully. VWM3 is the third complete
remote 26.04 wave.

## GWV result — 2026-07-17

GWV entered the next serial wave with five exact probes, no camera runtime,
approximately -48 dBm routed Wi-Fi, and fresh backup/restore proof. Ordinary
25.10 maintenance passed first, followed by approved baseline
`os_upgrade_readiness_20260717_223002_496339.json`. Its larger installed desktop
set required about 3.8 GiB of cached packages. The persistent release unit
recorded `cache.commit()`, completed the Ubuntu 26.04 transaction, and exited
successfully. Direct Tailscale reachability remained through the temporary
OpenSSH replacement window.

The managed sensor venv was atomically rebuilt for Python 3.14. Guarded reboot
`reboot_20260717_230051.json` promoted kernel `7.0.0-1014-raspi`; strict report
`os_upgrade_verification_20260717_230107_563357.json` passes all 26 checks,
including unchanged identity/application/configuration, five exact probes,
active service, advancing telemetry, Snap, NTP, zero throttling, and settled
boot state. Post-upgrade encrypted snapshot
`8eea58f450fff80658736a4c673fab7e495ffca4f67e66bee8539deedf60400c`
was decrypted and restore-tested successfully. GWV is the fourth complete remote
26.04 wave.

## VWM2 result — 2026-07-17

VWM2 proved the operator-authorized weak-link procedure. Its routed signal was
approximately -78 dBm, but current reachability, five exact probes, service and
telemetry health, writable boot storage, free space, and fresh backup/restore
proof all passed. Ordinary 25.10 maintenance first required a guarded reboot;
the release upgrader correctly refused to start until that reboot completed.
Fresh approved baseline `os_upgrade_readiness_20260717_231743_924141.json` then
bound the post-reboot state.

The retried persistent upgrade passed Snap checks, downloaded about 2.56 GiB,
recorded `cache.commit()`, and completed successfully. OpenSSH was unavailable
for roughly ten minutes during service replacement, while direct Tailscale
reachability and the local package transaction remained intact. The sensor venv
was atomically rebuilt for Python 3.14. Guarded reboot
`reboot_20260717_235236.json` and strict report
`os_upgrade_verification_20260717_235259_728089.json` pass all 26 checks,
including exact probes, active service, advancing telemetry, Snap, NTP, zero
throttling, and settled boot state. Post-upgrade encrypted snapshot
`6ddb4ee205160deb04e5ff449dbeef3be35dcc0c892ea207590e817f7a04164c`
was decrypted and restore-tested successfully. VWM2 is the fifth complete remote
26.04 wave and confirms that weak signal can remain advisory when the hard gates
and persistent transaction controls pass.

## GCMC result — 2026-07-18

GCMC entered the next serial wave with five exact probes, its installed camera
agent, approximately -51 dBm routed Wi-Fi, and fresh encrypted backup/restore
proof. Ordinary 25.10 maintenance passed first, followed by approved baseline
`os_upgrade_readiness_20260717_235947_758776.json`. The persistent release unit
downloaded about 3.14 GiB, recorded `cache.commit()` twice across package setup
and cleanup, and exited with `Result=success` and status 0. Direct Tailscale
reachability remained available through the expected OpenSSH replacement window.

Both the sensor and camera environments were atomically rebuilt for Python 3.14
before reboot. Guarded reboot `reboot_20260718_003757.json` passed, and strict
report `os_upgrade_verification_20260718_003812_283853.json` passes all 26
checks, including unchanged camera software and site identity, five exact probes,
active sensor service, complete sensor and camera runtimes, advancing telemetry,
Snap, NTP, zero throttling, and settled boot state. Post-upgrade encrypted
snapshot `a13d9c4b57fd0b72387c3b21a45bc59ac30968544921980abeca40863dcee9c8`
was decrypted and restore-tested successfully. GCMC is the sixth complete remote
26.04 wave and raises the reachable target-OS count to 12 of 23.

## Pittston Sola result — 2026-07-18

Pittston Sola entered the next serial camera-host wave with five exact probes,
approximately -40 dBm routed Wi-Fi, and a newly created and restore-tested
encrypted backup. Ordinary 25.10 maintenance had zero packages and required no
reboot. Approved baseline `os_upgrade_readiness_20260718_004638_735040.json`
bound its application, camera software, configuration, identities, and live
health before the release transaction.

The persistent unit cached about 3.0 GiB, recorded `cache.commit()` twice, and
completed successfully. Tailscale remained reachable through an approximately
7.5-minute OpenSSH replacement window. Both Python environments were atomically
rebuilt for Python 3.14. Guarded reboot `reboot_20260718_012328.json` passed, and
strict report `os_upgrade_verification_20260718_012409_781404.json` passes all
26 checks, including unchanged camera software, five exact probes, active and
advancing sensor telemetry, complete sensor and camera runtimes, Snap, NTP, zero
throttling, and settled boot state. Post-upgrade snapshot
`d660ebae42bd1948f94e770ccb75bfe37cd01bf8608b471592669902226df602`
was decrypted and restore-tested successfully. Pittston Sola is the seventh
complete remote wave and raises the reachable target-OS count to 13 of 23.

## Muncy result — 2026-07-18

Muncy entered the next serial camera-host wave with five exact probes,
approximately -43 dBm routed Wi-Fi, and a newly created and restore-tested
encrypted backup. Ordinary maintenance had zero packages and no pending reboot.
Approved baseline `os_upgrade_readiness_20260718_013251_660075.json` passed all
hard gates before the persistent release transaction began.

The slower link extended only the download phase; installation began at the
`cache.commit()` marker and remained local. Tailscale stayed reachable through
an approximately 6.75-minute OpenSSH replacement window. Inventory was corrected
to record Muncy's actual legacy sensor venv at
`/home/muncymr/mike-mri-cooling/venv`; the first generic recovery failed before
replacing anything, and its rescue handler restarted the prior service. The
rerun rebuilt both sensor and camera environments for Python 3.14.

Guarded reboot `reboot_20260718_021556.json` timed out because OpenSSH regenerated
Muncy's host key and the controller still trusted the pre-upgrade key. The new
fingerprint was verified both by live scan and directly against Muncy's
`/etc/ssh/ssh_host_ed25519_key.pub`, then refreshed on the controller and backup
hub. No second reboot was needed. Strict report
`os_upgrade_verification_20260718_021751_880930.json` passes all 26 checks,
including five exact probes, unchanged camera software, complete Python 3.14
runtimes, active and advancing telemetry, Snap, NTP, zero throttling, and settled
boot state. Post-upgrade snapshot
`b6799d79d0e315533027f37307392d95d4ec3854c4daacc75f9fd8d6875995ea`
was decrypted and restore-tested successfully. Muncy is the eighth complete
remote wave and raises the reachable target-OS count to 14 of 23.

## Pittston Vida result — 2026-07-18

Pittston Vida entered the next serial camera-host wave with five exact probes,
approximately -54 dBm routed Wi-Fi, and a newly created and restore-tested
encrypted backup. Ordinary 25.10 maintenance had zero packages and no pending
reboot. Approved baseline `os_upgrade_readiness_20260718_022734_204175.json`
passed all hard gates before the persistent transaction began.

The release unit recorded `cache.commit()` twice, remained protected through an
approximately 7.75-minute OpenSSH replacement window, and exited successfully.
Both sensor and camera environments were atomically rebuilt for Python 3.14.
Guarded reboot `reboot_20260718_030349.json` passed, and strict report
`os_upgrade_verification_20260718_030413_247874.json` passes all 26 checks,
including five exact probes, unchanged camera software, complete runtimes,
active and advancing telemetry, Snap, NTP, zero throttling, and settled boot
state. Post-upgrade snapshot
`6f1066dcdd5cb41779ea8e92a6f1d14aec9e2a36f658fdb6d4498b9dfbb302fc`
was decrypted and restore-tested successfully. Pittston Vida is the ninth
complete remote wave and raises the reachable target-OS count to 15 of 23.

## OSW MR1 result — 2026-07-18

OSW MR1 entered the next serial camera-host wave with exact probes, active and
advancing telemetry, writable boot storage, idle package management, responsive
Snap, and a newly created and restore-tested encrypted backup. Weak/variable
Wi-Fi lengthened only the download phase. Ordinary 25.10 maintenance had zero
packages and required no reboot. Approved baseline
`os_upgrade_readiness_20260718_031411_757026.json` bound the application,
camera software, configuration, identities, and live health before the
persistent release transaction began.

The release unit cached about 3.44 GiB, recorded `cache.commit()`, remained
protected through an approximately eight-minute OpenSSH replacement window,
and exited successfully. Inventory was corrected to record OSW MR1's actual
legacy sensor venv at `/home/oswmr1/mike-mri-cooling/venv`; the first generic
recovery failed before replacing anything, and its rescue handler restarted the
prior service. The rerun atomically rebuilt both sensor and camera environments
for Python 3.14.

Guarded reboot `reboot_20260718_041421.json` passed on kernel
`7.0.0-1014-raspi`. Strict report
`os_upgrade_verification_20260718_041441_864551.json` passes all 26 checks,
including unchanged camera software, exact probes, complete Python 3.14
runtimes, active and advancing telemetry, Snap, NTP, zero throttling, and
settled boot state. Post-upgrade snapshot
`c0946958a70d07c68a889b0485b24f234b3af27052a026ba90fa7c7207f3ad64`
was decrypted and restore-tested successfully. OSW MR1 is the tenth complete
remote wave and raises the reachable target-OS count to 16 of 23.

## GSWB result — 2026-07-18

GSWB entered the next serial camera-host wave with five exact probes, active and
advancing telemetry, approximately -63 dBm routed Wi-Fi, writable boot storage,
responsive Snap, and a newly created and restore-tested encrypted backup.
Ordinary 25.10 maintenance had zero packages and required no reboot. Approved
baseline `os_upgrade_readiness_20260718_042555_562473.json` bound its
application, camera software, configuration, identities, and live health before
the persistent release transaction began.

The release unit recorded `cache.commit()` twice, remained protected through an
approximately 7.5-minute OpenSSH replacement window, and exited successfully.
Inventory records GSWB's legacy sensor venv at
`/home/gswb/mike-mri-cooling/venv`; both sensor and camera environments were
atomically rebuilt for Python 3.14. Guarded reboot
`reboot_20260718_050617.json` passed on kernel `7.0.0-1014-raspi`.

Strict report `os_upgrade_verification_20260718_050632_633057.json` passes all
26 checks, including unchanged application and camera software, five exact
probes, complete Python 3.14 runtimes, active and advancing telemetry, Snap,
NTP, zero throttling, and settled boot state. Post-upgrade snapshot
`d4a866129fc1a04f55256e7af847332e64178daabed41f22312ea2b62fd79c90`
was decrypted and restore-tested successfully. GSWB is the eleventh complete
remote wave and raises the reachable target-OS count to 17 of 23.

## OSW MR2 result — 2026-07-18

OSW MR2 entered the next serial camera-host wave with five exact probes, active
and advancing telemetry, approximately -63 dBm routed Wi-Fi, writable NVMe boot
storage, responsive Snap, and a newly created and restore-tested encrypted
backup. Ordinary 25.10 maintenance had zero packages and required no reboot.
Approved baseline `os_upgrade_readiness_20260718_051734_685039.json` bound its
application, camera software, configuration, identities, and live health before
the persistent release transaction began.

The release unit recorded `cache.commit()` twice, remained protected through an
approximately 7.5-minute OpenSSH replacement window, and exited successfully.
Inventory records OSW MR2's legacy sensor venv at
`/home/oswmr2/mike-mri-cooling/venv`; both sensor and camera environments were
atomically rebuilt for Python 3.14. Guarded reboot
`reboot_20260718_055157.json` passed on kernel `7.0.0-1014-raspi`.

Strict report `os_upgrade_verification_20260718_055215_151425.json` passes all
26 checks, including unchanged application and camera software, five exact
probes, complete Python 3.14 runtimes, active and advancing telemetry, Snap,
NTP, zero throttling, and settled boot state. Post-upgrade NVMe snapshot
`9c8a44b8362688b90d1f2233ceec18d88389a828b7a0be7e03f9984658ff6fcf`
was decrypted and restore-tested successfully. OSW MR2 is the twelfth complete
remote wave and raises the reachable target-OS count to 18 of 23.

## SVI MR2 result — 2026-07-18

SVI MR2 entered the next serial camera-host wave with five exact probes, active
and advancing telemetry, approximately -64 dBm routed Wi-Fi, writable boot
storage, responsive Snap, and a newly created and restore-tested encrypted
backup. Ordinary 25.10 maintenance completed cleanly. Approved baseline
`os_upgrade_readiness_20260718_060157_342543.json` bound its application,
camera software, configuration, identities, and live health before the
persistent release transaction began.

The release unit recorded `cache.commit()` twice, remained protected through an
approximately 8.5-minute OpenSSH replacement window, and exited successfully.
Inventory records SVI MR2's legacy sensor venv at
`/home/svimr2/mike-mri-cooling/venv`; both sensor and camera environments were
atomically rebuilt for Python 3.14. Guarded reboot
`reboot_20260718_064106.json` passed on kernel `7.0.0-1014-raspi`.

Strict report `os_upgrade_verification_20260718_064128_458289.json` passes all
26 checks, including unchanged application and camera software, five exact
probes, complete Python 3.14 runtimes, active and advancing telemetry, Snap,
NTP, zero throttling, and settled boot state. Post-upgrade snapshot
`b023331b81ca2ae15ba607c12e85195304f20efd8541c7ab1d80f6b934000ed7`
was decrypted and restore-tested successfully. SVI MR2 is the thirteenth
complete remote wave and raises the reachable target-OS count to 19 of 23.

## Jersey Shore result — 2026-07-18

Jersey Shore entered the next serial camera-host wave with five exact probes,
active and advancing telemetry, approximately -71 dBm routed Wi-Fi, writable
boot storage, responsive Snap, and a newly created and restore-tested encrypted
backup. Ordinary maintenance installed its already approved cached package set
and required a reboot. The first release launch correctly refused to run before
that reboot and made no OS change. Guarded maintenance reboot
`reboot_20260718_065458.json` promoted kernel 1011 to 1021 while preserving all
five probes, service, application, and telemetry. Approved post-reboot baseline
`os_upgrade_readiness_20260718_065617_334506.json` then passed every hard gate.

The persistent release unit recorded `cache.commit()` twice, remained protected
through an approximately 6.75-minute OpenSSH replacement window, and exited
successfully. Inventory records Jersey Shore's legacy sensor venv at
`/home/jsmr/mike-mri-cooling/venv`; both sensor and camera environments were
atomically rebuilt for Python 3.14. Guarded release reboot
`reboot_20260718_073457.json` passed on kernel `7.0.0-1014-raspi` despite
post-boot packet loss on the marginal Wi-Fi link.

Strict report `os_upgrade_verification_20260718_073517_647718.json` passes all
26 checks, including unchanged application and camera software, five exact
probes, complete Python 3.14 runtimes, active and advancing telemetry, Snap,
NTP, zero throttling, and settled boot state. Post-upgrade snapshot
`be7164cc511074accac81c1197bd8941cd5b97cde9c174f976f1103a263106a2`
was decrypted and restore-tested successfully. Jersey Shore is the fourteenth
complete remote wave and raises the reachable target-OS count to 20 of 23,
proving that approximately -71 dBm signal can remain advisory when every hard
gate passes and the release transaction is persistent and local.

## Reachable end-of-life fleet assessment — 2026-07-17

Preflight `preflight_20260717_165243.json` read-only audited all 17 reachable MRI
hosts still on Ubuntu 25.10 or 25.04. It changed nothing and completed facts,
backup, exact probe/service, routed-network, and telemetry checks for every host.
The resulting per-host `os_upgrade_readiness_20260717_165250_*` and
`os_upgrade_readiness_20260717_165251_*` records show:

- 14 Ubuntu 25.10 hosts pass their individual machine and exact-restore gates:
  GMC MR1, OSW MR1/MR2, SVI MR1/MR2, GBH, Muncy, Pittston Sola/Vida, GCMC,
  GCMC MR2, GSWB, GWV, and VWM3;
- Jersey Shore has approximately -71 dBm routed Wi-Fi and remains a field-improvement recommendation, not an upgrade blocker;
- VWM2 has approximately -79 dBm routed Wi-Fi and remains a critical field-improvement recommendation, not an upgrade blocker; and
- Shamokin is blocked because its Ubuntu 25.04 source needs a reviewed staged
  path rather than the direct 25.10-to-26.04 procedure.

After the explicit authorization to continue independently of MR2, these passing
records may enter the portal's OS lane once the successful MR3 primary pilot and
each host's own gates are present. The nearby attended MR1 transaction remains
the next intended wave. MR2 stays held on its own failed probe/service/telemetry
checks, and remote upgrades remain serial and fully verified rather than being
released as a single bulk mutation.

The operator subsequently directed that weak Wi-Fi signal alone must not stop
updates. Routed signal and bitrate remain visible recommendations, but no longer
enter the maintenance blocker list. A weak-link host may proceed when it is
currently reachable and its independent backup/restore, exact probes, sensor,
telemetry, writable boot storage, free-space, and package-manager gates pass.
Release upgrades continue through a persistent local systemd unit so a temporary
SSH interruption does not terminate the package transaction.

## Shamokin staged result — 2026-07-18

Shamokin could not safely take the direct 25.04→26.04 offer, so it followed the
supported 25.04→25.10→26.04 sequence. The signed Questing upgrader was verified
with the Ubuntu archive key on the Pi. Both stages had separate approved
baselines, successful package commits, Python-runtime recovery, guarded kernel
reboots, all 26 strict checks, and fresh encrypted snapshots that were decrypted
and restore-tested. Final verification is
`os_upgrade_verification_20260718_092050_378001.json`.

## GCMC MR2 result — 2026-07-18

Before mutation, natural session `GCMCMR2_SCHED_0718_090002` delivered exactly
camera uploads 01–10. A fresh restore-tested backup and readiness baseline
`os_upgrade_readiness_20260718_092708_746495.json` froze its five probes, sensor
application, distinct camera contract, exact camera software, schedules, and
both runtimes. After the persistent release transaction, both virtual
environments were rebuilt for Python 3.14 and guarded reboot
`reboot_20260718_100530.json` passed on kernel 7.0. Strict verification
`os_upgrade_verification_20260718_100554_297377.json` passes all 26 checks,
including exact camera preservation, and the final encrypted snapshot was
successfully decrypted and restored.

The reachable fleet now has 22 Pis on Ubuntu 26.04 LTS and the intentional GR
Ubuntu 24.04 LTS exception. No reachable host remains on an end-of-life interim
Ubuntu release.
