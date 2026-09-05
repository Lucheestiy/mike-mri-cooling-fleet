# MR3 SSH resilience pilot

Status as of 2026-07-30:

- AGC/GMC MR3 keeps ordinary OpenSSH on port 22 and also listens on port 2222
  bound only to its Tailscale IPv4 address, `100.103.6.98`.
- Fleet SSH, Ansible, and the backup hub use port 2222 for MR3.
- The backup hub's target format has an optional sixth SSH-port field; every
  existing five-field target remains backward-compatible with port 22.
- A two-minute banner-check timer restarts OpenSSH only after three consecutive
  failures, validates `sshd` configuration first, and rate-limits restarts to
  one per 15 minutes.
- The attended failure test stopped both OpenSSH listeners. The helper rebuilt
  them after its third failed probe, and a fresh controller connection passed.
- A controlled reboot then proved both SSH ports, the enabled health timer,
  Tailscale, the MRI sensor service, and the exact five-probe set all return.
  Production `AGCMR3` telemetry was online and current after the reboot.
- A new encrypted MR3 backup and matching decrypt/restore test passed over port
  2222.
- Tailscale SSH remains disabled until the tailnet SSH policy is narrowed.

## Why Tailscale SSH is still gated

MR3's compiled default SSH policy currently contains one delegated rule with 82
source addresses and permits the default broad local-user mapping. Enabling
Tailscale SSH in that state would make every same-owner fleet device a potential
SSH source. The Pi's node credential cannot edit the tailnet-wide policy.

## Required admin-console policy merge

Merge these tag owners into the existing `tagOwners` object:

```json
"tag:coolmri-admin": ["autogroup:admin"],
"tag:coolmri-ssh-pilot": ["autogroup:admin"]
```

Ensure the existing `grants` list contains this network permission. Existing
broader grants can satisfy the same requirement, but this rule documents the
intended least-privilege path:

```json
{
  "src": ["tag:coolmri-admin"],
  "dst": ["tag:coolmri-ssh-pilot"],
  "ip": ["tcp:22"]
}
```

Replace the broad default `ssh` rule rather than leaving it alongside the pilot
rule:

```json
"ssh": [
  {
    "action": "accept",
    "src": ["tag:coolmri-admin"],
    "dst": ["tag:coolmri-ssh-pilot"],
    "users": ["agcmr3"]
  }
]
```

Add an SSH policy test:

```json
"sshTests": [
  {
    "src": "tag:coolmri-admin",
    "dst": ["tag:coolmri-ssh-pilot"],
    "accept": ["agcmr3"],
    "deny": ["root"]
  }
]
```

After the policy saves successfully, use the Machines page to apply
`tag:coolmri-admin` to controller `mlweb` (`100.74.19.56`) and
`tag:coolmri-ssh-pilot` to `agcmr3` (`100.103.6.98`). Tagging converts those
machines from user-owned to tagged machine identities; do not apply either tag
to other devices during the pilot.

Only then enable MR3 with `tailscale set --ssh=true`, verify the compiled source
and local-user policy, prove a Tailscale SSH session as `agcmr3`, and leave
ordinary OpenSSH port 2222 plus the health timer in place.

Rollback order:

1. `tailscale set --ssh=false`
2. Remove the two pilot tags in the admin console only after deciding how those
   nodes should be re-authenticated as user-owned devices.
3. Keep port 2222 until the backup target is returned to port 22.
4. Run `playbooks/ssh_resilience_rollback.yml` only after the backup target has
   been reverted.
