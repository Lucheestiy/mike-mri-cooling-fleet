# Controlled package maintenance — 2026-07-15

## Method

Every device was selected only after confirming a configured backup repository,
recent repository activity, active sensor service, expected probes, current server
telemetry, adequate disk space, and no hardware throttle flags. Work proceeded one
device at a time. Each update was followed by a second audit; reboot occurred only
when required, followed by kernel, service, probes, application hash, Wi-Fi,
throttle, and server-telemetry verification.

The fleet command now encodes these checks as the default workflow. It blocks a
mutation without current server telemetry and reports `verification_failed` unless
local sensor health recovers and the API timestamp advances after the action. A
reboot also requires a lower post-action uptime, preventing an SSH response from
being mistaken for proof that a requested reboot occurred. After the July 16 CV
wave exposed delayed A/B/SSH settling, reboot verification was strengthened again:
it now requires 30 continuous seconds of successful, monotonic-uptime recovery
audits before accepting the host.

## Completed devices

| Device | Profile | Packages before | Packages after the run | Rebooted | Verified result |
| --- | --- | ---: | ---: | --- | --- |
| AGC MR3 | MRI | 46 | 0 | yes | kernel 6.17.0-1021, 5 probes, telemetry current |
| GMC EP3 | CV | 63 | 6 phased/deferred | yes | 3 expected probes, fixed-probe CV code preserved, telemetry current |
| GMC EP1/EP2 | CV | 15 | 6 phased/deferred | yes | kernel 7.0.0-1011, 5 probes after automatic rescan, telemetry current |
| GBH | MRI | 87 | 0 | yes | kernel 6.17.0-1021, 5 probes, telemetry current |
| SVI MR1 | MRI | 46 | 0 | yes | kernel 6.17.0-1021, 5 probes, telemetry current |
| SVI MR2 | MRI | 30 | 0 | yes | kernel 6.17.0-1021, 5 probes, telemetry current |

GMC EP1/EP2 initially exposed four probes after boot. The approved CV agent's
automatic discovery retry found and mapped all five roughly 28 seconds after
service start, and the subsequent audit plus advancing API timestamp confirmed
recovery. SVI MR1 briefly rejected a management-key check during early boot; the
fleet-specific key worked normally after SSH initialization completed.

The update and reboot action reports are `update_20260715_215726.json` through
`update_20260715_223551.json` and `reboot_20260715_215809.json` through
`reboot_20260715_223649.json`. The complete independent post-wave snapshot is
`audit_20260715_224228.json`.

## Current gates

- Do not update or reboot AGC MR2, GCMC MR2, VWM2, or VWM3 until a matching backup
  target and recent successful activity are verified.
- Do not mutate offline PHC, PHMV, VWM1, or GLH.
- Treat Shamokin's Ubuntu 25.04 release as an OS-path exception.
- The five remaining Ubuntu 26.04 CV meta-packages are phased/deferred; do not
  force them merely to make the portal show zero.
- Jersey Shore is backed up but its approximately -69 dBm Wi-Fi warrants an
  especially conservative reboot window and extended recovery monitoring.
- A successful backup batch and recent repository timestamp are not a restore test;
  perform one MRI and one CV restore exercise before OS-version upgrades.

The fleet mutation gate now enforces that Jersey Shore hold rather than leaving it
as documentation only. Read-only preflight `preflight_20260716_150905.json` blocks
the remote host at -69 dBm while allowing nearby GMC EP3 to remain a controlled
pilot candidate under the explicit nearby-site policy. The portal package and
reboot lanes likewise show no ready host. All routed links at or below -75 dBm are
hard-blocked; remote links at or below -67 dBm require physical improvement first.

Mutation recovery also now uses each host's exact configured probe IDs. Previously,
the generic CV floor of three could have accepted partial recovery on five-probe
GMC EP1/EP2. Read-only preflight `preflight_20260716_151343.json` proves the new
path: AGC MR3 reports 5/5 exact MRI IDs and GMC EP1/EP2 reports 5/5 exact CV IDs,
with no missing or unexpected probes. All 23 reachable hosts match their current
configured mappings in complete audit `audit_20260716_150755.json`.

## GMC IR3 A/B boot recovery — 2026-07-16

GMC IR3's package transaction initially stopped while configuring `dracut` because
`/boot/firmware` had mounted read-only. A non-writing `fsck.fat -n` reported a clean
filesystem and the disk was not hardware write-protected. After a controlled
read-write remount, `dpkg --configure -a` completed and the standard update verifier
proved the CV application, four probes, service, and telemetry were healthy.

Ubuntu 26.04 staged kernel `7.0.0-1010` under the Raspberry Pi A/B `new/` tree. A
normal reboot returned to known-good `7.0.0-1009`, exposing that reboot observation
alone was insufficient evidence. The fleet reboot workflow now detects
`new/state=unknown`, invokes the supported `piboot-try` path, and requires the kernel
to change when the staged and current kernel images differ. The corrected reboot
promoted `1010` to `current`, retained `1009` under
known-good `old`, left the boot partition read-write, and again proved hash, probes,
service, throttle, and advancing telemetry health.

