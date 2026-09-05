# MRI Cooling — Pi Fleet Setup

This folder is for repeatable Raspberry Pi provisioning over **Tailscale + SSH** (no copy/paste between terminals).

## What It Does
- Deploys the **temperature sensor agent** (DS18B20 / w1thermsensor) and configures it as a `systemd` service.
- Can deploy the **camera OCR edge scripts** and configure scheduled runs via `cron`.
  Camera deployment is currently protected by `camera_edge_deploy_approved: false`
  because the recovered role source does not match any live semantic family.
- Stores per-Pi differences (sensor IDs, calibration offsets, site IDs) in `inventory/host_vars/`.
- Installs a restricted root-owned disk imaging helper plus a narrow `sudoers` rule for disaster backups.
- Installs a restricted root-owned MRI sensor service helper plus a narrow `sudoers` rule for safe `mri-sensor.service` control without full sudo.

## Prereqs
- The Pi is on your Tailnet and reachable over SSH.
- Your controller machine has an SSH key installed on the Pi (example key name: `~/.ssh/mri_pi_fleet_ed25519`).
- You can `sudo` on the Pi (recommended: `ansible-playbook -K`).

## Quick Start (Controller)
1. Create a local Ansible venv:
   - `python3 -m venv .venv && . .venv/bin/activate && pip install -U pip ansible`
2. Bootstrap SSH access on a brand-new Pi if needed:
   - `MRI_PI_PASSWORD='...' scripts/bootstrap_password_ssh.sh <host> <user>`
   - Example: `MRI_PI_PASSWORD='...' scripts/bootstrap_password_ssh.sh 100.86.162.63 pts`
3. Edit inventory:
   - `inventory/hosts.yml`
   - `inventory/host_vars/<pi>.yml`
4. Run:
   - `ansible-playbook -i inventory/hosts.yml playbooks/site.yml -K`

The general site playbook intentionally skips camera code unless an explicitly
reviewed pilot sets `camera_edge_deploy_approved: true`. Do not enable that flag
fleet-wide until the camera convergence map and post-capture verification are
complete.

## Bench-Staged Devices
Use these host vars when you want to fully stage a Pi on the bench without sending live data yet:
- `temp_sensors.enable_service: false`
- `temp_sensors.start_service: false`
- `camera_edge.install_cron: false`

This keeps the sensor service disabled/inactive and removes the camera cron jobs while still installing the code, env files, groups, and dependencies.

## Current References
- Legacy camera tarball recovered from a working Pi:
  - `/home/mlweb/pi-setup/camera_setup_package_20250823_085631.tar.gz`
- Preferred repeatable workflow:
  - this Ansible repo under `/home/mlweb/mri-cooling-pi-fleet`
- Current staged bench devices:
  - `inventory/host_vars/pittstonvida.yml`
  - `inventory/host_vars/gcmcsola.yml`

## Snapshot Helper (Optional)
Pull key files from a Pi into `snapshots/<host>/`:
- `scripts/pull_pi_snapshot.sh agcmr1 agcmr1`

## Fleet Operations
Use the dedicated ops inventory when you need routine reachability checks, MAC/network collection, package updates, or reboots across the whole Raspberry Pi fleet.

- Inventory:
  - `inventory/fleet_hosts.yml`
- Controller script:
  - `python3 scripts/fleet_ops.py audit`
- Password handling:
  - the root-only controller credential is stored outside this repository at
    `/root/.config/coolmri/pi-fleet.env` (mode `0600`); source it only for an
    approved maintenance session
  - Ansible privilege escalation uses the root-only executable helper
    `/root/.config/coolmri/ansible-become-password` (mode `0700`), so the secret
    is not placed in command history or committed inventory
  - backup-hub privilege escalation uses the separate root-only password file
    `/root/.config/coolmri/backup-hub-become-password` (mode `0600`); it is never
    copied to a Pi or used as the fleet credential

### Examples
- Audit the full fleet and bootstrap missing SSH keys where password auth still works:
  - `python3 scripts/fleet_ops.py audit`
- Audit a subset by inventory name, label, or IP:
  - `python3 scripts/fleet_ops.py audit --hosts agcmr1,glh,100.66.66.116`
- Evaluate all maintenance gates without a password or mutation:
  - `python3 scripts/fleet_ops.py preflight`
- Preflight only the next serial candidates:
  - `python3 scripts/fleet_ops.py preflight --hosts muncymr,jsmr,gmcep3`
