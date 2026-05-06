#!/usr/bin/env bash
set -euo pipefail

HOST="${1:-}"
USER_NAME="${2:-}"
KEY_PATH="${3:-}"
PASSWORD="${MRI_PI_PASSWORD:-}"

if [[ -z "${HOST}" || -z "${USER_NAME}" ]]; then
  echo "Usage: MRI_PI_PASSWORD='<password>' $0 <host> <user> [public_key_path]"
  echo "Example: MRI_PI_PASSWORD='secret' $0 100.86.162.63 pts"
  exit 2
fi

if [[ -z "${PASSWORD}" ]]; then
  echo "MRI_PI_PASSWORD must be set"
  exit 2
fi

if [[ -z "${KEY_PATH}" ]]; then
  for candidate in "/home/mlweb/.ssh/mri_pi_fleet_ed25519.pub" "$HOME/.ssh/mri_pi_fleet_ed25519.pub"; do
    if [[ -f "${candidate}" ]]; then
      KEY_PATH="${candidate}"
      break
    fi
  done
fi

if [[ ! -f "${KEY_PATH}" ]]; then
  echo "Public key not found: ${KEY_PATH}"
  exit 2
fi

PUBKEY="$(cat "${KEY_PATH}")"

export SSHPASS="${PASSWORD}"
sshpass -e ssh -o StrictHostKeyChecking=accept-new "${USER_NAME}@${HOST}" \
  "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; grep -qxF '${PUBKEY}' ~/.ssh/authorized_keys || printf '%s\n' '${PUBKEY}' >> ~/.ssh/authorized_keys"

echo "Installed ${KEY_PATH} for ${USER_NAME}@${HOST}"