Unattended upgrades subsequently staged `7.0.0-1014`; a second controlled try-boot
promoted it successfully. GMC EP1/EP2 and GMC EP3 were also brought through the
same verified A/B path to `7.0.0-1014`. EP3 first required the same conservative
read-only boot-filesystem diagnosis and package-configuration recovery used for
IR3. All three CV systems preserved their approved application hashes, expected
probe counts, active services, and advancing production telemetry.

## Remote A/B candidate verification — 2026-07-16

After the nearby GMC validation, the backed GCMC Sola, GSWB, and GWV candidates
were promoted individually. Their staged and current `vmlinuz` hashes were
identical while the boot artifacts differed, so a correct promotion legitimately
kept the same reported kernel version. Verification now accepts that case only
when `current/state=good`, `new/` is absent, `old/state=good`, reboot is observed,
and application hash, probes, service health, throttle state, and fresh telemetry
all pass.

The GCMC Sola and GSWB controller run was interrupted after the devices had
recovered, so there is no completed reboot action report for those two. Their
promotion and health are independently evidenced by the subsequent audits and
matching pre-action kernel hashes. GWV completed normally in
`reboot_20260716_072100.json`; its candidate was promoted with all five probes and
advancing telemetry. The fleet loop now stops immediately after any failed
mutation or verification instead of continuing to the next serial host.

The independent post-work snapshot is `audit_20260716_072225.json`: 23 devices are
reachable and four are offline. Remaining candidates are held on AGC MR2, GCMC MR2,
and VWM2 because matching recent backups are not confirmed, and on Jersey Shore
because of its weak Wi-Fi link. GR is separately held because `/boot/firmware` is
read-only, `piboot-try` is absent, and 266 packages are pending.

GR's follow-up diagnosis found a successful boot-time FAT check, no FAT or NVMe
I/O errors, `defaults` in `/etc/fstab`, and both the namespace and boot partition
currently reporting block-layer `RO=0`. A prior no-file-write remount diagnostic
showed that the live namespace could be changed and was then deliberately returned
to `ro`; it did not clear the incident, prove durable media health, or prove the
next boot will mount writable. GR remains package- and reboot-held pending the
onsite inspection and natural-boot persistence evidence in
`docs/gr-boot-storage-remediation.md`.

The deeper July 16 boot-journal review found that `/boot/firmware` was already
reported as `source write-protected, mounted read-only` during the April 22 boot.
The native Crucial P3 Plus NVMe controller subsequently reset four times on April
29, with the kernel explicitly flagging a possible faulty power-saving mode. It is
currently live, the block layer reports writable, and PCIe AER counters are zero,
but that does not make remote firmware writes safe. Audit
`audit_20260716_164309.json` now records the boot-time write-protection event,
block-layer state, reset count, and power warning directly. GR remains held until
power/PCIe connection and drive health can be inspected and a controlled recovery
window is available; no boot argument is changed merely because the kernel log
suggests one.

## Active package-manager reboot gate — 2026-07-16

AGC MR1's unattended-upgrade service staged a new A/B candidate while processing a
large security package set. An attempted controlled reboot was denied by systemd's
active unattended-upgrade shutdown inhibitor, and no reboot occurred. The serial
controller stopped immediately; the sensor service, five probes, application hash,
RAM logging, and telemetry remained healthy. The fleet audit and mutation gate now
record active `apt`, `dpkg`, and unattended-upgrade work and hold all mutations
until it finishes.

The package manager later became idle without intervention. Fresh preflight
`preflight_20260716_080453.json` passed, and controlled report
`reboot_20260716_080545.json` advanced the kernel from 6.17.0-1011 to
6.17.0-1021 and promoted the A/B candidate. The application hash, five probes,
sensor service, zero-throttle state, camera RAM-log mount, and advancing production
telemetry all passed post-reboot verification; the reboot requirement cleared.

## CV security refresh and same-kernel promotion — 2026-07-16

The three nearby CV Pis received the same four security updates serially:
`ubuntu-pro-client`, its localization package, `ntfs-3g`, and its runtime library.
The five reported Ubuntu 26.04 meta/tooling updates remained normally
phased/deferred. Report `update_20260716_091227.json` proves all three application
hashes, site-account services, profile-specific probe counts, operational core,
zero-throttle state, and advancing CV telemetry survived.

Package triggers regenerated same-kernel A/B initramfs/boot assets. Those
candidates were promoted serially with `piboot-try`; report
`reboot_20260716_091729.json` records three successful recoveries. Follow-up fleet
reads overlapped delayed boot/network settling on EP1/EP2 and EP3, so neither
transient snapshot was accepted. Direct state checks and targeted audits proved
`current=good`, no `new/` candidate, `old=good`, active services, and stable site
identities on all three. Complete audit `audit_20260716_092233.json` restored
authoritative 23-online evidence with all CV candidates cleared and no reboot flags.

## AGC MR1 routine security/stability refresh — 2026-07-16

Fresh preflight `preflight_20260716_101909.json` proved recent backup activity,
idle package management, writable A/B boot storage, active sensor service, five
probes, zero throttling, and current AGCMR1 telemetry. Guarded update
`update_20260716_102241.json` installed all 44 pending Questing updates, including
cloud-init, networking, Linux firmware, EEPROM tooling, SSSD, snapd, and desktop
libraries; this was not a release upgrade. Pending packages fell to zero while the
sensor application hash and production telemetry remained unchanged.

