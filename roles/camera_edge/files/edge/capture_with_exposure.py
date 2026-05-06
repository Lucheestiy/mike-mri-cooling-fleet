#!/usr/bin/env python3
"""
Capture LCD display with manual exposure control using OpenCV
Designed to prevent overexposure and segment blooming
"""

import cv2
import numpy as np
import time
import os
import json
from pathlib import Path
from datetime import datetime
from seven_segment_ocr import SevenSegmentOCR

# Load configuration
from dotenv import load_dotenv
load_dotenv()
OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))

class ManualExposureCapture:
    """Camera capture with manual exposure control"""

    def __init__(self):
        self.cap = None
        self.decoder = SevenSegmentOCR(debug=False)

    def initialize_camera(self):
        """Initialize camera with manual exposure settings"""

        # Try different camera indices
        for index in [0, 1, 2]:
            self.cap = cv2.VideoCapture(index)
            if self.cap.isOpened():
                print(f"Camera opened on index {index}")
                break

        if not self.cap or not self.cap.isOpened():
            print("Failed to open camera with OpenCV")
            return False

        # Set resolution
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        # Try to set manual exposure
        # Note: These may not work on all systems
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # Manual exposure mode

        # Set very low exposure to prevent saturation
        # Values are camera-dependent, typically negative = darker
        for exposure_val in [-10, -8, -6, -4]:
            self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure_val)
            actual = self.cap.get(cv2.CAP_PROP_EXPOSURE)
            print(f"Tried exposure {exposure_val}, got {actual}")
            if abs(actual - exposure_val) < 1:
                break

        # Set low gain
        self.cap.set(cv2.CAP_PROP_GAIN, 0)

        # Disable auto white balance
        self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)

        # Let camera stabilize
        time.sleep(2)

        # Discard first few frames
        for _ in range(5):
            self.cap.read()

        return True

    def capture_and_analyze(self, save_path=None):
        """Capture frame and analyze exposure"""

        if not self.cap or not self.cap.isOpened():
            print("Camera not initialized")
            return None, None

        # Capture multiple frames and pick the best
        best_frame = None
        best_score = float('inf')

        for i in range(5):
            ret, frame = self.cap.read()
            if not ret:
                continue

            # Crop to ROI
            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            roi = frame[y:y+h, x:x+w]

            # Calculate saturation
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            saturated = np.sum(gray >= 250) / gray.size * 100

            # Score based on saturation (lower is better)
            score = saturated

            if score < best_score:
                best_score = score
                best_frame = frame

        if best_frame is None:
            print("Failed to capture frame")
            return None, None

        # Save if requested
        if save_path:
            cv2.imwrite(save_path, best_frame)

            # Also save the cropped ROI
            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            roi = best_frame[y:y+h, x:x+w]
            crop_path = save_path.replace('.jpg', '_crop.jpg')
            cv2.imwrite(crop_path, roi)

            print(f"Saved: {save_path}")
            print(f"Saved crop: {crop_path}")

        return best_frame, best_score

    def adaptive_exposure_capture(self):
        """Capture with adaptive exposure to find optimal settings"""

        if not self.cap or not self.cap.isOpened():
            if not self.initialize_camera():
                return None

        print("\nAdaptive exposure capture - finding optimal settings...")

        best_reading = None
        best_exposure = None

        # Try different exposure values
        exposure_values = [-12, -10, -8, -6, -4, -2, 0]

        for exp_val in exposure_values:
            print(f"\nTrying exposure: {exp_val}")

            # Set exposure
            self.cap.set(cv2.CAP_PROP_EXPOSURE, exp_val)
            time.sleep(0.5)  # Let it settle

            # Capture and analyze
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = f"/home/gmcmr2c/mri-cooling-camera/edge/images/adaptive_{exp_val}_{timestamp}.jpg"

            frame, saturation = self.capture_and_analyze(save_path)

            if frame is not None:
                print(f"  Saturation: {saturation:.1f}%")

                # Try to decode
                x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
                roi = frame[y:y+h, x:x+w]

                reading = self.decoder.decode_display(roi)
                print(f"  Decoded: '{reading}'")

                # Check if this is a good reading
                if reading and saturation < 5.0:
                    print(f"  ✓ Good candidate!")
                    if not best_reading or saturation < 1.0:
                        best_reading = reading
                        best_exposure = exp_val

                # If saturation is very low, we found good settings
                if saturation < 0.5:
                    print(f"  ✓✓ Excellent! Saturation < 0.5%")
                    break

        if best_exposure is not None:
            print(f"\n" + "="*50)
            print(f"OPTIMAL SETTINGS FOUND:")
            print(f"  Exposure: {best_exposure}")
            print(f"  Reading: '{best_reading}'")
            print(f"\nUse this exposure value in your capture scripts.")
        else:
            print("\nNo optimal settings found. Camera may not support manual exposure.")

        return best_reading

    def cleanup(self):
        """Release camera resources"""
        if self.cap:
            self.cap.release()

def main():
    """Test manual exposure capture"""

    capture = ManualExposureCapture()

    try:
        # Try adaptive exposure
        result = capture.adaptive_exposure_capture()

        if not result:
            print("\nFalling back to simple capture...")
            if capture.initialize_camera():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = f"/home/gmcmr2c/mri-cooling-camera/edge/images/manual_capture_{timestamp}.jpg"

                frame, saturation = capture.capture_and_analyze(save_path)
                if frame is not None:
                    print(f"\nCaptured with {saturation:.1f}% saturation")

                    # Try to decode
                    x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
                    roi = frame[y:y+h, x:x+w]

                    reading = capture.decoder.decode_display(roi)
                    print(f"Decoded: '{reading}'")

    finally:
        capture.cleanup()

if __name__ == "__main__":
    main()