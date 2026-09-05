# Backup restore verification

## Onboarding the four prepared backup-gap Pis

AGC MR2, GCMC MR2, VWM2, and VWM3 now have the canonical fixed-path export
helper, exact sudo rule, and a source-restricted hub key whose forced-command
dispatcher permits only the export and export-check actions. The guarded hub
playbook first requires the backup hub's root pull key to invoke each selected
helper's sanitized `check` action, then adds exact target records, runs real
targeted pulls, and verifies a latest Restic snapshot for every selected host.
Its default selection is only nearby GCMC MR2; later targets must be named
explicitly so the initial experiment cannot silently expand to all four Pis:

```sh
.venv/bin/ansible-playbook -i inventory/backup_hub.yml \
  playbooks/backup_hub_onboard.yml --check --diff

.venv/bin/ansible-playbook -i inventory/backup_hub.yml \
  playbooks/backup_hub_onboard.yml \
  -e backup_hub_onboard_confirm=true \
  --become-password-file /root/.config/coolmri/backup-hub-become-password
```

After GCMC MR2 has a recent verified snapshot, select a later wave explicitly:

```sh
.venv/bin/ansible-playbook -i inventory/backup_hub.yml \
  playbooks/backup_hub_onboard.yml --check --diff \
  -e '{"backup_hub_onboard_target_ids":["agcmr2","vwm2","vwm3"]}'
```

The second credential is intentionally a backup-hub credential, not the shared
Pi credential. It is stored separately in a root-only file on the management
host. Never count export readiness as a backup; rerun `scripts/backup_coverage.py`
after the first snapshots and confirm all four repositories have recent activity.

GCMC MR2 was deliberately used as the nearby first production target. Its first
encrypted snapshot completed on 2026-07-16, followed by a corrected snapshot
`bb58507e` after the export manifest was extended to include the target of the
`/etc/os-release` symlink. A production tmpfs restore from that latest snapshot
then passed. Pi-side and post-change checks also confirmed its active service,
unchanged five-probe set, and advancing CoolMRI telemetry.

Repository timestamps and a successful backup service prove that data was written;
they do not prove that the encryption key, repository indexes, archive stream, and
restoration path all work. The hub restore verifier closes that evidence gap without
writing a full Pi backup to SSD.

## What the verifier does

For one configured target, the root-owned helper:

1. selects the newest Restic snapshot with the target host and `pi-pull` tag;
2. locates the streamed tar file inside that encrypted snapshot;
3. decrypts and streams the archive through `tar`;
4. restores `etc/os-release` and `usr/lib/os-release` into a private directory
   under `/dev/shm`, correctly handling the operating-system symlink;
5. verifies the restored file is non-empty and structurally valid;
6. removes the temporary tree; and
7. atomically writes a non-sensitive JSON result for the fleet portal.

The helper accepts exactly one target ID, validates it against the configured target
file, serializes runs with `flock`, and never prints or copies the Restic password.
The production hub repository remains read-only during the test.

## Install on `mik-EQ`

Installation uses the backup hub's `mik` administrator account and its separate
root-only credential; the shared Pi password is not copied to the hub. Routine
collection continues through the restricted `resticbackup` SSH identity, while
the management identity is used only for reviewed administrative playbooks.

The production verifier and its narrow sudo authorization were installed on
2026-07-16. Repository indexes, encrypted data, and Restic passwords remain
root-only. The target catalog is intentionally non-secret and readable by the
unprivileged coverage collector.

A second live boundary check confirmed that `resticbackup` can enumerate the
root-owned repository directories and read the non-secret target catalog, but each
repository's config, keys, data, index, locks, and snapshots are mode `0700`/`0400`
for root. No password file exists in the service account's home, no RESTIC secret is
present in its environment, `sudo -n -l` requires authentication, and systemd
rejects an unprivileged service start. An unprivileged verifier therefore cannot be
made functional without deliberately weakening the backup design. No permissions,
ACLs, password locations, service policies, or hub files were changed.