Initramfs triggers staged same-kernel `6.17.0-1021` A/B assets and set the reboot
requirement. Controlled report `reboot_20260716_102425.json` promoted the candidate
through the supported try-boot path and passed the 30-second stable-recovery proof.
Independent audit `audit_20260716_102436.json` and complete fleet audit
`audit_20260716_102457.json` prove `current=good`, no staged candidate, zero pending
packages, cleared reboot flag, canonical site-account sensor service, five probes,
advancing telemetry, the 32 MiB volatile journal, recreated camera tmpfs with
durable retry state, and the headless service profile still intact.

## Muncy one-host remote security wave — 2026-07-16

Muncy was selected as the first follow-on remote host because it has recent backup
activity, strong approximately -43 dBm Wi-Fi, no camera workload, writable A/B boot
storage, canonical non-root MRI software, and a clean preflight. Report
`update_20260716_103131.json` records the guarded 89-package transaction, including
curl, NSS, SQLite, Perl, ncurses, Linux firmware/tooling, timezone data, and other
Questing security fixes. Application hash, five probes, service, zero throttle, and
MuncySola telemetry all passed afterward.

The three Raspberry Pi kernel meta-packages for `6.17.0-1021` remained normally
phased and were not forced, so the boot trigger staged a legitimate same-`1018`
initramfs/firmware candidate. Controlled report `reboot_20260716_103325.json`
promoted it without claiming a kernel advance. Target audit
`audit_20260716_103338.json` and complete audit `audit_20260716_103357.json` prove
`current=good`, no candidate, cleared reboot flag, only the three phased packages,
canonical site-account service, five readings, current telemetry, strong Wi-Fi,
zero throttling, and healthy SMART data.

The phased kernel subsequently became eligible and installed normally without
being forced. Preflight `preflight_20260716_110113.json` found zero pending
packages, a real candidate hash different from the known-good 1018 kernel, a
reboot requirement, recent backup, strong Wi-Fi, and healthy production service
and telemetry. Controlled report `reboot_20260716_110238.json` promoted it and
proved the running kernel advanced to `6.17.0-1021-raspi`, the candidate and
reboot flag cleared, five probes and the application hash were preserved, and
telemetry advanced after 30 seconds of stable uptime. Target audit
`audit_20260716_110247.json` and complete audit `audit_20260716_110258.json`
independently confirm the result.

## Eligible versus listed packages — 2026-07-16

Fleet audits now retain both views of package maintenance: `apt list
--upgradable` supplies the packages Ubuntu lists, while a no-lock simulation of
`apt-get upgrade --with-new-pkgs` supplies the packages Ubuntu currently permits
the guarded updater to install. The difference is recorded as deferred and does
not enter the portal's routine maintenance lane. This prevents phased packages
from looking like actionable backlog and preserves Ubuntu's rollout decision.

Target audit `audit_20260716_144542.json` validates the distinction on the nearby
GMC IR3, EP3, and EP1/EP2 systems. Each lists
`python3-software-properties` and `software-properties-common`, but each has zero
eligible packages and two deferred packages. No package transaction, service
restart, or reboot was performed.

The CLI report writer now uses the same semantics as the portal and mutation lane.
Live report `audit_20260716_151645.md` identifies the three GMC hosts as a combined
`0 eligible / 6 listed / 6 deferred`; each row states `0 eligible / 2 listed / 2
deferred` instead of the previous ambiguous `2 updates`. Its JSON companion carries
the aggregate counts, and post-action verification retains the full package object.

## GCMC Sola one-host remote security wave — 2026-07-16

GCMC Sola was the next serial remote host because it has recent backup activity,
approximately -38 dBm Wi-Fi, writable A/B boot storage, a canonical non-root MRI
service, five probes, and current `GCMCSola` telemetry. Its Ubuntu `sudo-rs` did
not emit the prompt Ansible expects, so the generic mutation helper was corrected
to call the already deployed prompt-compatibility shim. The shared root-only
password source remained unchanged, and a direct shim check proved sudo before
the transaction.

Guarded report `update_20260716_104412.json` records 194 installed updates, 152
from security pockets. Backup, package-idle, service, probe, disk, writable boot,
zero-throttle, application-checksum, and advancing-telemetry checks all passed.
The normally phased `linux-image-raspi` `6.17.0-1021.21` package was not forced;
it is the sole remaining upgradable package.

Package triggers staged same-`1011` boot assets, so controlled report
`reboot_20260716_104559.json` exercised `piboot-try` without claiming a kernel
advance. The candidate cleared, reboot-required cleared, and the known-good 1011
kernel remained active. Target audit `audit_20260716_104609.json` and complete
audit `audit_20260716_104620.json` independently prove the canonical application
hash, site-account service, all five probes, zero throttling, strong Wi-Fi, and
healthy telemetry. No second reboot is warranted while the only newer image is
phased.

## GWV Skyra one-host remote security wave — 2026-07-16

