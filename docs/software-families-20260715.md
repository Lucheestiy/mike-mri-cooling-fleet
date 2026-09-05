# Sensor software families — 2026-07-15

The complete 27-device audit originally found five known program families among the 23
reachable devices. CV and MRI intentionally remain separate profiles.

| Profile | Family | Reachable hosts | Status |
| --- | --- | ---: | --- |
| MRI | resilient recovery v2 | 19 | approved |
| MRI | legacy static discovery | 1 | lacks approved bounded runtime recovery |
| CV | flexible 3–5-probe v2 | 3 | approved |

The MRI pilot established the resilient-recovery build on GMC MR1–3. Wave 1 then
updated ten backed-up MRI devices, followed by SVI MR2 and GBH after installing
their restricted service helpers. On July 16, nearby GCMC MR2 received its first
encrypted backup and production restore proof, then converged successfully.
VWM3 subsequently passed the same backup, restore, site-state, probe, restart,
and telemetry transaction. VWM2 alone remains on the legacy family because its
routed Wi-Fi is critically weak. Every future
software wave remains serial with a server-side telemetry check after every restart.

The CV profile is intentionally distinct from MRI because it uses a different
payload and sensor mapping. Its nearby GMC convergence preserved the configured
three-, four-, and five-probe layouts while aligning all three source files.
The service-identity canary then moved GMC IR3 from root to its site account with
systemd filesystem/kernel hardening, followed serially by GMC EP3 and EP1/EP2.
All three passed exact-unit rollback gates and controlled reboot proofs while
preserving their four-, three-, and five-probe mappings respectively.

## Effective runtime-policy contract — 2026-07-16

Fleet alignment compares effective behavior, not whether every `.env` file has
identical text. This avoids copying identity or calibration between sites and
also avoids false drift when a setting is safely supplied by the approved
program's built-in default.

| Behavior | MRI target | CV target |
| --- | --- | --- |
| Poll interval | 10 seconds | 10 seconds |
| Average window | 5 samples | 5 samples |
| Application logging | RAM/console only; `MEMORY_ONLY_MODE=true` must be explicit | console only |
| HTTP request timeout | program behavior | 10 seconds |
| Invalid-cycle restart | 3 cycles | profile does not use MRI recovery |
| Initial sensor discovery | 90-second bound, 5-second retry | profile's flexible configured-ID discovery |
| Runtime rescan | 20-second bound, 5-second retry | profile does not use MRI rescan |
| Dual backend streaming | enabled for the configured secondary metrics feed | profile does not use dual streaming |

`WEAR_LEVELING`, `RAM_LOG_CAPACITY`, `DISK_SYNC_INTERVAL`, and `LOG_PATH` may
remain present on MRI hosts, but they do not affect writes while RAM-only mode is
active and therefore do not create behavioral drift. `SITE_ID`, `SITE_NAME`,
`SCANNER_ID`, `BACKEND_URL`, every probe ID, GPIO exceptions, and
`sensor_offsets.json` remain site-specific and are never fleet-normalized.

The portal's **Runtime policy** score resolves each value as `explicit`,
`program default`, `invalid`, or `unknown on legacy program`. A host is aligned
only when its program is the approved profile build and all effective values
match its profile target. A legacy MRI program therefore remains visible as a
policy deviation even if its older `.env` file happens to contain matching
poll and logging values; they lack the bounded recovery implementation itself.
SVI MR2's explicit 120-second discovery and 30-second rescan bounds are retained
and displayed as a reviewable exception to the 90/20-second profile values; it is
not changed remotely merely to improve the score.

## Wave 1 preflight

The serial wave-1 playbook passed check mode on all ten included devices on
2026-07-15. For every host it confirmed a successful/recent backup, current server
telemetry, expected file ownership, virtual-environment Python, and restricted
restart-helper access. Check mode predicted only the sensor program replacement;
it performed no write or restart.

SVI MR2 and GBH were initially excluded because the restricted restart helper was unavailable.
GCMC MR2, VWM2, and VWM3 were excluded because they lack current backup targets.

The first OSW MR1 apply attempt discovered that its older sudoers rule permits
restart/status but not parameterized helper log reads. The rescue block restored
the automatic backup, restarted the prior build, and stopped the wave. Audit and
CoolMRI telemetry confirmed the old semantic hash, active service, and online data.
The verifier now treats journal access as an additional capability and relies on
active service plus advancing server telemetry where restricted logs are unavailable.
Telemetry verification uses bounded polling for up to two minutes because sensor
discovery and API snapshot timing can exceed a single 35-second observation window.

## Wave 1 result

Wave 1 completed serially on OSW MR1, OSW MR2, SVI MR1, Shamokin, Muncy,
Jersey Shore, GR, GCMC Sola, GSWB, and GWV. The complete post-rollout audit
`audit_20260715_204126.json` independently confirmed on every wave host:

- approved MRI semantic hash;
- active `mri-sensor.service`;
- five visible 1-Wire probes;
- RAM-only application logging; and
- current, online CoolMRI telemetry.

