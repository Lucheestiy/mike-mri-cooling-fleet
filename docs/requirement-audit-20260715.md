# Fleet requirement audit — 2026-07-15

This record checks the requested end state against the authoritative complete
snapshot `audit_20260716_224912.json`, the live portal API, backup coverage collected
on July 16, and the controlled package/reboot action reports.

| Requested outcome | Current evidence | Status |
| --- | --- | --- |
| One manageable fleet | All 27 devices are inventoried; 23 are reachable by fleet key; a 15-minute timer refreshes the complete audit | working, four offline exceptions |
| Similar sensor software | 22/23 reachable devices use their approved profile family; all three CV devices share the flexible 3–5-probe program, while MRI and CV remain intentionally separate profiles. The active service virtual environments are directly assessed: 23/23 have compatible Python runtimes and all three required direct dependencies | substantially converged; only weak-link VWM2 remains, zero dependency gaps |
| Shared operational stack | Fresh read-only evidence assesses all 23 reachable Pis: all are arm64 with synchronized America/New_York clocks, active cron/Tailscale, and all 13 required operational packages. The portal's version-aware ledger reports 13/13 complete and separately marks eight packages with same-OS version spread, including exact contributing hosts. Tailscale channel inventory now reports 21 official-stable and two distribution-channel installations; spread remains review evidence and does not bypass update gates | achieved for required presence; two explicitly held channel exceptions remain visible |
| Shared operational controls | 23/23 reachable devices have the same readable, checksum-verified status helper; all three CV devices and all 20 reachable MRI devices have profile-specific restricted service control and bounded logs. The no-echo privilege wrapper is checksum-identical, executable, and successfully privilege-tested on all 23 reachable devices | achieved on reachable fleet |
| Runtime policy | Strict profile timing/logging/recovery targets match 21/23 reachable Pis. SVI MR2 is separately identified as one exact approved 120/30-second recovery exception rather than generic drift; only VWM2's legacy MRI program remains an actual deviation | working, one weak-link convergence hold remains |
| Least-privilege sensor identity | All 20 reachable MRI services and all three CV services use their site accounts; the CV units have reboot-verified systemd hardening | achieved on reachable fleet |
| Package maintenance | Nearby CV and backed MRI pilots updated/rebooted and recovered; GCMC MR2 and AGC MR2 most recently installed 47 and 42 packages and promoted 1021 kernels with exact recovery proof. Audits and the portal separate listed, eligible, and deferred packages, and mutations enforce backup, probes, sensor health, telemetry, routed Wi-Fi, A/B promotion, and 30-second stability. The current queue is 366 eligible packages on Jersey Shore, GR, and VWM2 plus eight deferred packages | working, Wi-Fi/storage-gated exceptions remain |
| OS convergence | Three CV devices run Ubuntu 26.04; 18 run 25.10; GR runs 24.04 LTS; Shamokin runs 25.04 | pilot stage, not converged |
| Reduce SSD writes | Sensor applications use RAM/stdout-only logging; AGC MR1, AGC MR3, GMC IR3, GMC EP1/EP2, and GMC EP3 have reboot-verified 32 MiB volatile journals. MR1 and MR3 have reboot-verified camera logs on tmpfs with durable retry state and have both passed scheduled production captures; MR3 additionally has the newer baseline-to-session machine-verifiable proof, while MR1 has its operational capture and complete post-capture audit. Duplicate persistent rsyslog writes are disabled on cross-profile canaries GMC IR3 and AGC MR1 while bounded journald remains active in RAM. Sanitized application-time markers prevent the portal from mixing pre-change and post-change write intervals. All reachable roots expose model and consecutive-audit write counters | working, five journal, two camera-log, and two rsyslog-RAM canaries; longer observation remains |
| Headless service optimization | Nearby AGC MR3, AGC MR1, and CV-profile GMC EP3/IR3 boot to `multi-user.target` with unused desktop/printing/Bluetooth/modem/color services stopped; all four are reboot-verified with profile-specific sensor workloads preserved | working, four nearby canaries verified |
| Central fleet website | `https://pi.coolmri.com` is deployed, authenticated, healthy, and read-only. Public DNS is Cloudflare-proxied, TLS covers `*.coolmri.com`, unauthenticated root returns 401, and `/healthz` returns 200. Every response carries CSP/HSTS/no-store/anti-framing/privacy headers and the UI has no third-party font dependency. Its evidence strip uses up to 96 complete audits for availability and gap-aware canary write traces; its Probe Map and 1-Wire GPIO scores expose configured/physical sensor equality plus boot-overlay/reported-pin/live-line agreement. Device details now expose sanitized latest verified update/reboot evidence for 17 hosts while omitting all raw command output | achieved |
| Health/settings/offsets/pins | Portal exposes these fields for all reachable devices; all 23 have exact equality between configured and physical probe IDs, 23/23 have valid calibration mappings, and 23/23 have aligned 1-Wire GPIO evidence. Live backend temperatures are normalized without conflating profiles: MRI keeps helium/primary names and deltas, while CV uses Sensor 1–5 according to each configured probe count. Freshness, required-channel completeness, and alarms are explicit maintenance gates. Nineteen hosts have explicit offsets for every probe; GMC EP1/EP2, EP3, IR3, and SVI MR1 have no stale IDs and use the supported 0° default. The assessment understands the default GPIO4 overlay and preserves GR's intentional explicit GPIO17 exception. Seventeen backed MRI/CV devices expose sanitized SMART health | achieved on reachable fleet |
| Backup visibility | 24/24 configured repositories have authoritative successful-snapshot markers; all four prepared targets are onboarded. The root-only verifier is installed and authorized, and six recent production restore proofs cover MRI, CV, and all three newly added repositories | achieved for configured/reachable fleet |
| Recommendations | Every device has contextual recommendations for offline state, Wi-Fi, OS, eligible/deferred updates, Tailscale channel, reboot, service, GPIO alignment, storage, backup, and logging. Wi-Fi grading follows the default-route interface so secondary onboard radios do not override working USB adapters. The Tailscale lane holds AGC MR1 through its camera proof and Jersey Shore until routed Wi-Fi improves. The live summary currently reports ten field priorities, two critical and three marginal routed Wi-Fi links, plus four offline devices and GR's storage/boot incident. GLH includes its last known Tailscale IP and WLAN MAC; offline rows include controller-observed last-seen dates and on-site recovery actions | achieved |

