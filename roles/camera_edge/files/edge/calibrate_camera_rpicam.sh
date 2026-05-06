#!/bin/bash
# Calibration mode using rpicam-still with manual exposure
# Sends images every 5 seconds for remote viewing/adjustment

echo "Starting calibration mode with rpicam-still..."
echo "Images will be sent every 5 seconds"
echo "Check the web interface to see both full view and cropped region"
echo "Press Ctrl+C to stop"
echo ""

source ../venv/bin/activate

# Set calibration mode
export CALIBRATION_MODE=true

# Run the OCR script in calibration mode
python3 camera_ocr.py --calibrate

echo ""
echo "Calibration mode stopped."
echo "Adjust OCR_CROP_COORDS in .env file if needed"