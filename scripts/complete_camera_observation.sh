#!/usr/bin/env bash
# Run a read-only post-schedule audit and verify it against a saved baseline.
set -euo pipefail

if (($# != 1)); then
    echo "usage: $0 BASELINE_JSON" >&2
    exit 2
fi

baseline="$1"
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ ! -r "$baseline" ]]; then
    echo "baseline is not readable: $baseline" >&2
    exit 2
fi

inventory_name="$(jq -er '.inventory_name' "$baseline")"
if [[ ! "$inventory_name" =~ ^[a-z0-9]+$ ]]; then
    echo "invalid inventory name in baseline" >&2
    exit 2
fi

python3 scripts/camera_schedule_observation.py wait \
    --baseline "$baseline" \
    --timeout 300 \
    --interval 15

# Verification is read-only and all managed camera hosts already use fleet key
# authentication. Do not make the unprivileged planner depend on root secrets.
audit_output="$(python3 scripts/fleet_ops.py audit \
    --hosts "$inventory_name" --no-bootstrap)"
printf '%s\n' "$audit_output"
audit_path="$(sed -n 's/^Wrote \(.*\.json\)$/\1/p' <<<"$audit_output" | tail -1)"
if [[ -z "$audit_path" || ! -r "$audit_path" ]]; then
    echo "target audit report was not produced" >&2
    exit 1
fi

python3 scripts/camera_schedule_observation.py verify \
    --baseline "$baseline" \
    --audit "$audit_path" \
    --report-dir reports