After the follow-up SVI MR2/GBH wave and transactional GMC EP3/IR3 CV wave,
approved profile software initially increased to 20 reachable devices: 17 MRI
devices on resilient recovery v2 and all three CV devices on flexible 3–5-probe
v2. GCMC MR2 and VWM3 subsequently increased that total to 22. VWM2 alone remains
outside its profile target because of weak Wi-Fi.

The remaining MRI device is deliberately gated: VWM2 has a verified backup and
restore, but needs a stronger or attended network path. CV remains a separate profile. Narrow
checksum-aligned service helpers are installed on all
three reachable CV devices and all 20 reachable MRI devices, so controlled
recovery and bounded log reads do not require general-purpose sudo.

The authoritative current evidence is `audit_20260716_092855.json`: all 23
reachable sensor services are active, all reachable devices expose the read-only
status helper, all reachable MRI devices expose the same bounded recovery helper,
all MRI and CV services run as their site accounts, and no device reports a
throttle flag. The final Muncy exception was corrected with exact-unit rollback,
five-probe validation, and advancing production telemetry.

## Final legacy-family wave readiness — 2026-07-16

`playbooks/sensor_code_remaining.yml` now targets only GCMC MR2, VWM2, and VWM3
through the proven serial rollout implementation. In addition to automatic
program rollback and advancing server telemetry, the shared workflow now records
and rechecks both the site `.env` and `sensor_offsets.json` SHA-256 values, the
exact physical 1-Wire ID set, and the installed approved program checksum. It
cannot overwrite sensor IDs, offsets, or other site settings because the only
copy target is `src/pi_sensor.py`.

The imported transaction also pins the only two raw source files it may encounter:
the reviewed legacy static-discovery build and the approved resilient build used
for an idempotent rerun. It refuses an unknown program checksum, a missing `.env`
or offsets file, unexpected ownership, or a missing production interpreter before
copying anything. Post-change proof still requires unchanged site-file checksums,
the identical physical probe set, the approved target checksum, an active service,
and advancing site-specific telemetry; failure restores the automatic pre-change
copy and stops the serial wave.

The safe rehearsal command is:

```bash
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/sensor_code_remaining.yml --check --diff
```

The July 16 rehearsal initially stopped at GCMC MR2 before inspecting or copying
the program because no recent backup repository existed. After its backup and
restore proof, both check mode and the explicitly confirmed apply passed. The
transaction preserved the `.env` and offsets checksums and exact five-probe set,
installed the approved checksum, restarted cleanly, and proved advancing site
telemetry. After later repositories are current, rerun check mode and then apply
to an explicitly limited eligible host:

```bash
.venv/bin/ansible-playbook -i inventory/fleet_hosts.yml \
  playbooks/sensor_code_remaining.yml --limit vwm3 \
  -e sensor_wave_confirm=true
```

VWM2's weak Wi-Fi remains a field recommendation, not a maintenance stop. The
sensor transaction reports the routed signal while retaining backup, exact-probe,
site-state, rollback, service, and advancing-telemetry gates.

After all four prepared repositories had authoritative success markers, VWM3's
limited check-mode rehearsal and explicitly confirmed apply both passed. The
transaction preserved its `.env` and offsets checksums and exact five-probe set,
installed the approved checksum, restarted through the restricted helper, found
no traceback or missing probe, and proved advancing production telemetry. Fresh
read-only preflight `preflight_20260716_224400.json` shows VWM2's backup gate now
passes and the routed -80 dBm Wi-Fi health gate alone blocks its mutation.

## Live effective-policy result — 2026-07-16

Fresh complete audit `audit_20260716_224912.json` collected the allow-listed
runtime keys from all 23 reachable Pis without exposing credentials. The portal
now resolves 21/23 as strictly aligned: all three CV devices and 18 approved MRI
devices. The remaining states are one exact approved exception—SVI MR2's retained
120/30-second bounded recovery policy—and one actual deviation on VWM2's legacy
program. The strict target score remains 21/23 rather
than hiding the SVI difference, while its portal finding is informational instead
of a generic drift warning. All reachable
MRI devices explicitly use RAM-only application logging and the configured
secondary metrics feed; all reachable devices retain the 10-second poll and
five-sample averaging policy. No remote setting was changed to manufacture this
score.

## Final VWM2 convergence — 2026-07-18

After the user made weak Wi-Fi advisory rather than blocking, the shared rollout
stopped enforcing its obsolete -67 dBm threshold and retained every functional
safety gate. VWM2's check-mode rehearsal passed at -72 dBm with a current backup,
the reviewed legacy checksum, exact five-probe set, protected `.env` and offsets
checksums, production interpreter, restricted recovery helper, and current server
telemetry. The transaction predicted only `src/pi_sensor.py`.

The confirmed serial apply completed at -73 dBm. It installed the approved MRI
resilient-recovery checksum, restarted through the restricted helper, found no
traceback or missing required probe, preserved both protected site-file checksums
and the identical physical probe set, and required advancing VWM2 telemetry before
success. Complete audit `audit_20260718_110912.json` independently proves 23/23
reachable Pis now use their approved MRI or CV program, VWM2's runtime policy is
strictly aligned, its service and five probes are operational, and current complete
production readings are present. A fresh encrypted post-change snapshot and real
tmpfs restore test also passed.
