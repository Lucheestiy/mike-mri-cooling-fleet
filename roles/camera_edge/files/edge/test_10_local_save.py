#!/usr/bin/env python3
"""
Capture 10 test images, save locally, and try uploading to calibration endpoint
"""

import time
import logging
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from improved_ocr import ImprovedOCR
import cv2
import numpy as np
import requests

# Configure logging for cleaner output
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def save_and_upload_test_images(image, crop, reading, capture_num, timestamp):
    """Save images locally and try uploading to website"""

    # Create test directory
    test_dir = Path("./images/test_session")
    test_dir.mkdir(parents=True, exist_ok=True)

    # Save full image
    full_path = test_dir / f"test_{capture_num:02d}_full_{timestamp.strftime('%H%M%S')}.jpg"
    cv2.imwrite(str(full_path), image)

    # Save crop
    crop_path = test_dir / f"test_{capture_num:02d}_crop_{timestamp.strftime('%H%M%S')}.jpg"
    cv2.imwrite(str(crop_path), crop)

    print(f"    💾 Saved: {full_path.name} & {crop_path.name}")

    # Try uploading to calibration endpoint
    from dotenv import load_dotenv
    load_dotenv()

    # Use the correct calibration endpoint from .env
    CALIBRATION_URL = os.getenv("CALIBRATION_URL", "https://cam.coolmri.com/api/camera/calibration")
    SITE_ID = os.getenv("SITE_ID", "GMCMR2")
    OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))

    # Convert images to base64
    _, full_buffer = cv2.imencode('.jpg', image)
    full_b64 = base64.b64encode(full_buffer).decode('utf-8')

    _, crop_buffer = cv2.imencode('.jpg', crop)  # Use JPG for crop too
    crop_b64 = base64.b64encode(crop_buffer).decode('utf-8')

    # Payload matching expected format
    payload = {
        "site_id": f"{SITE_ID}_TEST",
        "timestamp": timestamp.isoformat(),
        "image_full": full_b64,
        "image_crop": crop_b64,
        "reading": reading or "NONE",
        "test_info": {
            "capture_number": capture_num,
            "session": datetime.now().strftime("%Y%m%d_%H%M%S")
        }
    }

    try:
        session = requests.Session()
        session.timeout = 30
        response = session.post(CALIBRATION_URL, json=payload)

        if response.status_code == 200:
            print(f"    🌐 Uploaded successfully")
            return True
        else:
            print(f"    ❌ Upload failed: HTTP {response.status_code}")
            print(f"    Response: {response.text[:100]}")
            return False
    except Exception as e:
        print(f"    ❌ Upload error: {str(e)[:50]}...")
        return False

def test_10_captures_with_local_save():
    """Capture 10 images, save locally, and attempt upload"""

    print("🔍 Testing 10 LCD Captures with Local Save + Upload")
    print("=" * 65)
    print("This will:")
    print("- Capture 10 images with 2-second intervals")
    print("- Save all images locally in ./images/test_session/")
    print("- Attempt to upload to calibration endpoint")
    print("- Show you exactly what the OCR is reading\n")

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

            # Save and upload
            timestamp = datetime.now(timezone.utc)
            upload_success = save_and_upload_test_images(image, roi, reading, i, timestamp)

            if upload_success:
                uploads_successful += 1

            # Store result
            result = {
                'capture': i,
                'timestamp': timestamp.strftime("%H:%M:%S"),
                'reading': reading or "NO_READ",
                'saturation': saturation,
                'brightness': brightness,
                'p95': p95,
                'uploaded': upload_success
            }
            results.append(result)

            # Report this capture
            status = "✓" if reading else "✗"
            print(f"    {status} OCR Result: '{reading}'")
            print(f"    📊 Quality: {saturation:.1f}% sat, {brightness:.0f} bright, {p95:.0f} p95")
        else:
            print(f"    ❌ Capture failed")
            results.append({
                'capture': i,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'reading': "CAPTURE_FAILED",
                'saturation': None,
                'brightness': None,
                'p95': None,
                'uploaded': False
            })

        print()

        # Wait between captures (except last one)
        if i < 10:
            time.sleep(2)

    # Final summary
    print("=" * 65)
    print("📊 COMPLETE TEST RESULTS")
    print("=" * 65)

    successful_readings = [r for r in results if r['reading'] and r['reading'] not in ['NO_READ', 'CAPTURE_FAILED']]

    print(f"✅ Total captures: 10/10 (100%)")
    print(f"📖 Successful OCR readings: {len(successful_readings)}/10 ({len(successful_readings)*10}%)")
    print(f"🌐 Successful uploads: {uploads_successful}/10 ({uploads_successful*10}%)")
    print(f"💾 All images saved to: ./images/test_session/")

    if successful_readings:
        print(f"\n🔍 OCR READINGS DETECTED:")
        reading_counts = {}
        for r in successful_readings:
            reading = r['reading']
            reading_counts[reading] = reading_counts.get(reading, 0) + 1

        for reading, count in sorted(reading_counts.items()):
            print(f"  '{reading}': appeared {count} time{'s' if count != 1 else ''}")

        # Show most common reading
        most_common = max(reading_counts.items(), key=lambda x: x[1])
        print(f"\n🎯 Most common reading: '{most_common[0]}' ({most_common[1]}/10 times)")

    print(f"\n📋 DETAILED CAPTURE LOG:")
    print(f"{'#':<2} {'Time':<8} {'OCR Reading':<15} {'Sat%':<6} {'Bright':<7} {'P95':<6} {'Saved':<6}")
    print("-" * 65)

    for r in results:
        reading_str = r['reading'] if r['reading'] else "—"
        sat_str = f"{r['saturation']:.1f}" if r['saturation'] else "—"
        bright_str = f"{r['brightness']:.0f}" if r['brightness'] else "—"
        p95_str = f"{r['p95']:.0f}" if r['p95'] else "—"
        saved_str = "✅" if r['reading'] != "CAPTURE_FAILED" else "❌"

        print(f"{r['capture']:<2} {r['timestamp']:<8} {reading_str:<15} {sat_str:<6} {bright_str:<7} {p95_str:<6} {saved_str:<6}")

    print(f"\n📁 LOCAL FILES:")
    test_dir = Path("./images/test_session")
    if test_dir.exists():
        files = sorted(list(test_dir.glob("test_*.jpg")))
        print(f"Found {len(files)} saved images in {test_dir}")
        if files:
            print("Most recent files:")
            for f in files[-6:]:  # Show last 6 files
                print(f"  {f.name}")

    # Assessment
    if len(successful_readings) >= 8:
        print(f"\n🎉 EXCELLENT: {len(successful_readings)}/10 successful readings!")
        print("The OCR system is working very well.")
    elif len(successful_readings) >= 6:
        print(f"\n✅ GOOD: {len(successful_readings)}/10 successful readings")
        print("The OCR system is working well with minor inconsistencies.")
    elif len(successful_readings) >= 3:
        print(f"\n⚠️  FAIR: {len(successful_readings)}/10 successful readings")
        print("The OCR system works but may need ROI adjustment or lighting optimization.")
    else:
        print(f"\n❌ NEEDS WORK: Only {len(successful_readings)}/10 successful readings")
        print("The OCR system needs significant adjustment.")

    print(f"\n💡 NEXT STEPS:")
    print(f"1. Check the saved images in ./images/test_session/ to see what's being captured")
    print(f"2. Verify the OCR readings match what you see on the LCD display")
    print(f"3. If readings are incorrect, we may need to adjust the ROI coordinates")

    return results

if __name__ == "__main__":
    test_10_captures_with_local_save()