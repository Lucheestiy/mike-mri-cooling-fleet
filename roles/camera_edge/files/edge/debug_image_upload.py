#!/usr/bin/env python3
"""
Debug script to test image upload with minimal payload
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

def test_minimal_image_upload():
    """Test upload with minimal image payload to debug server issue"""

    print("🔍 Testing Minimal Image Upload to Debug Server")
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

    # Create very small test images
    small_image = cv2.resize(image, (320, 240))  # Much smaller full image
    small_crop = cv2.resize(roi, (100, 50))      # Much smaller crop

    # Encode with lower quality
    _, full_buffer = cv2.imencode('.jpg', small_image, [cv2.IMWRITE_JPEG_QUALITY, 50])
    full_b64 = base64.b64encode(full_buffer).decode('utf-8')

    _, crop_buffer = cv2.imencode('.jpg', small_crop, [cv2.IMWRITE_JPEG_QUALITY, 50])
    crop_b64 = base64.b64encode(crop_buffer).decode('utf-8')

    print(f"📏 Small full image: {len(full_b64):,} chars ({len(full_b64)/1024:.1f} KB)")
    print(f"📏 Small crop image: {len(crop_b64):,} chars ({len(crop_b64)/1024:.1f} KB)")

    # Create minimal payload
    UPLOAD_URL = "https://cam.coolmri.com/api/camera/pressure"
    SITE_ID = os.getenv("SITE_ID", "GMCMR2")

    payload = {
        "site_id": f"{SITE_ID}_DEBUG_SMALL",
        "return_pressure": 1.23,
        "confidence": 0.95,
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "image_full": full_b64,
        "image_crop": crop_b64,
        "metadata": {
            "test_type": "debug_small_images",
            "full_size": f"{len(full_b64)} chars",
            "crop_size": f"{len(crop_b64)} chars",
            "debug_session": datetime.now().strftime("%Y%m%d_%H%M%S")
        }
    }

    print(f"\n🚀 Uploading small images to {UPLOAD_URL}")
    print(f"🏷️  Site ID: {SITE_ID}_DEBUG_SMALL")

    try:
        session = requests.Session()
        session.timeout = 30

        response = session.post(
            UPLOAD_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MRI-OCR-Pi-Debug/1.0"
            }
        )

        print(f"📊 Response: HTTP {response.status_code}")

        if response.status_code in [200, 201]:
            print("✅ Upload successful!")
            print("📝 Response body:", response.text[:200])
        else:
            print("❌ Upload failed")
            print("📝 Response body:", response.text[:200])

    except Exception as e:
        print(f"❌ Upload error: {e}")

def test_no_image_upload():
    """Test upload without any images to see if server expects them"""

    print("\n🔍 Testing Upload WITHOUT Images")
    print("=" * 50)

    UPLOAD_URL = "https://cam.coolmri.com/api/camera/pressure"
    SITE_ID = os.getenv("SITE_ID", "GMCMR2")

    payload = {
        "site_id": f"{SITE_ID}_DEBUG_NO_IMG",
        "return_pressure": 4.56,
        "confidence": 0.85,
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "metadata": {
            "test_type": "no_images",
            "debug_session": datetime.now().strftime("%Y%m%d_%H%M%S")
        }
    }

    print(f"🚀 Uploading without images to {UPLOAD_URL}")
    print(f"🏷️  Site ID: {SITE_ID}_DEBUG_NO_IMG")

    try:
        session = requests.Session()
        session.timeout = 30

        response = session.post(
            UPLOAD_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MRI-OCR-Pi-Debug/1.0"
            }
        )

        print(f"📊 Response: HTTP {response.status_code}")

        if response.status_code in [200, 201]:
            print("✅ Upload successful!")
            print("📝 Response body:", response.text[:200])
        else:
            print("❌ Upload failed")
            print("📝 Response body:", response.text[:200])

    except Exception as e:
        print(f"❌ Upload error: {e}")

def test_different_field_names():
    """Test upload with different image field names in case server expects different names"""

    print("\n🔍 Testing Different Image Field Names")
    print("=" * 50)

    ocr = ImprovedOCR()

    # Capture small image
    image = ocr.capture_with_rpicam()
    if image is None:
        print("❌ Failed to capture image")
        return

    # Very small image
    small_image = cv2.resize(image, (160, 120))
    _, buffer = cv2.imencode('.jpg', small_image, [cv2.IMWRITE_JPEG_QUALITY, 30])
    img_b64 = base64.b64encode(buffer).decode('utf-8')

    print(f"📏 Test image: {len(img_b64):,} chars ({len(img_b64)/1024:.1f} KB)")

    UPLOAD_URL = "https://cam.coolmri.com/api/camera/pressure"
    SITE_ID = os.getenv("SITE_ID", "GMCMR2")

    # Try different field name combinations
    test_cases = [
        {"image": img_b64},
        {"image_data": img_b64},
        {"full_image": img_b64},
        {"image_full": img_b64, "image_crop": img_b64}
    ]

    for i, image_fields in enumerate(test_cases, 1):
        payload = {
            "site_id": f"{SITE_ID}_DEBUG_FIELD_{i}",
            "return_pressure": i * 1.0,
            "confidence": 0.8,
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "metadata": {
                "test_type": f"field_test_{i}",
                "fields_used": list(image_fields.keys())
            }
        }

        # Add image fields
        payload.update(image_fields)

        print(f"\n🧪 Test {i}: Using fields {list(image_fields.keys())}")
        print(f"🏷️  Site ID: {SITE_ID}_DEBUG_FIELD_{i}")

        try:
            session = requests.Session()
            session.timeout = 30

            response = session.post(UPLOAD_URL, json=payload)

            if response.status_code in [200, 201]:
                print(f"✅ HTTP {response.status_code} - Success!")
            else:
                print(f"❌ HTTP {response.status_code} - Failed")

        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_minimal_image_upload()
    test_no_image_upload()
    test_different_field_names()

    print("\n" + "=" * 60)
    print("🔍 DEBUG RESULTS:")
    print("Check your server dashboard for these debug uploads:")
    print("- GMCMR2_DEBUG_SMALL (small images)")
    print("- GMCMR2_DEBUG_NO_IMG (no images)")
    print("- GMCMR2_DEBUG_FIELD_1-4 (different field names)")
    print("\nThis will help identify if the issue is:")
    print("1. Image size too large")
    print("2. Server not expecting image fields")
    print("3. Wrong field names for images")
    print("4. Server-side image processing bug")