The recurring collector checks the exact restore-helper authorization with
`sudo -n -l` without executing a restore. It publishes a structured readiness
status that the portal renders separately from individual restore results.

The recurring unprivileged collector now records a structured status for each
of the four prepared gaps. A host counts as onboarded only when its exact target
record, repository directory, and atomic successful-backup marker all exist;
export-helper readiness or an empty initialized repository never satisfies it.
The root backup helper writes that non-secret marker only after Restic reports a
real latest snapshot, and a root-only refresher can backfill markers by querying
the encrypted repositories directly. Existing repositories retain their legacy
snapshots-directory timestamp until the next marked daily run. The same evidence
records whether the backup mount is visible and whether the production restore
verifier is installed. Final coverage at 22:43 reports 24 repositories, 24
configured targets, and all four prepared Pis onboarded with real
successful-snapshot markers.

```sh
.venv/bin/ansible-playbook \
  -i inventory/backup_hub.yml \
  playbooks/backup_restore_test.yml \
  --check --diff -K

.venv/bin/ansible-playbook \
  -i inventory/backup_hub.yml \
  playbooks/backup_restore_test.yml \
  -K
```

## Required first evidence

The required MRI and CV restore tests were run serially:

```sh
ssh mik-eq-backup sudo -n /usr/local/sbin/coolmri-restic-restore-test agcmr3
ssh mik-eq-backup sudo -n /usr/local/sbin/coolmri-restic-restore-test gmcep3
```

`scripts/backup_coverage.py` collects the resulting status records. The portal then
shows the per-device result and the fleet count of successful tests within the
90-day evidence window. A failure remains visible and does not get converted into
a successful backup state.

On 2026-07-16, production restores succeeded for AGC MR3 (`e4092ef4`), GMC EP3
(`c979f6c0`), GCMC MR2 (`bb58507e`), AGC MR2 (`1f766ec2`), VWM2
(`3b6230cb`), VWM3 (`02029c72`), AGC MR1 (`ce1d6f49`), GMC IR3
(`453d84d3`), and GMC EP1/EP2 (`cc0c6579`). Testing exposed and corrected two real
restore defects before those successes: Restic snapshot selection now sorts all
matching snapshots by timestamp instead of relying on path-grouped `--latest 1`
output, and the archive includes both sides of the `/etc/os-release` symlink.
The verifier still restores only into tmpfs and leaves production repositories
read-only.

The first AGC MR1 restore attempt then proved its older 05:30 snapshot was not
self-contained: it stored `/etc/os-release` as a symlink without the corresponding
`/usr/lib/os-release` target. The verifier was refined to accept a valid legacy
regular file or require the target when the restored path is a symlink; it never
converts a dangling symlink into success. Guarded playbook
`playbooks/backup_refresh_restore.yml` created a fresh encrypted AGC MR1 snapshot
with the corrected production exporter and immediately restored it successfully
in tmpfs. Remaining older repositories will gain the corrected layout through the
normal serial schedule instead of a forced concurrent fleet backup.

Weekly timer `coolmri-restic-restore-sweep.timer` is enabled on the hub for Sunday
at 07:00 with up to ten minutes of jitter, after the daily 05:30 pull window. The
sweep takes the production backup lock non-blockingly, runs every configured
repository serially through the same tmpfs verifier, and fails if any target fails;
it cannot overlap a Pi backup. Its service has no new privileges, a read-only home,
strict filesystem protection, and only the repository lock area, dedicated cache,
report directory, and `/run` writable. Per-repository results remain available to
the recurring portal collector.

