# Storage health and write-wear visibility

## Current fleet capability

All 23 reachable Pis now expose the root block device, transport, model, serial,
capacity, and kernel write-sector counter through the read-only audit. The current
fleet consists of 22 USB-attached SSD/NVMe devices and one native NVMe device at GR.

The portal compares counters from consecutive complete audits only when:

- both reports are at least five minutes apart;
- the root block-device identity is unchanged;
- uptime increases, proving no reboot reset the counter; and
- the write counter is monotonic.

It then reports actual bytes written during the sample and an extrapolated MiB/day
or GiB/day. Rates of at least 1 GiB/day produce an informational observation; rates
of at least 5 GiB/day produce a warning to correlate with package maintenance or
logging. These are operational write-rate signals, not SSD endurance estimates.

The authenticated evidence strip now retains up to 96 complete-audit points and
plots the five active optimization canaries. Missing, shorter-than-five-minute,
device-changed, counter-reset, and reboot-crossing samples render as gaps. This
prevents a reboot from appearing as zero writes or a false improvement. The API is
read-only and derives history from existing JSON reports rather than creating a new
database on the management server.

Package refresh and upgrade windows also render as gaps. The evaluator requires
the listed/eligible/deferred package signature to remain unchanged through every
intermediate audit and rejects any endpoint reporting a busy package manager. This
excludes AGC MR1's July 16 repository refresh and guarded tooling installation from
the quiet SSD-wear median instead of misattributing those maintenance writes to
the RAM/rsyslog policy.

Five consecutive valid quiet-window samples now show the same broad ordering:

| Window | Fleet median | AGC MR1 | GCMC MR2 |
| --- | ---: | ---: | ---: |
| 362 seconds | ~1.8 GiB/day | ~0.53 GiB/day | ~5.2 GiB/day |
| 568 seconds | ~1.65 GiB/day | ~0.40 GiB/day | ~6.78 GiB/day |
| 403 seconds | ~1.95 GiB/day | ~0.33 GiB/day | ~5.72 GiB/day |
| 679 seconds | ~1.72 GiB/day | ~0.39 GiB/day | ~5.61 GiB/day |
| 926 seconds | ~1.55 GiB/day | ~0.47 GiB/day | ~5.01 GiB/day |

AGC MR1, the first volatile-journal pilot, remains the lowest writer in every
sample. GCMC MR2 remains the highest. This is encouraging pilot evidence, not a
rollout decision: every window is short, includes normal audit activity, and must
still be confirmed across longer observation and a reboot. GCMC MR2 has no verified
fleet backup, so its write sources were inspected read-only and must not be changed
until backup coverage exists.

The latest direct size split confirms AGC MR1's active journal occupies 20 MiB in
`/run/log/journal`, below its 32 MiB cap. Its approximately 2.57 GiB
`/var/log/journal` tree is the deliberately retained historical archive and is not
the active journal target. The archive remains available for troubleshooting until
the reboot observation is complete; it should not be deleted merely to improve a
dashboard number.

AGC MR3 was selected as the second nearby pilot because it is backed up,
maintenance-ready, already reboot-verified as a headless canary, and was writing
about 2.9 GiB/day before the change. The serial play changed journald only; it did
not alter MR3's chrony-based time synchronization or other baseline settings.
After a controlled reboot, audit `audit_20260716_084126.json` proves
`Storage=volatile`, a 32 MiB runtime cap, an active sensor, five probes, the same
application hash, zero throttling, and inactive GDM. Its approximately 5.28 GB
historical journal archive remains on SSD but is no longer active. A longer
post-reboot counter window is still required before comparing write rates.

The first valid portal comparison after both journal-pilot reboots reports about
384 MiB/day on AGC MR1 and 513 MiB/day on AGC MR3. Both are well below the
approximately 1.06 GiB/day observed on nearby GMC EP1/EP2 with persistent
journald. These remain short operational samples rather than endurance forecasts,
but they support continued observation of the bounded volatile policy.

After the subsequent MR1 headless reboot, the longer common 839-second window
reports approximately 476 MiB/day on AGC MR1, 447 MiB/day on AGC MR3, and
350 MiB/day on GMC IR3. All three remain operationally healthy with bounded active
runtime journals under the 32 MiB cap. This is a longer consecutive-audit window,
not yet the multi-day evidence required for broad rollout; the 15-minute audit
timer will continue accumulating comparable samples without another mutation.