The scheduled collector now uses a 60-second read-only fact window and a
three-minute service ceiling. Two consecutive 25-second runs had timed out only on
GR even though immediate 45-second target audit `audit_20260716_185559.json`
returned healthy sensor/storage facts. After the controller-only adjustment,
complete audits `audit_20260716_185748.json` and `audit_20260716_190042.json`
returned all 23 reachable hosts; GR's known four NVMe resets and read-only boot
hold were unchanged. No Pi setting was altered by this collection fix.

## Evidence-backed remaining work

- Recover PHC, PHMV, VWM1, and GLH, then audit them before any mutation. Direct
  Tailscale-layer and port-22 probes return no path. Controller evidence last saw
  PHC on 2025-08-05, PHMV on 2026-03-06, GLH on 2026-06-17, and VWM1 on
  2026-07-15; VWM1 is the newest likely site power/network incident.
- Continue backed-up package maintenance serially. Jersey Shore and VWM2 remain
  held by routed Wi-Fi, while GR remains held by its boot-storage condition.
- Schedule the restore-gated AGC MR3 Ubuntu 26.04 pilot during an attended window.
  Every machine preflight now passes, but the interactive whole-OS upgrade is not
  appropriate to launch unattended.

Fresh read-only preflight `preflight_20260716_183647.json` rechecked all five
hosts with eligible packages. It blocked AGC MR2 and GCMC MR2 on backup coverage,
VWM2 on backup plus -79 dBm routed Wi-Fi, Jersey Shore at -71 dBm, and GR on its
read-only firmware filesystem. All were reachable, but the safe update queue was
zero; no package transaction or reboot was attempted.

