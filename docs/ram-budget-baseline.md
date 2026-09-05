# RAM budget and volatile-workload safety gate

## Purpose

Moving disposable logs into RAM reduces SSD writes, but only when memory pressure
is measured rather than assumed. The recurring audit now records a bounded,
sanitized RAM budget for every reachable Pi:

- total and currently available memory;
- swap capacity and usage, active swap device type, and whether zram is active;
- `/run` filesystem type, capacity, usage, and mount options; and
- a count of kernel out-of-memory events since the current boot.

The audit exports counts and device basenames only. It does not export kernel-log
content, process command lines, memory contents, or credentials.

## Decision thresholds

The portal assesses a host only when total memory, available memory, and `/run`
usage are present. The gate is:

| Evidence | Healthy | Warning | Critical |
|---|---:|---:|---:|
| Available memory | at least 20% | below 20% | below 10% |
| `/run` usage | below 70% | 70–89.9% | at least 90% |
| `/run` filesystem | `tmpfs` | anything else | — |
| OOM events since boot | zero | — | one or more |

Swap is descriptive, not mandatory. A Pi with no swap is healthy when it has
adequate available memory, low `/run` use, and no OOM evidence. This avoids
creating needless SSD writes merely to make swap configuration uniform.

The longer optimization observation is stricter: it requires at least 25%
available memory, `/run` on `tmpfs` below 70%, and zero OOM events for every
sample in the continuous 48-hour window. Because older reports lack this complete
evidence, the window restarted with the first schema-complete audit instead of
claiming that the earlier hours were proven.

## Initial fleet evidence

Complete read-only audit `audit_20260716_202822.json` assessed all 23 reachable
Pis:

- available memory ranged from 68.6% to 92.4%;
- `/run` usage ranged from 0.5% to 4.1%;
- all 23 used `tmpfs` for `/run`;
- no host reported a kernel OOM event since boot;
- nine hosts had no swap, while fourteen had a 1 GiB non-zram swap device; and
- every assessed host passed the portal RAM safety budget.

This is strong capacity evidence, but it is not authorization for immediate
fleet-wide expansion. The four reboot-verified optimization canaries must still
complete the new continuous 48-hour gate with healthy sensors, exact probe
mappings, current telemetry, quiet package state, and acceptable measured SSD
write rates. Until then, further volatile-journal, rsyslog, camera-log, or
headless rollout remains held.

GMC EP1/EP2 joined later as an expansion canary. Its independent 48-hour clock
is reported alongside the four original reference hosts, but it does not revoke
or reset reference-cohort evidence already earned. Fleet expansion remains
gated by all four reference hosts; each later canary must still pass its own
window before it is considered observation-ready.

The original reference cohort reached the gate at 08:43 EDT on 2026-07-21;
`audit_20260721_084327.json` independently reconstructs 68.0 continuous hours,
264 samples, and no blockers for AGC MR1, AGC MR3, GMC EP3, and GMC IR3. That
earned evidence is retained as accepted policy state. Later reference-host
outages still close the live rollout gate, but the portal identifies them as a
current health degradation instead of incorrectly claiming the 48-hour evidence
was never completed.

APT update, baseline, and download reports now contribute host-specific
maintenance windows to the sustained-write calculation. Intervals overlapping
those windows are excluded from its median, while the continuous health clock
keeps running. Legacy action reports receive a conservative 30-minute lookback.
This prevents a deliberate one-time package-cache fill from being mislabeled as
normal daily SSD wear without hiding health failures or ordinary write activity.
