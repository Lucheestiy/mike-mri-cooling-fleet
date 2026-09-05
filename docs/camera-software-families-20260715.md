# Camera agent inventory and software families — 2026-07-15

## Result

The read-only fleet audit discovered 13 reachable camera agents. Seven were already
declared as `camera_edge` modules; six working legacy installations were present but
not represented in the intended configuration model:

- AGC MR2 and AGC MR3
- Jersey Shore MR and Muncy MR
- OSW MR1 and OSW MR2

Inventory now labels those six as `camera_management: observed_legacy`. This records
reality without adding the `camera_edge` module and therefore does not authorize a
broad playbook to overwrite their software. The original seven are labeled
`managed`; that label means role-declared, not yet proven identical or approved.

No Pi was changed. The audit reads only a fixed allowlist of non-secret camera
settings. URL user information and query strings are removed defensively. Unknown
environment keys are never collected.

## Exact build fingerprints

The audit hashes the capture, retry, wrapper, and optional cleanup/pruning files and
then hashes the ordered manifest. The full SHA-256 values remain in
`reports/audit_20260715_233536.json`; prefixes below are for operator recognition.

| Host | Management | Fingerprint | Scheduled jobs |
| --- | --- | --- | ---: |
| AGC MR1 | managed | `c1e83687b2c3` | 3 |
| AGC MR2 | observed legacy | `bab0970ca533` | 3 |
| AGC MR3 | observed legacy | `2211adf62673` | 3 |
| OSW MR1 | observed legacy | `698df408e98d` | 4 |
| OSW MR2 | observed legacy | `f88e09748f3e` | 4 |
| SVI MR2 | managed | `2a35106d5196` | 3 |
| Muncy MR | observed legacy | `bfec0207f575` | 4 |
| Jersey Shore MR | observed legacy | `501f2a5df8d4` | 4 |
| Pittston Sola | managed | `9ae4a544f96b` | 3 |
| Pittston Vida | managed | `9ae4a544f96b` | 3 |
| GCMC Sola | managed | `b22bc2fdba09` | 3 |
| GCMC MR2 | managed | `94f52ec70f2c` | 3 |
| GSWB Sola | managed | `9ae4a544f96b` | 3 |

There are 11 exact fingerprints. Only Pittston Sola, Pittston Vida, and GSWB Sola
share an exact core manifest. A different fingerprint does not by itself prove a
fault: wrappers contain site-specific behavior and several hosts intentionally use
different camera settings. It does prove that a blind replacement would erase
real differences.

The recovered source packaged in `roles/camera_edge/files/edge` is not an approved
baseline: function-level AST comparison found no live agent matching its complete
main program. The general site playbook therefore skips camera deployment unless
`camera_edge_deploy_approved: true` is supplied for a reviewed pilot. This prevents
sensor standardization work from silently replacing working camera behavior.

That recovered runtime has now been replaced locally by canonical candidate v3.0.0.
It ships only four runtime files, bounds debug images and retry records, writes
retry state as atomic JSON, uses a single server-OCR API contract, avoids duplicate
cron logging, and preserves crop/exposure/upload mode as inventory settings. It is
still deployment-gated. On 2026-07-15 at 23:49 EDT, an upload-disabled AGC MR3
hardware canary captured one image in approximately one second with the existing
1000 µs / 0.5 gain settings. It wrote only a 268-byte log under `/dev/shm`, uploaded
nothing, cleaned its RAM workspace, and left all production camera hashes unchanged.
The guarded procedure is `playbooks/camera_v3_canary.yml`.

The explicit per-host preservation and decision map is
`inventory/camera_convergence.yml`. Backup is now verified for AGC MR2 and GCMC
MR2. AGC MR2 retains a hard contract block because it runs a distinct local-OCR
agent. GCMC MR2's production API review later cleared its payload block while
retaining distinct optics; details appear below. OSW MR1's misleading disabled
flag was subsequently resolved from production-delivery evidence; details appear
below.

