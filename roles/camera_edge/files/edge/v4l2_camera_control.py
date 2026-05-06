#!/usr/bin/env python3
"""
Camera control using v4l2-ctl commands for manual exposure
Works without needing additional software installation
"""

import subprocess
import os
import time
import json
from pathlib import Path
from datetime import datetime
import cv2
import numpy as np
from seven_segment_ocr import SevenSegmentOCR

# Load configuration
from dotenv import load_dotenv
load_dotenv()
OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))

class V4L2CameraControl:
    """Control camera exposure using v4l2-ctl commands"""

    def __init__(self):
        self.device = "/dev/video0"
        self.decoder = SevenSegmentOCR(debug=False)
        self.find_camera_device()

    def find_camera_device(self):
        """Find the correct camera device"""
        for i in range(10):
            dev = f"/dev/video{i}"
            if os.path.exists(dev):
                # Check if this is a camera device
                result = subprocess.run(
                    ["v4l2-ctl", "-d", dev, "--list-formats"],
                    capture_output=True, text=True
                )
                if "YUYV" in result.stdout or "MJPG" in result.stdout:
                    self.device = dev
                    print(f"Found camera at {dev}")
                    break

    def get_controls(self):
        """Get available camera controls"""
        result = subprocess.run(
            ["v4l2-ctl", "-d", self.device, "--list-ctrls"],
            capture_output=True, text=True
        )
        return result.stdout

    def set_manual_exposure(self, exposure_value=100):
        """Set manual exposure mode and value"""
        commands = [
            # Try to disable auto exposure
            ["v4l2-ctl", "-d", self.device, "--set-ctrl", "auto_exposure=1"],  # Manual mode
            ["v4l2-ctl", "-d", self.device, "--set-ctrl", "exposure_auto=1"],  # Alternative name

            # Set exposure value (lower = darker)
            ["v4l2-ctl", "-d", self.device, "--set-ctrl", f"exposure_absolute={exposure_value}"],
            ["v4l2-ctl", "-d", self.device, "--set-ctrl", f"exposure={exposure_value}"],

            # Set low gain
            ["v4l2-ctl", "-d", self.device, "--set-ctrl", "gain=0"],

            # Disable auto gain
            ["v4l2-ctl", "-d", self.device, "--set-ctrl", "autogain=0"],

            # Set brightness lower
            ["v4l2-ctl", "-d", self.device, "--set-ctrl", "brightness=64"],
        ]

        for cmd in commands:
            try:
                subprocess.run(cmd, capture_output=True, timeout=2)
            except:
                pass

    def capture_with_cam(self, output_path):
        """Capture using cam command"""
        # Try using cam command with current v4l2 settings
        cmd = [
            "cam", "-c", "0",
            "--capture=1",
            "--file=" + output_path,
            "-s", "width=1920,height=1080,role=still"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and os.path.exists(output_path):
                return True
        except:
            pass

        return False

    def capture_with_ffmpeg(self, output_path):
        """Capture using ffmpeg as alternative"""
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "v4l2",
            "-input_format", "mjpeg",
            "-video_size", "1920x1080",
            "-i", self.device,
            "-frames:v", "1",
            "-y",  # Overwrite
            output_path
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode == 0 and os.path.exists(output_path):
                return True
        except:
            pass

        return False

    def test_exposure_settings(self):
        """Test different exposure settings to find optimal value"""

        print("Testing camera exposure control with v4l2...")
        print("="*60)

        # Show available controls
        controls = self.get_controls()
        print("Available camera controls:")
        for line in controls.split('\n')[:20]:
            if 'exposure' in line.lower() or 'gain' in line.lower() or 'brightness' in line.lower():
                print(f"  {line.strip()}")

        print("\n" + "="*60)
        print("Testing different exposure values...")

        best_reading = None
        best_exposure = None
        best_saturation = 100

        # Test different exposure values
        test_exposures = [10, 25, 50, 100, 200, 400, 800]

        for exp_val in test_exposures:
            print(f"\nTesting exposure={exp_val}")

            # Set exposure
            self.set_manual_exposure(exp_val)
            time.sleep(1)  # Let camera adjust

            # Capture image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"/home/gmcmr2c/mri-cooling-camera/edge/images/v4l2_test_{exp_val}_{timestamp}.jpg"

            # Try different capture methods
            captured = False
            if self.capture_with_cam(output_path):
                captured = True
                print(f"  Captured with cam")
            elif self.capture_with_ffmpeg(output_path):
                captured = True
                print(f"  Captured with ffmpeg")
            else:
                print(f"  Failed to capture")
                continue

            if captured and os.path.exists(output_path):
                # Analyze image
                img = cv2.imread(output_path)
                if img is not None:
                    # Crop to ROI
                    x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
                    roi = img[y:y+h, x:x+w]

                    # Check saturation
                    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                    saturated = np.sum(gray >= 250) / gray.size * 100

                    print(f"  Saturation: {saturated:.1f}%")

                    # Try to decode
                    reading = self.decoder.decode_display(roi)
                    print(f"  Decoded: '{reading}'")

                    # Save crop for inspection
                    crop_path = output_path.replace('.jpg', '_crop.jpg')
                    cv2.imwrite(crop_path, roi)

                    # Check if this is the best so far
                    if saturated < best_saturation and saturated < 5.0:
                        best_saturation = saturated
                        best_exposure = exp_val
                        best_reading = reading
                        print(f"  ✓ New best!")

        print("\n" + "="*60)
        if best_exposure is not None:
            print(f"BEST RESULTS:")
            print(f"  Exposure: {best_exposure}")
            print(f"  Saturation: {best_saturation:.1f}%")
            print(f"  Reading: '{best_reading}'")
            print(f"\nTo use these settings:")
            print(f"  v4l2-ctl -d {self.device} --set-ctrl exposure_absolute={best_exposure}")
        else:
            print("No suitable exposure settings found.")
            print("The display may be too bright for software control alone.")
            print("Consider adding a neutral density filter.")

def main():
    """Test v4l2 camera control"""

    controller = V4L2CameraControl()
    controller.test_exposure_settings()

if __name__ == "__main__":
    main()