GWV followed serially because it has recent backup activity, approximately
-48 dBm Wi-Fi, no camera workload, writable A/B boot storage, canonical non-root
MRI software, five probes, and current telemetry. Guarded report
`update_20260716_105318.json` records 189 installed updates, 147 from security
pockets. The host briefly stopped accepting new SSH connections while its SSH
packages were replaced, but stayed directly reachable over Tailscale and the
original apt/dpkg session continued. Port 22 returned before the transaction
completed; no reboot or manual recovery occurred.

The normally phased `linux-image-raspi` `6.17.0-1021.21` package was not forced
and is the only remaining update. Package triggers staged identical 1011 boot
assets. Controlled report `reboot_20260716_105500.json` exercised the try-boot
path, passed 30 seconds of stable uptime plus advancing telemetry, cleared the
candidate and reboot flag, and correctly made no kernel-advance claim. Target
audit `audit_20260716_105514.json`, complete audit
`audit_20260716_105526.json`, and the no-reboot follow-up
`audit_20260716_110044.json` prove the application hash, site-account service,
five probes, zero throttling, and telemetry remained healthy. The five-minute
follow-up also cleared the portal's reboot-associated unsafe-shutdown observation.

## Pittston Sola one-host remote security wave — 2026-07-16

Pittston Sola was selected next because it has recent backup activity, strong
approximately -40 dBm Wi-Fi, writable A/B boot storage, canonical non-root MRI
software, five probes, and camera captures scheduled outside the maintenance
window. Preflight `preflight_20260716_110456.json` passed backup, package-idle,
sensor, disk, boot, throttle, and current `PittstonSola` telemetry gates.

Guarded report `update_20260716_111158.json` records 194 installed updates, 152
from security pockets. New SSH connections were briefly refused while SSH
packages were replaced, but the Pi stayed directly reachable over Tailscale and
the original apt/dpkg transaction continued normally. The sensor application,
site-account service, five probes, camera software/configuration, empty failed
session queue, durable retry state, and advancing telemetry all passed afterward.

The sole `linux-image-raspi` `6.17.0-1021.21` update remained normally phased and
was not forced. Package triggers staged identical 1011 boot assets. Controlled
report `reboot_20260716_111329.json` exercised the try-boot path without claiming
a kernel advance and passed reboot observation, 30 seconds of stable uptime, and
new telemetry. Target audit `audit_20260716_111344.json` and complete audit
`audit_20260716_111355.json` prove the candidate and reboot flag cleared, the
known-good 1011 kernel remained active, and production sensor/camera state was
preserved. The storage bridge's +2 unsafe-shutdown change is informational across
this controlled reboot. Complete audit `audit_20260716_112310.json`, more than
five minutes later without another reboot, reports a zero delta and clears the
observation.

The previously phased 1021 image subsequently became normally eligible and
installed without being forced. Preflight `preflight_20260716_114626.json` found
zero pending packages, a real candidate hash different from known-good 1011,
strong Wi-Fi, current backup/telemetry, and healthy sensor/camera state.
Controlled report `reboot_20260716_114754.json` promoted the candidate and proves
the running kernel advanced to `6.17.0-1021-raspi`, packages fell to zero, the
reboot flag and candidate cleared, and the application, five probes, zero-throttle
state, camera retry state, and telemetry recovered. Target audit
`audit_20260716_114805.json` and complete audit `audit_20260716_114816.json`
independently confirm the kernel promotion. Five-minute no-reboot audit
`audit_20260716_115350.json` reports a zero unsafe-shutdown delta and closes the
reboot-associated storage observation.

## Pittston Vida one-host remote security wave — 2026-07-16

Pittston Vida followed serially after its sibling because it passed the same
backup, package-idle, sensor, disk, writable A/B boot, throttle, and current
telemetry gates in `preflight_20260716_111522.json`. It had approximately
-55 dBm Wi-Fi, five probes, canonical non-root MRI software, and camera captures
scheduled outside the maintenance window.

Guarded report `update_20260716_112114.json` records 194 installed updates, 152
from security pockets. The expected brief SSH-package restart occurred while the
Pi remained directly reachable over Tailscale and the attached apt/dpkg process
continued. Application checksum, site-account service, all five probes, zero
throttling, camera software/configuration, empty failed-session queue, durable
retry state, and advancing `PittstonVida` telemetry passed afterward.

The sole 1021 kernel image remained normally phased and was not forced. Controlled
report `reboot_20260716_112250.json` safely promoted identical 1011 A/B assets,
made no kernel-advance claim, and passed the stable recovery proof. Target audit
`audit_20260716_112258.json` and complete audit `audit_20260716_112310.json`
prove the candidate and reboot flag cleared and all production state recovered.
Its storage bridge's +2 reboot-associated counter change was informational;
automatic complete audit `audit_20260716_112817.json`, more than five minutes
later without another reboot, reports zero delta and clears the observation.

