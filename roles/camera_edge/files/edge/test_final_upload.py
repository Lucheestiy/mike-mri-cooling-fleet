#!/usr/bin/env python3
"""
Test upload with the exact API format based on validation errors
"""

import requests
import json
import base64
import cv2
import numpy as np
from datetime import datetime, timezone
import time
import os
from dotenv import load_dotenv
from improved_ocr import ImprovedOCR

def create_correct_payload(pressure_value, confidence_score, image):
    """Create payload in the exact format the API expects"""

    load_dotenv()
    SITE_ID = os.getenv("SITE_ID", "GMCMR2")

    # Convert image to base64
    _, buffer = cv2.imencode('.jpg', image)
    image_b64 = base64.b64encode(buffer).decode('utf-8')

    # Create payload with all required fields based on validation errors
    payload = {
        "site_id": f"{SITE_ID}_TEST",
        "return_pressure": pressure_value,  # The actual pressure reading
        "confidence": confidence_score,     # Required field we discovered
        "timestamp": int(time.time()),      # Unix timestamp (integer, not ISO string)
        "image_full": image_b64,            # Base64 encoded image
        "metadata": {
            "camera": "rpicam-still",
            "exposure": "6ms",
            "gain": "10.0",
            "test_session": True
        }
    }

    return payload

