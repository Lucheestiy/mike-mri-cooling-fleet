# Shared operational package baseline — 2026-07-16

MRI and CV sensor applications remain separate profiles, but every reachable Pi
now shares the same operational support layer. A fresh full audit
`audit_20260716_154147.json` proves 23/23 reachable hosts have all 13 required
packages, an active profile-appropriate sensor service, active cron and
Tailscale, arm64 architecture, an NTP-synchronized clock, and an exact
configured-versus-physical probe mapping.

## Required on both profiles

- Runtime and deployment: `python3`, `python3-venv`, `python3-pip`, `git`
- Scheduling and transfer: `cron`, `rsync`
- TLS and API troubleshooting: `ca-certificates`, `curl`, `jq`
- Managed access and networking: `openssh-server`, `network-manager`, `tailscale`
- Retained rollback path for system logging: `rsyslog`

The baseline action queries the required layer and passes only genuinely missing
packages to `apt-get --no-remove`; it neither requests upgrades for already
present packages nor permits dependency removals. Package versions are not
expected to be byte-identical across different supported Ubuntu releases; the
installed capability and release-appropriate security version are the invariant.

## Optional diagnostics

`ethtool`, `iw`, `smartmontools`, and `nvme-cli` are inventoried separately.
They are shown in each portal host detail but do not mark a host as drifted.
The current fleet has `ethtool` on 23/23 reachable hosts, `iw` on 22/23,
`smartmontools` on 22/23, and `nvme-cli` on 0/23. The SMART package is installed
only where its sanitized on-demand query returned useful health data. GR is the
sole hold because its native NVMe/boot path has recorded controller resets and
must not receive package or firmware writes before onsite recovery.

## Convergence evidence

The first read-only expanded audit found only three gaps, each the absent `curl`
command package: GMC EP3, OSW MR2, and GWV. Exact transaction simulations on all
three reported one new package, zero upgrades, and zero removals.

- GMC EP3 was the nearby canary. `baseline_20260716_153833.json` proves the
  install, unchanged CV application checksum, active service, exact three-probe
  mapping, zero throttle flags, and advancing CV telemetry.
- OSW MR2 and GWV followed only after separate ready preflights.
  `baseline_20260716_154113.json` proves both installs, unchanged MRI application
  checksums, active services, exact five-probe mappings, zero throttle flags, and
  advancing MRI telemetry.
- The independent full audit `audit_20260716_154147.json` then proved the final
  23/23 operational-package result used by `pi.coolmri.com`.
- After hardening the baseline action to select only missing packages,
  `baseline_20260716_154530.json` exercised the already-aligned path on nearby
  GMC EP3. It reported no package transaction and still passed application,
  sensor mapping, service, throttle, and advancing-telemetry verification.

Ubuntu release convergence is a separate, higher-risk lane. Ubuntu 25.10 reached
end of life on 2026-07-09, so its hosts remain priority candidates for the guarded
26.04 LTS pilot in `docs/os-convergence-pilot.md`; package parity does not waive
the production restore-test requirement.