The phased 1021 image subsequently became normally eligible and installed
without being forced. Preflight `preflight_20260716_121057.json` found zero
pending packages, a real candidate hash different from known-good 1011, recent
backup, current telemetry, healthy camera/sensor state, and approximately
-55 dBm Wi-Fi. Controlled report `reboot_20260716_121300.json` proves the running
kernel advanced to `6.17.0-1021-raspi`, the candidate and reboot flag cleared,
and the application, five probes, camera retry state, zero-throttle state, and
telemetry recovered. Target audit `audit_20260716_121309.json` and complete audit
`audit_20260716_121320.json` independently confirm zero pending packages and the
kernel promotion. Five-minute no-reboot audit `audit_20260716_121849.json`
reports a zero unsafe-shutdown delta and closes the reboot-associated storage
observation.

## GSWB Sola one-host remote security wave — 2026-07-16

GSWB followed after a fresh preflight because it has recent backup activity,
approximately -59 dBm Wi-Fi, writable A/B boot storage, canonical non-root MRI
software, five probes, zero throttling, and camera captures scheduled outside the
maintenance window. Preflight `preflight_20260716_112933.json` passed the backup,
package-idle, sensor, disk, boot, and current `GSWBSola` telemetry gates.

Guarded report `update_20260716_113828.json` records 194 installed updates, 152
from security pockets. The attached apt/dpkg session remained healthy through the
expected SSH-package restart while the Pi stayed directly reachable over
Tailscale. Application checksum, site-account service, five probes, camera
software/configuration, empty failure queue, durable retry state, zero throttle,
and advancing telemetry passed afterward.

The sole `linux-image-raspi` 1021 update remained normally phased and was not
forced. Package triggers staged identical 1011 assets. Controlled report
`reboot_20260716_114010.json` exercised the try-boot path without claiming a
kernel advance and passed reboot observation, 30 seconds of stable uptime, and
new telemetry. Target audit `audit_20260716_114020.json` and complete audit
`audit_20260716_114031.json` prove the candidate and reboot flag cleared and all
production sensor/camera state recovered. A five-minute no-reboot storage sample
`audit_20260716_114816.json` reports zero delta and closes the reboot-associated
bridge observation.

## OSW MR1 one-host remote security wave — 2026-07-16

OSW MR1 was selected after fresh preflight because it has recent backup activity,
approximately -57 dBm Wi-Fi, writable A/B storage, a canonical non-root MRI
service, five probes, zero throttling, and 09:15/15:15 camera captures outside the
maintenance window. Preflight `preflight_20260716_115457.json` passed backup,
package-idle, sensor, disk, boot, and current `OSWMR1` telemetry gates.

Guarded report `update_20260716_120810.json` records 241 installed updates, 195
from security pockets. The larger download and configuration transaction stayed
attached throughout; the expected SSH-package restart briefly refused new SSH
connections while the Pi remained directly reachable over Tailscale. Application
checksum, site-account service, five probes, camera software/configuration, empty
failure queue, durable retry state, zero throttle, and advancing telemetry passed
afterward.

The three 1021 kernel meta-packages remained normally phased and were not forced.
Package triggers staged identical 1011 assets. Controlled report
`reboot_20260716_121006.json` exercised the try-boot path without claiming a
kernel advance and passed reboot observation, 30 seconds of stable uptime, and
new telemetry. Target audit `audit_20260716_121020.json` and complete audit
`audit_20260716_121849.json` prove only the three phased packages remain, the
candidate and reboot flag cleared, and production sensor/camera state recovered.
The same five-minute no-reboot audit reports zero unsafe-shutdown delta and
closes the reboot-associated bridge observation.

The three phased 1021 packages subsequently became normally eligible and
installed without being forced. Preflight `preflight_20260716_122957.json` found
zero pending packages, a real candidate hash different from known-good 1011,
recent backup, healthy camera/sensor state, and current telemetry. Controlled
report `reboot_20260716_123125.json` proves the running kernel advanced to
`6.17.0-1021-raspi`, the candidate and reboot flag cleared, and the application,
five probes, camera retry state, zero-throttle state, and telemetry recovered.
Target audit `audit_20260716_123134.json` and complete audit
`audit_20260716_123145.json` independently confirm zero pending packages and the
kernel promotion.

## OSW MR2 one-host remote security wave — 2026-07-16

OSW MR2 followed after a fresh preflight because it has recent backup activity,
approximately -62 dBm Wi-Fi, writable A/B storage, canonical non-root MRI
software, five probes, zero throttling, and 09:20/15:20 camera captures outside
the maintenance window. Preflight `preflight_20260716_122110.json` passed backup,
package-idle, sensor, disk, boot, and current `OSWMR2` telemetry gates.

Guarded report `update_20260716_122723.json` records 230 installed updates, 183
from security pockets. The attached apt/dpkg session remained healthy through the
expected SSH-package restart while the Pi stayed directly reachable over
Tailscale. Application checksum, site-account service, five probes, camera
software/configuration, empty failure queue, durable retry state, zero throttle,
and advancing telemetry passed afterward.

The sole 1021 kernel image remained normally phased and was not forced. Package
triggers staged identical 1011 assets. Controlled report
`reboot_20260716_122903.json` exercised the try-boot path without claiming a
kernel advance and passed reboot observation, 30 seconds of stable uptime, and
new telemetry. Target audit `audit_20260716_122912.json` and complete audit
`audit_20260716_123145.json` prove only the phased image remains, the candidate
and reboot flag cleared, and production sensor/camera state recovered. Complete
five-minute no-reboot audit `audit_20260716_124218.json` then reports zero new
unsafe-shutdown delta and closes the reboot-associated bridge observation.