- Pre-download eligible package files across reachable Pis without installing:
  - `python3 scripts/fleet_ops.py download --all`
  - download-only work runs on up to eight independent Pis concurrently, reuses
    each Pi's APT cache, bounds mirror retries, and skips hosts with a busy package
    manager or less than 1 GB free
- Run routine package updates on selected hosts:
  - `python3 scripts/fleet_ops.py update --hosts agcmr1,agcmr3`
  - the guarded updater uses `apt-get upgrade --with-new-pkgs`, so normally
    released kernel dependencies can install without the package-removal
    behavior of `full-upgrade`
- Install only the common operational support packages on selected hosts:
  - `python3 scripts/fleet_ops.py baseline --hosts oswmr2,svimr1,gbh,shmr,gr`
- Reboot a specific host:
  - `python3 scripts/fleet_ops.py reboot --hosts agcmr3`

Reports are written to `reports/` as timestamped JSON and Markdown files.
Both formats distinguish packages eligible for the guarded transaction from all
packages merely listed by apt and the deferred remainder; Markdown never labels a
phased-only host as having actionable updates.

Software installation and reboot commands are backup- and health-gated by default. The selected device
must have a configured repository, recent repository activity, a successful backup
batch, an active profile service, the minimum expected probe count, no throttle
flags, at least 1 GB free, and current server telemetry. After the action, the
command waits for the expected service/probes, preserved application hash, zero
throttle flags, an actually observed new boot when rebooting, and a telemetry
timestamp newer than the preflight sample. Gate and recovery evidence are recorded
in the action report. Emergency overrides exist as `--ignore-backup-gate`,
`--ignore-health-gate`, and `--skip-post-check`; use them only as explicit,
reviewed exceptions.

The `download` action changes only APT metadata and cached package files; it does
not install packages, stop services, change a kernel, or reboot. Its narrower
local gate checks disk space and package-manager activity, then verifies that the
sensor service, exact probe mapping, throttle state, and application hash remain
unchanged. Installation remains a separate serial, fully gated action.

When an audited sensor configuration exposes probe IDs, maintenance and recovery
verification require exact equality between those configured IDs and the physical
1-Wire devices. The older profile minimum is used only when no authoritative
mapping exists. This prevents a five-probe CV or MRI host from being accepted after
only three or four sensors return.

The same mutation gate follows the default-route Wi-Fi interface. Any routed link
at or below -75 dBm is blocked. A remote link at or below -67 dBm is also blocked;
the explicitly nearby AGC/GMC pilot hosts may still be rehearsed above the hard
-75 dBm floor because they are physically recoverable. This does not suppress the
portal's recommendation to improve a marginal nearby link before rebooted work.

The read-only `preflight` report uses the same backup, local health, and telemetry
logic as the mutating commands. It is the preferred way to select a maintenance
wave before opening a temporary privileged shell.

## Restricted Sensor Service Access
For hosts provisioned with the common role, the site user can manage only the temperature agent without needing the shared sudo password:

- Check status:
  - `sudo -n /usr/local/sbin/mri-sensor-service status`
- Restart the agent:
  - `sudo -n /usr/local/sbin/mri-sensor-service restart`
- Read recent logs:
  - `sudo -n /usr/local/sbin/mri-sensor-service logs --since '10 minutes ago' --lines 200`

This is intentionally narrower than full sudo and is the preferred path for routine sensor recovery.

## Convenience Access
Use the repo-local launcher when you want faster day-to-day maintenance without rebuilding SSH commands by hand:

- Launcher:
  - `/home/mlweb/mri-cooling-pi-fleet/fleet`
- Static group definitions:
  - `inventory/fleet_groups.yml`
- Maintenance notes:
  - `docs/fleet-maintenance-notes.md`

### SSH Aliases
The launcher can generate a dedicated SSH include for every Pi:

- Write/update aliases:
  - `./fleet ssh-config`
- Then connect directly:
  - `ssh agcmr1`
  - `ssh agc-mr1`
  - `ssh oswmr2-root`

### Group-Aware Commands
The launcher accepts inventory names, labels, IPs, and group names. It also exposes dynamic groups from the latest audit report:

- Dynamic groups:
  - `reachable`
  - `offline`
- Show groups:
  - `./fleet groups`
- List hosts in a group:
  - `./fleet list woodbine`