GMC EP3 rebooted after becoming the first CV headless canary, so its kernel write
counter correctly began a new observation epoch. The portal will not calculate a
rate until a later complete audit is at least five minutes after that boot.

Audit `audit_20260716_100428.json` supplies that first no-reboot comparison. EP3's
unsafe-shutdown counter stayed flat, confirming the one-count change belonged only
to the controlled reboot interval. Its first 516-second headless write rate is
approximately 2.55 GiB/day, versus approximately 2.12 GiB/day in the valid
778-second pre-headless window. The short post-boot sample is slightly higher, so
there is currently no evidence that headless mode reduced EP3 SSD writes. Its value
is reduced unused service/RAM/CPU overhead; journal policy remains the separate
write-reduction lever and no CV expansion should be justified from this sample.

AGC MR1's 09:00 scheduled camera workload then provided the missing functional
proof for RAM camera logs: all ten captures uploaded successfully, the job exited
zero, the backend exposed a fresh OCR result, and the three log files occupied
only about 15 KB under `/run/coolmri-camera-logs/agcmr1`. No failed session was
created and the durable retry directory remained on SSD.

AGC MR3 now uses the same camera-log design. Its 36.4 MiB historical directory
was retained on SSD, the failed-session queue remains durable, and only the live
`logs` link points to `/run/coolmri-camera-logs/agcmr3`. Controlled reboot
`reboot_20260716_131925.json` and audit `audit_20260716_131958.json` prove tmpfs
recreation, exact schedule preservation, canonical applications, active sensor,
five probes, zero throttling, and live telemetry. The 15:00 production capture is
still required before treating MR3's camera workload proof as complete. Its first
13:20 retry cron wrote only 139 bytes under tmpfs, found no failed sessions, and
preserved the durable retry queue. Five-minute audit
`audit_20260716_132544.json` reports a quiet interval of approximately 591 MiB/day,
zero unsafe-shutdown delta, and 692 bytes of live camera logs still confined to
tmpfs.

GMC IR3 extends the same journald policy to the separate CV profile. Before the
change, its persistent journal produced a portal rate of about 2.7 GiB/day. The
single-host transaction and reboot preserved the hardened `gmcir3` service user,
four physical/configured probes, canonical CV checksum, all mapped telemetry,
and zero throttling. Audit `audit_20260716_090805.json` proves the 32 MiB volatile
policy survived boot; a valid post-reboot write delta is intentionally pending.

GMC EP1/EP2 is the second CV-profile volatile-journal host after IR3 accumulated
nine valid post-change samples (median approximately 235 MiB/day, range 138–350).
The strengthened transaction required recent backup activity, idle packages,
canonical CV checksum, non-root site identity, five probes, zero throttle flags,
and five numeric mapped readings. Controlled reboot
`reboot_20260716_101556.json` and independent complete audit
`audit_20260716_101629.json` prove the 32 MiB policy, 8 MiB active runtime journal,
canonical application, five probes/readings, and healthy service after boot. Its
historical 973 MB journal directory is retained but inactive; write-rate evidence
starts only after the next valid no-reboot interval.

GMC EP3 was then selected as the third CV journal canary because it is nearby,
backed, already reboot-verified as a headless CV host, and remained the clear
write outlier: approximately 2.0 GiB/day since boot and 2.3 GiB/day in the latest
valid portal interval, versus roughly 0.3 GiB/day on IR3 and EP1/EP2. The
transactional playbook and rollback were extended with exact EP3 mappings:
canonical CV checksum, three probes, non-root helper, telemetry site `EP3`, and
numeric `helium_in`, `helium_out`, and `primary_in` readings.

Check mode passed before application. The live transaction preserved every gate,
and controlled report `reboot_20260716_123631.json` proves the 32 MiB volatile
policy survived boot with 8 MiB active runtime journal, canonical application,
three probes, zero throttling, active site-account service, and advancing mapped
telemetry. Independent target audit `audit_20260716_123642.json` and complete
audit `audit_20260716_123653.json` confirm the result. Complete five-minute
no-reboot audit `audit_20260716_124218.json` reports zero new unsafe shutdowns
and confirms the reboot interval is closed. Its historical 973 MB journal
directory is retained but inactive; the first short sample still contains heavy
post-boot filesystem activity, so savings must be judged from later quiet
no-reboot intervals rather than extrapolating that sample.