The static configuration-usage audit also found declared upload settings ignored
on SVI MR2, Pittston Sola, Pittston Vida, GCMC Sola, GCMC MR2, and GSWB Sola. In
those cases the live code follows a fixed cropped-image path even where inventory
declares `full_and_crop`. The portal now reports these mismatches instead of
presenting the `.env` value as effective behavior.

## Server-side delivery evidence

The portal now reads the camera backend's image-free recent-feed endpoint and maps
schedule IDs back to base sites. It shows the last upload age, source, and OCR status
for each camera without transferring stored images. A host warns after 36 hours and
becomes critical after 72 hours; a backend query failure is reported separately so
it cannot masquerade as 13 individual camera failures.

At 2026-07-16 00:02 EDT, all 13 camera agents had a matched tenth capture from the
2026-07-15 afternoon schedule. Upload ages were 8.5–9.0 hours, with zero stale or
missing camera sites. This also confirms that several programs whose `.env` upload
settings are ignored are currently delivering images despite the misleading local
declaration.

An additional upload-disabled AGC MR3 capture was streamed from RAM directly into
the production OCR processor without using HTTP or writing the database. The
decoder accepted the JPEG and completed in 15 ms; it returned no characters because
the midnight scanner display was effectively black (brightness 0, p95 1). The RAM
image and log were then deleted and production camera hashes remained unchanged.

## Schedule and configuration differences

All agents capture twice daily and retry failed sessions every five minutes, but
the start minutes are staggered. The standard role-declared pattern is 09:00 and
15:00. Observed legacy capture minutes are:

- AGC MR2 at :05, with numeric argument `10` passed to each capture wrapper
- AGC MR3 at :00
- OSW MR1 at :15, plus a 02:10 cleanup job
- OSW MR2 at :20 via `/etc/cron.d`, plus a 02:10 prune job
- Muncy MR at :25, plus a 01:30 cleanup job
- Jersey Shore MR at :30, plus a 04:10 failed-session prune job

Notable safe-setting differences include cropped-only upload at Jersey Shore and
Muncy, upload explicitly disabled at OSW MR1, and sparse older `.env` files at AGC
MR2, AGC MR3, and OSW MR2. An unset key means the program default controls behavior;
it must not be treated as equivalent to an explicit value during convergence.

Ten camera agents currently keep camera logs on persistent storage. AGC MR1 and
AGC MR3 were the initial bounded RAM-log pilots: their active `logs` paths resolve to
site-specific directories under `/run/coolmri-camera-logs` on tmpfs. On MR1,
the active path is
`/run/coolmri-camera-logs/agcmr1` on tmpfs, while the 38.6 MiB historical archive
and failed-session retry state remain durable on SSD. The role snapshots and
restores the exact pre-transition crontab rather than replacing legacy entries.
`reboot_20260716_073147.json` proves the tmpfiles path survived a controlled reboot,
the original three schedules returned unchanged, all five temperature probes and
the sensor service recovered, application hashes were preserved, and production
telemetry advanced.

The strengthened MR3 expansion added package-idle, exact application-hash,
service, five-probe, zero-throttle, and advancing-telemetry gates to the playbook
itself. The live transaction preserved the exact three-entry crontab, renamed the
36.4 MiB historical directory once, retained failed-session state on SSD, and
linked only disposable logs to `/run/coolmri-camera-logs/agcmr3`. Controlled
report `reboot_20260716_131925.json` and independent audit
`audit_20260716_131958.json` prove the tmpfiles path, headless target, volatile
journal, canonical sensor/camera hashes, five probes, and telemetry survived boot.
The 13:20 retry cron then wrote only 139 bytes to the tmpfs retry log, found no
failed sessions, and left the durable retry directory and exact crontab intact.
Five-minute no-reboot audit `audit_20260716_132544.json` clears the reboot-only
unsafe-shutdown delta and confirms 692 bytes of accumulated tmpfs camera logs,
durable retry state, and all production health gates.

The first guarded expansion beyond the nearby pilots completed on GCMC MR2 on
2026-07-17. `playbooks/camera_ram_logs_wave.yml` is restricted to one explicitly
selected user-crontab host and requires a current backup plus decrypt/restore,
exact configured-versus-physical probes, active sensor service, zero throttling,
at least 256 MiB available RAM, idle package and camera processes, an exact saved
schedule, protected sensor/camera hashes, and current telemetry. It automatically
restores persistent logs if any post-transition assertion fails and never reboots
or restarts the sensor.