- Audit reachable hosts:
  - `./fleet audit reachable`
- Run routine updates for Pittston:
  - `./fleet update pittston`
- Run a stricter package convergence pass:
  - `./fleet full-upgrade reachable`
- Check pending packages and reboot flags:
  - `./fleet check reachable`
- Reboot a specific group:
  - `./fleet reboot agc`

The wrapper delegates normal `audit`, `update`, and `reboot` runs to `scripts/fleet_ops.py`, and adds convenience commands for `ssh`, `check`, `groups`, `list`, `ssh-config`, and `full-upgrade`.

## Useful Host Vars
- `mri_hostname`: optional Linux hostname to set on the Pi
- `mri_modules`: include `temp_sensors`, `camera_edge`, or both
- `pi_backup.enable_restricted_disk_backup`: install the restricted disk-image helper and sudoers rule

## Fleet Portal

The read-only operations portal is deployed at `https://pi.coolmri.com`.

- It reads the newest complete 28-device audit from `reports/`.
- It joins host health with current MRI and CV API snapshots.
- Each device shows normalized live temperatures with a five-minute freshness
  boundary. MRI retains named helium/primary channels and deltas; CV retains its
  configured 3–5 probe count as Sensor 1–5. Missing required readings or active
  backend alarms hold maintenance instead of presenting partial data as healthy.
- It reports Wi-Fi strength, CPU/disk health, OS drift, eligible versus merely
  listed/phased package updates, pending reboots,
  sensor service state, 1-Wire IDs, calibration offsets, and backup repository coverage.
- Its operational software ledger proves required-package coverage across every
  currently assessed Pi and groups observed versions by Ubuntu cohort. This keeps
  a legitimate release-specific version difference visible without mislabeling it
  as missing software or forcing cross-release package versions. Multiple versions
  inside one OS cohort are labeled as an observed spread with the contributing
  host names; this remains review evidence, not permission to bypass maintenance gates.
- Its sensor-runtime panel executes the interpreter used by each active MRI/CV
  service and compares Python plus the three direct dependencies by profile. The
  current fleet is 23/23 dependency-complete; compatible minor-version families
  remain visible with exact host labels instead of triggering unsafe restarts.
- The Tailscale ledger also inventories the configured package channel. Official
  stable versus distribution-channel counts include exact host labels, so an old
  version caused by repository policy is distinguishable from a blocked routine update.
- A dedicated Tailscale-channel dispatch lane keeps source convergence separate
  from routine apt maintenance. It currently holds AGC MR1 for its planned camera
  proof and Jersey Shore for routed Wi-Fi remediation, and can release a host only
  when its normal maintenance gates are ready.
- Its Updates score separates packages on maintenance-ready hosts from packages
  held behind backup, routed-Wi-Fi, or boot-storage gates. The total is never
  presented as authorization to update every Pi.
- Its OS lane distinguishes a current restore from a complete machine-specific
  release-upgrade readiness proof. All 17 reachable end-of-life MRI hosts now
  have a guarded assessment: 14 Ubuntu 25.10 machines pass individually, Jersey
  Shore and VWM2 are blocked by routed Wi-Fi, and Shamokin requires a staged path
  from Ubuntu 25.04. Individually passing hosts remain held until GMC MR2 recovers
  all four probes and passes strict post-upgrade verification; technical
  preparation is never presented as authorization to bypass the nearby canary.
- Each device dialog lists the exact sanitized package names eligible for the
  guarded transaction separately from phased/deferred names. Deferred packages
  are labeled “not forced,” and eligible packages show the host's maintenance
  hold reasons and reboot requirement.
- Each device dialog includes the latest successfully verified fleet update,
  baseline, or reboot when one exists. Only sanitized action, package counts,
  kernel/reboot outcome, probes, service, throttle, application, and telemetry
  evidence are published; raw command output and credentials are never exposed.
- Its Probe Map score is positive configured-versus-physical evidence. Each host
  detail shows the exact expected/visible count, missing or unexpected IDs,
  calibration count, and live 1-Wire GPIO state.
- Its Calibration Map score validates that every stored offset belongs to a
  configured/physical probe and is numeric. Missing explicit entries are shown as
  the sensor program's supported 0° default rather than false drift; each device
  identifies explicit versus default values by probe ID.
- Its 1-Wire GPIO score independently checks the boot overlay, reported pin, and
  live GPIO line. This preserves explicit exceptions such as GR on GPIO17 rather
  than assuming every host uses the default GPIO4.
