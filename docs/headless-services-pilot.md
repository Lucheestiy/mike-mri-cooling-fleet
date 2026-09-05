# Headless background-services pilot

GBH is the first serial remote expansion host after the original four-host
reference cohort completed its continuous 48-hour health, RAM, and write-rate
gate. It has strong routed Wi-Fi, five exact probes, current telemetry, a recent
restored backup, and no camera workload. The same exact-state rollback record
and post-change sensor/telemetry checks used by the nearby pilots apply.

The check-mode rehearsal and live transaction passed on 2026-07-21. Controlled
reboot report `reboot_20260721_084832.json` proves uptime reset, the canonical
sensor application was preserved, all five exact probes recovered, throttling
remained zero, and server telemetry advanced through a 30-second stable recovery
window. Target audit `audit_20260721_084842.json` independently confirms
`multi-user.target`, active MRI sensor service, inactive selected desktop units,
and a strong -36 dBm routed Wi-Fi link. GBH now starts its own expansion-canary
observation window; it does not alter the accepted four-host reference cohort.

Shamokin MR followed as the second serial remote expansion. Its rehearsal and
live transaction preserved five probes, all critical services, and advancing
telemetry. After unattended upgrades finished cleanly, controlled reboot report
`reboot_20260721_085455.json` passed stable recovery. Target audit
`audit_20260721_085506.json` confirms `multi-user.target`, canonical sensing with
five probes, zero throttling, inactive selected desktop services, and a strong
-48 dBm routed Wi-Fi link. It now has its own headless-only observation window.

VWM3 followed as the third serial remote expansion. Its check-mode rehearsal,
live verification, and controlled reboot all passed. Report
`reboot_20260721_085956.json` proves stable recovery; target audit
`audit_20260721_090012.json` confirms `multi-user.target`, canonical sensing,
five exact probes, zero throttling, inactive selected desktop services, and a
strong -45 dBm routed Wi-Fi link. It now has its own headless-only observation
window.

GWV Skyra is the fourth serial remote expansion. The backup gate explicitly maps
inventory name `gwvskyra` to repository `gwv-skyra`; the initial check caught
that distinction before any change. The corrected rehearsal, live transaction,
and controlled reboot then passed. Report `reboot_20260721_090427.json` and target
audit `audit_20260721_090438.json` prove stable recovery, `multi-user.target`,
canonical sensing, five exact probes, zero throttling, inactive selected desktop
services, and a strong -48 dBm routed Wi-Fi link.

## Evidence

The complete read-only snapshot `audit_20260716_002355.json` shows the same desktop
and peripheral services running on all 23 reachable sensor Pis:

- GDM graphical login;
- CUPS and CUPS Browsed;
- Bluetooth;
- ModemManager;
- colord;
- Avahi; and
- rsyslog alongside journald.

Twelve also had fwupd active during the snapshot. This consistency is useful, but
the devices' production role is headless 1-Wire sensor acquisition. GCMC MR2, the
highest repeated writer, showed the full service set while producing approximately
5–7 GiB/day in recent short samples. That correlation does not prove causation.

## Nearby pilot boundary

The staged pilot is restricted to one backed nearby MRI/CV host at a time. It changes the default boot
target from graphical to multi-user and stops/disables only GDM, colord, CUPS,
CUPS Browsed, Bluetooth, and ModemManager. It intentionally preserves:

- NetworkManager and Tailscale;
- cron;
- the profile-specific MRI or CV sensor service and all 1-Wire configuration;
- Avahi;
- fwupd; and
- rsyslog and journald.

The playbook requires an explicit confirmation, current backup activity, a
successful backup batch, healthy server telemetry, critical services, and at least
four probes. After the change it waits for telemetry to advance. Any verification
failure automatically restores the prior default target and services.

Preview and apply only with a secure interactive privilege context:

```sh
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/headless_services_pilot.yml --check --diff

.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/headless_services_pilot.yml \
  -e headless_services_pilot_confirm=true
```

