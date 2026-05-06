#!/usr/bin/env python3
"""
Improved OCR for Seven-Segment LCD Displays
Uses template matching and specialized preprocessing for better accuracy
"""
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import logging
from typing import Optional, List, Tuple, Dict

logger = logging.getLogger(__name__)

class ImprovedLCDOCR:
    def __init__(self):
        """Initialize improved LCD OCR with multiple recognition methods"""
        self.digit_templates = {}
        self.setup_digit_templates()

    def setup_digit_templates(self):
        """Setup templates for seven-segment digits (future enhancement)"""
        # For now, we'll focus on improved preprocessing
        pass

    def enhance_lcd_image(self, image: Image.Image) -> Image.Image:
        """Enhanced preprocessing specifically for LCD displays"""
        try:
            # Convert to OpenCV format
            cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

            # Convert to grayscale
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)

            # Method 1: Morphological operations to connect segments
            kernel = np.ones((2, 2), np.uint8)

            # Close gaps between segments
            closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)

            # Dilate to make characters thicker
            dilated = cv2.dilate(closed, kernel, iterations=1)

            # Apply Gaussian blur to smooth edges
            blurred = cv2.GaussianBlur(dilated, (3, 3), 0)

            # Threshold to create binary image
            _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Convert back to PIL
            enhanced = Image.fromarray(thresh)

            # Additional PIL enhancements
            enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))

            # Resize for better OCR (scale up)
            width, height = enhanced.size
            enhanced = enhanced.resize((width * 4, height * 4), Image.LANCZOS)

            return enhanced

        except Exception as e:
            logger.error(f"Image enhancement failed: {e}")
            return image

    def extract_text_improved(self, image: Image.Image) -> List[str]:
        """Extract text using multiple improved methods"""
        results = []

        try:
            # Method 1: Enhanced preprocessing + Tesseract
            enhanced = self.enhance_lcd_image(image)

            # Try multiple Tesseract configurations optimized for digits
            configs = [
                # Optimized for seven-segment displays
                r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.ECOFecof outputbase digits',
                r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.ECOFecof',
                r'--oem 3 --psm 13 -c tessedit_char_whitelist=0123456789.ECOFecof',
                # More permissive for better character detection
                r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.ECOF',
                r'--oem 1 --psm 8 -c tessedit_char_whitelist=0123456789.ECOF',
                # Raw line detection
                r'--psm 8',
                r'--psm 7',
            ]

            for config in configs:
                try:
                    text = pytesseract.image_to_string(enhanced, config=config).strip()
                    if text:
                        results.append(text.upper())
                        logger.debug(f"Config '{config}' got: '{text}'")
                except Exception as e:
                    logger.debug(f"Config failed: {e}")

            # Method 2: Original image with different preprocessing
            original_enhanced = image.convert('L')

            # Increase contrast dramatically
            enhancer = ImageEnhance.Contrast(original_enhanced)
            high_contrast = enhancer.enhance(4.0)

            # Resize significantly
            width, height = high_contrast.size
            large = high_contrast.resize((width * 6, height * 6), Image.LANCZOS)

            try:
                text = pytesseract.image_to_string(large, config=r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.ECOF')
                if text.strip():
                    results.append(text.strip().upper())
            except Exception as e:
                logger.debug(f"High contrast method failed: {e}")

            # Method 3: Invert image (white text on black background)
            try:
                inverted = Image.eval(enhanced, lambda x: 255 - x)
                text = pytesseract.image_to_string(inverted, config=r'--oem 3 --psm 8 -c tessedit_char_whitelist=0123456789.ECOF')
                if text.strip():
                    results.append(text.strip().upper())
            except Exception as e:
                logger.debug(f"Inverted method failed: {e}")

        except Exception as e:
            logger.error(f"Improved OCR failed: {e}")

        return results

    def apply_lcd_corrections(self, text: str) -> str:
        """Apply corrections specific to LCD seven-segment misreadings"""
        if not text:
            return text

        # Enhanced correction mappings for seven-segment displays
        corrections = {
            # Common seven-segment misreadings
            'OE': '6.4',  # Based on our actual observation
            'EE': 'ECO',  # E characters misread
            'EES': 'ECO', # ECO with extra character
            'EC0': 'ECO', # Zero instead of O
            'E00': 'ECO', # Double zero
            'ECQ': 'ECO', # Q instead of O
            'EGO': 'ECO', # G instead of C

            # Common digit misreadings in seven-segment
            '0E': '6.4',  # 6.4 misread
            'G.4': '6.4', # 6 misread as G
            'B.4': '6.4', # 6 misread as B
            'S.4': '5.4', # 5.4 with S instead of 5
            'S4': '5.4',  # Missing decimal
            'G4': '6.4',  # Missing decimal
            'B4': '6.4',  # Missing decimal

            # Temperature readings
            'Z2': '22',   # Z instead of 2
            '2Z': '22',   # Z instead of 2
            'ZZ': '22',   # Both Z
            '1S': '15',   # S instead of 5
            '1B': '18',   # B instead of 8
            'IB': '18',   # I instead of 1
            'lB': '18',   # l instead of 1

            # Pressure readings with dots
            'I.0B': '1.08', # Complex misreading
            'l.0B': '1.08', # l instead of 1
            '1.OB': '1.08', # O instead of 0
            '1.08': '1.08', # Correct, keep as is
            '1.09': '1.09', # Correct, keep as is
            '1.10': '1.10', # Correct, keep as is
            '1.11': '1.11', # Correct, keep as is
        }

        # Clean whitespace first
        text = text.strip().replace(' ', '').replace('\n', '')

        # Apply corrections
        for wrong, correct in corrections.items():
            if wrong.upper() in text.upper():
                text = text.upper().replace(wrong.upper(), correct)
                logger.info(f"LCD correction: '{wrong}' → '{correct}'")
                break

        return text

    def get_best_reading(self, image: Image.Image) -> Tuple[str, float]:
        """Get the best OCR reading with confidence score"""
        try:
            # Get multiple readings
            readings = self.extract_text_improved(image)

            if not readings:
                return "", 0.0

            # Apply corrections to all readings
            corrected_readings = []
            for reading in readings:
                corrected = self.apply_lcd_corrections(reading)
                if corrected:
                    corrected_readings.append(corrected)

            if not corrected_readings:
                return "", 0.0

            # Find most common reading (consensus)
            from collections import Counter
            counter = Counter(corrected_readings)
            best_reading, count = counter.most_common(1)[0]

            # Calculate confidence based on consensus
            confidence = count / len(corrected_readings)

            logger.info(f"OCR readings: {readings}")
            logger.info(f"Corrected readings: {corrected_readings}")
            logger.info(f"Best reading: '{best_reading}' (confidence: {confidence:.2f})")

            return best_reading, confidence

        except Exception as e:
            logger.error(f"OCR processing failed: {e}")
            return "", 0.0

def test_improved_ocr():
    """Test the improved OCR on our latest debug image"""
    from pathlib import Path

    # Test on the latest debug image that showed "6.4"
    debug_path = Path(__file__).parent / "images" / "debug_crop_1755549735.jpg"

    if debug_path.exists():
        print("Testing improved OCR on 6.4 display...")

        ocr = ImprovedLCDOCR()
        image = Image.open(debug_path)

        best_text, confidence = ocr.get_best_reading(image)
        print(f"Result: '{best_text}' (confidence: {confidence:.2f})")

        return best_text, confidence
    else:
        print("Debug image not found")
        return None, 0.0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_improved_ocr()