- Its evidence strip reads a separate authenticated history endpoint containing up
  to 96 complete audits. Availability is shown as an audit tape; write traces show
  AGC MR1/MR3 and GMC IR3/EP3/EP1-EP2 with explicit gaps for reboots, short intervals, or
  invalid counters, rsyslog configuration boundaries, or package maintenance
  windows rather than treating missing evidence as zero writes.
- SSD-write findings use up to four non-overlapping, no-reboot intervals. A
  sustained warning requires at least three valid samples and a high median; one
  burst stays visible but is not presented as a trend.
- Its field-priority count combines unreachable devices with very weak Wi-Fi,
  throttling, and concerning SMART health; the network lane gives a concrete
  reposition/external-antenna/Ethernet recommendation for each marginal site.
- The Field Dispatch lane deduplicates those findings into one visit instruction
  per Pi. Offline devices sort first with last-contact identity where available,
  followed by critical and marginal routed-Wi-Fi, storage, power, or thermal work.
- Complete audits also join controller-visible Tailscale peer state. Offline rows
  show the last-seen date and a specific on-site power/network/LED check instead
  of implying that an unreachable Pi can be repaired remotely.
- Offline dialogs use a separately timestamped sanitized last-successful audit
  for field context when one exists. Historical settings, OS, Tailscale IP, and
  MACs are labeled stale and never satisfy current health or maintenance gates.
- Storage unsafe-shutdown counters are compared only for the same serial device.
  An increase across a known reboot is shown as an observation because USB/NVMe
  bridges may count orderly Pi restarts; an increase without a reboot is promoted
  to a power/cabling warning.
- It is protected by HTTP Basic authentication from the uncommitted `.env` file.
- Public HTML, assets, APIs, health, and authentication challenges all carry
  no-store, CSP, HSTS, anti-framing, no-referrer, restricted-permissions,
  MIME-sniffing, same-origin opener, and no-index headers. The UI uses only local
  system fonts and makes no Google Fonts or other third-party browser requests.
- Rotate credentials by editing `.env` and running `docker compose up -d --force-recreate dashboard`.
- The dashboard is intentionally read-only; changes, updates, and reboots stay in the
  audited CLI workflow until a pilot and rollback check are complete.
- `/api/history` is protected by the same Basic authentication as `/api/fleet`, is
  generated from existing reports, and retains no new device secrets or write state.
- Public `/healthz` exposes only controller state and report age. It returns 503
  when no complete 28-host report exists or the newest complete evidence is more
  than 45 minutes old, so external monitoring cannot report a healthy portal while
  fleet collection is stalled.

The systemd timer `coolmri-pi-fleet-audit.timer` refreshes health and backup coverage
every 15 minutes. It also rebuilds the continuous 48-hour RAM/headless canary
evidence gate used by the portal. Device details identify the exact first passing
audit and whether the current clean window began after a health-gate recovery,
an audit gap, or an rsyslog policy boundary. Unit source files are kept under
`systemd/`.

See `docs/fleet-standardization-plan.md` for the two-profile baseline and rollout gates.
See `docs/package-maintenance-20260715.md` for the first controlled update/reboot
wave and its per-host recovery evidence.
See `docs/requirement-audit-20260715.md` for the evidence-backed completion matrix
and remaining gates.
See `docs/backup-restore-verification.md` for the tmpfs restore verifier and the
required first MRI/CV production tests.

The backup hub also runs `coolmri-restic-restore-sweep.timer` weekly after the
daily Pi pull window. It decrypts and restores the OS identity from every
configured repository into tmpfs, shares the production backup lock to prevent
overlap, and publishes per-repository pass/fail evidence to the portal. Production
pulls use bounded groups of four independent repositories; the 2026-07-17 proof
completed 24/24 targets in 32:21, down from 72:49 serially. Its immediately
following exact latest-snapshot restore sweep passed 24/24 with zero failures.

The one-shot `coolmri-agcmr1-camera-proof-{baseline,complete}.timer` family is
armed around MR1's existing 09:00 schedule on 2026-07-18. It brackets the natural
job with read-only evidence and does not invoke captures; missed timers are
non-persistent and completion enforces a bounded freshness window. Each baseline
binds the expected backend source instead of assuming the legacy camera family.
AGC MR3 now runs managed v3.0.0 and has both its upload-disabled hardware smoke
proof and a natural 10/10 `camera_edge_v3` production proof. Broader deployment
awaits MR1's equivalent v3 proof and the remaining per-site contract reviews.
The production pilot keeps exposure profile-specific: MR1 retains 1500 µs / 2.5
with `full_and_crop`, while MR3 retains 1000 µs / 0.5 with `cropped_only`.