Read-only preflight `preflight_20260716_150905.json` now proves the mutation gate
itself enforces the remote Wi-Fi policy: Jersey Shore is blocked at -69 dBm while
nearby GMC EP3 remains eligible for controlled pilot work. The portal's package
and reboot queues contain no ready host; Jersey Shore is held at its current
routed -70 dBm sample.

The update/reboot gate and post-action verifier now require exact configured probe
IDs whenever the audited mapping is available, rather than accepting only the old
profile floor. Preflight `preflight_20260716_151343.json` proves 5/5 exact mappings
on nearby AGC MR3 and five-probe CV host GMC EP1/EP2. The complete portal source
shows no missing or unexpected IDs on any of the 23 reachable Pis.

The live portal now publishes that evidence explicitly rather than relying on an
absence of sensor warnings: `probe_mappings_aligned=23` of 23 assessed reachable
hosts. AGC MR3 and GMC EP1/EP2 API samples contain equal configured and physical ID
sets, and every device dialog includes expected/visible counts, mapping state,
stored calibration count, and live 1-Wire GPIO evidence.

End-to-end public verification on 2026-07-16 confirmed Cloudflare DNS resolution,
a Google Trust Services certificate valid for `coolmri.com` and
`*.coolmri.com`, HTTP 401 plus the expected Basic realm at the unauthenticated
root, HTTP 200 at `/healthz`, and authenticated HTML/API service. CSP, HSTS,
anti-framing, MIME, no-referrer, restricted-permissions, same-origin opener,
no-index, and no-store headers survive the public proxy on both 200 and 401
responses. Google Fonts links were removed in favor of local system fonts.
- Continue both AGC journal pilots through longer quiet write windows; reboot
  persistence and scheduled production camera captures have passed on MR1 and MR3.
  The latest common 839-second post-reboot window is approximately 476 MiB/day on
  MR1, 447 MiB/day on MR3, and 350 MiB/day on CV canary GMC IR3; retain observation
  because this is not yet multi-day evidence.
- Observe GMC IR3's rsyslog-RAM pilot through quiet no-reboot intervals before any
  expansion. Its conservative 30-second reboot verifier expired during network
  return, but independent audit at 34 seconds uptime proved the canonical service,
  four probes, zero throttling, RAM journal policy, and frozen historical logs.
- Onboard and verify GCMC MR2's backup before changing its logging policy. Four
  non-overlapping intervals prove a sustained 6.3 GiB/day median; read-only
  attribution found persistent 16 MiB journald files, active duplicate rsyslog,
  and 917 records/hour dominated by Tailscale resets and sensor INFO readings.
  The portal explicitly blocks logging changes until backup coverage exists.
- Keep the kernel GPIO fallback deployed on GR; it reports GPIO17 claimed by the
  1-Wire driver and high without adding a userspace package to the held system.
- Pilot OS-version convergence separately from routine package updates. Shamokin's
  Ubuntu 25.04 path and GR's supported 24.04 LTS installation are explicit exceptions.
  Fresh AGC MR3 preflight `preflight_20260716_143338.json` proves the direct 26.04
  offer, official sources, free space, zero pending packages, backup activity,
  service/probes/throttle, and telemetry gates; only production restore proof holds it.

The goal is therefore not complete: the central management and common application
baseline are operational, but backup/restore proof, offline recovery, OS convergence,
the journald observation, and the remaining controlled package wave still have
authoritative evidence gaps.

The RAM-capacity portion is now explicit rather than inferred from model size.
Complete audit `audit_20260716_202822.json` reports 23/23 reachable Pis with
`/run` on tmpfs, 68.6–92.4% memory available, only 0.5–4.1% of `/run` used, and
zero kernel OOM events since boot. Nine have no swap and fourteen have 1 GiB;
that difference is informational because all pass the measured headroom gate.
The portal exposes these facts and blocks additional RAM-backed rollout on low
headroom, `/run` pressure/non-tmpfs storage, or OOM evidence. The continuous
optimization window intentionally restarted because earlier audit samples did
not contain all of these proofs.