GCMC MR2 passed check mode and the confirmed transaction. Its 609,102-byte
historical log directory was preserved on SSD, while the live path now resolves
to `/run/coolmri-camera-logs/gcmc2` on tmpfs with bounded rotation. Independent
complete audit `audit_20260717_180155.json` proves five probes, active service,
unchanged camera fingerprint and retry state, only 346 bytes in the new RAM log,
and current telemetry. A new encrypted snapshot was then created and exact
snapshot `d3779860418d8e1b79c2baa42b228884d4120474a3329d8e8da71c067248437f`
was decrypted and restore-tested successfully in tmpfs. The live portal now
reports three RAM-backed camera log agents. OSW MR2 remains outside this wave
until the GCMC proof because its camera schedule is in `/etc/cron.d`. The role
now has a separately reviewed `cron_service_watchdog` strategy: it records the
root-owned file's exact SHA-256, mode, owner, and group; arms a two-minute
automatic cron-resume unit; pauses cron without editing the schedule; restores
cron immediately; disarms the watchdog; and proves the file metadata and digest
are unchanged. A check-mode-only OSW MR2 rehearsal passed this exact live
contract without changing the Pi.
Read-only controller timers are armed for 08:55 and 09:03 EDT on 2026-07-18
around GCMC MR2's unchanged 09:00 schedule. They expect its established
`camera_ocr` source and ten ordinals and cannot trigger a capture or replay.
The shared observation verifier now makes its journald contract explicit. MR1/MR3
retain the default `volatile` requirement; GCMC MR2 uses `preserve`, which records
its intentionally persistent journald state and requires that exact state after
the session. This prevents the camera-RAM proof from failing merely because the
separate journald wave has not begun, without weakening either proof. Both modes
also require the physical 1-Wire IDs to equal every configured profile probe ID;
a partial bus can no longer establish a baseline. A live controller-only baseline
rehearsal passed persistent-state preservation, all five exact GCMC MR2 probes,
current telemetry, RAM camera logs, durable retry state, zero failed sessions,
the current camera fingerprint and exact schedule.
The live portal has a separate **Camera logs to RAM** maintenance lane. It
currently holds the eight remaining approved user-crontab candidates and the
prepared OSW MR2 watchdog candidate behind that natural proof, and ties GMC MR2
to recovery of its older four-probe bus.
Once the reference proof matches the exact audited GCMC MR2 camera build, only
hosts with current maintenance and restore gates can enter the ready queue.
The 15:00 scheduled production capture subsequently passed the machine-verifiable
observation in `camera_observation_20260716_150304.json`: one new session contained
exactly ordinals 01–10, all ten uploads reached the backend, RAM log activity
advanced, the retry queue stayed empty and durable, and the sensor application,
five probes, schedule, uptime, throttle state, and telemetry were preserved.

The observation is now machine-verifiable rather than inferred from a single
latest-upload row. `scripts/camera_schedule_observation.py` records a pre-schedule
audit and live sensor-telemetry baseline, then requires one new backend session
containing exactly ordinals 01–10. It also proves no reboot, unchanged sensor and
camera hashes, exact probes and schedules, zero throttling, advancing MRI telemetry,
durable retry state, zero failed sessions, and increasing camera-log activity under
the same `/run` target. The portal reads only passing verification reports and shows
their session/count in the host detail.

For this observation, a one-shot local systemd timer runs the read-only completion
wrapper at 15:03 EDT. `scripts/complete_camera_observation.sh` reads the root-only
fleet credential file without printing it, audits only the baseline host, and feeds
that new audit to the verifier. It performs no update, service restart, or reboot.

## Safe convergence order

1. Continue quiet-write observation on both reboot-verified AGC RAM-log pilots;
   MR1 and MR3 have each passed a 10/10 production capture with logs in RAM.
   MR3 additionally has the newer baseline-to-session machine-verifiable proof;
MR1's earlier proof is an operational capture plus complete post-capture audit.

