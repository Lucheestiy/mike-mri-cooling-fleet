# GR boot-storage remediation and update gate

## Current decision

Status: resolved remotely on 2026-07-18 after Fable and Codex independently
reconciled the live FAT evidence. The original prohibition below is retained as
the incident-time safety record; the completed procedure and clearance evidence
are recorded at the end of this document.

This is a GR-specific storage incident, not a fleet configuration standard. The
other Pis must not inherit a read-only `/boot/firmware` mount from GR.

## Evidence captured without changing GR

Read-only inspection on 2026-07-16 established:

- `/etc/fstab` resolves `/boot/firmware` to `/dev/nvme0n1p1`, FAT, with
  `defaults`; no persistent `ro` option exists.
- The live mount is `ro,...,errors=remount-ro`, while the NVMe disk and both
  partitions report block-layer `RO=0`.
- At boot on 2026-04-22, mount logged `source write-protected, mounted
  read-only`. The mount unit nevertheless completed successfully.
- The boot-time FAT check exited successfully and reported 733 files with no
  repair in its journal summary.
- No `FAT-fs` or `I/O error` entries exist in the current boot journal.
- The native Crucial P3 Plus `CT1000P3PSSD8`, serial `25235095B566`, firmware
  `P9CR413`, currently reports controller state `live`.
- Four controller-down resets occurred between 21:58 and 22:46 EDT on
  2026-04-29. Each was accompanied by the kernel's faulty-power-saving-mode
  warning. No PCIe AER count is currently exposed.
- Root remains writable, has about 928 GB free, reports zero Pi throttle flags,
  and the sensor service and telemetry remain operational.
- Approximately 269 packages are eligible, including kernel, firmware, systemd,
  and boot-related packages. That makes a normal bulk upgrade unsafe while the
  boot partition is read-only.

The timestamps matter: the boot partition was mounted read-only a week before
the recorded controller resets. The resets therefore do not prove that the
kernel remounted FAT read-only. Together, however, the unexpected boot-time
write-protection state and later controller loss point to the same power, PCIe,
NVMe carrier, or drive path and justify an onsite inspection.

## Onsite procedure

Use a maintenance window with physical access and another computer or recovery
medium available. Record each result; do not proceed merely because one step
temporarily makes the mount writable.

1. Confirm a recent GR repository backup and its timestamp in `pi.coolmri.com`.
   Preserve a separate image or file-level copy of the 512 MB FAT boot partition
   before any repair. A root-filesystem backup alone is not evidence that the
   boot partition can be restored.
2. Record the current sensor readings and confirm all expected probes, service
   status, GPIO state, and fresh server telemetry. Cleanly shut down GR and wait
   for storage activity to stop before removing power.
3. Inspect the official power supply and USB-C connection, NVMe HAT/carrier,
   board-to-board or ribbon connection, standoffs, drive seating, and enclosure
   clearance. Look for heat damage, looseness, strain, contamination, or a drive
   touching conductive hardware. Reseat only with power disconnected.
4. With the FAT partition unmounted, run a read-only `fsck.fat -n` inspection.
   Save its full output. If it reports damage, retain the boot-partition copy and
   run a repair only in this recovery window; never run FAT repair against the
   mounted live partition.
5. Boot normally without changing `config.txt`. Verify that
   `/boot/firmware` naturally mounts `rw`, the block device remains writable,
   the boot journal has no source-write-protected warning, and the kernel has no
   new NVMe reset, timeout, PCIe, FAT, or I/O error.
6. Verify the sensor service, exact probe mapping, GPIO state, zero throttle
   flags, fresh telemetry, and SSH/Tailscale recovery. Observe the Pi for at
   least 24 hours and require another fleet audit with no new controller reset.

If a controller reset recurs, stop. Test one variable at a time in another onsite
window: known-good official power supply first, then the NVMe carrier/connection,
then the SSD. PCIe Gen 2 is a reversible diagnostic fallback because GR currently
requests Gen 3, but it must be tested onsite and documented; it is not the first
remote workaround and must not conceal failing hardware.

## Package-update clearance

GR may leave the update hold only when all of these are recorded:

- recent backup plus recoverable boot-partition evidence;
- offline FAT inspection/repair result;
- naturally writable `/boot/firmware` after a normal boot;
- no boot-time source-write-protection message;
- no new NVMe reset or related storage error for at least 24 hours;
- active sensor service, exact probes, expected GPIO, zero throttling, and fresh
  production telemetry; and
- idle package manager with a reviewed update simulation.

Then run the existing guarded preflight and perform the update serially. Because
GR's eligible set includes kernel and firmware packages, keep physical access
through the first reboot. Re-audit the mount, kernel, service, probes, GPIO,
storage journal, and telemetry before declaring the update complete.

## Failure rollback

If the updated system fails but storage remains accessible, restore the preserved
boot partition and the known-good package/boot state during the same onsite
window. If the NVMe device disappears or resets, do not repeat writes: power down,
replace the suspected connection/carrier/power component, and recover from the
verified backup. Never make repeated remote reboot attempts against an unstable
boot device.

## Resolution evidence — 2026-07-18

The read-only mount was a stale runtime state, not the configured boot policy.
After a successful read-write remount and synced write/delete probe, a compressed
image of the entire 512 MB boot partition was stored off-host at
`/root/.local/share/coolmri/boot-images/gr-boot-20260718T162544Z.img.gz`.
Its SHA-256 is
`e65eef504f4f47a5548ba7cdbe46d723602bca6d1f50565f28b605e5fc830deb`, and
the controller-side gzip validation passed.

The partition was then cleanly unmounted. `fsck.fat -a` returned zero, a second
offline `fsck.fat -n` returned zero and clean, and the natural remount was
read-write. The apparent dirty bit and primary/backup byte-65 difference seen
while mounted read-write were normal live FAT dirty-flag state, as Fable
explained, not structural corruption.

Guarded preflight `preflight_20260718_122919.json` and simulation admitted 269
upgrades plus three new dependencies with no broken packages or removals.
`update_20260718_123717.json` completed the transaction, advanced Tailscale to
1.98.9, left zero eligible packages, and preserved the sensor application,
service, five exact probes, and advancing telemetry. Controlled reboot
`reboot_20260718_123957.json` promoted kernel 6.8.0-1052 to 6.8.0-1060. The boot
partition mounted read-write naturally, the current boot has zero NVMe resets or
storage errors, and no reboot is required.

Fresh encrypted post-update and post-policy snapshots both passed exact tmpfs
restore tests. Complete audit `audit_20260718_125026.json` independently reports
the writable boot mount, zero GR packages, zero controller resets, healthy
SMART data, active sensor service, five exact probes, current Tailscale, and the
standard restart policy. The portal no longer emits GR update, boot-read-only,
NVMe-reset, or SMART-hold findings.