## Normally eligible 1021 follow-through — 2026-07-16

Read-only preflight `preflight_20260716_124438.json` found OSW MR2, GCMC Sola,
GSWB, GWV, and Shamokin ready with recent backups, idle package managers,
healthy MRI services, five probes, zero throttling, writable boot storage, and
current telemetry. Shamokin's only ordinary update was Tailscale 1.98.4 to
1.98.9; guarded report `update_20260716_124654.json` proves zero packages remain
and its application, service, probes, Tailscale connection, and telemetry were
preserved without a reboot.

The first GCMC pass, `update_20260716_124546.json`, installed nothing because
plain `apt-get upgrade` cannot add the new dependency packages required by the
now-eligible kernel meta-package. The guarded updater was corrected to use
`upgrade --with-new-pkgs`: it can add dependencies but, unlike `full-upgrade`,
does not permit removals as part of dependency resolution. Repository tests
cover that invariant.

The corrected serial wave then installed normally released 1021 kernel packages
without forcing phasing. GCMC report `update_20260716_124936.json` and controlled
reboot `reboot_20260716_125105.json`, GWV report
`update_20260716_125242.json` and reboot `reboot_20260716_125411.json`, OSW MR2
report `update_20260716_125533.json` and reboot
`reboot_20260716_125702.json`, and GSWB report
`update_20260716_130053.json` and reboot `reboot_20260716_130228.json` each prove
a real 1011-to-1021 kernel advance, successful A/B promotion, 30 seconds of
stable recovery, zero pending packages, the canonical application checksum,
active site-account service, five probes, zero throttling, and advancing
telemetry. GSWB's transaction was slower over its marginal link, so it remained
serial and was not rebooted until the complete post-update gate passed.

Complete no-reboot audit `audit_20260716_130822.json` independently confirms all
four promoted hosts on `6.17.0-1021-raspi`, zero pending packages, no reboot
requirement, active site-account services, five probes, zero throttling, and
zero new unsafe-shutdown delta after the reboot intervals closed.

## GMC CV-profile package alignment — 2026-07-16

Nearby-profile preflight `preflight_20260716_130940.json` passed current backup,
package-idle, CV service, exact probe, zero-throttle, disk, boot, and live
`EP1and2`/`EP3`/`IR3` telemetry gates for all three GMC CV Pis. Each exposed the
same five updates: build and Ubuntu desktop meta-packages were normally eligible,
while two software-properties packages remained phased.

EP3 was updated first in guarded report `update_20260716_131049.json`. It retained
the canonical flexible CV checksum, three probes, its `gmcep3` service identity,
advancing mapped telemetry, `multi-user.target`, disabled graphical/printing/
Bluetooth/modem services, and its 32 MiB volatile journal. IR3 report
`update_20260716_131148.json` and EP1/EP2 report
`update_20260716_131246.json` then passed the same profile-specific gates with
their four- and five-probe mappings. No host required a reboot. The two phased
packages were deliberately left pending on all three hosts.

Complete audit `audit_20260716_131326.json` independently confirms all three CV
applications approved, services active under their site accounts, exact probes,
zero throttling, live telemetry, and the shared volatile-journal cap. Its storage
interval overlaps the package transactions and is therefore excluded from quiet
write-rate conclusions.

Later complete audit `audit_20260716_132544.json` supplies the quiet interval:
EP1/EP2, EP3, and IR3 report approximately 247, 260, and 359 MiB/day respectively,
zero unsafe-shutdown deltas, no reboot requirement, and only the two common phased
packages pending.

## Header-only maintenance wave — 2026-07-16

A later repository refresh exposed `linux-libc-dev` as the only normally
eligible package on GMC EP3, OSW MR2, and GWV. Exact simulations on all three
showed one upgrade, no new packages, no removals, and no kernel image or boot
artifact. GMC EP3 ran first as the nearby canary; OSW MR2 and GWV followed
serially only after ready preflights.

Reports `update_20260716_155642.json` and `update_20260716_155845.json` prove all
three updates completed with no reboot requirement, no remaining eligible
packages, unchanged profile application hashes, active sensor services, exact
configured probe mappings, zero throttle flags, and advancing production
telemetry. The independent full audit `audit_20260716_160229.json` left the
portal's maintenance-ready package queue empty. GMC EP3's two phased
software-properties packages remain correctly deferred rather than actionable.

## Current package holds after restart-policy work — 2026-07-16

Independent audit `audit_20260716_171808.json` reports 453 normally eligible
packages across five Pis, but the guarded ready queue remains empty. AGC MR2,
GCMC MR2, and VWM2 lack authoritative recent backup coverage; VWM2 is also at
-79 dBm. Jersey Shore is held at -71 dBm because its eligible set includes a
reboot requirement. GR's firmware boot filesystem is read-only and remains a
field-inspection hold. The three GMC CV Pis and VWM3 each expose only two phased
packages, which remain deferred and are not forced. No package transaction or
reboot was performed from this snapshot.