AGC MR1 passed the same stronger proof on its natural 09:00 EDT legacy-agent
schedule on 2026-07-17: exactly ten ordered uploads reached the backend while
sensor telemetry, five probes, schedules, RAM logs, retry state, and uptime were
preserved. Controller-only one-shot timers are now re-armed around the natural
09:00 schedule on 2026-07-18 to prove the newly installed v3 agent in production.
They take a fresh read-only baseline at 08:55 and run verification at 09:03. Both timers are deliberately
non-persistent: if the controller misses either window, they do not replay late
against an already-started capture. The completion wrapper also rejects baselines
outside the intended 30-minute window. Neither timer invokes camera software,
restarts a Pi, or creates an extra upload session.
2. Define one approved camera core while preserving per-host site, crop, exposure,
   upload, stagger, and retention settings.
3. Compare semantic diffs, not hashes alone, beginning with nearby backed-up AGC
   MR3. AGC MR2 remains blocked by its special local-OCR contract, not backup.
4. Add `camera_edge` management to an observed legacy host only after its settings
   are represented explicitly and a restore path is verified.
5. Roll out in small backed-up waves with a post-capture server-side image check.

## Staged nearby AGC production v3 pilot

`playbooks/camera_v3_production_pilot.yml` is the production convergence
transaction. It is limited to explicit reviewed profiles for nearby AGC MR1 and
MR3, preserving each host's site ID, upload mode, debug behavior, current hashes,
and rollback modes. It will not replace a working runtime until the backup hub
records a recent successful production restore for that exact repository.

After the restore gate exists, the playbook additionally requires a recent backup,
idle package manager, writable boot partition, nearby Wi-Fi above the hard floor,
active sensor service, all five probes, zero throttle flags, an empty camera retry
queue, RAM-backed logs, current telemetry, and the exact reviewed legacy hashes and
three-job crontab. It stages only the four reviewed v3 runtime files and `.env` in
tmpfs, validates fixed candidate hashes, and replaces them while holding the same
camera lock used by production.

The immediate smoke capture forces uploads off and uses a disposable tmpfs
workspace. Success requires one captured image and zero uploads, unchanged cron,
exact installed v3 hashes, healthy sensors/probes/telemetry, RAM logs, and no retry
records. Any failure after replacement restores the byte-exact legacy files and
environment under the camera lock. Production approval still requires the next
scheduled 10/10 backend observation; a successful smoke test alone does not grant
fleet rollout.

```sh
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/camera_v3_production_pilot.yml --check --diff \
  -e camera_v3_production_target=agcmr1

.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/camera_v3_production_pilot.yml \
  -e camera_v3_production_target=agcmr1 \
  -e camera_v3_production_confirm=true
```

## Secondary v3 hardware canaries

`playbooks/camera_v3_candidate_canary.yml` prepares the next camera-family
stage without changing an installed camera agent. It accepts only an explicit
host whose convergence status begins `eligible_after_primary_pilot`, and takes
that host's reviewed upload mode, crop, shutter, and gain directly from
`inventory/camera_convergence.yml`. The inventory also records the separate
sensor API identity and backup repository identity needed by legacy sites such
as Muncy, Jersey Shore, OSW MR2, and the hyphenated backup repositories.

The playbook refuses to reach the hardware test until both nearby primaries have
a natural, successful 10/10 `camera_edge_v3` production observation. It then
requires a current backup, a recent exact decrypt/restore, active sensor
service, byte-exact agreement between every configured probe ID and the
physical 1-Wire bus, zero throttle flags, current sensor telemetry, and an idle
camera. One capture runs from canonical source with uploads forced off and all
temporary image, log, retry, and lock state in `/dev/shm`. It never reboots or
restarts the sensor. Success additionally requires zero uploads, unchanged
production camera hashes, exact probes and active service after capture, and a
newer sensor telemetry timestamp. Only after every assertion passes does it
atomically write `camera_v3_candidate_canary_<host>_<time>.json` on the
controller. The portal accepts that proof only when its v3 source hash and
reviewed target contract still match, all non-mutation and health fields pass,
and the four audited production runtime hashes remain exactly what the canary
tested. A stale or edited runtime therefore cannot inherit an older pass.

