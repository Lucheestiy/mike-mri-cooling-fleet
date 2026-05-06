#!/usr/bin/env python3
"""
Test the correct upload format based on validation error
"""

import requests
import json
import base64
import cv2
import numpy as np
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

def create_test_payload():
    """Create test image and correct payload"""

    # Create a test image showing what we're testing
    test_image = np.zeros((182, 364, 3), dtype=np.uint8)  # Same size as ROI
    cv2.rectangle(test_image, (10, 10), (354, 172), (50, 50, 50), -1)  # Dark background
    cv2.putText(test_image, 'F95', (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 3, (255, 100, 100), 8)  # Red text

    _, buffer = cv2.imencode('.jpg', test_image)
    image_b64 = base64.b64encode(buffer).decode('utf-8')

    # Based on the validation error, the API expects 'return_pressure'
    payload = {
        "site_id": "GMCMR2_TEST",
        "return_pressure": 2.5,  # Changed from 'pressure' to 'return_pressure'
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "image_full": image_b64,
        "metadata": {
            "test": True,
            "camera": "rpicam-still",
            "exposure": "6ms",
            "gain": "10.0"
        }
    }

    return payload

def test_pressure_endpoint():
    """Test the pressure endpoint with correct format"""

    load_dotenv()

    print("🔍 Testing Correct Upload Format")
    print("=" * 50)

    payload = create_test_payload()

    print(f"Testing POST to: https://cam.coolmri.com/api/camera/pressure")
    print(f"Payload keys: {list(payload.keys())}")
    print(f"Site ID: {payload['site_id']}")
    print(f"Return Pressure: {payload['return_pressure']}")
    print(f"Image size: {len(payload['image_full'])} chars")

    try:
        session = requests.Session()
        session.timeout = 30

        response = session.post(
            "https://cam.coolmri.com/api/camera/pressure",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        print(f"\n📡 Response:")
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            print("✅ SUCCESS! Upload worked!")
            print(f"Response: {response.text}")
        elif response.status_code == 422:
            print("❌ VALIDATION ERROR - Still wrong format")
            print(f"Details: {response.text[:500]}")

            # Parse the error to see what's missing
            try:
                error_data = response.json()
                if 'detail' in error_data:
                    print("\n🔍 Missing/Invalid fields:")
                    for error in error_data['detail']:
                        field = error.get('loc', ['unknown'])[-1]
                        msg = error.get('msg', 'Unknown error')
                        print(f"  - {field}: {msg}")
            except:
                pass
        elif response.status_code == 413:
            print("❌ PAYLOAD TOO LARGE")
            print("Image might be too big for upload")
        else:
            print(f"❌ ERROR {response.status_code}")
            print(f"Response: {response.text[:200]}")

    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")

def test_image_upload_methods():
    """Try different methods to upload images"""

    print(f"\n" + "=" * 50)
    print("🔍 Testing Image Upload Methods")
    print("=" * 50)

    # Create a small test crop image
    crop_image = np.zeros((100, 200, 3), dtype=np.uint8)
    cv2.putText(crop_image, 'TEST', (50, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    _, crop_buffer = cv2.imencode('.png', crop_image)
    crop_b64 = base64.b64encode(crop_buffer).decode('utf-8')

    # Method 1: Try the old calibration approach with correct structure
    calibration_payload = {
        "site_id": "GMCMR2_TEST_CALIB",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "image_crop": crop_b64,
        "reading": "F95",
        "test_info": {
            "method": "calibration_test",
            "session": datetime.now().strftime("%Y%m%d_%H%M%S")
        }
    }

    print("Testing calibration-style upload...")
    try:
        session = requests.Session()
        session.timeout = 15

        # Since /api/camera/images only accepts GET, maybe there's a different endpoint
        # Let's try a few possibilities
        test_urls = [
            "https://cam.coolmri.com/api/camera/calibration",
            "https://cam.coolmri.com/api/calibration",
            "https://cam.coolmri.com/calibration"
        ]

        for url in test_urls:
            try:
                response = session.post(url, json=calibration_payload, timeout=10)
                print(f"  {url}: HTTP {response.status_code}")
                if response.status_code in [200, 422]:
                    print(f"    Found endpoint! Response: {response.text[:100]}")
                    break
            except:
                print(f"  {url}: Connection failed")

    except Exception as e:
        print(f"Error testing calibration uploads: {e}")

    print(f"\n💡 SUMMARY:")
    print("1. /api/camera/pressure accepts POST but needs 'return_pressure' field")
    print("2. /api/camera/images only accepts GET (retrieves images)")
    print("3. No obvious calibration upload endpoint found yet")
    print("4. You may need to check your backend API documentation")

if __name__ == "__main__":
    test_pressure_endpoint()
    test_image_upload_methods()