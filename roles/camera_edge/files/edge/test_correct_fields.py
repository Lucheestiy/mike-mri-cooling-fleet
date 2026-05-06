#!/usr/bin/env python3
"""
Test upload with correct field names that server expects
"""

import cv2
import base64
import json
import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from improved_ocr import ImprovedOCR

load_dotenv()

def test_correct_field_names():
    """Test upload with server's expected field names"""

    print("🔍 Testing Correct Server Field Names")
    print("=" * 60)

    ocr = ImprovedOCR()

    # Capture image
    print("📷 Capturing image...")
    image = ocr.capture_with_rpicam()

    if image is None:
        print("❌ Failed to capture image")
        return

    # Get crop coordinates
    OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 708, "y": 520, "w": 364, "h": 182}'))
    x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
    roi = image[y:y+h, x:x+w]

    # Encode with good quality
    _, full_buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    full_b64 = base64.b64encode(full_buffer).decode('utf-8')

    _, crop_buffer = cv2.imencode('.jpg', roi, [cv2.IMWRITE_JPEG_QUALITY, 90])
    crop_b64 = base64.b64encode(crop_buffer).decode('utf-8')

    print(f"📏 Full image: {len(full_b64):,} chars ({len(full_b64)/1024:.1f} KB)")
    print(f"📏 Crop image: {len(crop_b64):,} chars ({len(crop_b64)/1024:.1f} KB)")

    UPLOAD_URL = "https://cam.coolmri.com/api/camera/pressure"
    SITE_ID = os.getenv("SITE_ID", "GMCMR2")

    # Get OCR reading
    reading = ocr.extract_lcd_reading(image)

    # Parse pressure
    if reading and reading not in ['NO_READ', 'NONE', None]:
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
                pressure = 0.0
                confidence = 0.3
        except:
            pressure = 0.0
            confidence = 0.3
    else:
        pressure = 0.0
        confidence = 0.1

    # Test different combinations of field names based on server response
    test_cases = [
        {
            "full_image_base64": full_b64,
            "cropped_image_base64": crop_b64,
            "test": "server_expected_fields"
        },
        {
            "full_image_base64": full_b64,
            "crop_image_base64": crop_b64,
            "test": "alt_crop_name"
        },
        {
            "image_full_base64": full_b64,
            "image_crop_base64": crop_b64,
            "test": "alt_format"
        }
    ]

    for i, image_fields in enumerate(test_cases, 1):
        payload = {
            "site_id": f"{SITE_ID}_CORRECT_{i}",
            "return_pressure": pressure,
            "confidence": confidence,
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "metadata": {
                "reading_detected": reading or "NONE",
                "test_type": image_fields.pop("test"),
                "camera": "rpicam-still",
                "crop_coords": OCR_CROP_COORDS
            }
        }

        # Add image fields
        payload.update(image_fields)

        print(f"\n🧪 Test {i}: Using fields {list(image_fields.keys())}")
        print(f"🏷️  Site ID: {SITE_ID}_CORRECT_{i}")
        print(f"📖 Reading: '{reading}' -> Pressure: {pressure}")

        try:
            session = requests.Session()
            session.timeout = 30

            response = session.post(
                UPLOAD_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "MRI-OCR-Pi-FieldTest/1.0"
                }
            )

            print(f"📊 Response: HTTP {response.status_code}")

            if response.status_code in [200, 201]:
                print("✅ Upload successful!")
                # Print more of the response to see field names
                response_text = response.text
                if len(response_text) > 500:
                    print("📝 Response (first 300 chars):", response_text[:300] + "...")
                    print("📝 Response (last 200 chars): ..." + response_text[-200:])
                else:
                    print("📝 Response body:", response_text)
            else:
                print("❌ Upload failed")
                print("📝 Response body:", response.text[:300])

        except Exception as e:
            print(f"❌ Upload error: {e}")

if __name__ == "__main__":
    test_correct_field_names()

    print("\n" + "=" * 60)
    print("🔍 FIELD NAME TEST RESULTS:")
    print("Check your server dashboard for uploads:")
    print("- GMCMR2_CORRECT_1 (full_image_base64, cropped_image_base64)")
    print("- GMCMR2_CORRECT_2 (full_image_base64, crop_image_base64)")
    print("- GMCMR2_CORRECT_3 (image_full_base64, image_crop_base64)")
    print("\nThe server response will show which fields are actually stored!")