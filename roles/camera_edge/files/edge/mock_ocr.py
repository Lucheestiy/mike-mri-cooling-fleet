#!/usr/bin/env python3
"""
Mock OCR for testing when tesseract is not available
"""
import numpy as np
from PIL import Image
import re

def simple_pattern_ocr(image):
    """
    Simple pattern-based OCR that looks for number-like patterns
    This is a basic fallback when tesseract is not available
    """
    # Convert to grayscale array
    if isinstance(image, Image.Image):
        if image.mode != 'L':
            image = image.convert('L')
        img_array = np.array(image)
    else:
        img_array = image

    # Very basic pattern recognition
    # Look for light regions (potential text) on dark background or vice versa

    # Get image statistics
    mean_val = np.mean(img_array)
    std_val = np.std(img_array)

    # Simple heuristic: if image has good contrast and reasonable size
    height, width = img_array.shape

    if width > 50 and height > 20 and std_val > 30:
        # Mock: return a typical pressure reading for testing
        # In a real scenario, this would be actual OCR
        mock_values = [35.7, 42.3, 28.9, 31.2, 45.6]

        # Use image characteristics to select a value
        selected_idx = int(mean_val) % len(mock_values)
        return mock_values[selected_idx], 0.8  # Mock confidence

    return None, 0.0

def test_mock_ocr():
    """Test mock OCR functionality"""
    print("Testing mock OCR...")

    # Create test image
    img = Image.new('L', (200, 100), color=255)  # White background

    # Add some "text-like" pattern
    img_array = np.array(img)
    img_array[30:70, 50:150] = 0  # Black rectangle (simulating text)
    img = Image.fromarray(img_array)

    pressure, confidence = simple_pattern_ocr(img)

    if pressure is not None:
        print(f"Mock OCR result: {pressure} PSI (confidence: {confidence})")
        return True
    else:
        print("Mock OCR failed")
        return False

if __name__ == "__main__":
    success = test_mock_ocr()
    exit(0 if success else 1)