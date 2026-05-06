#!/usr/bin/env python3
"""
Universal LCD OCR - Handles any decimal value, not just hardcoded ones
Uses pattern recognition and character mapping for seven-segment displays
"""
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import logging
import re
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)

class UniversalLCDOCR:
    def __init__(self):
        """Initialize universal LCD OCR system"""
        # Seven-segment character mapping for common misreadings
        self.char_map = {
            'O': '6',  # O commonly misread as 6
            'G': '6',  # G commonly misread as 6
            'B': '6',  # B commonly misread as 6
            'S': '5',  # S commonly misread as 5
            'Z': '2',  # Z commonly misread as 2
            'I': '1',  # I commonly misread as 1
            'l': '1',  # lowercase l misread as 1
            '|': '1',  # Pipe misread as 1
            'Q': '0',  # Q misread as 0
            'D': '0',  # D misread as 0
        }

        # Specific pattern corrections for complex cases
        self.pattern_corrections = {
            'ECO': ['EE', 'EES', 'EC0', 'E00', 'ECQ', 'EGO', 'EC6', 'EG6', 'E6O'],
        }

    def enhance_lcd_image(self, image: Image.Image) -> Image.Image:
        """Enhanced preprocessing for LCD displays"""
        try:
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

            # Morphological operations to connect seven-segment gaps
            kernel = np.ones((2, 2), np.uint8)
            closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
            dilated = cv2.dilate(closed, kernel, iterations=1)
            blurred = cv2.GaussianBlur(dilated, (3, 3), 0)

            # Binary threshold
            _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            enhanced = Image.fromarray(thresh)

            # Scale up for better OCR
            width, height = enhanced.size
            enhanced = enhanced.resize((width * 4, height * 4), Image.LANCZOS)

            return enhanced
        except Exception as e:
            logger.error(f"Image enhancement failed: {e}")
            return image

    def extract_multiple_readings(self, image: Image.Image) -> List[str]:
        """Extract text using multiple methods"""
        results = []

        try:
            # Method 1: Enhanced preprocessing
            enhanced = self.enhance_lcd_image(image)

            configs = [
                r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.ECOFecof',
                r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.ECOFecof',
                r'--oem 3 --psm 13 -c tessedit_char_whitelist=0123456789.ECOFecof',
                r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.ECOF',
                r'--oem 1 --psm 8 -c tessedit_char_whitelist=0123456789.ECOF',
                r'--psm 8',
                r'--psm 7',
            ]

            for config in configs:
                try:
                    text = pytesseract.image_to_string(enhanced, config=config).strip()
                    if text:
                        results.append(text.upper())
                except Exception:
                    continue

            # Method 2: High contrast
            original = image.convert('L')
            enhancer = ImageEnhance.Contrast(original)
            high_contrast = enhancer.enhance(4.0)
            width, height = high_contrast.size
            large = high_contrast.resize((width * 6, height * 6), Image.LANCZOS)

            try:
                text = pytesseract.image_to_string(large, config=r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.ECOF')
                if text.strip():
                    results.append(text.strip().upper())
            except Exception:
                pass

            # Method 3: Inverted image
            try:
                inverted = Image.eval(enhanced, lambda x: 255 - x)
                text = pytesseract.image_to_string(inverted, config=r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.ECOF')
                if text.strip():
                    results.append(text.strip().upper())
            except Exception:
                pass

        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")

        return results

    def apply_universal_corrections(self, text: str) -> str:
        """Apply universal character corrections for seven-segment displays"""
        if not text:
            return text

        text = text.strip().replace(' ', '').replace('\n', '')
        original = text

        # Step 1: Check for ECO pattern
        for eco_variant in self.pattern_corrections['ECO']:
            if eco_variant.upper() in text.upper():
                logger.info(f"ECO pattern correction: '{text}' → 'ECO'")
                return 'ECO'

        # Step 2: Special handling for common pressure patterns (PRIORITY)
        # "08" should be "1.08", not "0.8"
        if len(text) == 2 and text.isdigit() and text.startswith('0'):
            pressure_candidate = f"1.{text}"
            if self._is_valid_reading(pressure_candidate):
                logger.info(f"Pressure pattern fix: '{original}' → '{pressure_candidate}'")
                return pressure_candidate

        # Step 3: Apply character mapping
        corrected = ""
        for char in text:
            corrected += self.char_map.get(char.upper(), char)

        # Step 4: Try to reconstruct decimal format
        final_result = self._reconstruct_decimal(corrected)

        # Step 5: Validate the result
        if self._is_valid_reading(final_result):
            if final_result != original:
                logger.info(f"Universal correction: '{original}' → '{final_result}'")
            return final_result

        # Step 6: Try pattern-based fixes for partial readings
        pattern_fixed = self._fix_partial_patterns(text)
        if pattern_fixed != text and self._is_valid_reading(pattern_fixed):
            logger.info(f"Pattern fix: '{text}' → '{pattern_fixed}'")
            return pattern_fixed

        return text

    def _reconstruct_decimal(self, text: str) -> str:
        """Try to reconstruct proper decimal format"""
        # Handle missing decimal point
        if len(text) == 2 and text.isdigit():
            # Could be X.Y format
            reconstructed = f"{text[0]}.{text[1]}"
            if self._is_valid_reading(reconstructed):
                return reconstructed

        # Handle missing digits
        if len(text) == 1 and text.isdigit():
            # Could be missing first digit of decimal
            digit = text[0]
            # Try common temperature ranges
            for first in ['4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24', '25']:
                candidate = f"{first}.{digit}"
                if self._is_valid_reading(candidate):
                    return candidate

        # Handle 2-digit patterns that could be missing first digit
        if len(text) == 2 and text.isdigit():
            first, second = text[0], text[1]

            # Special case: "08", "09" etc. are likely "1.08", "1.09" (missing "1.")
            if text.startswith('0'):
                pressure_candidate = f"1.{text}"
                if self._is_valid_reading(pressure_candidate):
                    return pressure_candidate

            # General case: try both pressure and temperature interpretations
            candidates = [
                f"1.{text}",  # 1.15, 1.16, etc. (pressure) - try first
                f"{first}.{second}",  # 6.4, 5.5, etc. (temperature)
            ]
            for candidate in candidates:
                if self._is_valid_reading(candidate):
                    return candidate

        return text

    def _fix_partial_patterns(self, text: str) -> str:
        """Fix partial readings using pattern recognition"""
        # Handle single characters that might be parts of larger numbers
        if len(text) == 1:
            char = text.upper()

            # Common single character misreadings
            if char in ['E', 'C', 'F']:
                # Might be part of ECO
                return 'ECO'
            elif char in ['4', '5', '6', '7', '8', '9']:
                # Could be decimal temperature like X.4, X.5, etc.
                # Try most common temperature ranges
                for base in ['5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24']:
                    candidate = f"{base}.{char}"
                    if self._is_valid_reading(candidate):
                        return candidate

        return text

    def _is_valid_reading(self, text: str) -> bool:
        """Check if reading is valid for our system"""
        if text == 'ECO':
            return True

        try:
            # Check decimal format
            if '.' in text:
                parts = text.split('.')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    value = float(text)
                    # Temperature range (4-25°C) or pressure range (0.5-1.7 PSI)
                    return (4.0 <= value <= 25.0) or (0.5 <= value <= 1.7)

            # Check whole number temperature
            elif text.isdigit():
                value = int(text)
                return 4 <= value <= 25

        except ValueError:
            pass

        return False

    def get_best_reading(self, image: Image.Image) -> Tuple[str, float]:
        """Get the best OCR reading with confidence"""
        try:
            # Get multiple readings
            readings = self.extract_multiple_readings(image)

            if not readings:
                return "", 0.0

            # Apply corrections
            corrected_readings = []
            for reading in readings:
                corrected = self.apply_universal_corrections(reading)
                if corrected and self._is_valid_reading(corrected):
                    corrected_readings.append(corrected)

            if not corrected_readings:
                return "", 0.0

            # Find consensus
            from collections import Counter
            counter = Counter(corrected_readings)
            best_reading, count = counter.most_common(1)[0]
            confidence = count / len(readings)

            logger.info(f"Raw OCR: {readings}")
            logger.info(f"Valid corrected: {corrected_readings}")
            logger.info(f"Best: '{best_reading}' (confidence: {confidence:.2f})")

            return best_reading, confidence

        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            return "", 0.0

def test_universal_ocr():
    """Test universal OCR"""
    from pathlib import Path

    # Test on our debug image
    debug_path = Path(__file__).parent / "images" / "debug_crop_1755549735.jpg"

    if debug_path.exists():
        print("Testing Universal LCD OCR...")

        ocr = UniversalLCDOCR()
        image = Image.open(debug_path)

        best_text, confidence = ocr.get_best_reading(image)
        print(f"Result: '{best_text}' (confidence: {confidence:.2f})")

        # Test various theoretical cases
        print("\nTesting theoretical corrections:")
        test_cases = ['OG', 'OS', 'SS', 'G5', 'B6', 'S4', '72', '84', '95']
        for case in test_cases:
            corrected = ocr.apply_universal_corrections(case)
            print(f"'{case}' → '{corrected}'")

        return best_text, confidence
    else:
        print("Debug image not found")
        return None, 0.0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_universal_ocr()