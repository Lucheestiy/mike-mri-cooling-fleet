#!/bin/bash
# Wrapper script for scheduled capture to ensure proper environment setup

# Set paths
BASE_DIR="$HOME/mri-cooling-camera"
SCRIPT_DIR="$BASE_DIR/edge"
VENV_DIR="$BASE_DIR/venv"
LOG_FILE="$SCRIPT_DIR/logs/cron.log"

# Create logs directory
mkdir -p "$(dirname "$LOG_FILE")"

# Log execution start
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting scheduled capture" >> "$LOG_FILE"

# Change to script directory
cd "$SCRIPT_DIR" || {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Cannot change to script directory" >> "$LOG_FILE"
    exit 1
}

# Activate virtual environment
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Virtual environment activated" >> "$LOG_FILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: Virtual environment not found" >> "$LOG_FILE"
    exit 1
fi

# Run the scheduled capture script
python3 scheduled_capture.py 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

# Log completion
echo "$(date '+%Y-%m-%d %H:%M:%S') - Scheduled capture completed with exit code: $EXIT_CODE" >> "$LOG_FILE"
echo "----------------------------------------" >> "$LOG_FILE"

exit $EXIT_CODE
