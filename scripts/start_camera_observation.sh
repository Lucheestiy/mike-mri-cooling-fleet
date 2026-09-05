#!/usr/bin/env bash
# Save a fresh, read-only baseline immediately before an existing camera schedule.
set -euo pipefail

if (($# < 5 || $# > 7)); then
    echo "usage: $0 INVENTORY_NAME CAMERA_SITE_ID EXPECTED_COUNT NOT_BEFORE EXPECTED_SOURCE [volatile|preserve] [ram|preserve]" >&2
    exit 2
fi

inventory_name="$1"
camera_site_id="$2"
expected_count="$3"
not_before="$4"
expected_source="$5"
journald_policy="${6:-volatile}"
camera_log_policy="${7:-ram}"

if [[ ! "$inventory_name" =~ ^[a-z0-9]+$ ]] \
    || [[ ! "$camera_site_id" =~ ^[A-Za-z0-9_-]+$ ]] \
    || [[ ! "$expected_count" =~ ^[1-9][0-9]*$ ]] \
    || [[ ! "$expected_source" =~ ^[a-z0-9_]+$ ]] \
    || [[ "$journald_policy" != volatile && "$journald_policy" != preserve ]] \
    || [[ "$camera_log_policy" != ram && "$camera_log_policy" != preserve ]]; then
    echo "invalid camera-observation argument" >&2
    exit 2
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

audit_output="$(python3 scripts/fleet_ops.py audit \
    --hosts "$inventory_name" --no-bootstrap \
    --connect-timeout 3 --command-timeout 45)"
printf '%s\n' "$audit_output"
audit_path="$(sed -n 's/^Wrote \(.*\.json\)$/\1/p' <<<"$audit_output" | tail -1)"
if [[ -z "$audit_path" || ! -r "$audit_path" ]]; then
    echo "fresh target audit report was not produced" >&2
    exit 1
fi

baseline_path="$(python3 scripts/camera_schedule_observation.py baseline \
    --audit "$audit_path" \
    --host "$inventory_name" \
    --camera-site-id "$camera_site_id" \
    --not-before "$not_before" \
    --expected-count "$expected_count" \
    --expected-source "$expected_source" \
    --journald-policy "$journald_policy" \
    --camera-log-policy "$camera_log_policy" \
    --report-dir reports)"
if [[ -z "$baseline_path" || ! -r "$baseline_path" ]]; then
    echo "passing camera baseline was not produced" >&2
    exit 1
fi

pointer="reports/camera_observation_active_${inventory_name}.path"
temporary="${pointer}.tmp"
printf '%s\n' "$baseline_path" >"$temporary"
chmod 0644 "$temporary"
mv -f "$temporary" "$pointer"
printf 'Armed %s from %s\n' "$inventory_name" "$baseline_path"
