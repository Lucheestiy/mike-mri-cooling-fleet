# Sensor service-unit convergence

The 2026-07-16 full audit found all 23 reachable sensor services active, enabled,
and running as their site accounts. MRI and CV retain different executable paths
and profile-specific hardening; those are intentional differences rather than
drift.

Twenty-two unit files pass `systemd-analyze verify`. GR is the only syntax
exception: its otherwise standard MRI unit has the literal line `Ini, TOML`
before `[Unit]`. Systemd ignores the line and the effective runtime properties
match the clean AGC MR1/MR3 reference, but leaving the warning makes future unit
validation less trustworthy.

`playbooks/gr_sensor_unit_header_repair.yml` removes only that exact line. It
requires a recent successful backup, exactly five probes, an active restricted
service helper, and current GR telemetry. It preserves the original unit for
rollback, validates the candidate, reloads systemd metadata without restarting
the sensor, proves all effective service properties are unchanged, rechecks the
application checksum and exact probe set, and requires telemetry to advance.
GR's systemd version rejects extensionless Ansible temporary filenames, so the
transaction validates the real `.service` path immediately after the exact-line
edit and restores the preserved original through the surrounding rescue block if
validation fails.

Rehearse before applying:

```bash
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/gr_sensor_unit_header_repair.yml --check --diff \
  --become-password-file /root/.config/coolmri/ansible-become-password
```

Apply only after the rehearsal predicts removal of the one ignored line:

```bash
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/gr_sensor_unit_header_repair.yml \
  -e gr_unit_repair_confirm=true \
  --become-password-file /root/.config/coolmri/ansible-become-password
```

The first apply attempt made no remote change because GR's older systemd rejected
Ansible's extensionless temporary validation filename. The rescue path restored
the already-original unit, kept the service active, and reported `changed=0`.
After moving validation to the real `.service` path inside the same rollback
block, check mode again predicted only the one-line deletion. The confirmed apply
then succeeded without restarting the service: effective properties were
identical, the application checksum and five-probe set were unchanged, and
production telemetry advanced.

## Nearby MRI crash-recovery pilot

Thirteen reachable MRI units restarted after only 100 ms (AGC MR2 used five
seconds) and allowed five starts in a 10-second window. A burst of failures
could therefore exhaust systemd's finite start limit and leave a sensor stopped.
Six other MRI units already inherited the resilient 15-second/unlimited policy.
CV remains a separate profile: all three CV services use a suitable 15-second
restart delay, and their existing start-limit and hardening are intentionally
retained.

`playbooks/mri_restart_policy_pilot.yml` began restricted to one explicitly
selected backed AGC MR1 or MR3 host, the nearby rooms selected for safe
experimentation. It adds a systemd drop-in with
`Restart=always`, `RestartSec=15s`, and `StartLimitIntervalSec=0`. The playbook
requires current backup and telemetry evidence, the approved application, the
exact probe set, and an active service. It reloads systemd metadata without
restarting the sensor, then proves the PID and active-start timestamp did not
change, the exact executable and probes are unchanged, the service remains
active, and production telemetry advances.

Two initial applies exercised the automatic rollback path safely. The first
comparison included transient `ExecStart` status metadata; the second expected
the textual value `infinity`, while this systemd reports a disabled start-limit
as `0`. Both attempts restored the prior drop-in state, reloaded metadata, and
kept the original process active. After narrowing the executable assertion and
accepting systemd's actual `0` representation, the confirmed apply completed on
2026-07-16 with one intended change and no sensor restart. Promotion remained
held until actual automatic recovery was exercised on that nearby pilot.

The follow-up automatic-recovery test then exercised the behavior rather than
relying only on effective-property inspection. With a fresh backup, approved
application, exact five-probe set, active service, and current telemetry all
gated, `playbooks/mri_restart_recovery_test.yml` sent one `SIGKILL` to only the
AGC MR1 sensor main process. Systemd recovered it automatically in 15.947
seconds with PID `1514` replaced by `49593`; the effective restart policy,
application checksum, and probe IDs remained exact. Production telemetry then
advanced by 65 seconds. The structured proof is retained in
`reports/restart_recovery_20260716_210859.json`; no Pi reboot or manual service
restart was required.

After that exercised proof, the same transaction became eligible for a second
nearby metadata-only rollout on backed AGC MR3. AGC MR2 was initially excluded
until its backup and restore evidence became authoritative.

AGC MR3 check mode predicted only the drop-in directory and six-line policy.
The confirmed transaction completed with PID `1526` and active-start timestamp
`9296754` unchanged, proving no sensor restart occurred. The service remained
active with the exact application and five probes, MRI telemetry advanced, and
the effective properties now report `RestartUSec=15s` and
`StartLimitIntervalUSec=0`.

The portal's read-only Crash recovery policy lane now converts the remaining
effective-property evidence into a serial queue. It admits only online MRI hosts
with recent backup activity, current telemetry, healthy probes/storage/power,
the approved application, and an aligned service unit. It holds every exception
with its exact gate reason and does not treat CV's intentional finite limit as
MRI drift.

After both nearby transactions passed and MR1's recovery was exercised, the
same playbook was extended to an explicit allowlist matching that portal queue.
It still accepts exactly one host per run and now independently rechecks the
default-route Wi-Fi floor, writable root/boot filesystems, idle package manager,
zero live throttle flags, current backup activity, approved code, exact probes,
active site-account service, and production telemetry. Portal readiness is
therefore planning evidence, not a substitute for live mutation gates.

