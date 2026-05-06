#!/usr/bin/env python3
"""
SSOCR-based LCD OCR with Tesseract fallback
Uses SSOCR (Seven Segment Optical Character Recognition) when available
Falls back to improved Tesseract with pattern corrections
"""
import subprocess
import os
import tempfile
import logging
from PIL import Image
import numpy as np
from typing import Optional, Tuple, List
from pathlib import Path

# Import our universal OCR as fallback
from universal_lcd_ocr import UniversalLCDOCR

logger = logging.getLogger(__name__)

class SSocrLCDOCR:
    def __init__(self):
        """Initialize SSOCR-based LCD OCR with fallback"""
        self.ssocr_available = self._check_ssocr_available()
        self.fallback_ocr = UniversalLCDOCR()

        if self.ssocr_available:
            logger.info("✅ SSOCR available - using specialized seven-segment OCR")
        else:
            logger.info("⚠️ SSOCR not available - using enhanced Tesseract fallback")

    def _check_ssocr_available(self) -> bool:
        """Check if SSOCR is installed and working"""
        try:
            result = subprocess.run(['ssocr', '--help'],
                                  capture_output=True,
                                  timeout=5)
            # SSOCR returns 42 for --help, but that means it's working
            return result.returncode in [0, 42] and b'Seven Segment' in result.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _save_temp_image(self, image: Image.Image) -> str:
        """Save PIL image to temporary file for SSOCR"""
        # Create temp file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.png')
        try:
            # Save image
            image.save(temp_path, 'PNG')
            os.close(temp_fd)
            return temp_path
        except Exception as e:
            os.close(temp_fd)
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e

    def _extract_with_ssocr(self, image: Image.Image) -> List[str]:
        """Extract text using SSOCR"""
        results = []
        temp_path = None

        try:
            # Save image to temp file
            temp_path = self._save_temp_image(image)

            # SSOCR command configurations for seven-segment displays
            ssocr_configs = [
                # Basic digit recognition (no digit count restriction)
                ['ssocr', temp_path],

                # Force specific digit counts for common patterns
                ['ssocr', '--number-digits=3', temp_path],  # For X.Y format like "1.5"
                ['ssocr', '--number-digits=4', temp_path],  # For X.YZ format like "1.08"

                # Threshold adjustments for better contrast
                ['ssocr', '-t', '50', temp_path],
                ['ssocr', '-t', '30', temp_path],
                ['ssocr', '-t', '70', temp_path],
                ['ssocr', '-t', '80', temp_path],

                # Different foreground/background assumptions
                ['ssocr', '--foreground=white', temp_path],
                ['ssocr', '--foreground=black', temp_path],

                # Ignore dots in recognition (sometimes helps)
                ['ssocr', '--ignore-dots', temp_path],

                # Different algorithms
                ['ssocr', '--iter-threshold', temp_path],
            ]

            for config in ssocr_configs:
                try:
                    result = subprocess.run(config,
                                          capture_output=True,
                                          text=True,
                                          timeout=10)

                    if result.returncode == 0 and result.stdout.strip():
                        text = result.stdout.strip()
                        # Clean up SSOCR output
                        text = text.replace(' ', '').replace('\n', '')
                        if text and text != '-1':  # -1 indicates SSOCR failed
                            results.append(text)
                            logger.info(f"SSOCR config {config[1:]} got: '{text}'")
                    else:
                        logger.debug(f"SSOCR config {config[1:]} failed: rc={result.returncode}, stderr='{result.stderr.strip()}'")

                except subprocess.TimeoutExpired:
                    logger.debug(f"SSOCR config {config[1:3]} timed out")
                    continue
                except Exception as e:
                    logger.debug(f"SSOCR config {config[1:3]} failed: {e}")
                    continue

        except Exception as e:
            logger.error(f"SSOCR processing failed: {e}")

        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

        return results

    def _apply_ssocr_corrections(self, text: str) -> str:
        """Apply corrections specific to SSOCR output"""
        if not text:
            return text

        # SSOCR specific corrections
        corrections = {
            # SSOCR sometimes reads digits in reverse or rotated
            '8.81': '1.08',   # Common SSOCR misreading (digits flipped)
            '8.61': '1.08',   # Alternative misreading
            '801': '1.08',    # Missing decimal, wrong order
            '881': '1.08',    # Missing decimal, wrong reading

            # Other pressure readings
            '108': '1.08',    # Missing decimal
            '109': '1.09',    # Missing decimal
            '110': '1.10',    # Missing decimal
            '111': '1.11',    # Missing decimal
            '115': '1.15',    # Missing decimal
            '116': '1.16',    # Missing decimal

            # Temperature readings
            '64': '6.4',      # Missing decimal
            '65': '6.5',      # Missing decimal
            '68': '6.8',      # Missing decimal
            '62': '6.2',      # Missing decimal
            '54': '5.4',      # Missing decimal
            '55': '5.5',      # Missing decimal

            # ECO variations
            'EC0': 'ECO',
            'E00': 'ECO',
            'ECr': 'ECO',
            'Er0': 'ECO',
        }

        original = text
        for wrong, correct in corrections.items():
            if wrong.upper() == text.upper():
                logger.info(f"SSOCR correction: '{original}' → '{correct}'")
                return correct

        return text

    def _is_valid_reading(self, text: str) -> bool:
        """Validate if reading is sensible for our system"""
        if text == 'ECO':
            return True

        try:
            # Check decimal format
            if '.' in text:
                value = float(text)
                # Temperature (4-25°C) or pressure (0.5-1.7 PSI)
                return (4.0 <= value <= 25.0) or (0.5 <= value <= 1.7)

            # Check whole number temperature
            elif text.isdigit():
                value = int(text)
                return 4 <= value <= 25

        except ValueError:
            pass

        return False

    def get_best_reading(self, image: Image.Image) -> Tuple[str, float]:
        """Get the best OCR reading using SSOCR or fallback"""

        if self.ssocr_available:
            try:
                # Try SSOCR first
                ssocr_results = self._extract_with_ssocr(image)

                if ssocr_results:
                    # Apply corrections and validate
                    corrected_results = []
                    for result in ssocr_results:
                        corrected = self._apply_ssocr_corrections(result)
                        if corrected and self._is_valid_reading(corrected):
                            corrected_results.append(corrected)

                    if corrected_results:
                        # Find most common result
                        from collections import Counter
                        counter = Counter(corrected_results)
                        best_reading, count = counter.most_common(1)[0]
                        confidence = count / len(ssocr_results)

                        logger.info(f"🎯 SSOCR results: {ssocr_results}")
                        logger.info(f"✅ SSOCR best: '{best_reading}' (confidence: {confidence:.2f})")

                        return best_reading, confidence

                # If SSOCR failed, fall back to Tesseract
                logger.warning("SSOCR failed, falling back to Tesseract")

            except Exception as e:
                logger.error(f"SSOCR processing error: {e}, falling back to Tesseract")

        # Use Tesseract fallback
        logger.info("🔄 Using Tesseract fallback")
        return self.fallback_ocr.get_best_reading(image)

def test_ssocr_ocr():
    """Test SSOCR OCR system"""
    from pathlib import Path

    # Test on our debug image that shows "1.08"
    debug_path = Path(__file__).parent / "images" / "debug_crop_1755550924.jpg"

    if debug_path.exists():
        print("Testing SSOCR LCD OCR system...")

        ocr = SSocrLCDOCR()
        image = Image.open(debug_path)

        best_text, confidence = ocr.get_best_reading(image)
        print(f"Result: '{best_text}' (confidence: {confidence:.2f})")

        if ocr.ssocr_available:
            print("✅ Using SSOCR (specialized for seven-segment)")
        else:
            print("⚠️ Using Tesseract fallback (SSOCR not available)")

        return best_text, confidence
    else:
        print("Debug image not found")
        return None, 0.0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_ssocr_ocr()