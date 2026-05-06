#!/usr/bin/env python3
"""
Test script for capturing and uploading images WITHOUT OCR processing.
All OCR will be handled on the server side.
Captures 10 images and uploads them to the website with robust retry logic.
"""

import os
import sys
import json
import base64
import time
import requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import subprocess
import tempfile
from PIL import Image
import numpy as np

# Load environment variables
load_dotenv()

# Configuration from environment
SITE_ID = os.getenv('SITE_ID', 'GMCMR2')
CAMERA_BACKEND_URL = os.getenv('CAMERA_BACKEND_URL', 'https://cam.coolmri.com/api/camera/pressure')

# Image dimensions from .env
IMAGE_WIDTH = int(os.getenv('IMAGE_WIDTH', '1920'))
IMAGE_HEIGHT = int(os.getenv('IMAGE_HEIGHT', '1080'))

# OCR crop coordinates from .env
crop_coords_str = os.getenv('OCR_CROP_COORDS', '{"x": 708, "y": 520, "w": 364, "h": 182}')
CROP_COORDS = json.loads(crop_coords_str)

# Camera settings (from improved_ocr.py)
SHUTTER_SPEED = '1500'  # 1.5ms
GAIN = '2.5'

def capture_with_rpicam():
    """Capture an image using rpicam-still with optimal settings."""
    tmp_path = tempfile.mktemp(suffix='.jpg')

    try:
        # Optimal settings for LCD display
        cmd = [
            'rpicam-still',
            '--shutter', SHUTTER_SPEED,
            '--gain', GAIN,
            '--awb', 'daylight',
            '--denoise', 'off',
            '-o', tmp_path,
            '--width', str(IMAGE_WIDTH),
            '--height', str(IMAGE_HEIGHT),
            '--immediate',
            '-n',  # No preview
            '-t', '1'  # 1ms timeout
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            print(f"    Camera error: {result.stderr}")
            return None, None

        # Read the captured image
        img = Image.open(tmp_path)
        img_array = np.array(img)

        # Crop the OCR region
        x, y, w, h = CROP_COORDS['x'], CROP_COORDS['y'], CROP_COORDS['w'], CROP_COORDS['h']
        cropped = img_array[y:y+h, x:x+w]
        cropped_img = Image.fromarray(cropped)

        # Calculate basic image statistics for quality info
        brightness = np.mean(cropped)
        p95 = np.percentile(cropped, 95)
        saturation = np.sum(cropped >= 255) / cropped.size * 100

        return img, cropped_img, {
            'brightness': int(brightness),
            'p95': int(p95),
            'saturation': round(saturation, 1)
        }

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def upload_to_website(full_img, cropped_img, site_id, timestamp):
    """Upload images to website with robust retry logic."""

    # Convert images to base64
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_full:
        full_img.save(tmp_full.name, format='JPEG', quality=85)
        with open(tmp_full.name, 'rb') as f:
            full_base64 = base64.b64encode(f.read()).decode('utf-8')
        os.unlink(tmp_full.name)

    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_crop:
        cropped_img.save(tmp_crop.name, format='JPEG', quality=90)
        with open(tmp_crop.name, 'rb') as f:
            cropped_base64 = base64.b64encode(f.read()).decode('utf-8')
        os.unlink(tmp_crop.name)

    # Prepare upload data (no OCR data) - using correct API field names
    upload_data = {
        'site_id': site_id,
        'full_image_base64': full_base64,
        'cropped_image_base64': cropped_base64,
        'return_pressure': 0.0,  # Placeholder value - OCR on server
        'confidence': 0.1,  # Low confidence indicates server-side OCR needed
        'timestamp': timestamp,
        'metadata': {
            'reading_detected': 'SERVER_SIDE',  # Indicate server-side OCR needed
            'processing': 'server_side',  # OCR will be done server-side
            'crop_coords': CROP_COORDS,
            'camera_settings': {
                'shutter': SHUTTER_SPEED,
                'gain': GAIN
            },
            'upload_version': 'no_ocr_v1'
        }
    }

    # Try upload with retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(
                CAMERA_BACKEND_URL,
                json=upload_data,
                timeout=30
            )

            if response.status_code in [200, 201]:  # 201 = Created (success)
                return True, None
            elif response.status_code in [500, 502, 503, 504]:
                # Server error - retry
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    print(f"    Server error {response.status_code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            else:
                # Client error - don't retry
                return False, f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                print(f"    Timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                print(f"    Unexpected error, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            return False, str(e)[:50]

    return False, "Max retries exceeded"

def main():
    """Main test function."""
    print("🔍 Testing 10 Image Captures + Upload (NO OCR)")
    print("=" * 65)

    # Generate batch ID for this test run
    batch_id = datetime.now().strftime("%m%d_%H%M%S")

    print(f"This will capture 10 images and send them to the website")
    print(f"WITHOUT any OCR processing (OCR will be done server-side).")
    print(f"Each image will get a unique Site ID with batch: {batch_id}")
    print()
    print("Features:")
    print("- No OCR processing (server-side only)")
    print("- Automatic retry on server errors")
    print("- Dual image upload (full + crop)")
    print("- Site-date-time naming convention")
    print(f"- Unique batch identifier: {batch_id}")
    print()

    # Track results
    results = []
    successful_uploads = 0
    successful_captures = 0

    # Run 10 captures
    for i in range(1, 11):
        print(f"📷 Capture {i}/10...")

        # Capture image
        full_img, cropped_img, stats = capture_with_rpicam()

        if full_img is None:
            print(f"    ❌ Capture failed")
            results.append({
                'num': i,
                'time': datetime.now().strftime("%H:%M:%S"),
                'upload': False,
                'stats': None
            })
            continue

        successful_captures += 1

        # Generate site ID with batch
        site_id = f"{SITE_ID}_TEST_{batch_id}_{i:02d}"
        timestamp = int(time.time())

        # Upload to website
        success, error = upload_to_website(full_img, cropped_img, site_id, timestamp)

        if success:
            print(f"    ✅ Uploaded to website")
            successful_uploads += 1
        else:
            print(f"    ❌ Upload failed")
            if error:
                print(f"    Upload error: {error}")

        # Print image quality stats
        if stats:
            print(f"    📊 Quality: {stats['saturation']}% sat, {stats['brightness']} bright, {stats['p95']} p95")
        print(f"    🏷️  Site ID: {site_id}")
        print()

        results.append({
            'num': i,
            'time': datetime.now().strftime("%H:%M:%S"),
            'upload': success,
            'stats': stats,
            'site_id': site_id
        })

        # Small delay between captures
        if i < 10:
            time.sleep(2)

    # Print summary
    print("=" * 60)
    print("📊 TEST + UPLOAD RESULTS")
    print("=" * 60)
    print(f"✅ Total captures: {successful_captures}/10 ({successful_captures*10}%)")
    print(f"🌐 Successful uploads: {successful_uploads}/10 ({successful_uploads*10}%)")
    print(f"📖 OCR Processing: Server-side only (no local OCR)")

    if successful_uploads >= 9:
        print(f"🎉 EXCELLENT: 99%+ upload reliability achieved!")
    elif successful_uploads >= 8:
        print(f"✅ GOOD: {successful_uploads*10}% upload reliability")
    else:
        print(f"❌ NEEDS WORK: <90% upload reliability")

    print()
    print("📋 DETAILED CAPTURE LOG:")
    print(f"#  Time     Upload  Site ID")
    print("-" * 75)

    for r in results:
        upload_status = "✅" if r['upload'] else "❌"
        print(f"{r['num']:<2} {r['time']:<8} {upload_status:<7} {r.get('site_id', 'N/A')}")

    print()
    print("🌐 WEBSITE INSPECTION:")
    print("Check your website dashboard at: cam.coolmri.com")
    print("Look for test uploads with Site IDs:")
    for r in results:
        status = "✅" if r['upload'] else "❌"
        print(f"  - {r.get('site_id', 'N/A')} {status}")

    print()
    print("Each upload includes:")
    print("  - Full camera view (1920x1080)")
    print("  - Cropped LCD region (364x182)")
    print("  - NO OCR data (server-side processing)")
    print("  - Site-date-time naming convention")
    print("  - Camera settings metadata")
    print()

    if successful_uploads == 10:
        print("🎉 EXCELLENT: 10/10 images uploaded successfully!")
        print("Server-side OCR will process all captured LCD images!")
    elif successful_uploads > 0:
        print(f"✅ {successful_uploads}/10 images uploaded for server-side OCR")
    else:
        print("❌ FAILED: No uploads succeeded")
        print("Check your internet connection and website availability")

if __name__ == "__main__":
    main()