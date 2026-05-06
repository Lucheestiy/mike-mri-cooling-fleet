#!/bin/bash
# Capture LCD with optimal exposure settings
# Generated after testing various exposure values

rpicam-still \
    --shutter 8000 \
    --gain 12.0 \
    --awb daylight \
    --denoise off \
    --width 1920 \
    --height 1080 \
    --immediate \
    -n \
    -t 1 \
    -o "${1:-lcd_capture.jpg}"

echo "Captured to: ${1:-lcd_capture.jpg}"
echo "Exposure: 8000µs, Gain: 12.0"