The next complete no-reboot samples, `audit_20260716_130259.json` and
`audit_20260716_130822.json`, reduced EP3's recent extrapolation to approximately
235–238 MiB/day from the pre-pilot 2.0–2.3 GiB/day observations, with zero
unsafe-shutdown delta. This is encouraging but still short same-day evidence;
retain the pilot until multi-day evidence exists.

## Rsyslog duplicate-write pilot

Synchronized 45-second samples on all five volatile-journal canaries showed that
`rsyslog.service` was still actively updating persistent `syslog`, `kern.log`, and
`auth.log` files even though journald itself was bounded in RAM. Payload growth was
small, but the same windows showed materially larger root-device write deltas, so
GMC IR3 was selected as the nearby, backed CV-profile canary.

`playbooks/rsyslog_ram_pilot.yml` is serial, requires an explicit one-host limit and
confirmation, and permits only the reviewed nearby IR3 and AGC MR1 profiles. It
records the exact active/enabled service state, confirms recent backup coverage,
package-manager idleness, writable boot storage, Wi-Fi above the nearby hard floor,
an idle camera, the exact profile checksum and site-account service, exact probes,
zero throttling, current and advancing mapped telemetry, and the effective 32 MiB
volatile-journal policy. Any failed gate restores rsyslog to its recorded state.
The matching rollback reads the same durable state file and restores only that
service state.

After application and the controlled reboot at 13:53 EDT, IR3 returned with
rsyslog inactive/disabled, journald active and bounded in RAM, the canonical CV
application unchanged, four probes, zero throttling, and live telemetry. The
guarded command's 30-second verifier timed out while Wi-Fi/Tailscale was returning;
independent audit `audit_20260716_135341.json` at 34 seconds uptime proved recovery.
The three retained historical log files remained byte-for-byte unchanged across
the extended observation. Five-minute audit `audit_20260716_135827.json` and
consecutive no-reboot audit `audit_20260716_135907.json` confirm the state and show
the adapter's reboot-only unsafe-shutdown counter stopped increasing afterward.
This was the first canary, not approval for a fleet-wide rollout by itself.

AGC MR1 became the second, cross-profile canary after IR3 accumulated repeated
low-write audits and stayed healthy through reboot. Check mode passed 18 gates with
`changed=0`, including its recent backup, -73 dBm nearby link above the -75 dBm hard
floor, writable boot partition, idle packages/camera, canonical MRI checksum,
site-account service, five probes, zero throttling, fresh telemetry, and bounded
volatile journald. The live transaction then stopped and disabled only rsyslog,
preserved its exact prior state for rollback, and verified unchanged application,
service/probes, mapped numeric readings, and advancing production telemetry.

Independent audit `audit_20260716_181928.json` confirmed the post-change state. In a
45-second quiet observation, `syslog`, `auth.log`, and `kern.log` retained identical
sizes and mtimes while the root device wrote only 466 sectors (about 233 KiB). The
sensor remained active with five probes and `Storage=volatile`/`RuntimeMaxUse=32M`.
This did not require a reboot. Longer no-reboot audit intervals remain the authority
for write-rate comparison; the short sample proves only that duplicate log files
stopped advancing.

Each successful pilot also publishes a sanitized marker containing only the
inventory name, profile, and application time. The exact pre-change service state
remains root-only on the Pi for rollback. Audit write-rate history treats the
public timestamp as a hard configuration boundary: an interval that starts before
the change is discarded, and the combined optimization observation clock restarts
at that timestamp. This prevents pre-pilot writes from being presented as
post-pilot savings when older audit files do not yet contain the marker.

## Multi-interval attribution — 2026-07-16

The portal now distinguishes a sustained writer from one extrapolated burst. It
uses up to four non-overlapping complete-audit intervals, each at least five
minutes with increasing uptime and monotonic same-device counters. At least three
samples and a median of 5 GiB/day are required for the sustained-high warning.

Complete audit `audit_20260716_152349.json` left exactly one sustained host:
the then-unbacked GCMC MR2 at a 6.3 GiB/day median across four 929–965 second intervals.
The same calculation reports approximately 443 MiB/day on AGC MR1, 489 MiB/day on
AGC MR3, and 109 MiB/day on rsyslog-RAM canary GMC IR3. This is materially stronger
than using the latest interval alone.

