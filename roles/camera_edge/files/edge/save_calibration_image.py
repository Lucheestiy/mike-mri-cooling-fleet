#!/usr/bin/env python3
"""
Save calibration images with clear naming for remote viewing
"""
import os
import json
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw
import numpy as np
import sys
sys.path.append('/usr/lib/python3/dist-packages')

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False

# Load config from .env
from dotenv import load_dotenv
load_dotenv()

OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))
IMAGE_WIDTH = int(os.getenv("IMAGE_WIDTH", "1920"))
IMAGE_HEIGHT = int(os.getenv("IMAGE_HEIGHT", "1080"))

def capture_and_save():
    """Capture and save calibration images with clear names"""
    print("📷 Capturing calibration image...")

    # Capture using libcamera command-line tools
    import subprocess
    import tempfile

    try:
        # Create temporary file for capture
        with tempfile.NamedTemporaryFile(suffix='.ppm', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        # Capture using cam command
        cmd = [
            'cam',
            '-c', '1',  # Camera 1 (imx708_wide)
            '--capture=1',  # Capture 1 frame
            f'--file={tmp_path}',  # Output file
            '--stream', f'width={IMAGE_WIDTH},height={IMAGE_HEIGHT},role=still,pixelformat=BGR888'
        ]

        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)

        if result.returncode == 0 and os.path.exists(tmp_path):
            # Load image
            with Image.open(tmp_path) as img:
                img_rgb = img.convert('RGB')

                # Save full image with crop region marked
                full_copy = img_rgb.copy()
                draw = ImageDraw.Draw(full_copy)
                x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
                draw.rectangle([x, y, x+w, y+h], outline="red", width=5)

                # Save with clear names
                images_dir = Path("images")
                images_dir.mkdir(exist_ok=True)

                full_path = images_dir / "CURRENT_FULL_VIEW.jpg"
                full_copy.save(full_path, quality=95)
                print(f"✅ Full camera view saved: {full_path}")

                # Save cropped region
                cropped = img_rgb.crop((x, y, x + w, y + h))
                crop_path = images_dir / "CURRENT_CROP_REGION.jpg"
                cropped.save(crop_path, quality=95)
                print(f"✅ Crop region saved: {crop_path}")

                print("\n" + "="*60)
                print("📸 CALIBRATION IMAGES SAVED")
                print("="*60)
                print(f"Full view: {full_path.absolute()}")
                print(f"Crop region: {crop_path.absolute()}")
                print(f"Current crop: x={x}, y={y}, w={w}, h={h}")
                print("\nTo adjust crop:")
                print("1. View the images above")
                print("2. Edit .env file: OCR_CROP_COORDS")
                print("3. Run this script again to test")
                print("="*60)

        else:
            print(f"❌ Capture failed: {result.stderr}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Clean up
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)

if __name__ == "__main__":
    capture_and_save()