The operating-system update mechanism is also unified at the behavior layer.
Complete audit `audit_20260716_203454.json` proves all 23 reachable Pis have
active/enabled daily apt and unattended-upgrade timers, effective daily refresh
and upgrade policy, no held packages, and automatic reboot left disabled by
default. Three `unattended-upgrades` package versions correctly follow the three
Ubuntu cohorts. Four devices report a required reboot, but their existing backup
or network gates keep those reboots deliberate; none can reboot itself through
unattended-upgrades. The portal now exposes and assesses this contract per host.

The final application drift is exactly one MRI Pi: VWM2. GCMC MR2 and VWM3 passed
the guarded transaction with unchanged site `.env`, calibrated offsets, and exact
five-probe sets plus advancing production telemetry. VWM2 now has a marked backup
and successful restore, but preflight `preflight_20260716_224400.json` blocks it
at a critically weak -80 dBm routed Wi-Fi link. No override was used.

AGC MR3's scheduled 15:00 production camera observation passed in
`camera_observation_20260716_150304.json`. It links to the exact baseline checksum,
contains the single backend session `AGCMR3_SCHED_0716_150001` with contiguous
ordinals 01–10, and proves unchanged sensor/camera hashes, five probes, zero
throttle, no reboot, advancing sensor telemetry, durable retry state, and camera
log growth on tmpfs. The portal accepted the proof dynamically and now reports
zero pending camera observations.

Read-only preflight `preflight_20260715_230335.json` independently classified 19
devices ready and eight blocked: four unreachable devices plus AGC MR2, GCMC MR2,
VWM2, and VWM3 without backup coverage. All 23 reachable telemetry gates passed.
The targeted follow-up `preflight_20260716_192256.json` rechecked nearby AGC MR2
after its package queue reached 42 eligible updates: service, exact four-probe
mapping, boot storage, package-manager state, routed Wi-Fi, and production
telemetry all pass, but the missing backup repository remains a hard gate. No
override or mutation was performed.

The read-only snapshot `audit_20260716_001543.json` initially found five package-
only deviations. The serial gated action `baseline_20260716_064703.json` corrected
OSW MR2, SVI MR1, GBH, Shamokin, and GR. The independent complete snapshot
`audit_20260716_064720.json` then proved 23/23 reachable devices aligned, with
sensor services, application hashes, probes, and telemetry preserved.

The corrected Raspberry Pi A/B workflow was then validated on nearby GMC IR3,
EP1/EP2, and EP3. Backed remote candidates on GCMC Sola, GSWB, and GWV were promoted
with services, hashes, probes, and production telemetry preserved. The latest
snapshot `audit_20260716_081816.json` shows four candidates still held and GR's
read-only boot filesystem as a separate mutation blocker.

AGC MR1's unattended upgrade completed without intervention. Fresh preflight
`preflight_20260716_080453.json` then allowed a controlled A/B test reboot recorded
in `reboot_20260716_080545.json`: the kernel advanced from 6.17.0-1011 to
6.17.0-1021, the candidate was promoted, and the application hash, five probes,
camera RAM logs, zero-throttle state, and advancing telemetry were preserved.

The explicitly confirmed serial status-helper rollout aligned all 23 reachable
devices to SHA-256 `7af8be15f99479f6c6b04d63730142d51f62e03a81cabecf034d9939d13a83a4`.
Every helper was queried as its unprivileged fleet user. The GR fallback reads the
kernel GPIO view and reports GPIO17 claimed by `onewire@11`, output-high, so the
fleet now has 23/23 live pin readings without installing another package.

The nearby backed CV wave then converged GMC EP3 and IR3 to the flexible program
already used by EP1/EP2. Transactional deployment preserved each `.env` mapping
(five, three, and four probes respectively), matched every configured probe,
compiled in the production virtual environments, restarted cleanly, and proved
advancing correctly mapped CV telemetry. Complete audit `audit_20260716_083151.json`
shows all three CV programs at SHA-256
`a7bb0bc02e548f37993345e54cd664ac4d6e3dc47ba0b5525d7402f3a07717aa`
and approved software on 20/23 reachable devices.