```sh
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/camera_v3_candidate_canary.yml --check \
  -e camera_v3_candidate_target=oswmr1

.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/camera_v3_candidate_canary.yml \
  -e camera_v3_candidate_target=oswmr1 \
  -e camera_v3_candidate_confirm=true
```

The check is expected to remain stopped at the primary-proof gate until GMC MR1
completes its armed natural observation. A passing secondary canary authorizes
review of that host's production transaction; it does not itself install v3.

## Secondary v3 production transaction

`playbooks/camera_v3_candidate_production.yml` closes the gap between a passing
secondary hardware canary and upload-enabled v3 without treating either as a
natural production proof. It accepts only an `eligible_after_primary_pilot`
host and requires that host's atomic canary report to match the current reviewed
target, canonical source hash, zero-upload capture, non-reboot/non-restart
safety assertions, and exact four-file legacy production hash list. A fresh
backup and decrypt/restore, exact probes, active sensor, zero throttling, empty
retry backlog, current telemetry, and idle package manager remain mandatory.

The transaction stages canonical v3, the reviewed per-host environment, and
byte-exact legacy runtime/environment rollback data in tmpfs. Immediately before
replacement it arms a ten-minute automatic cron-resume watchdog, pauses cron,
and waits for camera work to finish. Replacement uses the production camera
lock. The installed smoke capture is wholly in tmpfs with uploads forcibly off;
success requires one capture, zero uploads, exact canonical hashes, the entire
user/cron.d schedule contract unchanged, exact probes, active service, empty
retry state, zero throttle flags, and newer sensor telemetry. Cron is always
resumed and the watchdog disarmed. Any post-replacement failure restores the
legacy runtime and environment and verifies both hashes and environment bytes
before stopping.

Only a fully successful transaction writes an atomic
`camera_v3_candidate_deployment_<host>_<time>.json`. The portal accepts it only
while all four installed hashes and the reviewed contract still match, and
shows **v3 installed — natural proof pending**. The host does not become
`v3_production_verified` until the normal scheduled 10/10 backend observation
matches that exact installed build. Check mode currently stops at the missing
secondary canary, before contacting a Pi, as intended.

## AGC MR3 v3 production-smoke result — 2026-07-16

After backup and restore proof became authoritative, check mode passed every
gate and the explicitly confirmed transaction installed camera agent v3.0.0 on
nearby AGC MR3. The playbook captured one real image with uploads forcibly off,
proved zero uploads, exact candidate hashes, the unchanged three-job crontab,
empty durable retry state, RAM-backed logs, all five temperature probes, zero
throttling, and advancing MRI telemetry. Post-deployment target audit
`audit_20260716_225307.json` reports v3.0.0 and the expected cropped-only AGC MR3
settings. Complete fleet audit `audit_20260716_232156.json` independently
confirms the managed inventory state, exact v3 hashes, all typed environment
settings in use, five probes, RAM-backed logs, unchanged schedules, and an empty
retry queue.

Controller-only non-persistent timers are armed for 08:55 and 09:03 EDT on
2026-07-17 around the existing 09:00 schedule. They take read-only audits and
verify a natural 10/10 backend session; they cannot invoke a camera capture or
replay after the guarded time window.

The natural v3 session itself succeeded, but the first controller verification
incorrectly required the legacy `camera_ocr` record source and therefore marked
the otherwise complete `camera_edge_v3` session as failed. The verifier now binds
the expected source into each pre-schedule baseline instead of assuming one
software family. Regression coverage proves that it accepts the declared v3
source and still rejects a different source. Corrected verification
`camera_observation_20260717_164454.json`, linked to the original passing baseline,
proves the later natural 15:00 session `AGCMR3_SCHED_20260717T190001Z`: 10/10
ordered `camera_edge_v3` records, unchanged v3 hashes and schedules, RAM-backed
logs and temporary capture storage, durable empty retry state, all five probes,
active and advancing sensor telemetry, no reboot, and zero throttling. The portal
now labels AGC MR3 `v3_production_verified`.

## AGC MR1 v3 production-smoke result — 2026-07-17

