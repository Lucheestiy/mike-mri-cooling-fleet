#!/usr/bin/env python3
"""
Test robust upload with retry logic and error handling for 99%+ success rate
"""

import time
import logging
import base64
import json
import os
from datetime import datetime, timezone
from improved_ocr import ImprovedOCR
import cv2
import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging for better error tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_robust_session():
    """Create HTTP session with retry logic and timeouts"""
    session = requests.Session()

    # Configure retry strategy
    retry_strategy = Retry(
        total=3,  # Total number of retries
        backoff_factor=1,  # Wait 1s, then 2s, then 4s between retries
        status_forcelist=[502, 503, 504, 429, 500],  # HTTP codes to retry on
        allowed_methods=["POST"]  # Only retry POST requests
    )

    # Mount adapter with retry strategy
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # Set reasonable timeouts
    session.timeout = (10, 30)  # (connect timeout, read timeout)

    return session

def upload_with_retry(payload, max_attempts=3):
    """Upload with robust retry logic"""

    UPLOAD_URL = "https://cam.coolmri.com/api/camera/pressure"

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"Upload attempt {attempt}/{max_attempts}")

            session = create_robust_session()

            response = session.post(
                UPLOAD_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "MRI-OCR-Pi/1.0"
                }
            )

            # Success codes
            if response.status_code in [200, 201]:
                logger.info(f"✅ Upload successful on attempt {attempt}")
                return True, f"Success (HTTP {response.status_code})"

            # Server errors - worth retrying
            elif response.status_code in [500, 502, 503, 504]:
                logger.warning(f"Server error {response.status_code}, attempt {attempt}/{max_attempts}")
                if attempt < max_attempts:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    return False, f"Server error after {max_attempts} attempts (HTTP {response.status_code})"

            # Client errors - don't retry
            elif response.status_code in [400, 401, 403, 404, 422]:
                logger.error(f"Client error {response.status_code}: {response.text[:100]}")
                return False, f"Client error (HTTP {response.status_code})"

            # Other errors
            else:
                logger.error(f"Unexpected status {response.status_code}")
                return False, f"Unexpected error (HTTP {response.status_code})"

        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error on attempt {attempt}: {e}")
            if attempt < max_attempts:
                time.sleep(2 ** attempt)
                continue
            else:
                return False, f"Connection failed after {max_attempts} attempts"

        except requests.exceptions.Timeout as e:
            logger.warning(f"Timeout on attempt {attempt}: {e}")
            if attempt < max_attempts:
                time.sleep(2 ** attempt)
                continue
            else:
                return False, f"Timeout after {max_attempts} attempts"

        except Exception as e:
            logger.error(f"Unexpected error on attempt {attempt}: {e}")
            if attempt < max_attempts:
                time.sleep(2 ** attempt)
                continue
            else:
                return False, f"Unexpected error: {str(e)[:50]}"

    return False, "Max attempts exceeded"

def send_robust_upload(image, crop, reading, capture_num, timestamp):
    """Send upload with robust error handling"""

    from dotenv import load_dotenv
    load_dotenv()

    SITE_ID = os.getenv("SITE_ID", "GMCMR2")

    try:
        # Convert images to base64 with error handling
        _, full_buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        full_b64 = base64.b64encode(full_buffer).decode('utf-8')

        _, crop_buffer = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        crop_b64 = base64.b64encode(crop_buffer).decode('utf-8')

        logger.info(f"Image sizes: Full={len(full_b64)} chars, Crop={len(crop_b64)} chars")

    except Exception as e:
        logger.error(f"Failed to encode images: {e}")
        return False, "Image encoding failed"

    # Parse reading with robust handling
    if reading and reading not in ['NO_READ', 'NONE', None]:
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

    # Create robust payload
    payload = {
        "site_id": f"{SITE_ID}_ROBUST_{capture_num:02d}",
        "return_pressure": pressure,
        "confidence": confidence,
        "timestamp": int(timestamp.timestamp()),
        "full_image_base64": full_b64,
        "cropped_image_base64": crop_b64,
        "metadata": {
            "test_capture": capture_num,
            "reading_detected": reading or "NONE",
            "test_session": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "camera": "rpicam-still",
            "exposure": "3ms",
            "gain": "8.0",
            "crop_coords": json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 708, "y": 520, "w": 364, "h": 182}')),
            "upload_version": "robust_v1"
        }
    }

    # Validate payload size
    payload_size = len(json.dumps(payload))
    if payload_size > 10_000_000:  # 10MB limit
        logger.warning(f"Large payload: {payload_size:,} bytes")

    return upload_with_retry(payload, max_attempts=3)