All 20 reachable MRI devices also received one checksum-verified restricted
service helper. Its exact no-argument `recent-logs` action returns a fixed
two-minute, 160-line window and works with `sudo-rs` without wildcard sudo
permissions. Every MRI host passed unprivileged service-state and bounded-log
checks; no sensor was restarted during this control alignment.

The second nearby volatile-journal pilot was applied to backed AGC MR3 only after
check mode, backup, sensor, and current-telemetry gates passed. Reboot report
`reboot_20260716_084057.json` and independent complete audit
`audit_20260716_084126.json` prove that the 32 MiB runtime cap survived boot while
the application checksum, five probes, active service, headless canary, zero
throttling, and production telemetry remained intact. Its 5.28 GB historical
journal directory was deliberately retained and is no longer the active target.

The CV service-identity pilot and follow-up wave moved GMC IR3, GMC EP3, and GMC
EP1/EP2 from implicit root to their respective site accounts. The transaction first proved
that the account could read the exact `.env`, production virtual environment, and
all configured 1-Wire devices, then required the canonical program checksum,
recent backup, active service, and current mapped telemetry. Reboot reports
`reboot_20260716_084742.json`, `reboot_20260716_085025.json`, and
`reboot_20260716_085328.json` prove all three units return under the non-root
identity with their four-, three-, and five-probe mappings intact. Complete audit
`audit_20260716_085345.json` independently reports all three site users, active
services, canonical checksums, expected probes, zero throttling, and online data.

The portal scoreboard then exposed Muncy as the sole remaining root-run MRI
service. Its separately gated transaction required recent backup activity, the
approved MRI checksum, account-readable configuration and five probes, active
service, and current production telemetry. It installed the canonical MRI unit,
restarted without rebooting the remote host, matched every probe, and proved
advancing mapped data. Complete audit `audit_20260716_085953.json` now proves all
23 reachable sensor services run under their respective site accounts.

At 09:00 after reboot, AGC MR1's scheduled camera job completed in 25 seconds with
10/10 captures and 10/10 uploads, exit code zero, no failed-session records, and
fresh backend OCR telemetry. Its capture, retry, and cron logs remained in `/run`
tmpfs (about 15 KB immediately afterward), while durable retry state remained on
SSD. Complete post-capture audit `audit_20260716_090330.json` confirms the sensor
service, five probes, camera RAM-log mode, zero throttling, and both telemetry
streams remained healthy.

The first CV-profile journal canary then completed on nearby backed GMC IR3. Its
pre-change persistent-journal rate was about 2.7 GiB/day. The profile-aware serial
transaction required four physical probes, its non-root CV service, current mapped
CV telemetry, and recent backup activity before installing the same 32 MiB volatile
policy. Controlled reboot `reboot_20260716_090731.json` and complete post-reboot
audit `audit_20260716_090805.json` prove the policy, canonical CV checksum,
`gmcir3` service identity, four probes, zero throttling, and mapped telemetry all
returned together.

The subsequent CV security refresh installed the same four security packages on
all three CV hosts and deliberately left five phased/deferred meta-packages. Its
same-kernel boot assets were promoted serially. Complete audit
`audit_20260716_092233.json` proves all three candidates cleared with current and
old states good, no reboot flags, exact probe mappings, non-root services, and
online CV telemetry. The verifier now requires a 30-second stable recovery window
so a brief first SSH return cannot end a two-stage boot check early.

AGC MR1 then became the second headless-service canary after its camera RAM-log
and scheduled-capture gates passed. The reversible transaction preserved all
networking, management, logging, sensor, and cron services. Stable reboot report
`reboot_20260716_092816.json` and complete audit `audit_20260716_092855.json`
prove the multi-user target, stopped optional service set, canonical application,
five probes, zero throttling, camera tmpfs recreation, and telemetry recovery.
