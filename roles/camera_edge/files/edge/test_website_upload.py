#!/usr/bin/env python3
"""
Test the correct website upload endpoints
"""

import requests
import json
import base64
import cv2
import numpy as np
from datetime import datetime, timezone
import os
from dotenv import load_dotenv

def test_upload_endpoints():
    """Test both upload endpoints to see which ones work"""

    load_dotenv()
    SITE_ID = os.getenv("SITE_ID", "GMCMR2")

    # Create a simple test image
    test_image = np.ones((100, 200, 3), dtype=np.uint8) * 128  # Gray image
    cv2.putText(test_image, 'TEST', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    _, buffer = cv2.imencode('.jpg', test_image)
    image_b64 = base64.b64encode(buffer).decode('utf-8')

    print("🔍 Testing Website Upload Endpoints")
    print("=" * 60)

    # Test endpoints
    endpoints = [
        {
            'name': 'Calibration (images)',
            'url': 'https://cam.coolmri.com/api/camera/images',
            'method': 'GET',  # We know this works from curl test
            'data': None
        },
        {
            'name': 'Pressure readings',
            'url': 'https://cam.coolmri.com/api/camera/pressure',
            'method': 'POST',  # We know this accepts POST
            'data': {
                "site_id": SITE_ID + "_TEST",
                "pressure": 2.5,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "image_full": image_b64,
                "metadata": {"test": True}
            }
        }
    ]

    session = requests.Session()
    session.timeout = 10

    for endpoint in endpoints:
        print(f"\n📡 Testing {endpoint['name']}")
        print(f"URL: {endpoint['url']}")
        print(f"Method: {endpoint['method']}")

        try:
            if endpoint['method'] == 'GET':
                response = session.get(endpoint['url'])
            elif endpoint['method'] == 'POST':
                response = session.post(endpoint['url'], json=endpoint['data'])

            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                print("✅ SUCCESS")
                if len(response.text) < 200:
                    print(f"Response: {response.text}")
                else:
                    print(f"Response: {response.text[:200]}...")
            elif response.status_code == 405:
                print("❌ METHOD NOT ALLOWED")
                print("This endpoint doesn't accept this HTTP method")
            elif response.status_code == 422:
                print("⚠️  VALIDATION ERROR")
                print("Endpoint exists but data format is wrong")
                print(f"Response: {response.text[:200]}")
            else:
                print(f"❌ ERROR: {response.status_code}")
                print(f"Response: {response.text[:200]}")

        except requests.exceptions.RequestException as e:
            print(f"❌ CONNECTION ERROR: {e}")

    print(f"\n" + "=" * 60)
    print("🔍 ENDPOINT DISCOVERY")
    print("=" * 60)

    # Try to discover more endpoints
    common_paths = [
        '/api',
        '/api/camera',
        '/api/camera/calibration',
        '/api/camera/upload',
        '/api/upload'
    ]

    print("Testing common API paths...")
    for path in common_paths:
        url = f"https://cam.coolmri.com{path}"
        try:
            response = session.get(url, timeout=5)
            if response.status_code in [200, 405, 422]:
                print(f"✅ Found: {url} (HTTP {response.status_code})")
            elif response.status_code == 404:
                print(f"❌ Not found: {url}")
        except:
            print(f"❌ Error: {url}")

    print(f"\n💡 RECOMMENDATIONS:")
    print("Based on the curl tests:")
    print("1. /api/camera/images accepts GET (returns existing images)")
    print("2. /api/camera/pressure accepts POST (for pressure data)")
    print("3. Both endpoints are working but may need specific data formats")
    print("\nFor image uploads, we likely need:")
    print("- Correct Content-Type headers")
    print("- Proper payload structure")
    print("- Maybe multipart/form-data instead of JSON")

if __name__ == "__main__":
    test_upload_endpoints()