Explicit rollback:

```sh
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/headless_services_rollback.yml \
  -e headless_services_rollback_confirm=true
```

Expansion remains serial and nearby-first. AGC MR3 first had to survive a reboot,
sensor/telemetry recovery, camera workload, and multiple comparable write windows.

## Applied canary — 2026-07-16

The AGC MR3 canary was applied after a clean live preflight and check-mode run.
The playbook stopped all eight selected units and moved the default target to
`multi-user.target` without invoking rollback. An independent post-change audit
proved the approved sensor application hash was unchanged, all five probes remained
visible, throttle flags remained zero, Wi-Fi remained -52 dBm, and server telemetry
was current. Avahi, fwupd, and rsyslog remain active by design. The portal therefore
marks the pilot as active observation, not approved for fleet expansion.

The controlled reboot report `reboot_20260716_064933.json` then proved an actual
new boot, preserved application hash, five recovered probes, zero throttle flags,
and advancing telemetry. `multi-user.target` persisted; all eight selected units
remained inactive while the critical sensor and management services recovered.
The remaining gate is multiple comparable quiet write-rate windows.

## Nearby MR1 expansion — 2026-07-16

Multiple later portal samples placed AGC MR3 around 0.5 GiB/day with its sensor
and scheduled camera workload healthy. AGC MR1 separately passed its rebooted
volatile journal, tmpfs camera logs, and a real 10/10 scheduled capture/upload.
The generalized playbook then required a recent backup, idle package manager,
current telemetry, and all critical services before applying MR1's reversible
headless profile.

The live change stopped the same eight desktop/printing/Bluetooth/modem/color
units while preserving NetworkManager, Tailscale, cron, Avahi, rsyslog, the MRI
sensor, and camera cron jobs. Controlled report `reboot_20260716_092816.json` was
the first to pass the strengthened 30-second stable-recovery verifier. Independent
audit `audit_20260716_092855.json` proves `multi-user.target`, inactive selected
units, active sensor, five probes, canonical hash, zero throttling, volatile
journald, recreated camera tmpfs storage, and advancing telemetry after boot.

## First CV-profile canary — GMC EP3

The reversible profile was generalized without conflating sensor programs: GMC
EP3 is gated against `cv-room-sensor.service`, CV site `EP3`, the CV snapshot
endpoint, and exactly three physical probes. Its recent Restic activity, idle
package manager, current telemetry, and critical services passed before change.

Controlled reboot `reboot_20260716_095400.json` passed the 30-second stable recovery
verifier. Independent audit `audit_20260716_095447.json` then proved canonical CV
SHA-256 `a7bb0bc02e548f37993345e54cd664ac4d6e3dc47ba0b5525d7402f3a07717aa`,
non-root `gmcep3` service, exactly three probes, zero throttling, current primary
and helium readings, persistent `multi-user.target`, and all eight selected units
inactive after boot. It is an observation canary; EP1/EP2 and IR3 remain unchanged
until comparable CV write and workload evidence accumulates. This describes the
initial boundary; IR3's later strong-link expansion is recorded below.

The first 516-second no-reboot window after the canary reports approximately
2.55 GiB/day, compared with approximately 2.12 GiB/day during the valid
778-second pre-change window. This does not demonstrate SSD-write savings and is
still influenced by recent boot activity. Headless mode remains justified as an
unused-service/RAM/CPU optimization. EP3 subsequently became a separate
reboot-verified 32 MiB volatile-journal canary in
`reboot_20260716_123631.json`; later quiet samples will determine its write effect.

## Strong-link CV expansion — GMC IR3

After the CV software, non-root service, package, and volatile-journal waves had
all passed, IR3 was selected ahead of weak-link EP1/EP2. Preflight
`preflight_20260716_132715.json` proved recent backup activity, an idle package
manager, canonical CV code, the `gmcir3` service identity, exactly four probes,
zero throttling, approximately -51 dBm Wi-Fi, and current four-reading telemetry.