def test_working_upload():
    """Test upload with correct API format"""

    print("🔍 Testing Final Upload Format")
    print("=" * 60)
    print("Using correct format based on API validation:")
    print("- return_pressure: float")
    print("- confidence: float (required)")
    print("- timestamp: integer (unix timestamp)")
    print("- image_full: base64 string")
    print("- site_id: string")

    # Create OCR system and capture a real image
    ocr = ImprovedOCR()

    print(f"\n📷 Capturing real LCD image...")
    image = ocr.capture_with_rpicam()

    if image is None:
        print("❌ Failed to capture image")
        return False

    # Get real reading from the image
    reading = ocr.extract_lcd_reading(image)
    print(f"📖 OCR Reading: '{reading}'")

    # Determine pressure and confidence
    if reading and reading not in ['NO_READ', 'NONE']:
        # Try to parse as pressure
        try:
            if reading.startswith('F'):
                # Fault code
                pressure = 0.0
                confidence = 0.9
                print(f"🚨 Fault code detected: {reading}")
            elif 'ECO' in reading.upper():
                # ECO mode
                pressure = 0.0
                confidence = 0.8
                print(f"🌱 ECO mode detected")
            else:
                # Try to parse as numeric
                cleaned = ''.join(c for c in reading if c.isdigit() or c == '.')
                if cleaned:
                    if '.' in cleaned:
                        pressure = float(cleaned)
                    else:
                        # Multi-digit like "23" -> "2.3"
                        if len(cleaned) >= 2:
                            pressure = float(f"{cleaned[0]}.{cleaned[1:]}")
                        else:
                            pressure = float(cleaned)
                    confidence = 0.85
                    print(f"📊 Pressure reading: {pressure} PSI")
                else:
                    pressure = 0.0
                    confidence = 0.3
        except:
            pressure = 0.0
            confidence = 0.3
    else:
        pressure = 0.0
        confidence = 0.1
        print(f"❌ No reading detected")

    # Create correct payload
    payload = create_correct_payload(pressure, confidence, image)

    print(f"\n📡 Uploading to API...")
    print(f"Site ID: {payload['site_id']}")
    print(f"Pressure: {payload['return_pressure']}")
    print(f"Confidence: {payload['confidence']}")
    print(f"Timestamp: {payload['timestamp']}")
    print(f"Image size: {len(payload['image_full'])} characters")

    try:
        session = requests.Session()
        session.timeout = 30

        response = session.post(
            "https://cam.coolmri.com/api/camera/pressure",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        print(f"\n📡 API Response:")
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            print("✅ SUCCESS! Upload worked perfectly!")
            print(f"Response: {response.text}")
            return True
        elif response.status_code == 422:
            print("❌ Still validation errors:")
            try:
                error_data = response.json()
                if 'detail' in error_data:
                    for error in error_data['detail']:
                        field = error.get('loc', ['unknown'])[-1]
                        msg = error.get('msg', 'Unknown')
                        input_val = str(error.get('input', ''))[:50]
                        print(f"  - {field}: {msg} (got: {input_val})")
            except:
                print(f"  Raw response: {response.text[:300]}")
        elif response.status_code == 413:
            print("❌ Image too large")
        else:
            print(f"❌ HTTP Error {response.status_code}")
            print(f"Response: {response.text[:200]}")

        return False

    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def test_multiple_uploads():
    """Test uploading multiple images from our test session"""

    print(f"\n" + "=" * 60)
    print("🔄 Testing Multiple Real Image Uploads")
    print("=" * 60)

    from pathlib import Path

    # Load some of our saved test images
    test_dir = Path("./images/test_session")
    if not test_dir.exists():
        print("❌ No test images found. Run test_10_local_save.py first")
        return

    crop_files = sorted(list(test_dir.glob("test_*_crop_*.jpg")))[:3]  # Test first 3

    if not crop_files:
        print("❌ No crop images found")
        return

    print(f"Testing {len(crop_files)} saved crop images...")

    ocr = ImprovedOCR()
    success_count = 0

    for i, crop_file in enumerate(crop_files):
        print(f"\n📷 Testing {crop_file.name}...")

        # Load the crop image
        crop_image = cv2.imread(str(crop_file))
        if crop_image is None:
            continue

        # Get reading from crop
        reading = ocr.decoder.decode_display(crop_image)

        # Create a fake "full" image with this crop in the center
        full_image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        h, w = crop_image.shape[:2]
        y_pos = (1080 - h) // 2
        x_pos = (1920 - w) // 2
        full_image[y_pos:y_pos+h, x_pos:x_pos+w] = crop_image

        # Determine pressure/confidence as before
        if reading and reading not in ['NO_READ', 'NONE']:
            if reading.startswith('F'):
                pressure, confidence = 0.0, 0.9
            elif any(x in reading.upper() for x in ['ECO', 'EC']):
                pressure, confidence = 0.0, 0.8
            else:
                try:
                    cleaned = ''.join(c for c in reading if c.isdigit() or c == '.')
                    if cleaned:
                        if '.' in cleaned:
                            pressure = float(cleaned)
                        elif len(cleaned) >= 2:
                            pressure = float(f"{cleaned[0]}.{cleaned[1:]}")
                        else:
                            pressure = float(cleaned)
                        confidence = 0.85
                    else:
                        pressure, confidence = 0.0, 0.3
                except:
                    pressure, confidence = 0.0, 0.3
        else:
            pressure, confidence = 0.0, 0.1

        print(f"  Reading: '{reading}' → {pressure} PSI (conf: {confidence})")

        # Create and upload payload
        payload = create_correct_payload(pressure, confidence, full_image)
        payload['site_id'] = f"GMCMR2_BATCH_{i+1:02d}"

        try:
            session = requests.Session()
            session.timeout = 20

            response = session.post(
                "https://cam.coolmri.com/api/camera/pressure",
                json=payload
            )

            if response.status_code == 200:
                print(f"  ✅ Upload successful!")
                success_count += 1
            else:
                print(f"  ❌ Upload failed: HTTP {response.status_code}")

        except Exception as e:
            print(f"  ❌ Upload error: {e}")

        time.sleep(1)  # Brief pause between uploads

    print(f"\n📊 Batch Upload Results: {success_count}/{len(crop_files)} successful")

    if success_count > 0:
        print("✅ Upload system is working!")
        print("You should now see test data on your website dashboard")
    else:
        print("❌ No uploads succeeded - check API format")

if __name__ == "__main__":
    # Test single upload first
    success = test_working_upload()

    # If that works, test multiple
    if success:
        test_multiple_uploads()
    else:
        print("\n⚠️ Single upload failed, skipping batch test")
        print("Check the API documentation for the correct format")