#!/usr/bin/env python3
"""
Find optimal exposure settings for LCD display using rpicam-still
Tests multiple exposure values to minimize saturation
"""

import subprocess
import os
import time
import cv2
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from seven_segment_ocr import SevenSegmentOCR

# Load configuration
from dotenv import load_dotenv
load_dotenv()
OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))

def capture_with_rpicam(shutter_us, gain, output_path):
    """Capture image with specific settings using rpicam-still"""

    cmd = [
        'rpicam-still',
        '--shutter', str(shutter_us),
        '--gain', str(gain),
        '--awb', 'daylight',  # Fixed white balance
        '--denoise', 'off',   # No denoise for sharper segments
        '-o', output_path,
        '--width', '1920',
        '--height', '1080',
        '--immediate',  # Capture immediately
        '-n',  # No preview
        '-t', '1'  # 1ms timeout
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and os.path.exists(output_path):
            return True
        else:
            print(f"  Error: {result.stderr[:100]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  Timeout!")
        return False
    except Exception as e:
        print(f"  Exception: {e}")
        return False

def analyze_image(image_path):
    """Analyze image saturation and decode LCD"""

    img = cv2.imread(image_path)
    if img is None:
        return None, None, None

    # Crop to ROI
    x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
    roi = img[y:y+h, x:x+w]

    # Convert to grayscale
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # Calculate saturation statistics
    total_pixels = gray.size
    saturated_pixels = np.sum(gray >= 250)
    fully_saturated = np.sum(gray == 255)

    sat_percent = (saturated_pixels / total_pixels) * 100
    full_sat_percent = (fully_saturated / total_pixels) * 100

    # Get percentiles
    p95 = np.percentile(gray, 95)
    p99 = np.percentile(gray, 99)
    mean_val = np.mean(gray)

    # Save cropped image
    crop_path = image_path.replace('.jpg', '_crop.jpg')
    cv2.imwrite(crop_path, roi)

    # Try to decode
    decoder = SevenSegmentOCR(debug=False)
    reading = decoder.decode_display(roi)

    return {
        'saturation': sat_percent,
        'full_saturation': full_sat_percent,
        'p95': p95,
        'p99': p99,
        'mean': mean_val,
        'reading': reading
    }

def find_optimal_settings():
    """Test different exposure settings to find optimal configuration"""

    print("Finding optimal exposure settings for LCD display")
    print("="*60)

    # Create test directory
    test_dir = Path("./images/exposure_tests")
    test_dir.mkdir(parents=True, exist_ok=True)

    # Test configurations (shutter_microseconds, gain)
    test_configs = [
        # Very short exposures first
        (100, 1.0),    # 0.1ms
        (250, 1.0),    # 0.25ms
        (500, 1.0),    # 0.5ms
        (750, 1.0),    # 0.75ms
        (1000, 1.0),   # 1ms
        (1500, 1.0),   # 1.5ms
        (2000, 1.0),   # 2ms
        (3000, 1.0),   # 3ms
        (5000, 1.0),   # 5ms
        (8000, 1.0),   # 8ms (good for 60Hz)
        (10000, 1.0),  # 10ms (good for 50Hz)
    ]

    results = []
    best_config = None
    best_score = float('inf')

    for shutter, gain in test_configs:
        print(f"\nTesting: shutter={shutter}µs, gain={gain}")

        # Capture image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(test_dir / f"test_{shutter}us_{gain}g_{timestamp}.jpg")

        if capture_with_rpicam(shutter, gain, output_path):
            # Analyze
            stats = analyze_image(output_path)

            if stats:
                print(f"  Saturation: {stats['saturation']:.1f}%")
                print(f"  Full sat: {stats['full_saturation']:.1f}%")
                print(f"  95th percentile: {stats['p95']:.0f}")
                print(f"  Mean: {stats['mean']:.0f}")
                print(f"  Reading: '{stats['reading']}'")

                # Score based on target metrics
                # Target: <0.5% saturation, p95 around 200-220
                score = abs(stats['saturation'] - 0.3) + abs(stats['p95'] - 210) / 100

                results.append({
                    'shutter': shutter,
                    'gain': gain,
                    'stats': stats,
                    'score': score,
                    'path': output_path
                })

                # Check if this is the best so far
                if stats['saturation'] < 2.0 and 150 < stats['p95'] < 240:
                    print(f"  ✓ Good candidate!")
                    if score < best_score:
                        best_score = score
                        best_config = {
                            'shutter': shutter,
                            'gain': gain,
                            'stats': stats,
                            'path': output_path
                        }
                elif stats['saturation'] > 10:
                    print(f"  ✗ Too bright - segments will bloom")
                else:
                    print(f"  ~ Marginal")
            else:
                print(f"  Failed to analyze")
        else:
            print(f"  Failed to capture")

        # Brief pause between captures
        time.sleep(1)

    # Summary
    print("\n" + "="*60)
    print("RESULTS SUMMARY")
    print("="*60)

    # Sort by score
    results.sort(key=lambda x: x['score'])

    print("\nTop 3 configurations:")
    for i, result in enumerate(results[:3]):
        print(f"\n{i+1}. Shutter: {result['shutter']}µs, Gain: {result['gain']}")
        print(f"   Saturation: {result['stats']['saturation']:.1f}%")
        print(f"   95th percentile: {result['stats']['p95']:.0f}")
        print(f"   Reading: '{result['stats']['reading']}'")
        print(f"   Score: {result['score']:.2f}")

    if best_config:
        print("\n" + "="*60)
        print("RECOMMENDED SETTINGS:")
        print(f"  Shutter: {best_config['shutter']} microseconds")
        print(f"  Gain: {best_config['gain']}")
        print(f"  Saturation: {best_config['stats']['saturation']:.1f}%")
        print(f"  Reading: '{best_config['stats']['reading']}'")
        print(f"\nBest image saved at: {best_config['path']}")

        # Create a script with optimal settings
        create_capture_script(best_config['shutter'], best_config['gain'])
    else:
        print("\nNo ideal settings found. Display may be too bright.")
        print("Consider adding a neutral density filter.")

    return best_config

def create_capture_script(shutter, gain):
    """Create a capture script with optimal settings"""

    script_content = f"""#!/bin/bash
# Capture LCD with optimal exposure settings
# Generated by find_optimal_exposure.py

rpicam-still \\
    --shutter {shutter} \\
    --gain {gain} \\
    --awb daylight \\
    --denoise off \\
    --width 1920 \\
    --height 1080 \\
    --immediate \\
    -n \\
    -t 1 \\
    -o "${{1:-lcd_capture.jpg}}"

echo "Captured to: ${{1:-lcd_capture.jpg}}"
echo "Exposure: {shutter}µs, Gain: {gain}"
"""

    script_path = Path("capture_lcd_optimal.sh")
    script_path.write_text(script_content)
    script_path.chmod(0o755)

    print(f"\nCreated capture script: {script_path}")
    print("Usage: ./capture_lcd_optimal.sh [output_filename.jpg]")

if __name__ == "__main__":
    find_optimal_settings()