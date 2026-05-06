# MRI Cooling — Pi Fleet Setup

This folder is for repeatable Raspberry Pi provisioning over **Tailscale + SSH** (no copy/paste between terminals).

## What It Does
- Deploys the **temperature sensor agent** (DS18B20 / w1thermsensor) and configures it as a `systemd` service.
- Deploys the **camera OCR edge scripts** and configures scheduled runs via `cron`.
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
  - export the shared password only in your shell for the run, for example:
  - `export MRI_PI_PASSWORD='...'`

### Examples
- Audit the full fleet and bootstrap missing SSH keys where password auth still works:
  - `python3 scripts/fleet_ops.py audit`
- Audit a subset by inventory name, label, or IP:
  - `python3 scripts/fleet_ops.py audit --hosts agcmr1,glh,100.66.66.116`
- Run routine package updates on selected hosts:
  - `python3 scripts/fleet_ops.py update --hosts agcmr1,agcmr3`
- Reboot a specific host:
  - `python3 scripts/fleet_ops.py reboot --hosts agcmr3`

Reports are written to `reports/` as timestamped JSON and Markdown files.

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
