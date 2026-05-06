#!/usr/bin/env python3
"""
Test OCR functionality with a sample image
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw, ImageFont
import numpy as np
from camera_ocr import CameraOCR

def create_test_image():
    """Create a test image with pressure reading"""
    # Create a test image with pressure reading
    img = Image.new('RGB', (1920, 1080), color='black')
    draw = ImageDraw.Draw(img)

    # Try to use a large font
    try:
        # Use default font but make it large
        font_size = 48
        font = ImageFont.load_default()

        # Draw pressure reading at the expected location
        x, y = 850, 450  # OCR_CROP_COORDS position
        draw.rectangle([x-10, y-10, x+220, y+110], fill='white', outline='gray')
        draw.text((x+20, y+20), "35.7", fill='black', font=font)

    except Exception as e:
        print(f"Font error: {e}")
        # Fallback to simple rectangle
        draw.rectangle([850, 450, 1050, 550], fill='white')
        draw.text((900, 480), "35.7", fill='black')

    return img

def test_ocr():
    """Test OCR on sample image"""
    print("Creating test image...")
    test_img = create_test_image()

    # Save test image
    test_img.save('/home/gmcmr2c/mri-cooling-camera/edge/test_image.jpg')
    print("Test image saved as test_image.jpg")

    # Convert to numpy array for OCR processing
    img_array = np.array(test_img)

    # Create OCR instance
    ocr = CameraOCR()

    # Test preprocessing and OCR
    print("Testing OCR preprocessing...")
    processed = ocr.preprocess_for_ocr(img_array)

    print("Testing OCR extraction...")
    pressure, confidence = ocr.extract_pressure(processed)

    if pressure is not None:
        print(f"SUCCESS: Extracted pressure: {pressure} PSI (confidence: {confidence})")
    else:
        print("FAILED: No pressure value extracted")

    return pressure is not None

if __name__ == "__main__":
    success = test_ocr()
    sys.exit(0 if success else 1)