After MR1's 10/10 legacy-agent natural delivery proof and the complete 24-target
backup/restore sweep, both check mode and the confirmed transaction passed every
production gate. Camera agent v3.0.0 was installed with the same reviewed core as
MR3 while preserving MR1's `AGCMR1`, `full_and_crop`, debug-image, crop, exposure,
ten-capture, and three-job schedule contract. Its upload-disabled smoke captured
one image and uploaded zero, and the post-change checks proved exact v3 hashes,
five probes, active and advancing sensor telemetry, zero throttling, RAM-backed
logs, an empty retry queue, and unchanged cron. Independent target audit
`audit_20260717_152843.json` and complete audit `audit_20260717_153108.json`
confirm the result. The read-only 2026-07-18 observation remains required before
MR1 v3 receives natural 10/10 production-delivery approval. Its installed
controller baseline unit explicitly requires `camera_edge_v3`, so the MR3
verifier defect cannot create the same false failure tomorrow.

### MR1 exposure-contract correction — 2026-07-17

A post-deployment contract comparison found that the two-host production pilot
had correctly preserved MR1's site ID, `full_and_crop` upload mode, debug-image
behavior, crop, count, and schedules, but its generated environment hard-coded
MR3's 1000 µs / 0.5 exposure for both profiles. MR1's reviewed inventory and the
legacy program defaults require 1500 µs / 2.5. The pilot is now profile-driven
for both shutter and gain, with regression assertions for MR1 and MR3; MR1's
expected-current hashes and modes also describe the installed v3 build so the
rollback-capable transaction can safely revalidate it.

Check mode passed all backup, restore, Wi-Fi, boot, process, exact-hash, schedule,
probe, service, RAM-log, retry, throttle, and telemetry gates. The confirmed
transaction restored only the intended environment contract while reinstalling
the same byte-exact v3 core under its camera lock. Its upload-disabled smoke
captured one image and produced zero `AGCMR1-SMOKE` backend records. Target audit
`audit_20260717_165940.json` and complete audit `audit_20260717_170048.json` prove
v3.0.0, 1500 µs / 2.5, `full_and_crop`, the exact crop and debug settings, the
unchanged three-job cron, five probes, active sensor service, RAM-backed logs,
empty durable retry state, and zero throttling. Tomorrow's natural proof is still
required and now observes the correct MR1 exposure contract.

### GCMC MR2 payload and optics review — 2026-07-17

Read-only AST extraction from the installed capture agent proves its production
path uploads cropped-only JPEG data to `/api/camera/pressure` with server-side OCR.
The running backend's `PressurePayload` schema accepts the v3 fields, including a
null pressure/confidence pair, and the ingestion service explicitly uses that pair
to trigger OCR. A schema-only in-container construction passed without making an
HTTP request or creating a database record. The legacy `metadata` object is not a
persisted API field and is not required by ingestion, filtering, or forwarding.

The host remains optically distinct: its live program reads
`CAMERA_SHUTTER_US=2500` and `CAMERA_GAIN=1.0`, and its crop is exactly
`{"x":760,"y":600,"w":320,"h":180}` rather than the common
`708,520,364,182` rectangle. The convergence map now records all five values
explicitly and changes the host from payload-review-blocked to
`eligible_after_primary_pilot_distinct_optics`. This is eligibility only: do not
deploy until MR1's natural v3 proof passes, then require a fresh restore gate and
an upload-disabled hardware smoke that proves the distinct crop and exposure.
The production transaction now renders crop JSON from the selected host profile
for both the installed environment and upload-disabled smoke; MR1 and MR3 check
mode both pass after this change. A future GCMC MR2 profile therefore cannot
silently inherit the common crop through a hard-coded deployment value.
The portal camera lane now models the same sequence: completed v3 hosts disappear
from its action queue, eligible hosts remain held until both AGC natural proofs
exist, and only then can a backed, maintenance-ready host enter the ready queue
for an upload-disabled hardware canary. A hardware canary is still not treated as
upload-enabled production approval.
All 12 hosts with a convergence target now carry an explicit upload mode,
shutter, gain, debug-image policy, and bounded crop rectangle. A direct comparison
against complete audit `audit_20260717_172259.json` verifies every recorded crop
and debug setting matches the live host; AGC MR2 remains targetless because its
local-OCR contract is intentionally blocked rather than guessed.

