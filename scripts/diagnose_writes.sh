#!/usr/bin/env bash
# Read-only short write-attribution sample for a Linux fleet host.
set -euo pipefail

sample_seconds="${1:-45}"
if ! [[ "$sample_seconds" =~ ^[0-9]+$ ]] || (( sample_seconds < 5 || sample_seconds > 300 )); then
    echo "sample duration must be an integer from 5 to 300 seconds" >&2
    exit 2
fi

before="$(mktemp /tmp/coolmri-io-before.XXXXXX)"
after="$(mktemp /tmp/coolmri-io-after.XXXXXX)"
cleanup() { rm -f "$before" "$after"; }
trap cleanup EXIT

snapshot_process_writes() {
    local file pid value
    for file in /proc/[0-9]*/io; do
        pid="${file#/proc/}"
        pid="${pid%/io}"
        value="$(awk '$1 == "write_bytes:" {print $2}' "$file" 2>/dev/null || true)"
        if [[ -n "$value" ]]; then
            printf '%s %s\n' "$pid" "$value"
        fi
    done | sort -n
    return 0
}

root_partition="$(findmnt -n -o SOURCE /)"
root_device="$(lsblk -ndo PKNAME "$root_partition" 2>/dev/null || true)"
[[ -n "$root_device" ]] || root_device="${root_partition#/dev/}"
root_device="${root_device%%[0-9]*}"

snapshot_process_writes > "$before"
base_sectors="$(awk -v device="$root_device" '$3 == device {print $10}' /proc/diskstats)"
sleep "$sample_seconds"
snapshot_process_writes > "$after"
current_sectors="$(awk -v device="$root_device" '$3 == device {print $10}' /proc/diskstats)"

sector_delta=$((current_sectors - base_sectors))
printf 'sample_seconds=%s root_device=/dev/%s sectors_written_delta=%s bytes_written_delta=%s\n' \
    "$sample_seconds" "$root_device" "$sector_delta" "$((sector_delta * 512))"
printf 'process_write_bytes_delta:\n'
join "$before" "$after" \
    | awk '$3 > $2 {print $3 - $2, $1}' \
    | sort -nr \
    | head -15 \
    | while read -r bytes pid; do
        printf '%s %s ' "$bytes" "$pid"
        tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true
        printf '\n'
    done || true

printf 'recent_log_files:\n'
find /var/log -xdev -type f -mmin -10 \
    -printf '%s %TY-%Tm-%TdT%TH:%TM:%TS %p\n' 2>/dev/null \
    | sort -nr \
    | head -25 || true