Fresh read-only Jersey Shore preflight `preflight_20260716_174538.json` measured
the routed link at -72 dBm and blocked the host at the same health gate used by
the updater. No package transaction, service restart, or reboot was attempted.
Its backed status is not enough to override the remote -67 dBm policy; reposition
the existing antenna/Pi or install an external-antenna USB adapter/Ethernet,
remeasure, and rerun preflight.

Read-only five-host preflight `preflight_20260716_183647.json` reconfirmed the
entire actionable queue immediately before the next maintenance decision. AGC
MR2 (42 packages) and GCMC MR2 (47) remain backup-gated; VWM2 (51) remains both
backup-gated and critically weak at -79 dBm; Jersey Shore (46) remains held at
-71 dBm; and GR (269 simulated upgrades from 266 listed packages) remains held
by its read-only firmware filesystem. The simulation/list-count difference on GR
comes from dependency resolution and is not evidence of a partial transaction.
All five sensor endpoints were reachable, but none passed the mutation gates, so
zero packages were installed and no Pi was rebooted.

## AGC MR1 tooling refresh — 2026-07-16

The 18:57 complete audit found four newly published, normally eligible packages
only on the nearby AGC MR1 canary: `bpftool`, `linux-libc-dev`, `linux-perf`, and
`linux-tools-common`. Guarded preflight `preflight_20260716_185838.json` passed
recent backup, idle package manager, writable boot storage, nearby-link policy,
approved application, exact five-probe mapping, zero throttling, service identity,
and current telemetry. The exact simulation required four upgrades, no new or
removed packages, no kernel image, and no reboot.

Report `update_20260716_185927.json` installed the 5.1 MB tooling/header refresh
and verified advancing production telemetry, unchanged application checksum, all
five exact probe IDs, active site-account service, zero throttling, retained RAM
logging policies, zero remaining packages, and no reboot requirement. Independent
target audit `audit_20260716_185951.json` and complete fleet audit
`audit_20260716_190042.json` confirm the result. The fleet queue returned to 455
eligible packages on the same five held Pis plus eight deferred packages; the safe
queue is again empty.

That action report was produced immediately before a verifier schema correction:
its nested legacy `reboot_observed: true` meant the reboot requirement was
satisfied, including the case where no reboot action was requested. The unchanged
30922-to-30947-second uptime, `reboot_required: false`, and stable 1021 kernel prove
that MR1 did not reboot. Future reports separate `reboot_requested`, the literal
`reboot_observed`, and `reboot_requirement_satisfied`, so a no-reboot update can no
longer be misread as a restart.

## AGC MR3 Tailscale channel canary — 2026-07-16

A fleetwide read-only policy check found that eight reachable Pis still relied on
Ubuntu's bundled Tailscale channel while fifteen used Tailscale's signed stable
repository. AGC MR3 was selected as the nearby, backed, strong-link canary.
Preflight `preflight_20260716_195252.json` passed before the repository-only
change. The canary verified the already-installed signing key by exact SHA-256,
added the release-specific `questing` stable source, refreshed metadata, and did
not install or restart anything. The candidate moved from Ubuntu's installed
1.92.1 to stable 1.98.9.

Post-source preflight `preflight_20260716_195321.json` again passed backup,
storage, package-manager, exact sensor, link, and telemetry gates. Guarded report
`update_20260716_195415.json` then installed Tailscale plus four routine Ubuntu
kernel-tool updates. Its recovery proof shows Tailscale 1.98.9, an online
Tailscale backend, the unchanged MRI application checksum, active sensor service,
all five exact probes, advancing telemetry, zero remaining packages, and no
reboot requirement. Complete audit `audit_20260716_195548.json` independently
confirms 23 reachable / 4 offline and restores the portal's full-fleet snapshot.

After the nearby canary, current preflight `preflight_20260716_195710.json`
approved a five-host follow-up. OSW MR1, SVI MR1, SVI MR2, GBH, and Muncy were
processed one at a time; each source correction was followed by a new preflight,
guarded package transaction, and recovery proof before the next host began. The
five update reports from `update_20260716_195923.json` through
`update_20260716_200325.json` all prove Tailscale 1.98.9, unchanged sensor
applications, exact five-probe mappings, active services, advancing telemetry,
zero remaining eligible packages, and no reboot requirement.

Complete audit `audit_20260716_200755.json` reports 21 official-stable and two
distribution-channel Tailscale installations across the 23 reachable Pis. The
portal now inventories this channel state directly. AGC MR1 and Jersey Shore are
the only distribution-channel systems and remain deliberately held by the camera
proof window and remote Wi-Fi policy respectively.

## GCMC MR2 backup-gate release — 2026-07-16

After GCMC MR2 gained a recent encrypted snapshot and successful production
restore proof, the routine updater's exact repository map was extended for the
four prepared onboarding targets. Regression coverage preserves the fail-closed
behavior for unknown hosts. Fresh preflight `preflight_20260716_215310.json`
then passed GCMC MR2's backup, -56 dBm routed Wi-Fi, writable boot storage,
package-manager, exact five-probe, sensor, throttle, and production-telemetry
gates.

