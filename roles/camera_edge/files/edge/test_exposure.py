#!/usr/bin/env python3
"""Test different exposure settings to fix LCD overexposure"""

import subprocess
import os
import time
from PIL import Image
import numpy as np
from pathlib import Path
import json

# Load crop coordinates from .env
from dotenv import load_dotenv
load_dotenv()
OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))

def capture_with_exposure(shutter_us, gain, output_name):
    """Capture image with specific exposure settings"""

    cmd = [
        'libcamera-still',
        '-n',  # No preview
        '--immediate',  # Capture immediately
        '--width', '1920',
        '--height', '1080',
        '--shutter', str(shutter_us),  # Exposure time in microseconds
        '--gain', str(gain),  # Analog gain
        '--awb', 'auto',  # Keep AWB for now
        '--denoise', 'off',  # Disable denoise for sharper segments
        '-o', f'/home/gmcmr2c/mri-cooling-camera/edge/images/exposure_test_{output_name}.jpg'
    ]

    print(f"Testing shutter={shutter_us}µs, gain={gain}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None

    return f'/home/gmcmr2c/mri-cooling-camera/edge/images/exposure_test_{output_name}.jpg'

def analyze_saturation(image_path):
    """Analyze image saturation levels"""

    img = Image.open(image_path)

    # Crop to ROI
    x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
    cropped = img.crop((x, y, x+w, y+h))

    # Convert to numpy array
    arr = np.array(cropped)

    # Calculate saturation statistics
    total_pixels = arr.size
    saturated_pixels = np.sum(arr >= 250)  # Near-saturated pixels
    fully_saturated = np.sum(arr == 255)  # Fully saturated

    sat_percent = (saturated_pixels / total_pixels) * 100
    full_sat_percent = (fully_saturated / total_pixels) * 100

    # Get percentiles
    p95 = np.percentile(arr, 95)
    p99 = np.percentile(arr, 99)
    mean_val = np.mean(arr)

    print(f"  Saturation (>250): {sat_percent:.2f}%")
    print(f"  Full saturation (255): {full_sat_percent:.2f}%")
    print(f"  95th percentile: {p95:.0f}")
    print(f"  99th percentile: {p99:.0f}")
    print(f"  Mean: {mean_val:.0f}")

    # Save cropped image for visual inspection
    crop_path = image_path.replace('.jpg', '_crop.jpg')
    cropped.save(crop_path)

    return sat_percent, p95

def main():
    print("LCD Exposure Test - Finding optimal settings to prevent segment blooming\n")
    print("Target: <0.5% saturation, 95th percentile ~200-220\n")

    # Test configurations (shutter_microseconds, gain)
    test_configs = [
        # Start with very short exposures
        (500, 1.0),    # 0.5ms, unity gain
        (1000, 1.0),   # 1ms
        (2000, 1.0),   # 2ms
        (3000, 1.0),   # 3ms
        (5000, 1.0),   # 5ms
        (8000, 1.0),   # 8ms (for 60Hz environments)
        (10000, 1.0),  # 10ms (for 50Hz environments)

        # If still too bright, try with even shorter
        (250, 1.0),    # 0.25ms
        (100, 1.0),    # 0.1ms
    ]

    best_config = None
    best_score = float('inf')

    for shutter, gain in test_configs:
        img_path = capture_with_exposure(shutter, gain, f"{shutter}us_{gain}g")

        if img_path and os.path.exists(img_path):
            sat_percent, p95 = analyze_saturation(img_path)

            # Score based on how close we are to target
            # Target: <0.5% saturation, p95 around 200-220
            score = abs(sat_percent - 0.3) + abs(p95 - 210) / 100

            if sat_percent < 1.0 and 180 < p95 < 240:
                print(f"  ✓ Good candidate!\n")
                if score < best_score:
                    best_score = score
                    best_config = (shutter, gain)
            elif sat_percent > 5:
                print(f"  ✗ Too bright - segments will bloom\n")
            else:
                print(f"  ~ Marginal\n")
        else:
            print(f"  Failed to capture\n")

        time.sleep(2)  # Brief pause between captures

    print("\n" + "="*60)
    if best_config:
        print(f"RECOMMENDED SETTINGS:")
        print(f"  Shutter: {best_config[0]} microseconds")
        print(f"  Gain: {best_config[1]}")
        print(f"\nAdd these to your capture command:")
        print(f"  --shutter {best_config[0]} --gain {best_config[1]} --awb off")
    else:
        print("No ideal settings found. Try even shorter exposures or add an ND filter.")

if __name__ == "__main__":
    main()