Read-only attribution on GCMC MR2 found persistent journald and active/enabled
rsyslog. Its 133.6 MiB journal contains fixed-size 16 MiB active system and user
files; the last hour had 917 records, led by 273 Tailscale reset notices and 252
sensor INFO readings. A continuous 150-second disk-counter sample wrote roughly
13 MiB in periodic bursts even after the SSH session settled, while logical
`syslog` growth was only a few kilobytes. This points to persistent journal block
updates/allocation plus duplicate rsyslog, not application file logging.

GCMC MR2 was initially left unchanged because it had no registered backup. It is
now onboarded to the encrypted backup hub, has a recent successful snapshot, and
has passed a real tmpfs restore test. It nevertheless remains unchanged while the
nearby volatile-journal canaries complete their strict 48-hour observation: GCMC
is a distant site and should not become the next experiment merely because backup
coverage has caught up. After that evidence is accepted, the existing
rollback-capable volatile-journal workflow can be extended with a current
one-host preflight. Reducing the fleet audit cadence would not address the
500-plus hourly sensor/Tailscale records, so the 15-minute health cadence remains
unchanged.

## Why this is better than copying programs to RAM

Linux already caches executable code and frequently read files in RAM. Moving the
whole application tree into tmpfs would complicate boot and recovery while hiding
configuration changes. The useful optimization is to reduce repeated writes:

- sensor application logs remain stdout/RAM-only;
- journald is bounded on five canaries: AGC MR1/MR3 and GMC IR3/EP1-EP2/EP3;
- duplicate rsyslog disk writes are disabled on the backed GMC IR3 and AGC MR1
  cross-profile canaries;
- configuration, offsets, retry state, and backup evidence remain durable; and
- measured write deltas determine whether further intervention is justified.

## SMART limitation and pilot

Representative checks on Crucial USB/NVMe, Samsung T7, SanDisk SATA/USB, and native
NVMe devices found neither `smartctl` nor `nvme-cli` installed. The portal therefore
labels media-health visibility unavailable instead of inferring drive health from
capacity or write counters.

When privileged maintenance resumes, install `smartmontools` on one nearby backed-up
GMC device first. Confirm that its RTL9210 bridge exposes valid JSON health data and
that queries do not reset or disconnect the USB storage device. Pilot native NVMe
health separately on GR only after backup/restore evidence. Do not install a package
fleet-wide merely to remove the portal finding.

The pilot completed serially across both profiles: the three backed nearby GMC CV
Pis plus backed nearby MRI MR1 and MR3. Two backed MRI waves then completed on
OSW MR1/MR2, SVI MR1/MR2, GBH, Shamokin, Muncy, Pittston Sola/Vida, GCMC Sola,
GSWB, and GWV, initially raising usable SMART visibility to 17 devices. A final
guarded wave covered Jersey Shore, GCMC MR2, VWM2, and VWM3 despite marginal
Wi-Fi where present, followed by AGC MR2 under the operator's explicit instruction
that its separate sensor-bus fault not block software work. This raises usable
SMART visibility to 22/23 reachable devices; GR alone remains held by its native
NVMe controller-reset and read-only-boot incident. It installs no
background SMART daemon,
exposes only a no-argument sanitized helper, and requires an explicit flag. The
all 22 devices returned valid health through their storage paths: SMART passed,
0% wear where the bridge exposed wear, zero media errors, no critical warnings,
and temperatures from 23–38 °C. The final five report 25–32 °C. Sensor services,
expected probes, application hashes,
throttle state, optimization pilots, and production telemetry remained healthy.
AGC MR2 retained its already-known 0/4 physical 1-Wire fault without regression.
Complete audit `audit_20260718_114526.json` proves 22/23 visibility, no eligible
packages or reboot requirements on the five new hosts, and no concerning SMART
result. Fresh post-change encrypted snapshots and exact tmpfs restore tests passed;
AGC MR2's newest snapshot is
`d4675e3e666b01701299aef33de513e2a0b098cfd4fe826759582757d3f46912`.
Post-query kernel-log inspection across AGC MR2, Jersey Shore, GCMC MR2, VWM2,
and VWM3 found zero USB disconnect/reset, NVMe reset/timeout, I/O, ext4/FAT, or
read-only-remount events. Consecutive SMART samples on the first four retained
unchanged unsafe-shutdown counters; AGC MR2 now has its first authoritative
baseline for the next recurring comparison.
The portal now shows temperature, wear, media errors, power-on hours, and the
cumulative unsafe-shutdown counter in each pilot device's storage detail.
GR's portal finding is now `smart_held`, not the obsolete generic pilot advice:
it explicitly requires onsite native-NVMe/power inspection and a stable writable
boot before installing the same tooling.
An explicit serial rollback is staged in `playbooks/storage_health_rollback.yml`;
it removes only the helper, its narrow sudo rule, and the pilot package.