The one-host check-mode rehearsal passed before the live transaction. Exact
service states were saved, and the selected desktop/printing/Bluetooth/modem/color
units stopped while CV, NetworkManager, Tailscale, cron, Avahi, and rsyslog stayed
active. Audit `audit_20260716_132935.json` independently confirmed the live state.
Controlled report `reboot_20260716_133109.json` then proved an actual reboot,
30 seconds of stable recovery, canonical application preservation, four probes,
zero throttling, and advancing CV telemetry. Target audit
`audit_20260716_133125.json` confirms `multi-user.target`, all selected units
inactive, the non-root service active, and the 32 MiB volatile journal intact.
Complete five-minute no-reboot audit `audit_20260716_133742.json` clears the
reboot-only unsafe-shutdown delta and reports approximately 416 MiB/day with all
CV health gates still passing. The portal now counts four reboot-verified
headless canaries.
EP1/EP2 remains excluded from headless expansion because its Wi-Fi is marginal.

The portal now expresses the current gate directly: the four completed canaries
remain in multi-day observation, while EP1/EP2 is held for routed Wi-Fi improvement
before any rebooted headless wave. Remote hosts are no longer described as waiting
for the already-completed AGC MR3 canary; they wait for multi-day nearby-canary
evidence plus their normal backup, health, and network gates.

Future pilot records now include each changed unit's exact `ActiveState` and
`UnitFileState`. Both automatic rescue and explicit rollback restore those saved
states rather than generically enabling everything. The rollback retains a legacy
fallback for the three canaries whose original records predate exact-state capture;
both new and legacy paths were exercised in check mode without changing EP3.

## Automatic 48-hour evidence gate

The audit collector now records the explicit systemd default target. This avoids
counting old reports where GDM happened to be inactive but no proven headless
profile was active. After every scheduled 15-minute fleet audit,
`scripts/optimization_observation.py` writes the compact
`reports/optimization_observation.json` gate consumed by `pi.coolmri.com`.

For each of AGC MR1, AGC MR3, GMC EP3, and GMC IR3, the continuous window resets
if an audit is missing for more than 45 minutes or any of these checks fails:

- `multi-user.target` is the explicit default and selected desktop/peripheral
  services remain inactive;
- volatile journald remains active;
- the profile-specific sensor service, approved application checksum, and exact
  configured/physical probe mapping remain healthy;
- throttle flags remain zero and at least 25% RAM remains available;
- production telemetry is current; and
- at least three valid write intervals have a median no higher than 2 GiB/day.

Expansion requires 48 continuous hours and at least 24 audit samples across the
active canary cohort. Weak routed Wi-Fi is reported as an advisory, not a hard
maintenance blocker; expansion remains serial and requires stable recovery
verification. The first explicit-target sample was collected at 16:02 EDT on
July 16. An end-to-end systemd service run at 16:05 succeeded and automatically
advanced the original four canaries to two samples and approximately 0.1 observed
hours.

## Nearby expansion after the evidence gate — GMC EP1/EP2

On 2026-07-21 the original four-host cohort cleared the automatic gate with more
than 67 continuous hours and 258 samples per host. GMC EP1/EP2 was the next
nearby, backed candidate even though its routed signal was approximately -69 dBm.

The explicit check-mode rehearsal passed before the serial live transaction. The
profile then moved the Pi to `multi-user.target` and stopped the same unused
desktop, printing, Bluetooth, modem, and color services. NetworkManager,
Tailscale, cron, rsyslog, Avahi, `cv-room-sensor.service`, and all five probes
remained healthy, and CV telemetry advanced. Controlled reboot report
`reboot_20260721_075948.json` proves a real reboot, the canonical CV application
hash, exact five-probe recovery, zero throttling, stable management access, and
advancing `EP1and2` telemetry. This fifth host begins a new observation window;
remote expansion remains serial while its post-reboot evidence accumulates.