The first full service-path sweep on 2026-07-16 passed seven repositories and
failed 17 older latest snapshots: GBH, GCMC Sola, GMC EP1/EP2, GMC IR3, GR, GSWB,
GWV, Jersey Shore, Muncy, OSW MR1, OSW MR2, Pittston Sola, Pittston Vida,
sewer-pi, Shamokin, SVI MR1, and SVI MR2. Their reports remain failures in the
portal; snapshot existence is not presented as restore success. The corrected
exporter is already installed, so subsequent daily pulls will create
self-contained archives for reachable targets. Offline targets cannot clear this
finding until field recovery permits a fresh pull.

That sweep also exposed a 7.3 GiB peak while reading repositories. The scheduled
service now gives Restic two Go worker CPUs, a 2 GiB Go memory target, a 3 GiB
systemd soft limit, and a 4 GiB hard ceiling. This bounds weekly verification so
it cannot pressure other services on the 16 GiB hub.

Nearby-first repair then created fresh encrypted snapshots for GMC IR3 and GMC
EP1/EP2 and immediately restored both successfully, reducing current state to nine
passes and 15 failures. The remaining targets are remote or offline, so they stay
on the normal daily serial pull rather than receiving a forced overnight fleet
refresh. Target audit `audit_20260716_233336.json` independently confirms both
Pis retained the approved CV application, active non-root sensor services, exact
four- and five-probe sets, zero throttling, no reboot requirement, and zero
eligible packages after the backup reads.

## Daily target-loop correction — 2026-07-17

The 05:30 service reported `success` but refreshed only AGC MR1. Its target
catalog was connected to the shell loop's standard input; the first SSH probe
and legacy-export heredoc could consume the remaining records, allowing the
script to reach a successful end after one target. The helper now reads the
catalog through dedicated descriptor 3 and uses stdin-disabled SSH for canonical
checks and exports. Regression tests require both protections.

The corrected helper was installed with rollback protection and created a real
GCMC MR2 canary snapshot. A separate two-target production proof then processed
GCMC MR2 followed by AGC MR2 in the same invocation, publishing distinct snapshot
IDs `7d7e9d80` and `98a85b1f`; both newest snapshots decrypted and restored
`etc/os-release` successfully in tmpfs. This proves that the loop advances past
its first target without weakening the read-only exporter or repository controls.

The coverage collector now cross-checks successful snapshot markers against the
systemd service's exact start/finish window. Consequently the earlier green exit
is truthfully reported as `incomplete (1/24)` instead of a successful fleet batch.
The corrected daily timer remains scheduled for 05:30; its next run must publish
24/24 in-window markers, after which the weekly restore sweep can clear corrected
reachable archives. The four offline fleet Pis remain outside the configured
catalog until they return and can produce a first real snapshot.

The guarded 2026-07-17 repair wave subsequently refreshed Pittston Sola,
Pittston Vida, GCMC Sola, and GSWB Sola. All four new encrypted snapshots
decrypted and restored `etc/os-release` in tmpfs, increasing current restore proof
to 13 passes and reducing older failures to 11. Those proofs released only the
four corresponding one-package updates; they do not convert the still-incomplete
05:30 batch into a fleetwide success.

The remaining 11 configured targets were then refreshed and restore-tested.
GBH and Muncy initially exposed an older exporter that omitted the target of the
`/etc/os-release` symlink. Their canonical exporters were replaced
transactionally with rollback protection while preserving exact application
checksums, probes, services, and advancing telemetry. Fresh snapshots from both
then passed the same tmpfs decrypt-and-restore test. Current evidence is therefore
24/24 successful configured targets, including sewer-pi, and 23/23 successful
reachable fleet hosts with zero current restore failures. This does not relabel
the prior `incomplete (1/24)` scheduled run: the next corrected 05:30 execution
must still publish a complete batch in its own service window.

## Complete corrected batch and restore sweep — 2026-07-17

A manual service-path run of the corrected production helper began at 14:03:14
EDT and finished at 15:16:03 EDT with systemd result `success` and exit status 0.
All 24 configured targets published atomic successful-snapshot markers inside
that exact service window; `scripts/backup_coverage.py` reports 24 expected, 24
completed, no missing targets, and `complete: true`. This closes the target-loop
proof gap exposed by the earlier misleading one-target run without rewriting its
historical result.

