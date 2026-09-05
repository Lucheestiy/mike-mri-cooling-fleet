# Sensor runtime dependency baseline

The MRI and CV applications remain separate profile programs, but both depend on
the same three direct Python libraries. Complete fleet audit
`audit_20260716_201643.json` executes the interpreter declared by each active
systemd sensor service and inventories only these direct packages; it does not
publish a full environment dump.

## Compatible contract

- `python-dotenv>=1.0.0,<2`
- `requests>=2.31.0,<3`
- `w1thermsensor>=2.0.0,<3`

The MRI and CV deployment manifests now declare the same contract. These ranges
preserve the validated API generation and prevent a future role run from
downgrading a working newer minor release merely to make version strings equal.
The portal treats a missing package, a version below the floor, or the next major
API as drift. Compatible minor-version differences remain visible with exact host
labels and do not independently authorize a sensor restart.

## Current evidence

All 23 reachable Pis are dependency-complete and compatible:

- MRI: 20/20. Python reflects the installed Ubuntu cohort; the three libraries
  form several compatible minor-version groups.
- CV: 3/3. All three use Python 3.14.4 with identical direct dependencies:
  python-dotenv 1.0.1, requests 2.32.3, and w1thermsensor 2.0.0.

No Pi was changed or restarted from this finding. Exact dependency convergence
would add service-restart risk without fixing a missing capability. If a future
audit reports actual drift, repair one backed host at a time and require the same
application-hash, exact-probe, active-service, and advancing-telemetry proof used
by sensor program waves.
