#!/usr/bin/env python3
"""
Improved OCR script using rpicam-still and 7-segment decoding
Replaces Tesseract with deterministic 7-segment pattern matching
"""

import os
import time
import logging
import json
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import requests
from dotenv import load_dotenv
import subprocess
import tempfile
import cv2
import numpy as np
from PIL import Image

# Import our custom 7-segment decoder
from seven_segment_ocr import SevenSegmentOCR

# Load environment
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Configuration
BACKEND_URL = os.getenv("CAMERA_BACKEND_URL", "http://localhost:8001/api/camera/pressure")
SITE_ID = os.getenv("SITE_ID", "GMCMR2")
CAPTURE_INTERVAL = int(os.getenv("CAPTURE_INTERVAL", "60"))
IMAGE_WIDTH = int(os.getenv("IMAGE_WIDTH", "1920"))
IMAGE_HEIGHT = int(os.getenv("IMAGE_HEIGHT", "1080"))
OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))
DEBUG_SAVE_IMAGES = os.getenv("DEBUG_SAVE_IMAGES", "true").lower() == "true"
CALIBRATION_MODE = os.getenv("CALIBRATION_MODE", "false").lower() == "true"
CALIBRATION_URL = os.getenv("CALIBRATION_URL", "https://cam.coolmri.com/api/camera/images")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

