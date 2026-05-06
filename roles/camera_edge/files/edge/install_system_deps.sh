#!/bin/bash
"""
System Dependencies Installation Script
Run this script with sudo privileges to complete the camera OCR setup
"""

echo "===================================="
echo "Camera OCR System Dependencies Setup"
echo "===================================="

echo "Updating package list..."
apt update

echo "Installing Tesseract OCR Engine..."
apt install -y tesseract-ocr tesseract-ocr-eng

echo "Installing Raspberry Pi Camera support..."
apt install -y python3-picamera2 libcamera-tools libcamera-apps

echo "Installing additional camera tools..."
apt install -y python3-libcamera

echo "Adding user to video group (if not already)..."
usermod -a -G video gmcmr2c

echo "Verifying installations..."
echo "Tesseract version:"
tesseract --version | head -1

echo "Libcamera tools:"
libcamera-hello --list-cameras 2>/dev/null || echo "libcamera-hello not found"
rpicam-hello --list-cameras 2>/dev/null || echo "rpicam-hello not found"

echo "Python packages:"
python3 -c "import picamera2; print('picamera2 available')" 2>/dev/null || echo "picamera2 not available in system Python"

echo "===================================="
echo "Installation complete!"
echo "Please reboot the system or log out/in for group changes to take effect"
echo "Then run: python camera_ocr.py --single"
echo "===================================="