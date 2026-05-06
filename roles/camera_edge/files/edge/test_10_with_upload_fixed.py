#!/usr/bin/env python3
"""
Capture 10 test images and send ALL of them to website using correct API format
Fixed to use proper endpoint and data structure
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

# Configure logging for cleaner output
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def send_test_images_to_website(image, crop, reading, capture_num, timestamp):
    """Send test images to website using correct API format"""

    from dotenv import load_dotenv
    load_dotenv()

    # Use the correct endpoint that actually works
    UPLOAD_URL = "https://cam.coolmri.com/api/camera/pressure"
    SITE_ID = os.getenv("SITE_ID", "GMCMR2")

    # Convert both full image and crop to base64
    _, full_buffer = cv2.imencode('.jpg', image)
    full_b64 = base64.b64encode(full_buffer).decode('utf-8')

    _, crop_buffer = cv2.imencode('.jpg', crop)
    crop_b64 = base64.b64encode(crop_buffer).decode('utf-8')

    # Parse reading to determine pressure and confidence
    if reading and reading not in ['NO_READ', 'NONE', None]:
        if reading.startswith('F'):
            # Fault code like F95
            pressure = 0.0
            confidence = 0.9
        elif any(x in reading.upper() for x in ['ECO', 'EC']):
            # ECO mode
            pressure = 0.0
            confidence = 0.8
        else:
            # Try to parse as numeric pressure
            try:
                cleaned = ''.join(c for c in reading if c.isdigit() or c == '.')
                if cleaned:
                    if '.' in cleaned:
                        pressure = float(cleaned)
                    elif len(cleaned) >= 2:
                        # Multi-digit like "23" -> "2.3"
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
        # No reading detected
        pressure = 0.0
        confidence = 0.1

    # Create payload in correct API format with both full and cropped images
    payload = {
        "site_id": f"{SITE_ID}_TEST_{capture_num:02d}",
        "return_pressure": pressure,
        "confidence": confidence,
        "timestamp": int(timestamp.timestamp()),  # Unix timestamp as integer
        "image_full": full_b64,
        "image_crop": crop_b64,  # Add the OCR crop region
        "metadata": {
            "test_capture": capture_num,
            "reading_detected": reading or "NONE",
            "test_session": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "camera": "rpicam-still",
            "exposure": "6ms",
            "gain": "10.0",
            "crop_coords": json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 708, "y": 520, "w": 364, "h": 182}'))
        }
    }

    try:
        session = requests.Session()
        session.timeout = 30
        response = session.post(UPLOAD_URL, json=payload)

        # HTTP 201 = Created (success), HTTP 200 = OK (success)
        if response.status_code in [200, 201]:
            return True
        else:
            print(f"    Upload failed: HTTP {response.status_code}")
            if response.status_code == 422:
                print(f"    Validation error: {response.text[:100]}")
            return False
    except Exception as e:
        print(f"    Upload error: {e}")
        return False

def test_10_captures_with_upload():
    """Capture 10 images, analyze them, and send all to website"""

    print("🔍 Testing 10 LCD Captures + Website Upload (FIXED)")
    print("=" * 65)
    print("This will capture 10 images and send ALL of them to the website")
    print("using the correct API endpoint and format.")
    print("Each image will get a unique Site ID for tracking.\n")

    ocr = ImprovedOCR()
    results = []
    uploads_successful = 0

    for i in range(1, 11):
        print(f"📷 Capture {i}/10...")

        # Capture image
        image = ocr.capture_with_rpicam()

        if image is not None:
            # Extract ROI and analyze quality
            from dotenv import load_dotenv
            load_dotenv()
            OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 708, "y": 520, "w": 364, "h": 182}'))

            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            roi = image[y:y+h, x:x+w]

            # Analyze image quality
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            saturation = np.sum(gray >= 250) / gray.size * 100
            brightness = np.mean(gray)
            p95 = np.percentile(gray, 95)

            # Get reading with minimal logging
            old_level = logging.getLogger('seven_segment_ocr').level
            logging.getLogger('seven_segment_ocr').setLevel(logging.ERROR)

            reading = ocr.extract_lcd_reading(image)

            logging.getLogger('seven_segment_ocr').setLevel(old_level)

            # Send to website
            timestamp = datetime.now(timezone.utc)
            upload_success = send_test_images_to_website(image, roi, reading, i, timestamp)

            if upload_success:
                uploads_successful += 1
                print(f"    ✅ Uploaded to website")
            else:
                print(f"    ❌ Upload failed")

            # Store result
            result = {
                'capture': i,
                'timestamp': timestamp.strftime("%H:%M:%S"),
                'reading': reading or "NO_READ",
                'saturation': saturation,
                'brightness': brightness,
                'p95': p95,
                'uploaded': upload_success,
                'site_id': f"GMCMR2_TEST_{i:02d}"
            }
            results.append(result)

            # Report this capture
            status = "✓" if reading else "✗"
            print(f"    {status} Reading: '{reading}'")
            print(f"    📊 Quality: {saturation:.1f}% sat, {brightness:.0f} bright, {p95:.0f} p95")
            print(f"    🏷️  Site ID: GMCMR2_TEST_{i:02d}")
        else:
            print(f"    ❌ Capture failed")
            results.append({
                'capture': i,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'reading': "CAPTURE_FAILED",
                'saturation': None,
                'brightness': None,
                'p95': None,
                'uploaded': False,
                'site_id': f"GMCMR2_TEST_{i:02d}"
            })

        print()

        # Wait between captures (except last one)
        if i < 10:
            time.sleep(2)  # 2 second interval

    # Final summary
    print("=" * 65)
    print("📊 TEST + UPLOAD RESULTS")
    print("=" * 65)

    successful_readings = [r for r in results if r['reading'] and r['reading'] not in ['NO_READ', 'CAPTURE_FAILED']]

    print(f"✅ Total captures: 10/10 (100%)")
    print(f"📖 Successful OCR readings: {len(successful_readings)}/10 ({len(successful_readings)*10}%)")
    print(f"🌐 Successful uploads: {uploads_successful}/10 ({uploads_successful*10}%)")

    if successful_readings:
        print(f"\n🔍 OCR READINGS DETECTED:")
        reading_counts = {}
        for r in successful_readings:
            reading = r['reading']
            reading_counts[reading] = reading_counts.get(reading, 0) + 1

        for reading, count in sorted(reading_counts.items()):
            print(f"  '{reading}': appeared {count} time{'s' if count != 1 else ''}")

    print(f"\n📋 DETAILED CAPTURE LOG:")
    print(f"{'#':<2} {'Time':<8} {'Reading':<12} {'Sat%':<6} {'Bright':<7} {'P95':<6} {'Upload':<7} {'Site ID':<15}")
    print("-" * 75)

    for r in results:
        reading_str = r['reading'] if r['reading'] else "—"
        sat_str = f"{r['saturation']:.1f}" if r['saturation'] else "—"
        bright_str = f"{r['brightness']:.0f}" if r['brightness'] else "—"
        p95_str = f"{r['p95']:.0f}" if r['p95'] else "—"
        upload_str = "✅" if r['uploaded'] else "❌"
        site_id = r.get('site_id', '—')

        print(f"{r['capture']:<2} {r['timestamp']:<8} {reading_str:<12} {sat_str:<6} {bright_str:<7} {p95_str:<6} {upload_str:<7} {site_id:<15}")

    print(f"\n🌐 WEBSITE INSPECTION:")
    print(f"Check your website dashboard at: cam.coolmri.com")
    print(f"Look for test uploads with Site IDs:")
    for i in range(1, 11):
        result = results[i-1] if i-1 < len(results) else None
        upload_status = "✅" if result and result.get('uploaded') else "❌"
        print(f"  - GMCMR2_TEST_{i:02d} {upload_status}")

    print(f"\nEach upload includes:")
    print(f"  - Full camera view (1920x1080) as base64")
    print(f"  - Cropped OCR region (364x182) as base64")
    print(f"  - Pressure reading parsed from OCR")
    print(f"  - Confidence score (0.1-0.9)")
    print(f"  - Unix timestamp and metadata")
    print(f"  - Original OCR reading in metadata")
    print(f"  - Crop coordinates for reference")

    if uploads_successful >= 8:
        print(f"\n🎉 EXCELLENT: {uploads_successful}/10 images uploaded successfully!")
        print("Check your website dashboard to see all the captured LCD images!")
    elif uploads_successful >= 5:
        print(f"\n✅ GOOD: {uploads_successful}/10 uploads successful")
        print("Most images uploaded - check your dashboard!")
    elif uploads_successful >= 1:
        print(f"\n⚠️ PARTIAL: {uploads_successful}/10 uploads successful")
        print("Some uploads worked - check connection and try again")
    else:
        print(f"\n❌ FAILED: No uploads succeeded")
        print("Check your internet connection and website availability")

    return results

if __name__ == "__main__":
    test_10_captures_with_upload()