class ImprovedOCR:
    """Improved OCR using rpicam-still and 7-segment decoding"""

    def __init__(self):
        self.decoder = SevenSegmentOCR(debug=DEBUG_SAVE_IMAGES)
        self.session = requests.Session()
        self.session.timeout = 30
        self.image_dir = Path(__file__).parent / "images"
        if DEBUG_SAVE_IMAGES:
            self.image_dir.mkdir(exist_ok=True)

    def capture_with_rpicam(self) -> Optional[np.ndarray]:
        """Capture image using rpicam-still with optimal settings"""

        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Optimal settings for LCD display (prevents segment overexposure)
            cmd = [
                'rpicam-still',
                '--shutter', '1500',    # 1.5ms exposure - prevents LCD clipping
                '--gain', '2.5',        # Lower gain to avoid overexposure
                '--awb', 'daylight',    # Fixed white balance
                '--denoise', 'off',     # No denoise for sharp segments
                '-o', tmp_path,
                '--width', str(IMAGE_WIDTH),
                '--height', str(IMAGE_HEIGHT),
                '--immediate',
                '-n',  # No preview
                '-t', '1'  # 1ms timeout
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            if result.returncode == 0 and os.path.exists(tmp_path):
                img = cv2.imread(tmp_path)
                return img
            else:
                logger.error(f"rpicam-still failed: {result.stderr[:200]}")
                return None

        except Exception as e:
            logger.error(f"Capture error: {e}")
            return None
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def extract_lcd_reading(self, image: np.ndarray) -> Optional[str]:
        """Extract LCD reading using 7-segment decoder"""

        # Crop to LCD region
        x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
        roi = image[y:y+h, x:x+w]

        # Analyze image quality
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        sat = np.sum(gray >= 250) / gray.size * 100
        mean_brightness = np.mean(gray)

        logger.info(f"ROI stats: saturation={sat:.1f}%, brightness={mean_brightness:.0f}")

        # Use 7-segment decoder
        reading = self.decoder.decode_display(roi)

        if reading:
            logger.info(f"7-segment decoded: '{reading}'")
            return reading
        else:
            logger.warning("No valid 7-segment pattern found")
            return None

    def parse_reading(self, text: str) -> Optional[float]:
        """Parse reading into a numeric value"""
        if not text:
            return None

        # Handle fault codes
        if text.startswith('F'):
            logger.warning(f"Fault code detected: {text}")
            return None

        # Handle ECO mode
        if 'ECO' in text.upper() or 'EC' in text.upper():
            logger.info("ECO mode detected")
            return None

        # Try to extract numeric value
        try:
            # Remove any non-digit/decimal characters and convert
            cleaned = ''.join(c for c in text if c.isdigit() or c == '.')
            if cleaned and '.' in cleaned:
                # Pressure reading like "7.5"
                return float(cleaned)
            elif cleaned and len(cleaned) >= 2:
                # Multi-digit reading like "95" -> assume decimal "9.5"
                if len(cleaned) == 2:
                    return float(f"{cleaned[0]}.{cleaned[1]}")
                else:
                    return float(cleaned)
        except (ValueError, IndexError):
            pass

        logger.warning(f"Could not parse reading: '{text}'")
        return None

    def send_reading(self, pressure: float, confidence: float, full_image: np.ndarray, crop_image: np.ndarray):
        """Send reading to backend with both full and cropped images"""

        # Convert both images to base64
        _, full_buffer = cv2.imencode('.jpg', full_image)
        full_b64 = base64.b64encode(full_buffer).decode('utf-8')

        _, crop_buffer = cv2.imencode('.jpg', crop_image)
        crop_b64 = base64.b64encode(crop_buffer).decode('utf-8')

        # Use correct API format
        payload = {
            "site_id": SITE_ID,
            "return_pressure": pressure,  # Correct field name
            "confidence": confidence,     # Required field
            "timestamp": int(time.time()), # Unix timestamp
            "full_image_base64": full_b64,
            "cropped_image_base64": crop_b64,       # OCR region for analysis
            "metadata": {
                "camera": "rpicam-still",
                "exposure": "3ms",
                "gain": "8.0",
                "decoder": "7-segment",
                "crop_coords": OCR_CROP_COORDS
            }
        }

        try:
            response = self.session.post(BACKEND_URL, json=payload)
            if response.status_code in [200, 201]:  # Accept both success codes
                logger.info("Reading sent successfully")
            else:
                logger.error(f"Backend error: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send reading: {e}")

    def send_calibration_images(self, full_image: np.ndarray, crop_image: np.ndarray):
        """Send images for calibration"""

        # Convert images to base64
        _, full_buffer = cv2.imencode('.jpg', full_image)
        full_b64 = base64.b64encode(full_buffer).decode('utf-8')

        _, crop_buffer = cv2.imencode('.png', crop_image)
        crop_b64 = base64.b64encode(crop_buffer).decode('utf-8')

        payload = {
            "site_id": SITE_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "image_full": full_b64,
            "image_crop": crop_b64,
            "crop_coords": OCR_CROP_COORDS
        }

        try:
            response = self.session.post(CALIBRATION_URL, json=payload)
            if response.status_code == 200:
                logger.info("Calibration images sent")
            else:
                logger.error(f"Calibration send failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Calibration send error: {e}")

    def run_single_capture(self):
        """Run single capture for testing"""

        logger.info("Running single capture with improved OCR...")

        # Capture image
        image = self.capture_with_rpicam()
        if image is None:
            logger.error("Failed to capture image")
            return

        # Extract LCD reading
        reading = self.extract_lcd_reading(image)

        # Save debug images if enabled
        if DEBUG_SAVE_IMAGES:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Save full image
            full_path = self.image_dir / f"improved_ocr_full_{timestamp}.jpg"
            cv2.imwrite(str(full_path), image)
            logger.info(f"Full image saved: {full_path}")

            # Save crop
            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            roi = image[y:y+h, x:x+w]
            crop_path = self.image_dir / f"improved_ocr_crop_{timestamp}.jpg"
            cv2.imwrite(str(crop_path), roi)
            logger.info(f"Crop saved: {crop_path}")

        # Parse and report
        if reading:
            pressure = self.parse_reading(reading)
            if pressure is not None:
                logger.info(f"✓ Pressure reading: {pressure} PSI")
            else:
                logger.info(f"✓ Display reading: '{reading}' (non-numeric)")
        else:
            logger.warning("✗ No reading detected")

    def run_calibration_mode(self):
        """Run calibration mode"""

        logger.info("Running calibration mode with improved OCR...")
        logger.info("Sending images every 5 seconds for remote calibration")
        logger.info("Press Ctrl+C to stop")

        try:
            while True:
                # Capture image
                image = self.capture_with_rpicam()
                if image is not None:
                    # Extract crop
                    x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
                    roi = image[y:y+h, x:x+w]

                    # Try to decode
                    reading = self.extract_lcd_reading(image)
                    logger.info(f"Current reading: '{reading}'")

                    # Send for calibration
                    self.send_calibration_images(image, roi)
                else:
                    logger.error("Capture failed")

                time.sleep(5)

        except KeyboardInterrupt:
            logger.info("Calibration mode stopped")

    def run_production_mode(self):
        """Run production monitoring"""

        logger.info("Running production mode with improved OCR...")
        logger.info(f"Checking every {CAPTURE_INTERVAL} seconds")

        try:
            while True:
                # Capture image
                image = self.capture_with_rpicam()
                if image is not None:
                    # Extract reading
                    reading = self.extract_lcd_reading(image)
                    pressure = self.parse_reading(reading) if reading else None

                    if pressure is not None:
                        # Convert to base64 for transmission
                        _, buffer = cv2.imencode('.jpg', image)
                        image_b64 = base64.b64encode(buffer).decode('utf-8')

                        # Send reading
                        self.send_reading(pressure, image_b64)
                        logger.info(f"✓ Sent: {pressure} PSI")
                    else:
                        logger.warning(f"Non-numeric reading: '{reading}'")
                else:
                    logger.error("Capture failed")

                time.sleep(CAPTURE_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Production mode stopped")

def main():
    """Main entry point"""
    import sys

    ocr = ImprovedOCR()

    if "--single" in sys.argv:
        ocr.run_single_capture()
    elif "--calibrate" in sys.argv or CALIBRATION_MODE:
        ocr.run_calibration_mode()
    else:
        ocr.run_production_mode()

if __name__ == "__main__":
    main()