Guarded update `update_20260716_215851.json` installed all 47 eligible packages
with no removals and left zero eligible or deferred packages. Its automatic
recovery proof confirmed the unchanged approved application checksum, all five
exact probes, active sensor service, zero throttling, and advancing telemetry.
The update staged the 1021 kernel and required a reboot.

Controlled report `reboot_20260716_220214.json` proves the A/B candidate was
promoted, the running kernel advanced from `6.17.0-1011-raspi` to
`6.17.0-1021-raspi`, the reboot flag cleared, the application and probe set were
preserved, and production telemetry advanced after the 30-second stability
window. No other Pi package mutation overlapped this serial transaction.

## AGC MR2 backup-gate release — 2026-07-16

AGC MR2's first snapshot `1f766ec2` and successful production tmpfs restore
unlocked fresh preflight `preflight_20260716_223537.json`. It passed the marked
backup, strong nearby routed link, writable A/B boot storage, exact four-probe
mapping, sensor, throttle, package-manager, and production-telemetry gates.

Guarded update `update_20260716_224024.json` installed all 42 eligible packages
with no removals and left zero eligible or deferred packages. Controlled reboot
`reboot_20260716_224218.json` promoted the staged kernel from
`6.17.0-1011-raspi` to `6.17.0-1021-raspi`, cleared the reboot flag, preserved
the exact application checksum and four-probe set, and proved advancing telemetry
after the stability window. Complete audit `audit_20260716_224329.json`
independently confirms the result.

## Current held package set — 2026-07-16 22:59 EDT

Complete audit `audit_20260716_225928.json` reports 371 listed upgrades, 366
normally eligible, and eight deferred. The eligible set is now confined to GR
(269 simulated), VWM2 (51), and Jersey Shore (46). GR remains held by its
read-only boot firmware filesystem and NVMe-reset evidence; VWM2 remains held at
about -80 dBm; Jersey Shore remains held around -71 dBm under the remote-site
policy. Their backup gates pass, but backup evidence does not override storage or
link safety. No package transaction or reboot was attempted on these hosts.

## Parallel cache preparation and verified releases — 2026-07-17

Package acquisition was separated from installation. Download-only report
`download_20260717_094242.json`, plus VWM2 retry proof
`download_20260717_094324.json`, refreshed metadata and verified local APT caches
on all 23 reachable Pis with up to eight independent downloads in flight. The
action installed nothing, rebooted nothing, and rechecked each sensor application,
service, probe map, and throttle state. Four offline Pis remained unreachable.

GMC EP1/EP2 was the nearby install canary. Its recent encrypted snapshot and
successful tmpfs restore satisfied the machine backup gate even though the
earlier fleet batch was incomplete. Report `update_20260717_095136.json` installed
cached `tar` and `linux-libc-dev`; all five exact CV probes, application checksum,
service, and advancing telemetry passed, with no reboot.

VWM3 then passed an isolated 213-package preflight with a recent decrypt/restore,
strong -46 dBm routed Wi-Fi, writable A/B boot storage, 460 GB free, five exact
MRI probes, and current telemetry. Report `update_20260717_100332.json` installed
the cached transaction with no removals or remaining packages. OpenSSH briefly
restarted as expected while Tailscale stayed online. Controlled reboot
`reboot_20260717_100523.json` promoted the staged kernel from
`6.17.0-1011-raspi` to `6.17.0-1021-raspi`, cleared the reboot flag, passed the
30-second stability window, preserved the application and five probes, and
advanced production telemetry.

Pittston Sola, Pittston Vida, GCMC Sola, and GSWB were initially held because
their older snapshots failed restore. The guarded refresh workflow created four
new encrypted snapshots and restored each `etc/os-release` in tmpfs. Fresh
preflight `preflight_20260717_101826.json` then passed all four. Serial report
`update_20260717_102250.json` installed only `linux-libc-dev` on each machine;
all four retained five exact probes, approved applications, active services,
zero throttling, advancing telemetry, zero remaining packages, and no reboot.

The remaining eligible queue is therefore 373 packages and entirely held: GR
272 by read-only boot firmware, VWM2 51 by critical routed Wi-Fi, and Jersey
Shore 50 by marginal remote Wi-Fi plus its pending reboot. Cache presence does
not override those storage or network safety gates.

## Reachable package queue cleared — 2026-07-18

VWM2 and Jersey Shore completed their guarded weak-Wi-Fi transactions first.
GR then passed a boot-partition image, offline FAT repair/check, writable remount,
fresh backup, exact simulation, and production-health preflight. Guarded update
`update_20260718_123717.json` installed the supported Ubuntu 24.04 package set
without application or probe drift. Controlled reboot
`reboot_20260718_123957.json` promoted kernel 6.8.0-1060, returned the boot FAT
read-write naturally, and logged no NVMe reset, timeout, I/O, or FAT error.
Complete audit `audit_20260718_125026.json` reports zero eligible packages and no
reboot requirements, with Tailscale 1.98.9 everywhere. Ubuntu lists two
phased/deferred packages on each of GMC EP1/EP2, EP3, and IR3—six aggregate—but
normal APT simulation offers none, so they are intentionally not forced. Fresh
post-configuration encrypted backup and exact tmpfs restore proof also passed.