### OSW MR1 observed-upload decision — 2026-07-17

The legacy `.env` declares `UPLOAD_ENABLED=false`, but static analysis proves the
installed program does not read that key and always calls its cropped-only upload
path. The production backend independently contains 80 `camera_ocr` records from
eight complete OSW MR1 scheduled sessions in the reviewed seven-day window; the
latest is ordinal 10 from the 2026-07-17 15:15 session. Preserving uploads is
therefore preservation of established production behavior and of the fleet's
data-delivery purpose, not activation of a dormant feature.

The convergence target now explicitly sets uploads true and cropped-only, while
retaining 1500 µs / 2.5, the common 708,520,364,182 crop, the staggered 09:15 and
15:15 schedules, and debug images off. OSW MR1 is eligible only after both primary
v3 proofs; it still requires current backup/restore and an upload-disabled
hardware canary before any production replacement.

### OSW secondary staging — 2026-07-18

OSW MR1 passed its upload-disabled hardware canary and guarded production-smoke
transaction with byte-exact rollback staged; its natural 15:15 ten-upload proof
remains the promotion gate. The controller planner runs every minute, will capture
the read-only baseline between 15:10 and 15:15 EDT, and will verify the natural
session after 15:18.

OSW MR2 was selected as the next standard-contract candidate, but not deployed.
Its independent rehearsal and RAM-only hardware canary passed with one capture,
zero uploads, unchanged production hashes, exact five probes, an active sensor,
zero throttling, no sensor restart or reboot, and telemetry advancing by 71
seconds. Evidence is
`camera_v3_candidate_canary_oswmr2_20260718T152646Z.json`; the canary used its
reviewed cropped-only, 1500 µs / 2.5, 708,520,364,182 contract and current exact
restore snapshot
`9c8a44b8362688b90d1f2233ceec18d88389a828b7a0be7e03f9984658ff6fcf`.

The production playbook now enforces the sequencing rule itself: every later
secondary must find a successful OSW MR1 `camera_edge_v3` natural observation
with exactly ten records. A live OSW MR2 check-mode attempt stopped at that gate
with zero remote changes, proving production cannot proceed early even if an
operator selects the host.

The portal maintenance queue now applies the same distinction. Reviewed hosts
without a canary may still enter the safe upload-disabled hardware-canary queue,
but OSW MR2's completed canary is held from production with the explicit OSW MR1
natural-proof reason. Once the exact current OSW MR1 build becomes
`v3_production_verified`, the same queue automatically releases OSW MR2 if its
backup, restore, and maintenance gates remain current.

OSW MR1's central host inventory now also records `camera_management: managed`.
Complete audit `audit_20260718_113122.json` removed the stale `camera_legacy`
recommendation while retaining the accurate pending-natural-proof state and the
scheduled-observation recommendation.

### Secondary upload-disabled canary wave — 2026-07-18

The remaining eight portal-eligible secondary hosts passed all preflight gates in
parallel: GCMC, GCMC MR2, GSWB, Jersey Shore, Muncy, Pittston Sola, Pittston Vida,
and SVI MR2. Each then ran the canonical v3 capture program from standard input,
used only a private `/dev/shm` workspace, captured one image with its reviewed
site-specific optics, uploaded zero, removed its RAM workspace and lock, and
proved production hashes, exact probes, sensor service, throttle state, and
telemetry health were unchanged.

The first verifier attempt exposed a controller-side timing defect: four retries
did not cover the sensor programs' five-sample averaging interval. No host or
production check failed, but evidence was correctly withheld. The verifier now
allows twelve ten-second attempts, with a regression test pinning that full
publish window. The repeated isolated captures then passed and produced the eight
`camera_v3_candidate_canary_*_20260718T1610*.json` reports. The portal now reports
nine passed secondary hardware canaries and holds every one behind OSW MR1's
exact-build natural 10/10 proof; no upload-enabled deployment was released.