Volatile-journal rollback uses `playbooks/volatile_journal_rollback.yml` with an
explicit one-host `--limit` and confirmation. It removes only the fleet drop-in,
then requires the profile sensor, exact probes, and advancing MRI/CV telemetry.
If verification fails, it restores the bounded volatile policy and proves the
sensor active rather than leaving an ambiguous half-rollback.

```sh
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/storage_health_pilot.yml --check --diff \
  --limit gmcep1and2 -e storage_health_pilot_confirm=true \
  --become-password-file /root/.config/coolmri/ansible-become-password
```

## Interpretation

A read-only attribution sample investigated GCMC MR2 after one portal interval
extrapolated to about 7.1 GiB/day. In 45 seconds, 8.0 of 8.3 MB of root writes came
from systemd-journald; no camera process appeared among writers. Only 291 journal
records totaling about 39 KB existed across the surrounding ten minutes, while
the active journal files expanded in multi-megabyte allocation chunks. This is
consistent with journal allocation/rotation amplified by audit and sudo/SSH
sessions, not a camera log storm. The host remains backup-blocked, so no logging
policy was changed; repeat quiet evidence after backup onboarding before treating
the extrapolation as sustained workload.

- A short spike during `apt` activity is expected; use a later quiet sample.
- A reboot resets the kernel counter, so that interval is intentionally omitted.
- Persistent multi-GiB/day idle writes warrant journal, swap, database, and retry-log
  investigation.
- SMART/NVMe critical warnings, media errors, or rapidly increasing wear would be a
  stronger replacement signal than write rate alone, once safely available.

## Maintenance-window correctness — 2026-07-17

The portal's short-term and multi-interval SSD calculations now consume the same
host-specific `update`, `baseline`, and `download` action windows as the 48-hour
optimization observer. Exact per-host start/finish timestamps are preferred;
older action reports receive a conservative 30-minute lookback. Any overlapping
interval is omitted, while older non-overlapping samples remain eligible. Package
state transitions, an active package manager, reboots, and rsyslog policy
boundaries continue to invalidate samples independently.

This corrected a visible false attribution after the authorized download-only
refresh. Jersey Shore, GR, and VWM2 had briefly appeared sustained-high because
their cache writes occurred entirely between audit endpoints while eligible
package counts stayed unchanged. After applying the recorded action windows, the
portal's sustained-high count fell from four to one; those three hosts lost only
the download-induced SSD warning. GCMC MR2 remains the single sustained-high host
at roughly 8.9 GiB/day median across four clean, non-overlapping intervals. It now
has verified backup/restore and camera RAM logging, but broader journald/rsyslog
expansion remains held behind the active 48-hour canary observation rather than
being changed from a maintenance-contaminated signal.

The read-only portal exposes this as a separate `Persistent journal to RAM`
maintenance lane. A host enters the lane only when it is online, still uses a
persistent journal with rsyslog active, and has a clean sustained-high write
trend. Release additionally requires a recent restore proof, maintenance
readiness, the completed 48-hour nearby optimization cohort, and—where a camera
is installed—a passing observation tied to that exact camera build. As of the
July 17 19:00 audit, GCMC MR2 is the only candidate and remains held for its
scheduled natural 10/10 camera RAM-log proof; no logging policy change is queued.

## GR SMART clearance — 2026-07-18

GR's storage hold cleared only after the boot-partition image, offline clean FAT
checks, full package update, controlled reboot, naturally writable boot mount,
zero current-boot NVMe/storage errors, and fresh decrypt/restore proof passed.
The same serial playbook then installed `smartmontools`, kept its daemon disabled
and stopped, and installed only the sanitized on-demand helper and narrow sudo
rule. The native NVMe reports SMART passed, 0% used, zero media errors, zero
critical warning, and 34 C. Complete audit `audit_20260718_125026.json` proves
usable non-concerning SMART visibility on all 23 reachable Pis; the explicit
rollback allowlist now includes GR.
