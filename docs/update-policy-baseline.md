# Operating-system update policy baseline

## Fleet contract

MRI and CV sensor applications remain profile-specific, but every reachable Pi
uses the same safe operating-system update behavior:

- `unattended-upgrades` is installed from the host's supported Ubuntu cohort;
- `apt-daily.timer` and `apt-daily-upgrade.timer` are enabled and active;
- package lists refresh daily;
- unattended upgrades run daily;
- unattended upgrades do not automatically reboot the Pi; and
- package holds are empty unless an explicitly documented exception is created.

Package acquisition and package installation are separate operations. The
download-only fleet action refreshes metadata and fills local APT caches on up to
eight independent Pis concurrently, but cannot install, remove, or reboot. It is
guarded by local free-space and package-manager-idle checks and followed by exact
sensor/application verification. Installation remains serial and uses either a
successful complete backup batch or a recent successful machine-specific decrypt
and tmpfs restore as its backup gate.

Package version equality across different Ubuntu releases is not required.
Presence and effective behavior are the contract. This lets Ubuntu 24.04, 25.10,
and 26.04 use their supported package revisions without reporting false drift.

Unattended upgrades may install eligible security fixes, but a required reboot
remains visible until the fleet transaction can verify backup, storage, routed
network quality, sensor service, exact probe mapping, and advancing server
telemetry. Reboots are therefore deliberate and recovery-verified rather than
scheduled blindly by apt.

## Evidence

Complete read-only audit `audit_20260716_203454.json` proves the contract on all
23 reachable Pis:

- 23/23 have both apt timers enabled and active;
- 23/23 report `APT::Periodic::Update-Package-Lists=1`;
- 23/23 report `APT::Periodic::Unattended-Upgrade=1`;
- 23/23 leave automatic reboot unset, whose package default is off;
- no package is held on any reachable host; and
- the three observed `unattended-upgrades` revisions map to their Ubuntu OS
  cohorts rather than representing behavioral drift.

At that audit, four hosts had `/run/reboot-required`: AGC MR2, Jersey Shore MR,
GCMC MR2, and VWM2. The current complete audit has only Jersey Shore and VWM2;
both remain held for marginal/critical routed Wi-Fi, not because the update
policy is inconsistent. The portal shows the exact policy and reboot status for
each Pi and will create an actionable recommendation if a timer is disabled,
daily upgrades stop, a package hold appears, or automatic reboot is enabled.

## Exact cache evidence — 2026-07-17

Download completion is no longer treated as proof that current packages remain
cached. Each audit now derives the exact package/version candidates from APT's
no-lock simulation and compares them with the non-empty Debian archives currently
present under `/var/cache/apt/archives`. The guarded download post-check fails if
any current candidate version is absent, and the portal publishes the current
candidate and cached counts plus missing names instead of carrying a stale success
forward.

Complete download report `download_20260717_183839.json` proves the only three
hosts with eligible packages are fully cached: Jersey Shore 50/50, GR 272/272,
and VWM2 51/51. APT performed no installation or reboot; the post-check also
proved active sensor services, all five configured probes, unchanged application
hashes, and zero throttle flags. These packages remain installation-held: Jersey
Shore has marginal routed Wi-Fi, VWM2 has critical routed Wi-Fi, and GR has the
separate boot-firmware/storage incident. The other 20 reachable hosts currently
have no eligible package candidates; six packages on the three nearby GMC CV
systems are phased/deferred and are not forced. Complete independent audit
`audit_20260717_184014.json` confirms 23/23 reachable caches assessed and complete,
with 373/373 current eligible candidate versions present.
