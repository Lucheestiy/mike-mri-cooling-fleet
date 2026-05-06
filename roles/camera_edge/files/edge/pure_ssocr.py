#!/usr/bin/env python3
"""
Pure SSOCR-only LCD OCR - NO TESSERACT
Uses only SSOCR (Seven Segment Optical Character Recognition)
Designed specifically for seven-segment LCD displays
"""
import subprocess
import os
import tempfile
import logging
import re
import json
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
from typing import Optional, Tuple, List
from pathlib import Path
from dotenv import load_dotenv

# Load environment for crop coordinates
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 708, "y": 520, "w": 364, "h": 182}'))

logger = logging.getLogger(__name__)

class PureSSocrLCDOCR:
    def __init__(self):
        """Initialize pure SSOCR-based LCD OCR"""
        self.ssocr_available = self._check_ssocr_available()
        self.last_confidence = 0.0

        if not self.ssocr_available:
            raise RuntimeError("SSOCR not available! Cannot proceed without SSOCR.")

        logger.info("✅ Pure SSOCR mode - specialized seven-segment OCR only")

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

    def _preprocess_for_ssocr(self, image: Image.Image) -> List[Image.Image]:
        """Create multiple preprocessed versions for SSOCR"""
        variants = []

        # Original image
        variants.append(image)

        # High contrast version
        enhancer = ImageEnhance.Contrast(image)
        high_contrast = enhancer.enhance(3.0)
        variants.append(high_contrast)

        # More aggressive contrast for LCD
        ultra_contrast = enhancer.enhance(5.0)
        variants.append(ultra_contrast)

        # Brightness adjusted versions
        brightness_enhancer = ImageEnhance.Brightness(image)
        bright = brightness_enhancer.enhance(1.5)
        dark = brightness_enhancer.enhance(0.7)
        very_bright = brightness_enhancer.enhance(2.0)
        variants.append(bright)
        variants.append(dark)
        variants.append(very_bright)

        # Sharpened version
        sharpened = image.filter(ImageFilter.SHARPEN)
        variants.append(sharpened)

        # Scaled up version for better digit recognition
        width, height = image.size
        scaled = image.resize((width * 2, height * 2), Image.LANCZOS)
        variants.append(scaled)

        return variants

    def _extract_with_ssocr(self, image: Image.Image) -> List[str]:
        """Extract text using SSOCR designed for RED LCD digits on full images"""
        results = []
        temp_path = None

        try:
            # Save the ORIGINAL image without preprocessing to preserve color information
            temp_path = self._save_temp_image(image)

            # SSOCR configurations specifically for RED LCD digits
            # Use crop command to extract LCD region directly from full color image
            ssocr_configs = [
                # Direct crop from full image with RGB processing for red digits
                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 'r_threshold', '-t', '30', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 'r_threshold', '-t', '40', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 'r_threshold', '-t', '50', '--number-digits=-1', '--foreground=white', temp_path],

                # RGB threshold approach for red digits
                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 'rgb_threshold', '-t', '30', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 'rgb_threshold', '-t', '40', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 'rgb_threshold', '-t', '50', '--number-digits=-1', '--foreground=white', temp_path],

                # Direct crop with various thresholds (no color processing)
                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 '-t', '30', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 '-t', '40', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 '-t', '50', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 '-t', '60', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 '-t', '70', '--number-digits=-1', '--foreground=white', temp_path],

                # With morphological processing for red LCD
                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 'make_mono', 'erosion', '-t', '40', '--number-digits=-1', '--foreground=white', temp_path],

                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 'make_mono', 'dilation', '-t', '40', '--number-digits=-1', '--foreground=white', temp_path],

                # Iterative thresholding with crop
                ['ssocr', 'crop', str(OCR_CROP_COORDS['x']), str(OCR_CROP_COORDS['y']),
                 str(OCR_CROP_COORDS['w']), str(OCR_CROP_COORDS['h']),
                 '--iter-threshold', '--number-digits=-1', '--foreground=white', temp_path],
            ]

            for config in ssocr_configs:
                try:
                    result = subprocess.run(config,
                                          capture_output=True,
                                          text=True,
                                          timeout=10)

                    # SSOCR returns non-zero exit codes even on success sometimes
                    if result.stdout.strip():
                        text = result.stdout.strip()
                        # Clean and validate
                        cleaned = self._clean_ssocr_output(text)
                        if cleaned and self._is_valid_reading(cleaned):
                            results.append(cleaned)
                            logger.debug(f"SSOCR config {config[1:3]}: '{cleaned}'")

                except subprocess.TimeoutExpired:
                    logger.debug(f"SSOCR timeout for config: {config}")
                    continue
                except Exception as e:
                    logger.debug(f"SSOCR error for config {config}: {e}")
                    continue

        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

        return results

    def _clean_ssocr_output(self, text: str) -> str:
        """Clean SSOCR output text"""
        if not text:
            return ""

        # Remove whitespace and clean up
        cleaned = text.strip()

        # Remove any non-digit/non-decimal characters
        cleaned = re.sub(r'[^0-9.]', '', cleaned)

        # Handle missing leading digit and decimal point for pressure readings
        # Common SSOCR patterns for LCD pressure readings:
        # "08" should be "1.08", "88" should be "1.88" (if reasonable), etc.

        if len(cleaned) == 2 and cleaned.isdigit():
            # Two digits like "08", "12" etc. - be conservative
            value = int(cleaned)
            if 5 <= value <= 17:  # Only reasonable pressure values (1.05 to 1.17)
                cleaned = f"1.{cleaned}"
            # Reject "88", "81" etc. that don't make sense
        elif len(cleaned) == 3 and cleaned.isdigit():
            # Three digits like "108" - only handle obvious cases
            if cleaned.startswith('10') and cleaned[2:] in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                # "108" -> "1.08", "109" -> "1.09", etc.
                cleaned = f"1.{cleaned[1:]}"
            # Reject patterns like "881", "188" etc.
        elif cleaned.startswith('.') and len(cleaned) >= 2:
            # If starts with decimal point like ".88", ".85", etc.
            try:
                decimal_value = float(cleaned)
                if 0.5 <= decimal_value <= 0.99:  # Likely missing "1" at start
                    cleaned = "1" + cleaned  # Make it 1.88, 1.85, etc.
            except ValueError:
                pass

        # Handle LCD dual decimal format: "1.0.1" should become "1.01"
        if cleaned.count('.') == 2:
            # Pattern like "1.0.1" -> "1.01"
            parts = cleaned.split('.')
            if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
                # Combine: "1" + "." + "0" + "1" = "1.01"
                cleaned = parts[0] + '.' + parts[1] + parts[2]
        elif cleaned.count('.') > 2:
            # Multiple dots - keep only first one (fallback)
            parts = cleaned.split('.')
            cleaned = parts[0] + '.' + ''.join(parts[1:])

        return cleaned

    def _is_valid_reading(self, text: str) -> bool:
        """Check if reading is valid for our use case"""
        if not text or len(text) < 1:
            return False

        try:
            # Must be numeric
            value = float(text)

            # Check ranges for our expected values
            # Temperature: 4-25°C, Pressure: 0.5-1.7 PSI
            # Expanded range to handle variations and OCR inaccuracies
            if 0.4 <= value <= 25.0:  # Temperature and pressure ranges
                return True

        except ValueError:
            pass

        return False

    def _score_reading(self, text: str) -> float:
        """Score reading based on likelihood and format"""
        if not text:
            return 0.0

        try:
            value = float(text)
            score = 0.0

            # Pressure range scoring (most important)
            if 0.5 <= value <= 1.7:
                score += 0.8  # High score for pressure range
            elif 0.4 <= value <= 2.0:
                score += 0.6  # Medium score for near-pressure range

            # Temperature range scoring
            elif 4.0 <= value <= 25.0:
                score += 0.5  # Medium score for temperature range

            # Format scoring
            if '.' in text:
                score += 0.2  # Decimal format is expected

            # Length scoring (3-4 characters typical: 1.5, 1.08, etc.)
            if 3 <= len(text) <= 4:
                score += 0.1

            return min(score, 1.0)

        except ValueError:
            return 0.0

    def get_best_reading(self, image: Image.Image) -> Tuple[str, float]:
        """Get the best OCR reading using pure SSOCR with emergency fallback"""

        # Extract with SSOCR
        ssocr_results = self._extract_with_ssocr(image)

        if not ssocr_results:
            logger.warning("❌ SSOCR: No valid readings found")
            self.last_confidence = 0.0
            return "", 0.0

        # Score all candidates
        scored_results = [(result, self._score_reading(result))
                         for result in ssocr_results]

        # Filter valid scores
        valid_scored = [(r, s) for r, s in scored_results if s > 0]

        if not valid_scored:
            logger.warning("❌ SSOCR: No valid scored readings")
            self.last_confidence = 0.0
            return "", 0.0

        # Get best result
        best_result, best_score = max(valid_scored, key=lambda x: x[1])

        # Calculate confidence based on consensus
        from collections import Counter
        result_counts = Counter(ssocr_results)
        consensus = result_counts.get(best_result, 1)
        confidence = min(best_score * (consensus / len(ssocr_results)), 1.0)

        # Store for external access
        self.last_confidence = confidence

        logger.info(f"🔄 Using SSOCR only")
        logger.info(f"📊 SSOCR candidates: {list(set(ssocr_results))}")
        logger.info(f"✅ Best: '{best_result}' (confidence: {confidence:.2f})")

        return best_result, confidence


# Test function
def test_pure_ssocr():
    """Test function for pure SSOCR"""
    try:
        ocr = PureSSocrLCDOCR()

        # Test with debug image if available
        debug_image_path = Path(__file__).parent / "images" / "debug_crop_1755556263.jpg"
        if debug_image_path.exists():
            image = Image.open(debug_image_path)
            result, confidence = ocr.get_best_reading(image)
            print(f"Test result: '{result}' (confidence: {confidence:.2f})")
            return result, confidence
        else:
            print("No test image found")
            return None, 0.0

    except Exception as e:
        print(f"Test failed: {e}")
        return None, 0.0

if __name__ == "__main__":
    test_pure_ssocr()