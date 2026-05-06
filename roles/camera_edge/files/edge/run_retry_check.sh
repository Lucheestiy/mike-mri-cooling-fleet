#!/bin/bash
# Wrapper script for retry checking to ensure proper environment setup

# Set paths
BASE_DIR="$HOME/mri-cooling-camera"
SCRIPT_DIR="$BASE_DIR/edge"
VENV_DIR="$BASE_DIR/venv"
LOG_FILE="$SCRIPT_DIR/logs/retry.log"

# Create logs directory
mkdir -p "$(dirname "$LOG_FILE")"

# Change to script directory
cd "$SCRIPT_DIR" || exit 1

# Activate virtual environment
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Virtual environment not found" >> "$LOG_FILE"
    exit 1
fi

# Run the retry check script (suppress output unless there are actual retries)
python3 retry_failed_sessions.py 2>&1 | grep -v "No failed sessions found for retry" >> "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

exit $EXIT_CODE