The controller timer `coolmri-camera-proof-planner.timer` checks once per minute
for a successful guarded secondary v3 deployment that still matches the latest
complete fleet audit and reviewed camera contract. It derives the next existing
capture time in `America/New_York`, starts only the read-only observation wrapper
five minutes beforehand, and runs only the verification wrapper afterward. It
does not invoke a camera, change a schedule, update software, or reboot a Pi; stale
deployment evidence or changed runtime hashes are refused. Plans and results are
written atomically under `reports/`, and a passing post-deployment natural 10/10
proof prevents further actions for that host.

The additive `playbooks/backup_export_prepare.yml` prepares an online backup-gap
Pi for the existing hub pull workflow. It installs a fixed-path streaming helper
and exact sudo rule, then proves the sensor checksum, probe mapping, service, and
telemetry remain healthy. Passing this playbook means only that the Pi is export-
ready; coverage is not granted until the hub has a target, root SSH authorization,
and a successful first backup. For newly onboarded targets, an atomic non-secret
success marker is written only after Restic reports a real snapshot; an empty
initialized repository never satisfies mutation gates.
See `docs/os-convergence-pilot.md` for the supported, nearby AGC MR3 Ubuntu 26.04
LTS pilot, its strict pre/post evidence command, and the Shamokin/GR exceptions.
See `docs/operational-package-baseline-20260716.md` for the 13-package shared
MRI/CV support layer, optional diagnostic capabilities, and 23/23 audit proof.
See `docs/software-families-20260715.md` for the separate MRI/CV application
families, the effective runtime-policy matrix, and the backup-gated final
MRI convergence work. GCMC MR2 and VWM3 are complete; VWM2 has verified backup
and restore coverage but remains held by weak Wi-Fi. The portal compares effective timing, logging,
and recovery behavior without treating site identity, probe IDs, calibration,
GPIO exceptions, or backend selection as settings to copy between Pis.
See `docs/service-unit-convergence.md` for profile-aware service-unit validation
and the no-restart GR header correction with exact rollback.
See `docs/storage-health-and-wear.md` for measured write-rate semantics and the
separate SMART visibility pilot.
See `docs/ram-budget-baseline.md` for the fleet-wide available-memory, swap/zram,
`/run` tmpfs, and OOM safety gate that must remain healthy before expanding
RAM-backed logging or headless optimizations.
See `docs/update-policy-baseline.md` for the shared daily apt/unattended-upgrade
contract, OS-cohort-aware package versions, package-hold visibility, and the
deliberate no-automatic-reboot policy.
See `docs/completion-audit-20260716.md` for the requirement-by-requirement
production evidence matrix, including achieved coverage and the remaining
offline, backup, OS, application, camera, update, reboot, and RAM-observation gaps.
See `docs/gr-boot-storage-remediation.md` for GR's unexpected read-only boot
partition, onsite storage procedure, and explicit package-update clearance gate.
See `docs/wifi-field-guidance.md` for routed-interface diagnostics, per-site
antenna/Ethernet recommendations, and the safe USB-adapter acceptance test.

### MRI sensor-code wave 1

The guarded rollout is limited to backed-up MRI devices with the restricted
restart helper. It runs serially, compiles before replacement, backs up the old file,
requires telemetry to advance, and automatically rolls back on verification failure.

- Preflight only: `.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml playbooks/sensor_code_wave_1.yml --check --diff`
- Apply after review: `.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml playbooks/sensor_code_wave_1.yml -e sensor_wave_confirm=true`
- Devices without current backup evidence remain intentionally excluded.

### CV sensor-code convergence

The CV profile remains separate from MRI, but GMC EP1/EP2, EP3, and IR3 now use
one flexible 3–5-probe program. Host `.env` files retain their site IDs and exact
probe mappings. The EP3/IR3 playbook is backup- and telemetry-gated, compiles in
the production virtual environment, verifies every configured probe and mapped
reading, and restores the automatic pre-change copy on failure.

