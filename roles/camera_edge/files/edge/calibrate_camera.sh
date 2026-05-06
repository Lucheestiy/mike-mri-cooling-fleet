#!/bin/bash
# Camera OCR Calibration Script
# This script runs the camera in calibration mode to send images to your website

echo "========================================"
echo "📷 CAMERA OCR CALIBRATION MODE"
echo "========================================"
echo ""
echo "✅ PRODUCTION SETTINGS ACTIVE:"
echo "  - 3ms exposure (LCD overexposure fixed)"
echo "  - Custom 7-segment OCR decoder"
echo "  - Robust upload with retry logic"
echo ""
echo "This will:"
echo "1. Capture images with optimized camera settings"
echo "2. Send them to https://cam.coolmri.com/api/camera/calibration"
echo "3. Allow you to see the OCR crop region remotely"
echo "4. Update every 5 seconds for easy adjustment"
echo ""
echo "To adjust the crop region:"
echo "1. View the images on your website"
echo "2. Edit the .env file and change OCR_CROP_COORDS"
echo "3. Restart this script to see the changes"
echo ""
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# Navigate to the project directory
cd "$(dirname "$0")"
cd ..

# Activate virtual environment
source venv/bin/activate

# Set calibration mode environment variable
export CALIBRATION_MODE=true

# Run the camera OCR in calibration mode
cd edge
python improved_ocr.py --calibrate