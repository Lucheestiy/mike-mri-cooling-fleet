#!/usr/bin/env bash
# Complete the saved baseline only shortly after its intended natural schedule.
set -euo pipefail

if (($# != 1)) || [[ ! "$1" =~ ^[a-z0-9]+$ ]]; then
    echo "usage: $0 INVENTORY_NAME" >&2
    exit 2
fi

inventory_name="$1"
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"
pointer="reports/camera_observation_active_${inventory_name}.path"

if [[ ! -r "$pointer" ]]; then
    echo "no active camera baseline for $inventory_name" >&2
    exit 1
fi
read -r baseline <"$pointer"
case "$baseline" in
    "$repo_dir"/reports/camera_observation_baseline_*.json|reports/camera_observation_baseline_*.json) ;;
    *) echo "camera baseline path is outside the expected report directory" >&2; exit 2 ;;
esac
if [[ ! -r "$baseline" ]] || [[ "$(jq -er '.inventory_name' "$baseline")" != "$inventory_name" ]]; then
    echo "camera baseline is unreadable or belongs to another host" >&2
    exit 2
fi

not_before_epoch="$(jq -er '.not_before_epoch | floor' "$baseline")"
now_epoch="$(date +%s)"
if ((now_epoch < not_before_epoch || now_epoch > not_before_epoch + 1800)); then
    echo "camera completion is outside the guarded 30-minute schedule window" >&2
    exit 1
fi

scripts/complete_camera_observation.sh "$baseline"
rm -f "$pointer"