- Preflight: `.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml playbooks/cv_sensor_code_wave.yml --limit gmcep3:gmcir3 --check --diff`
- Apply after review: `.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml playbooks/cv_sensor_code_wave.yml --limit gmcep3:gmcir3 -e cv_sensor_wave_confirm=true`

All three CV units also run as their site accounts rather than root. The serial
service-identity wave preserves the exact old unit for rollback, validates the
unit before replacement, verifies every configured probe and mapped reading, and
has passed controlled reboots on the three-, four-, and five-probe hosts.

- Rehearse one host: `.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml playbooks/cv_nonroot_service_pilot.yml --limit gmcep3 --check --diff`
- Apply one host: `.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml playbooks/cv_nonroot_service_pilot.yml --limit gmcep3 -e cv_nonroot_pilot_confirm=true`

### Restricted fleet controls

`playbooks/pi_status_helper.yml` aligns the no-argument read-only health helper.
`playbooks/mri_service_helper.yml` aligns the MRI recovery helper and its exact
bounded `recent-logs` action. Both require explicit confirmation and an explicit
reachable-host limit; neither restarts a sensor during alignment.

The user-owned `sudo-rs-ansible-compat` wrapper is also checksum-audited. Its
security baseline disables PTY input echo before Ansible sends a become password,
restores terminal state afterward, and is identical on all 23 reachable Pis. The
portal blocks privileged maintenance when a reported wrapper differs from that
baseline.

Unattended audits deliberately carry no general sudo credential. Their JSON now
records `sudo_check: not_checked_no_credential` and `sudo_ok: null`, while still
testing every narrow status/service helper with passwordless fixed commands. A
credentialed maintenance audit records `verified` or `credential_failed`; absence
of unattended authority is never presented as a broken Pi.

### SSD-wear pilot

The journal optimization is isolated from application provisioning:

- Check one nearby host: `.venv/bin/ansible-playbook -i inventory/hosts.yml playbooks/edge_baseline.yml --limit agcmr1 --check --diff -K`
- Apply to MR1 only: `.venv/bin/ansible-playbook -i inventory/hosts.yml playbooks/edge_baseline.yml --limit agcmr1 -K`
- Roll back MR1 only: `.venv/bin/ansible-playbook -i inventory/hosts.yml playbooks/edge_baseline_rollback.yml --limit agcmr1 -K`
- The playbook is `serial: 1` and stops at the first failure.
- Rollback removes only the fleet journald drop-in and restores the OS/default journal policy.
- Five reboot-verified canaries use the 32 MiB volatile policy: AGC MR1/MR3 and
  GMC IR3/EP1-EP2/EP3. Other hosts remain persistent until quiet write evidence
  and troubleshooting retention justify another serial, rollback-capable expansion.
- Nearby AGC MR1 and MR3 also keep disposable camera logs in bounded tmpfs while
  preserving historical logs and failed-session retry state on SSD. Both log
  paths are reboot-verified and both have passed scheduled production captures;
  the portal consumes the checksum-linked MR3 proof directly.
- GMC IR3 is the first rsyslog-to-RAM pilot. Its volatile journald policy remains
  capped at 32 MiB while `rsyslog.service` is stopped and disabled, preventing
  duplicate writes to `syslog`, `kern.log`, and `auth.log`. The transactional
  playbook records and restores the exact prior service state on failure; the
  explicit rollback is `playbooks/rsyslog_ram_rollback.yml`.

Production camera/RAM-log observations use
`scripts/camera_schedule_observation.py`. A pre-job baseline refuses unhealthy
sensor, probe, throttle, telemetry, journal, retry, or camera-log state. The post-job
verification requires one exact scheduled session with uploads `01` through `10`,
preserved application/camera hashes and schedules, advancing sensor telemetry, and
continued RAM-only logs. Passing reports are consumed dynamically by the portal.

The recurring audit also records a sanitized per-device RAM budget. The portal
shows available memory, `/run` use and filesystem type, swap/zram state, and OOM
events. No-swap hosts are not treated as faulty when their measured headroom is
healthy. The four-canary observation now requires at least 25% memory available,
`/run` on `tmpfs` below 70%, and zero OOM events in every sample; its 48-hour
window restarted at the first audit containing all three proofs.

Wi-Fi health follows the interface carrying the default route. On Pis with both
the onboard radio and a USB adapter, an inactive or secondary interface no longer
creates a false weak-signal recommendation; the strongest connected interface is
used only when route evidence is unavailable.