The production restore-sweep service then ran from 15:17:29 through 15:20:20 EDT.
It exited successfully after decrypting each newly created latest snapshot and
restoring `etc/os-release` in tmpfs. All 24 restore reports have status `success`
and snapshot IDs that exactly match the corresponding new backup markers. The
collector now reports the restore sweep `ready`, zero failed repositories, and
the next timer run on Sunday. Fresh complete fleet audit
`audit_20260717_152121.json` and the authenticated public portal API expose the
same 24/24 batch and restore evidence.

## Bounded concurrent production batch — 2026-07-17

The user correctly noted that the Pis use independent hospital links, so serial
source reads unnecessarily extended the backup window. The production helper now
processes four distinct repositories concurrently by default, with a validated
operator range of one through eight. Workers retain the global batch lock, use a
different repository per process, publish the same atomic per-target marker only
after Restic commits, and return target-specific initialization, SSH, backup,
status, or retention failures to the parent. Four-worker groups bound memory and
SSD pressure instead of starting all 24 processes simultaneously. Backup and
restore services still share the nonblocking production lock and cannot overlap.

A guarded four-repository canary ran GCMC MR2, AGC MR2, VWM2, and VWM3 in parallel.
Process evidence showed four simultaneous Restic streams; all four new marker IDs
matched their repositories and all four decrypted/restored successfully. The full
systemd service then ran from 15:50:12 through 16:22:33 EDT with result `success`,
exit 0, and 24/24 markers inside that exact window. Elapsed time fell from 72:49
for the serial proof to 32:21, approximately 56% faster. The immediately following
production restore sweep ran from 16:23:32 through 16:26:23 and passed exact
latest-snapshot tmpfs restores for all 24 repositories. Coverage and complete
fleet audit `audit_20260717_163832.json` publish the concurrent result without
rewriting either earlier historical batch.

The guarded targeted refresh workflow now passes its complete selected target
list to that same bounded helper in one invocation instead of calling the helper
once per repository. The post-SMART wave therefore backed Jersey Shore, GCMC MR2,
VWM2, and VWM3 concurrently while keeping restores isolated and serial. All four
new snapshots committed around 11:39 EDT and their exact newest snapshot IDs then
decrypted/restored successfully in tmpfs. Single-target refreshes retain identical
behavior.

## Append-only marker history and corrected MR1 snapshot — 2026-07-17

After MR1's camera exposure contract was corrected to 1500 µs / 2.5, guarded
`backup_refresh_restore.yml` check mode and its confirmed one-target run created
snapshot `8f5b3999faa0f7d0f2e45c0dec6f1a430e8e62cdb7d4fff05b96ffe7b0245e22`
at 17:02 and restored its `etc/os-release` in tmpfs at 17:09. The latest
recoverable MR1 state therefore contains the corrected camera environment.

That targeted success exposed an evidence-accounting issue: the hub kept one
atomic latest marker per repository, so replacing MR1's marker made the immutable
15:50–16:22 full systemd batch appear 23/24 even though its original MR1 snapshot
and exact restore had passed. The pull helper now writes every successful marker
both to the latest path and to append-only per-repository/snapshot history. The
coverage collector uses the newest marker for freshness but any matching
historical marker for the exact systemd batch window. A narrow rollback-capable
migration verified the authoritative hub log boundaries and MR1 completion,
seeded all current markers, and preserved the overwritten full-batch MR1 marker
for snapshot `8500dba169eae8c11f3518d670705ec1a2233f70ecb7ad2cfb74a655384281fe`
completed at 15:57:31. It invoked no backup.

Collector evidence at 17:12 again reports the historical full batch `success`
24/24, while independently reporting MR1's newer 17:08 activity and exact 17:09
restore. Regression coverage proves a newer targeted marker cannot erase an
older in-window full-batch success.
