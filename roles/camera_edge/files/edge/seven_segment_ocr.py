#!/usr/bin/env python3
"""
Seven-segment display decoder with overexposure handling
Designed to work with saturated/blooming LCD displays
"""

import cv2
import numpy as np
from PIL import Image, ImageEnhance
import json
import os
from pathlib import Path
from typing import Tuple, List, Optional, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SevenSegmentOCR:
    """Robust 7-segment decoder for overexposed LCD displays"""

    # 7-segment truth table (segments a-g as bits)
    # Layout:  aaaa
    #         f    b
    #         f    b
    #          gggg
    #         e    c
    #         e    c
    #          dddd
    DIGIT_PATTERNS = {
        0b0111111: '0',  # abcdef
        0b0000110: '1',  # bc
        0b1011011: '2',  # abdeg
        0b1001111: '3',  # abcdg
        0b1100110: '4',  # bcfg
        0b1101101: '5',  # acdfg
        0b1111101: '6',  # acdefg
        0b0000111: '7',  # abc
        0b1111111: '8',  # abcdefg
        0b1101111: '9',  # abcdfg
        0b1110001: 'F',  # aefg (for fault codes)
        0b1111001: 'E',  # adefg
        0b0111001: 'C',  # adef
        0b0111111: 'O',  # abcdef (same as 0)
    }

    def __init__(self, debug=False):
        self.debug = debug
        self.debug_dir = Path("./debug_7seg")
        if debug:
            self.debug_dir.mkdir(exist_ok=True)

    def preprocess_overexposed(self, image: np.ndarray) -> np.ndarray:
        """Preprocess overexposed LCD image to recover segments"""

        # Convert to grayscale if needed
        if len(image.shape) == 3:
            # Use green channel (usually less saturated than red for red displays)
            gray = image[:, :, 1]
        else:
            gray = image

        # Apply logarithmic compression to reduce saturation effects
        # This helps recover detail in blown-out areas
        gray_float = gray.astype(np.float32) / 255.0
        compressed = np.log1p(gray_float * 10) / np.log1p(10)
        gray = (compressed * 255).astype(np.uint8)

        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        # This helps separate segments that are merged due to blooming
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        gray = clahe.apply(gray)

        # Use adaptive thresholding to handle varying brightness
        # This is crucial for overexposed images
        binary = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=15,  # Small block size for fine details
            C=-5  # Negative constant to be more aggressive with bright areas
        )

        # Light morphological operations to clean up
        kernel = np.ones((2, 2), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        # Small erosion to separate merged segments
        kernel_erode = np.ones((2, 2), np.uint8)
        binary = cv2.erode(binary, kernel_erode, iterations=1)

        if self.debug:
            cv2.imwrite(str(self.debug_dir / "preprocessed.png"), binary)

        return binary

    def find_digit_regions(self, binary: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Find individual digit bounding boxes"""

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours by size and aspect ratio
        digit_boxes = []
        h, w = binary.shape
        min_area = (h * w) * 0.01  # At least 1% of image
        max_area = (h * w) * 0.4   # At most 40% of image

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            aspect_ratio = h / w if w > 0 else 0

            # 7-segment digits are typically taller than wide
            if (min_area < area < max_area and
                1.2 < aspect_ratio < 3.0):
                digit_boxes.append((x, y, w, h))

        # Sort by x-coordinate (left to right)
        digit_boxes.sort(key=lambda box: box[0])

        # For "F95" or similar 3-character displays, we expect 3 digits
        # If we found more, take the 3 largest
        if len(digit_boxes) > 3:
            digit_boxes = sorted(digit_boxes, key=lambda b: b[2]*b[3], reverse=True)[:3]
            digit_boxes.sort(key=lambda box: box[0])

        return digit_boxes

    def decode_segment_pattern(self, digit_img: np.ndarray) -> str:
        """Decode a single digit from its binary image"""

        h, w = digit_img.shape

        # Define segment sampling regions (relative positions)
        # Adjusted for typical 7-segment layout
        segments = {
            'a': (0.25, 0.1, 0.5, 0.08),   # top horizontal
            'b': (0.65, 0.15, 0.15, 0.3),  # top right vertical
            'c': (0.65, 0.55, 0.15, 0.3),  # bottom right vertical
            'd': (0.25, 0.82, 0.5, 0.08),  # bottom horizontal
            'e': (0.2, 0.55, 0.15, 0.3),   # bottom left vertical
            'f': (0.2, 0.15, 0.15, 0.3),   # top left vertical
            'g': (0.25, 0.46, 0.5, 0.08),  # middle horizontal
        }

        # Sample each segment region
        segment_states = {}
        for seg_name, (rx, ry, rw, rh) in segments.items():
            # Convert relative to absolute coordinates
            x1 = int(rx * w)
            y1 = int(ry * h)
            x2 = int((rx + rw) * w)
            y2 = int((ry + rh) * h)

            # Extract segment region
            segment_roi = digit_img[y1:y2, x1:x2]

            # Check if segment is "on" (more white than black pixels)
            if segment_roi.size > 0:
                white_ratio = np.sum(segment_roi > 128) / segment_roi.size
                segment_states[seg_name] = white_ratio > 0.3  # 30% threshold
            else:
                segment_states[seg_name] = False

        # Convert to bit pattern
        pattern = 0
        for i, seg in enumerate('abcdefg'):
            if segment_states.get(seg, False):
                pattern |= (1 << (6 - i))

        # Look up in truth table
        if pattern in self.DIGIT_PATTERNS:
            return self.DIGIT_PATTERNS[pattern]

        # If no exact match, find closest pattern
        best_match = None
        min_diff = 8
        for p, digit in self.DIGIT_PATTERNS.items():
            diff = bin(pattern ^ p).count('1')  # Hamming distance
            if diff < min_diff:
                min_diff = diff
                best_match = digit

        logger.warning(f"No exact pattern match (0b{pattern:07b}), closest: {best_match}")
        return best_match if best_match else '?'

    def decode_display(self, image_path: str) -> str:
        """Decode the complete LCD display from an image file"""

        # Load image
        if isinstance(image_path, str):
            image = cv2.imread(image_path)
        else:
            image = image_path

        if image is None:
            logger.error(f"Failed to load image: {image_path}")
            return ""

        # Preprocess for overexposure
        binary = self.preprocess_overexposed(image)

        # Find digit regions
        digit_boxes = self.find_digit_regions(binary)

        if not digit_boxes:
            logger.warning("No digit regions found")
            return ""

        # Decode each digit
        result = ""
        for i, (x, y, w, h) in enumerate(digit_boxes):
            # Extract digit with some padding
            pad = 5
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(binary.shape[1], x + w + pad)
            y2 = min(binary.shape[0], y + h + pad)

            digit_img = binary[y1:y2, x1:x2]

            if self.debug:
                cv2.imwrite(str(self.debug_dir / f"digit_{i}.png"), digit_img)

            # Decode the digit
            digit = self.decode_segment_pattern(digit_img)
            result += digit

        # Handle decimal points (if needed for pressure readings)
        # For "F95" this won't apply, but for "7.5" it would
        # This would require additional decimal point detection logic

        return result

def test_on_current_images():
    """Test the decoder on existing captured images"""

    decoder = SevenSegmentOCR(debug=True)

    # Test on recent captures
    image_dir = Path("/home/gmcmr2c/mri-cooling-camera/edge/images")
    test_images = [
        "CURRENT_CROP_REGION.jpg",
        "debug_crop_1755558018.jpg",
        "debug_crop_1755558004.jpg",
    ]

    print("Testing 7-segment decoder on current images:\n")
    print("-" * 50)

    for img_name in test_images:
        img_path = image_dir / img_name
        if img_path.exists():
            print(f"\nImage: {img_name}")
            result = decoder.decode_display(str(img_path))
            print(f"Decoded: '{result}'")

            # Also try with direct OpenCV processing
            img = cv2.imread(str(img_path))
            if img is not None:
                # Check saturation level
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                saturated = np.sum(gray >= 250) / gray.size * 100
                print(f"Saturation: {saturated:.1f}%")
        else:
            print(f"\nImage not found: {img_name}")

    print("\n" + "-" * 50)
    print("\nNote: For better results, reduce camera exposure to prevent segment blooming.")
    print("The decoder tries to handle overexposure but works best with proper exposure.")

if __name__ == "__main__":
    test_on_current_images()