GBH was selected as the first remote serial candidate because its routed Wi-Fi
was the strongest in the ready queue at -36 dBm. The full live rehearsal and
confirmed transaction passed, changed only the drop-in directory and policy,
kept the original sensor PID/start timestamp, preserved the approved program and
five-probe set, and required server telemetry to advance before success.

SVI MR1 followed as the second remote serial candidate at approximately -41 dBm.
Its separate check-mode rehearsal passed every live gate and predicted the same
two filesystem changes. The confirmed transaction retained PID `1556` and
active-start timestamp `8670694`, preserved the approved program and exact
five-probe set, and completed only after production telemetry advanced.

GCMC Sola followed after another isolated rehearsal. Its strong link, current
backup, writable filesystems, idle package manager, zero throttle state,
approved program, five probes, service identity, and telemetry all passed. The
confirmed transaction retained PID `1516` and start timestamp `9575282`, then
accepted success only after fresh production telemetry.

Shamokin MR was converged separately without touching its Ubuntu 25.04 release.
The service retained PID `512733` and active-start timestamp `7290181982075`;
all local gates passed immediately, and the play deliberately waited through its
longer reporting interval until production telemetry advanced before succeeding.

Pittston Vida's first rehearsal stopped safely before mutation because its raw
program checksum differs from the canonical file. Investigation proved Vida and
Pittston Sola share the same variant and that normalizing only CRLF/line endings
and trailing whitespace produces the exact approved fleet checksum. The
playbook now computes that same normalized checksum locally on each Pi for
behavioral approval while retaining the raw pre/post checksum comparison, so
the application must still remain byte-for-byte unchanged by this transaction.

With that stronger gate, Pittston Vida's second rehearsal passed and the
confirmed transaction retained PID `1526` and active-start timestamp `8861791`.
The raw application checksum stayed byte-for-byte identical, all five probes
remained exact, and production telemetry advanced before success.

Pittston Sola then passed the same strengthened application gate and isolated
rehearsal. The confirmed transaction retained PID `1520` and active-start
timestamp `10175704`, preserved the raw application and five probes, and received
fresh production telemetry immediately after the metadata reload.

OSW MR1 followed through its own live rehearsal and confirmed transaction. It
retained PID `1620` and active-start timestamp `9578625`, the raw approved
program and five probes remained exact, and server telemetry advanced without a
service restart.

OSW MR2 was the penultimate ready candidate. Its live link remained above the
remote floor, every rehearsal gate passed, and the confirmed transaction retained
PID `1546` and active-start timestamp `8946533`. Application bytes, probes, and
service identity stayed exact, and the play waited for advancing telemetry.

GSWB was the final currently ready candidate. Its fresh signal remained above
the strict -67 dBm remote floor, all live gates passed, and the transaction
retained PID `1518` and active-start timestamp `8711671`. The application and
five probes remained exact and telemetry advanced, closing that ready queue with
no sensor restart.

After AGC MR2 gained authoritative backup and restore proof, the portal admitted
it as the final nearby candidate. Two rehearsals stopped with zero changes while
the playbook learned its intentional four-probe mapping and exact older
`on-failure`/5-second service baseline. The host-aware third rehearsal passed,
and the confirmed transaction retained PID `1697` and active-start timestamp
`17913560`, preserved the raw application and exact four-probe set, and waited
for production telemetry to advance. Complete audit `audit_20260716_234347.json`
independently reports the active site-account service with `Restart=always`, a
15-second delay, and unlimited restart window.

Jersey Shore was the final safely mutable restart-policy candidate. The
allowlisted rehearsal passed at -70 dBm and treated the weak link as an
advisory while retaining the backup, writable-filesystem, idle-package-manager,
power, approved-code, exact-probe, active-service, telemetry, and automatic
rollback gates. The confirmed transaction passed at -68 dBm, retained PID
`1847` and active-start timestamp `35004434`, preserved the exact application
and five probes, and accepted success only after production telemetry advanced.
Complete audit `audit_20260718_111746.json` independently reports the effective
15-second/unlimited policy. A new encrypted snapshot and exact tmpfs decrypt-and-
restore test then passed as snapshot
`279ac651a579175268553f6735d93663b887fed1d29973b98e01449cda7cacf4`.

GR is now the only reachable MRI restart-policy deviation. Its root filesystem
is writable, but `/boot/firmware` remains read-only after four NVMe controller
resets and a power-management warning. Because its configured mount policy
already requests normal writable operation, it remains an onsite storage/power
hold rather than a configuration-convergence target.

## GR closes the reachable restart-policy queue — 2026-07-18

After GR's offline FAT check, guarded package update, reboot, and fresh
backup/restore all passed, the one-host rehearsal admitted it to the existing
restart-policy playbook. GR lacks `iw`, so unavailable signal measurement is now
an advisory just like weak Wi-Fi; live SSH/Tailscale, backup, writable
filesystems, idle package management, zero throttling, exact probes, active
service, and current telemetry remain mandatory.

The confirmed metadata-only transaction retained PID `1259` and activation
timestamp `7904681`, preserved the exact application and five-probe set, and
waited for production telemetry to advance. Complete audit
`audit_20260718_125026.json` reports `Restart=always`, a 15-second delay, an
unlimited restart window, and no reachable restart-policy deviation.
