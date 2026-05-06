#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-}"
USER="${2:-}"
KEY="${MRI_PI_FLEET_SSH_KEY:-}"
OUT_DIR="${OUT_DIR:-$(cd "$(dirname "$0")/.." && pwd)/snapshots}"

if [[ -z "${HOST}" || -z "${USER}" ]]; then
  echo "Usage: $0 <host> <user>"
  echo "Example: $0 agcmr1 agcmr1"
  exit 2
fi

DEST="${OUT_DIR}/${HOST}"
mkdir -p "${DEST}"

if [[ -z "${KEY}" ]]; then
  for candidate in "/home/mlweb/.ssh/mri_pi_fleet_ed25519" "$HOME/.ssh/mri_pi_fleet_ed25519"; do
    if [[ -f "${candidate}" ]]; then
      KEY="${candidate}"
      break
    fi
  done
fi

SSH="ssh -i ${KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new"
REMOTE_HOME="$(${SSH} "${USER}@${HOST}" 'printf %s "$HOME"')"

echo "== Snapshot: ${USER}@${HOST} -> ${DEST}"

${SSH} "${USER}@${HOST}" 'crontab -l || true' > "${DEST}/crontab.user.txt"
${SSH} "${USER}@${HOST}" 'cat /etc/systemd/system/mri-sensor.service 2>/dev/null || true' > "${DEST}/mri-sensor.service"

${SSH} "${USER}@${HOST}" 'cd "$HOME/mike-mri-cooling" 2>/dev/null && egrep "^(LOG_PATH|BACKEND_URL|ALERTER_METRICS_URL|DEV_BACKEND_URL|ENABLE_DUAL_STREAMING|MEMORY_ONLY_MODE|WEAR_LEVELING|RAM_LOG_CAPACITY|DISK_SYNC_INTERVAL|PROBE_(IN|OUT|PRIMARY_IN|PRIMARY_OUT|ROOM)_ID|AVG_WINDOW|POLL_SEC|SITE_NAME|SCANNER_ID)=" .env || true' \
  > "${DEST}/mike-mri-cooling.env.filtered"

${SSH} "${USER}@${HOST}" 'cd "$HOME/mri-cooling-camera/edge" 2>/dev/null && egrep "^(SITE_ID|CAMERA_BACKEND_URL|CALIBRATION_URL|UPLOAD_ENABLED|UPLOAD_MODE|IMAGE_WIDTH|IMAGE_HEIGHT|OCR_CROP_COORDS|SHUTTER_SPEED|GAIN|CAPTURES_PER_SESSION|CAPTURE_INTERVAL|DEBUG_SAVE_IMAGES|CALIBRATION_MODE)=" .env || true' \
  > "${DEST}/mri-cooling-camera-edge.env.filtered"

mkdir -p "${DEST}/files"
rsync -av -e "ssh -i ${KEY} -o StrictHostKeyChecking=accept-new" "${USER}@${HOST}:${REMOTE_HOME}/mike-mri-cooling/src/pi_sensor.py" "${DEST}/files/" 2>/dev/null || true
rsync -av -e "ssh -i ${KEY} -o StrictHostKeyChecking=accept-new" "${USER}@${HOST}:${REMOTE_HOME}/mike-mri-cooling/src/requirements_pi.txt" "${DEST}/files/" 2>/dev/null || true
rsync -av -e "ssh -i ${KEY} -o StrictHostKeyChecking=accept-new" "${USER}@${HOST}:${REMOTE_HOME}/mike-mri-cooling/src/sensor_offsets.json" "${DEST}/files/" 2>/dev/null || true

echo "Done."
