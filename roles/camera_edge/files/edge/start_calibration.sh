#!/bin/bash
# Start calibration mode with image viewer

echo "========================================"
echo "📷 CAMERA CALIBRATION MODE"
echo "========================================"
echo ""
echo "This will:"
echo "1. Start a web server on port 8080"
echo "2. Capture images every few seconds"
echo "3. Show you what the camera sees"
echo ""

# Get Pi IP address
PI_IP=$(hostname -I | awk '{print $1}')

echo "🌐 View calibration at: http://$PI_IP:8080"
echo ""
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# Navigate to edge directory
cd "$(dirname "$0")"

# Activate virtual environment
cd ..
source venv/bin/activate
cd edge

# Start image server in background
python serve_images.py &
SERVER_PID=$!

# Give server time to start
sleep 2

echo "🌐 Calibration viewer: http://$PI_IP:8080"
echo "📸 Capturing images..."

# Function to capture images every 5 seconds
capture_loop() {
    while true; do
        python save_calibration_image.py > /dev/null 2>&1
        sleep 5
    done
}

# Start capture loop
capture_loop &
CAPTURE_PID=$!

# Wait for user to stop
wait

# Cleanup on exit
trap 'kill $SERVER_PID $CAPTURE_PID 2>/dev/null' EXIT