def test_robust_uploads():
    """Test robust upload system with 15 captures for reliability testing"""

    print("🔄 Testing Robust Upload System (Target: 99%+ Success Rate)")
    print("=" * 70)
    print("Features:")
    print("- Automatic retry on server errors (500, 502, 503, 504)")
    print("- Exponential backoff between retries")
    print("- Connection timeout handling")
    print("- Payload size validation")
    print("- Detailed error logging")
    print()

    ocr = ImprovedOCR()
    results = []
    total_attempts = 0
    successful_uploads = 0

    # Test with 15 captures to get good statistics
    for i in range(1, 16):
        print(f"📷 Capture {i}/15...")

        # Capture image
        image = ocr.capture_with_rpicam()

        if image is not None:
            # Extract ROI
            from dotenv import load_dotenv
            load_dotenv()
            OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 708, "y": 520, "w": 364, "h": 182}'))

            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            roi = image[y:y+h, x:x+w]

            # Get OCR reading
            old_level = logging.getLogger('seven_segment_ocr').level
            logging.getLogger('seven_segment_ocr').setLevel(logging.ERROR)
            reading = ocr.extract_lcd_reading(image)
            logging.getLogger('seven_segment_ocr').setLevel(old_level)

            # Upload with robust retry
            timestamp = datetime.now(timezone.utc)
            success, error_msg = send_robust_upload(image, roi, reading, i, timestamp)

            total_attempts += 1
            if success:
                successful_uploads += 1
                print(f"    ✅ Upload successful")
            else:
                print(f"    ❌ Upload failed: {error_msg}")

            print(f"    📖 Reading: '{reading}'")
            print(f"    🏷️  Site ID: GMCMR2_ROBUST_{i:02d}")

            results.append({
                'capture': i,
                'reading': reading,
                'uploaded': success,
                'error': error_msg if not success else None,
                'site_id': f"GMCMR2_ROBUST_{i:02d}"
            })
        else:
            print(f"    ❌ Camera capture failed")
            results.append({
                'capture': i,
                'reading': 'CAPTURE_FAILED',
                'uploaded': False,
                'error': 'Camera capture failed',
                'site_id': f"GMCMR2_ROBUST_{i:02d}"
            })

        print()
        time.sleep(1)  # Shorter interval for stress test

    # Calculate reliability statistics
    success_rate = (successful_uploads / total_attempts) * 100 if total_attempts > 0 else 0

    print("=" * 70)
    print("📊 ROBUST UPLOAD RELIABILITY TEST RESULTS")
    print("=" * 70)

    print(f"✅ Total uploads attempted: {total_attempts}")
    print(f"✅ Successful uploads: {successful_uploads}")
    print(f"📈 Success Rate: {success_rate:.1f}%")

    if success_rate >= 99.0:
        print("🎉 EXCELLENT: 99%+ reliability achieved!")
    elif success_rate >= 95.0:
        print("✅ GOOD: 95%+ reliability achieved")
    elif success_rate >= 90.0:
        print("⚠️ FAIR: 90%+ reliability achieved")
    else:
        print("❌ NEEDS WORK: <90% reliability")

    # Error analysis
    failures = [r for r in results if not r['uploaded']]
    if failures:
        print(f"\n❌ FAILURE ANALYSIS:")
        error_types = {}
        for failure in failures:
            error = failure['error']
            error_types[error] = error_types.get(error, 0) + 1

        for error, count in error_types.items():
            print(f"  - {error}: {count} times")

    # Success distribution
    successful_readings = [r for r in results if r['uploaded'] and r['reading'] not in ['NO_READ', 'CAPTURE_FAILED']]
    if successful_readings:
        print(f"\n📖 SUCCESSFUL OCR READINGS:")
        reading_counts = {}
        for r in successful_readings:
            reading = r['reading']
            reading_counts[reading] = reading_counts.get(reading, 0) + 1

        for reading, count in sorted(reading_counts.items(), key=lambda x: (x[0] is None, x[0])):
            print(f"  '{reading}': {count} times")

    print(f"\n🌐 UPLOADED SITE IDs:")
    successful_uploads_list = [r for r in results if r['uploaded']]
    for r in successful_uploads_list:
        print(f"  - {r['site_id']} ✅")

    if failures:
        print(f"\n❌ FAILED SITE IDs:")
        for r in failures:
            print(f"  - {r['site_id']} ❌ ({r['error']})")

    print(f"\n💡 RECOMMENDATIONS:")
    if success_rate >= 99.0:
        print("System is ready for production deployment!")
    elif success_rate >= 95.0:
        print("System is nearly ready. Monitor for occasional failures.")
    else:
        print("Need to investigate and fix reliability issues before production.")
        print("Check network stability, server capacity, and error patterns.")

    return results

if __name__ == "__main__":
    test_robust_uploads()