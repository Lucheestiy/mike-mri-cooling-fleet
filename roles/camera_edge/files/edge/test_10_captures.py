#!/usr/bin/env python3
"""
Capture 10 test images and report all readings for evaluation
"""

import time
import logging
from datetime import datetime
from improved_ocr import ImprovedOCR
import json
import cv2
import numpy as np

# Configure logging for cleaner output
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def test_10_captures():
    """Capture 10 images and report all readings"""

    print("🔍 Testing 10 Consecutive LCD Captures")
    print("=" * 60)
    print("This will capture 10 images with 3-second intervals")
    print("and report all readings for evaluation.\n")

    ocr = ImprovedOCR()
    results = []

    for i in range(1, 11):
        print(f"Capture {i}/10...")

        # Capture image
        image = ocr.capture_with_rpicam()

        if image is not None:
            # Extract ROI and analyze quality
            from dotenv import load_dotenv
            import os
            load_dotenv()
            OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))

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

            # Parse reading
            pressure = ocr.parse_reading(reading) if reading else None

            # Store result
            result = {
                'capture': i,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'reading': reading or "NO_READ",
                'pressure': pressure,
                'saturation': saturation,
                'brightness': brightness,
                'p95': p95
            }
            results.append(result)

            # Report this capture
            status = "✓" if reading else "✗"
            pressure_str = f"{pressure} PSI" if pressure else "non-numeric"
            print(f"  {status} Reading: '{reading}' → {pressure_str}")
            print(f"    Quality: {saturation:.1f}% sat, {brightness:.0f} brightness, {p95:.0f} p95")
        else:
            print(f"  ✗ Capture failed")
            results.append({
                'capture': i,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'reading': "CAPTURE_FAILED",
                'pressure': None,
                'saturation': None,
                'brightness': None,
                'p95': None
            })

        print()

        # Wait between captures (except last one)
        if i < 10:
            time.sleep(3)

    # Final summary
    print("=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)

    successful_readings = [r for r in results if r['reading'] and r['reading'] not in ['NO_READ', 'CAPTURE_FAILED']]
    numeric_readings = [r for r in results if r['pressure'] is not None]

    print(f"Total captures: 10")
    print(f"Successful readings: {len(successful_readings)}/10 ({len(successful_readings)*10}%)")
    print(f"Numeric readings: {len(numeric_readings)}/10 ({len(numeric_readings)*10}%)")

    if successful_readings:
        print(f"\nAll readings detected:")
        reading_counts = {}
        for r in successful_readings:
            reading = r['reading']
            reading_counts[reading] = reading_counts.get(reading, 0) + 1

        for reading, count in sorted(reading_counts.items()):
            print(f"  '{reading}': {count} times")

    if successful_readings:
        avg_sat = np.mean([r['saturation'] for r in successful_readings if r['saturation']])
        avg_bright = np.mean([r['brightness'] for r in successful_readings if r['brightness']])
        avg_p95 = np.mean([r['p95'] for r in successful_readings if r['p95']])

        print(f"\nImage quality averages:")
        print(f"  Saturation: {avg_sat:.1f}% (target: <1%)")
        print(f"  Brightness: {avg_bright:.0f} (good range: 20-80)")
        print(f"  95th percentile: {avg_p95:.0f} (target: 180-220)")

    print(f"\n📋 DETAILED RESULTS:")
    print(f"{'#':<2} {'Time':<8} {'Reading':<12} {'Pressure':<10} {'Sat%':<6} {'Bright':<6} {'P95':<6}")
    print("-" * 60)

    for r in results:
        reading_str = r['reading'] if r['reading'] else "—"
        pressure_str = f"{r['pressure']:.1f}" if r['pressure'] else "—"
        sat_str = f"{r['saturation']:.1f}" if r['saturation'] else "—"
        bright_str = f"{r['brightness']:.0f}" if r['brightness'] else "—"
        p95_str = f"{r['p95']:.0f}" if r['p95'] else "—"

        print(f"{r['capture']:<2} {r['timestamp']:<8} {reading_str:<12} {pressure_str:<10} {sat_str:<6} {bright_str:<6} {p95_str:<6}")

    print("\n" + "=" * 60)

    # Recommendations
    if len(successful_readings) >= 8:
        print("🎉 EXCELLENT: 80%+ successful readings!")
    elif len(successful_readings) >= 6:
        print("✅ GOOD: 60%+ successful readings")
    elif len(successful_readings) >= 3:
        print("⚠️  FAIR: Some readings successful, may need ROI adjustment")
    else:
        print("❌ NEEDS WORK: Few successful readings")

    if successful_readings:
        avg_sat = np.mean([r['saturation'] for r in successful_readings if r['saturation']])
        if avg_sat < 1:
            print("✅ Exposure: Excellent (no saturation)")
        elif avg_sat < 3:
            print("✅ Exposure: Good (minimal saturation)")
        elif avg_sat < 10:
            print("⚠️  Exposure: Fair (some saturation)")
        else:
            print("❌ Exposure: Poor (high saturation)")

    return results

if __name__ == "__main__":
    test_10_captures()