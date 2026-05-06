#!/usr/bin/env python3
"""
Smart MRI Cooling System Monitor
Captures rotating LCD display and extracts:
- Water temperature (4-25°C)
- ECO pressure (0.5-1.7 PSI during ECO mode)
- Scan pressure (0.5-1.7 PSI during MRI scanning)
"""
import os
import json
import time
import re
import logging
import base64
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import requests
from dotenv import load_dotenv
from PIL import Image, ImageEnhance
import numpy as np

# Import pure SSOCR-only LCD OCR
from pure_ssocr import PureSSocrLCDOCR

# Import camera functionality from existing OCR module
import sys
sys.path.append(str(Path(__file__).parent))

try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    import cv2

# Load environment
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Configuration
BACKEND_URL = os.getenv("CAMERA_BACKEND_URL", "https://cam.coolmri.com/api/camera/pressure")
SITE_ID = os.getenv("SITE_ID", "GMCMR2")
IMAGE_WIDTH = int(os.getenv("IMAGE_WIDTH", "1920"))
IMAGE_HEIGHT = int(os.getenv("IMAGE_HEIGHT", "1080"))
OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 708, "y": 520, "w": 364, "h": 182}'))

# Monitoring settings - Extended for pressure priority
CAPTURE_SEQUENCE_DURATION = 45  # Capture for 45 seconds to ensure pressure readings
CAPTURE_INTERVAL = 1.5  # Take picture every 1.5 seconds during sequence
MAX_WAIT_FOR_ECO = 120  # Maximum seconds to wait for ECO mode detection
PRESSURE_PRIORITY_MODE = True  # Continue until pressure is found

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

class SmartMRIMonitor:
    def __init__(self):
        self.camera = None
        self.session = requests.Session()
        self.session.timeout = 30
        self.image_dir = Path(__file__).parent / "images"
        self.image_dir.mkdir(exist_ok=True)

        # Initialize pure SSOCR LCD OCR
        self.lcd_ocr = PureSSocrLCDOCR()

        # Data storage for current monitoring session
        self.captured_readings = {
            'temperature': None,
            'eco_pressure': None,
            'scan_pressure': None,
            'eco_detected': False,
            'scan_detected': False
        }

    def initialize_camera(self) -> bool:
        """Initialize camera (same as camera_ocr.py)"""
        if PICAMERA2_AVAILABLE:
            return self._init_picamera2()
        elif self._check_libcamera_tools():
            return self._init_libcamera()
        else:
            return self._init_opencv()

    def _check_libcamera_tools(self) -> bool:
        """Check if libcamera command-line tools are available"""
        import subprocess
        try:
            result = subprocess.run(['cam', '--list'], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _init_libcamera(self) -> bool:
        """Initialize using libcamera command-line tools"""
        try:
            logger.info("Using libcamera command-line tools...")
            self.camera = "libcamera"
            logger.info("Libcamera tools initialized")
            return True
        except Exception as e:
            logger.error(f"Libcamera initialization failed: {e}")
            return False

    def _init_picamera2(self) -> bool:
        """Initialize Picamera2"""
        try:
            logger.info("Initializing Picamera2...")
            self.camera = Picamera2()
            config = self.camera.create_preview_configuration(
                main={"size": (IMAGE_WIDTH, IMAGE_HEIGHT), "format": "RGB888"}
            )
            self.camera.configure(config)
            self.camera.start()
            time.sleep(2)
            logger.info(f"Picamera2 initialized: {IMAGE_WIDTH}x{IMAGE_HEIGHT}")
            return True
        except Exception as e:
            logger.error(f"Picamera2 initialization failed: {e}")
            return False

    def _init_opencv(self) -> bool:
        """Fallback to OpenCV"""
        try:
            logger.info("Falling back to OpenCV...")
            backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
            devices = [0, 1, 2, 3]

            for backend in backends:
                for device in devices:
                    cap = cv2.VideoCapture(device, backend)
                    if cap.isOpened():
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, IMAGE_WIDTH)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, IMAGE_HEIGHT)
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            self.camera = cap
                            logger.info(f"OpenCV camera initialized - Device: {device}")
                            return True
                        cap.release()
            return False
        except Exception as e:
            logger.error(f"OpenCV initialization failed: {e}")
            return False

    def capture_image(self) -> Optional[np.ndarray]:
        """Capture a single frame"""
        try:
            if PICAMERA2_AVAILABLE and isinstance(self.camera, Picamera2):
                array = self.camera.capture_array("main")
                return array
            elif self.camera == "libcamera":
                return self._capture_with_libcamera()
            else:
                ret, frame = self.camera.read()
                if ret:
                    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return None
        except Exception as e:
            logger.error(f"Image capture failed: {e}")
            return None

    def _capture_with_libcamera(self) -> Optional[np.ndarray]:
        """Capture image using libcamera command-line tools"""
        import subprocess
        import tempfile

        try:
            with tempfile.NamedTemporaryFile(suffix='.ppm', delete=False) as tmp_file:
                tmp_path = tmp_file.name

            cmd = [
                'cam', '-c', '1', '--capture=1', f'--file={tmp_path}',
                '--stream', f'width={IMAGE_WIDTH},height={IMAGE_HEIGHT},role=still,pixelformat=BGR888'
            ]

            result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)

            if result.returncode == 0 and os.path.exists(tmp_path):
                with Image.open(tmp_path) as img:
                    array = np.array(img.convert('RGB'))
                    return array
            return None
        except Exception as e:
            logger.error(f"Libcamera capture error: {e}")
            return None
        finally:
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def preprocess_for_ocr(self, image: np.ndarray) -> Image.Image:
        """Preprocess image for OCR"""
        pil_image = Image.fromarray(image)

        # Crop to LCD display region
        x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
        cropped = pil_image.crop((x, y, x + w, y + h))

        # Convert to grayscale and enhance
        gray = cropped.convert('L')
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.0)

        return enhanced

    def extract_display_text(self, image: Image.Image) -> str:
        """Extract text from LCD display using pure SSOCR"""
        try:
            # Use pure SSOCR LCD OCR system
            best_text, confidence = self.lcd_ocr.get_best_reading(image)

            if confidence > 0.1:  # Lower threshold since SSOCR is more reliable
                logger.info(f"✅ Pure SSOCR: '{best_text}' (confidence: {confidence:.2f})")
                return best_text.upper()
            else:
                logger.warning(f"❌ Low confidence SSOCR: '{best_text}' (confidence: {confidence:.2f})")
                return ""

        except RuntimeError as e:
            logger.error(f"SSOCR not available: {e}")
            raise
        except Exception as e:
            logger.error(f"Pure SSOCR extraction failed: {e}")
            return ""


    def parse_reading(self, text: str) -> Dict[str, any]:
        """Parse OCR text to extract temperature, pressure, and mode"""
        result = {
            'temperature': None,
            'pressure': None,
            'is_eco': False,
            'raw_text': text
        }

        if not text:
            return result

        # Check for ECO mode
        if 'ECO' in text:
            result['is_eco'] = True
            logger.info(f"ECO mode detected in: {text}")

        # Fix common LCD OCR errors first
        fixed_text = self._fix_lcd_ocr_errors(text)
        if fixed_text != text:
            logger.info(f"Fixed LCD OCR: '{text}' -> '{fixed_text}'")
            text = fixed_text

        # Extract temperature (4-25°C range) - NO C suffix, just numbers
        # Temperature appears as plain numbers: 18, 22, 8.4, etc.
        # Need to distinguish from pressure based on value ranges

        # Look for temperature values (4-25 range)
        temp_patterns = [
            r'^(\d{1,2})$',        # e.g., "18", "22" (whole numbers 4-25)
            r'^(\d\.\d)$',         # e.g., "8.4" (but only if >= 4.0)
        ]

        for pattern in temp_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    temp = float(match)
                    if 4.0 <= temp <= 25.0:
                        # Additional check: if it's a decimal like 8.4, it could be temperature
                        # if it's in the reasonable temperature range
                        if '.' in match and temp < 10.0:
                            # Values like 8.4, 9.2 are likely temperature
                            result['temperature'] = temp
                            logger.info(f"Temperature detected: {temp}°C from text: {text}")
                            break
                        elif '.' not in match:
                            # Whole numbers 4-25 are likely temperature
                            result['temperature'] = temp
                            logger.info(f"Temperature detected: {temp}°C from text: {text}")
                            break
                except ValueError:
                    continue

        # Extract pressure (0.5-1.7 PSI range) - only if not already identified as temperature
        if result['temperature'] is None:  # Only look for pressure if no temperature found
            pressure_patterns = [
                r'^(\d\.\d{1,2})$',  # e.g., "1.08", "0.95" (exact match)
                r'^(\d{1})$',        # e.g., "1" (single digit in pressure range)
            ]

            for pattern in pressure_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    try:
                        pressure = float(match)
                        if 0.4 <= pressure <= 2.0:  # Expanded range for SSOCR variations
                            result['pressure'] = pressure
                            logger.info(f"Pressure detected: {pressure} PSI from text: {text}")
                            break
                    except ValueError:
                        continue

        return result

    def _fix_lcd_ocr_errors(self, text: str) -> str:
        """Fix common 3-character LCD OCR misreadings"""
        original_text = text

        # Clean whitespace and normalize
        text = text.strip().replace(' ', '').replace('\n', '')

        # LCD pressure readings - both 3-character (X.XX) and 3-character (X.X) formats
        pressure_fixes = {
            # 4-character format: "1.08" type readings (when displayed as 1.08, 1.09, etc.)
            '(08': '1.08', ')08': '1.08', 'C08': '1.08', 'G08': '1.08', 'O08': '1.08', 'S08': '1.08',
            '(09': '1.09', ')09': '1.09', 'C09': '1.09', 'G09': '1.09', 'O09': '1.09', 'S09': '1.09',
            '(07': '1.07', ')07': '1.07', 'C07': '1.07', 'G07': '1.07', 'O07': '1.07', 'S07': '1.07',
            '(06': '1.06', ')06': '1.06', 'C06': '1.06', 'G06': '1.06', 'O06': '1.06', 'S06': '1.06',
            '(05': '1.05', ')05': '1.05', 'C05': '1.05', 'G05': '1.05', 'O05': '1.05', 'S05': '1.05',
            '(10': '1.10', ')10': '1.10', 'C10': '1.10', 'G10': '1.10', 'O10': '1.10', 'S10': '1.10',
            '(11': '1.11', ')11': '1.11', 'C11': '1.11', 'G11': '1.11', 'O11': '1.11', 'S11': '1.11',
            '(12': '1.12', ')12': '1.12', 'C12': '1.12', 'G12': '1.12', 'O12': '1.12', 'S12': '1.12',
            '(13': '1.13', ')13': '1.13', 'C13': '1.13', 'G13': '1.13', 'O13': '1.13', 'S13': '1.13',
            '(14': '1.14', ')14': '1.14', 'C14': '1.14', 'G14': '1.14', 'O14': '1.14', 'S14': '1.14',
            '(15': '1.15', ')15': '1.15', 'C15': '1.15', 'G15': '1.15', 'O15': '1.15', 'S15': '1.15',
            '(16': '1.16', ')16': '1.16', 'C16': '1.16', 'G16': '1.16', 'O16': '1.16', 'S16': '1.16',
            '(17': '1.17', ')17': '1.17', 'C17': '1.17', 'G17': '1.17', 'O17': '1.17', 'S17': '1.17',

            # NOTE: Removed auto-conversion of 8.4->0.84 style since 8.4 is likely temperature
            # Only keep obvious pressure readings in 0.5-1.7 range

            # Alternative misreadings with colon/semicolon
            '1:08': '1.08', '1;08': '1.08', '1,08': '1.08',
            '1:09': '1.09', '1;09': '1.09', '1,09': '1.09',
            '1:07': '1.07', '1;07': '1.07', '1,07': '1.07',
            '1:06': '1.06', '1;06': '1.06', '1,06': '1.06',
            '1:05': '1.05', '1;05': '1.05', '1,05': '1.05',
            '1:10': '1.10', '1;10': '1.10', '1,10': '1.10',
            '1:11': '1.11', '1;11': '1.11', '1,11': '1.11',
            '1:12': '1.12', '1;12': '1.12', '1,12': '1.12',
            '1:13': '1.13', '1;13': '1.13', '1,13': '1.13',
            '1:14': '1.14', '1;14': '1.14', '1,14': '1.14',
            '1:15': '1.15', '1;15': '1.15', '1,15': '1.15',
            '1:16': '1.16', '1;16': '1.16', '1,16': '1.16',
            '1:17': '1.17', '1;17': '1.17', '1,17': '1.17',

            # Letter misreadings
            'l.08': '1.08', 'I.08': '1.08', '|.08': '1.08',
            'l.09': '1.09', 'I.09': '1.09', '|.09': '1.09',
            'l.07': '1.07', 'I.07': '1.07', '|.07': '1.07',
            'l.10': '1.10', 'I.10': '1.10', '|.10': '1.10',
            'l.11': '1.11', 'I.11': '1.11', '|.11': '1.11',
            'l.12': '1.12', 'I.12': '1.12', '|.12': '1.12',
            'l.13': '1.13', 'I.13': '1.13', '|.13': '1.13',
            'l.14': '1.14', 'I.14': '1.14', '|.14': '1.14',
            'l.15': '1.15', 'I.15': '1.15', '|.15': '1.15',
            'l.16': '1.16', 'I.16': '1.16', '|.16': '1.16',
            'l.17': '1.17', 'I.17': '1.17', '|.17': '1.17',
        }

        # Temperature readings (no C suffix - just numbers)
        temp_fixes = {
            # Keep temperature values as-is (no C added)
            '22': '22', '23': '23', '24': '24', '25': '25',
            '21': '21', '20': '20', '19': '19', '18': '18',
            '17': '17', '16': '16', '15': '15', '14': '14',
            '13': '13', '12': '12', '11': '11', '10': '10',
            # Remove conflicting single/double digit mappings that interfere with pressure readings

            # Common temperature misreadings (no C added)
            '2Z': '22', '2S': '25', '2O': '20', 'Z2': '22', 'S2': '25',
            '1S': '15', '1B': '18', '1O': '10', 'OS': '5', 'O5': '5',
            'ZZ': '22', 'SS': '25', 'BB': '18',
        }

        # ECO readings (3 characters)
        eco_fixes = {
            'ECO': 'ECO', 'EC0': 'ECO', 'E00': 'ECO', 'ECQ': 'ECO', 'EGO': 'ECO'
        }

        # Apply all fixes
        all_fixes = {**pressure_fixes, **temp_fixes, **eco_fixes}

        for wrong, correct in all_fixes.items():
            if wrong.upper() in text.upper():
                text = text.upper().replace(wrong.upper(), correct)
                break  # Apply first match

        # Pattern-based reconstruction for incomplete readings
        # Handle cases where only 2 characters are detected
        if len(text) == 2:
            # Could be missing first character (pressure reading)
            if text.isdigit() and 5 <= int(text) <= 17:
                text = f"1.{text[0]}{text[1]}"
            # Temperature readings stay as-is (no C suffix added)

        # Handle single digit
        elif len(text) == 1 and text.isdigit():
            # Keep as-is, don't add C suffix
            pass

        return text

    def send_debug_image_to_website(self, full_image: np.ndarray, cropped_image: Image.Image,
                                   ocr_text: str, reading: Dict[str, any]) -> bool:
        """Send debug images to website for user review"""
        try:
            # Convert full image to PIL and draw crop box
            full_pil = Image.fromarray(full_image)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(full_pil)

            # Draw red rectangle around crop region
            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            draw.rectangle([x, y, x + w, y + h], outline='red', width=3)

            # Convert images to base64
            def image_to_base64(img):
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85)
                return base64.b64encode(buffer.getvalue()).decode()

            full_b64 = image_to_base64(full_pil)
            crop_b64 = image_to_base64(cropped_image.convert('RGB'))

            # Create payload
            payload = {
                "timestamp": int(datetime.now().timestamp()),
                "site_id": SITE_ID,
                "source": "smart_monitor_debug",
                "full_image": full_b64,
                "cropped_image": crop_b64,
                "ocr_text": ocr_text,
                "reading": reading,
                "crop_coords": OCR_CROP_COORDS
            }

            # Try multiple endpoints to send images
            endpoints = [
                "https://cam.coolmri.com/api/camera/images",
                "https://cam.coolmri.com/api/camera/calibration",
                "https://cam.coolmri.com/api/camera/debug"
            ]

            success = False
            for debug_url in endpoints:
                try:
                    response = self.session.post(debug_url, json=payload, timeout=10)
                    if response.status_code in [200, 201]:
                        logger.info(f"✅ Images sent to {debug_url}")
                        success = True
                        break
                    else:
                        logger.debug(f"Endpoint {debug_url} returned {response.status_code}")
                except Exception as e:
                    logger.debug(f"Endpoint {debug_url} failed: {e}")

            if not success:
                # Save locally as backup
                timestamp = int(datetime.now().timestamp())
                full_path = self.image_dir / f"debug_full_{timestamp}.jpg"
                crop_path = self.image_dir / f"debug_crop_{timestamp}.jpg"

                full_pil.save(full_path, "JPEG", quality=85)
                cropped_image.convert('RGB').save(crop_path, "JPEG", quality=85)

                logger.info(f"📁 Images saved locally: {full_path} and {crop_path}")
                logger.info(f"🔍 OCR: '{ocr_text}' → {reading}")
                return False

            if response.status_code in [200, 201]:
                logger.info(f"Debug image sent: OCR='{ocr_text}', Reading={reading}")
                return True
            else:
                logger.warning(f"Debug endpoint returned {response.status_code}")
                return False

        except Exception as e:
            logger.warning(f"Failed to send debug image: {e}")
            return False

    def run_capture_sequence(self) -> Dict[str, any]:
        """Run capture sequence to collect all rotating display values - PRESSURE PRIORITY"""
        logger.info(f"🎯 Starting {CAPTURE_SEQUENCE_DURATION}s PRESSURE-PRIORITY capture sequence...")
        logger.info("🔍 Will continue until pressure readings are found!")

        start_time = time.time()
        capture_count = 0
        readings = []
        pressure_found = False

        while time.time() - start_time < CAPTURE_SEQUENCE_DURATION or (PRESSURE_PRIORITY_MODE and not pressure_found):
            # Capture image
            image = self.capture_image()
            if image is None:
                logger.warning("Failed to capture image, continuing...")
                time.sleep(CAPTURE_INTERVAL)
                continue

            # Process OCR - pass FULL image to preserve color for SSOCR
            full_pil_image = Image.fromarray(image)
            text = self.extract_display_text(full_pil_image)

            # Still create processed version for debug/backup
            processed = self.preprocess_for_ocr(image)

            if text:
                reading = self.parse_reading(text)
                readings.append(reading)
                logger.info(f"Capture {capture_count + 1}: {reading}")

                # Send image to website for review and comparison
                try:
                    self.send_individual_reading_to_backend(image, processed, text, reading, capture_count + 1)
                    self.send_debug_image_to_website(image, processed, text, reading)
                except Exception as e:
                    logger.warning(f"Failed to send debug image: {e}")

                # Update captured readings
                if reading['temperature'] is not None:
                    self.captured_readings['temperature'] = reading['temperature']

                if reading['pressure'] is not None:
                    pressure_found = True  # Mark that we found pressure
                    logger.info(f"🎯 PRESSURE FOUND: {reading['pressure']} PSI")

                    if reading['is_eco']:
                        self.captured_readings['eco_pressure'] = reading['pressure']
                        self.captured_readings['eco_detected'] = True
                        logger.info(f"✅ ECO pressure captured: {reading['pressure']} PSI")
                    else:
                        self.captured_readings['scan_pressure'] = reading['pressure']
                        self.captured_readings['scan_detected'] = True
                        logger.info(f"✅ SCAN pressure captured: {reading['pressure']} PSI")

                # Check if we have essential readings for early exit
                if PRESSURE_PRIORITY_MODE and pressure_found and capture_count >= 10:
                    logger.info(f"🎯 PRESSURE PRIORITY: Essential readings captured after {capture_count} images")
                    break

            capture_count += 1
            time.sleep(CAPTURE_INTERVAL)

        elapsed = time.time() - start_time
        logger.info(f"🎯 PRESSURE-PRIORITY capture complete: {capture_count} images in {elapsed:.1f}s")

        if pressure_found:
            logger.info("✅ SUCCESS: Return pressure readings captured!")
        else:
            logger.warning("❌ WARNING: No pressure readings found - may need longer capture or different timing")

        return self.captured_readings

    def send_individual_reading_to_backend(self, image_array: np.ndarray, processed_image: Image.Image, ocr_text: str, reading_data: Dict, capture_num: int) -> bool:
        """Send individual capture image with OCR annotation to backend for comparison"""
        try:
            timestamp = int(datetime.now(timezone.utc).timestamp())

            # Convert to PIL Image
            full_image = Image.fromarray(image_array)

            # Create cropped image (processed_image is already cropped)
            cropped_image = processed_image

            # Convert images to base64
            def image_to_base64(img):
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=95)
                return base64.b64encode(buffer.getvalue()).decode('utf-8')

            full_image_b64 = image_to_base64(full_image)
            cropped_image_b64 = image_to_base64(cropped_image)

            # Create detailed source name with OCR results for comparison
            ocr_confidence = self.lcd_ocr.last_confidence if hasattr(self.lcd_ocr, 'last_confidence') else 0.0
            source_name = f"capture_{capture_num:02d}_ocr_{ocr_text.replace('.', 'p')}_conf_{ocr_confidence:.2f}_calibration"

            payload = {
                "site_id": SITE_ID,
                "timestamp": timestamp,
                "source": source_name,
                "return_pressure": reading_data.get('pressure', 0.0),
                "confidence": ocr_confidence,
                "water_temperature": reading_data.get('temperature'),
                "eco_pressure": reading_data['pressure'] if reading_data.get('is_eco') else None,
                "scan_pressure": reading_data['pressure'] if not reading_data.get('is_eco') else None,
                "eco_mode_detected": reading_data.get('is_eco', False),
                "scan_mode_detected": not reading_data.get('is_eco', False),
                "monitoring_session": f"individual_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "full_image_base64": full_image_b64,
                "cropped_image_base64": cropped_image_b64,
                "crop_coordinates": json.dumps(OCR_CROP_COORDS),
                "ocr_raw_text": ocr_text,
                "capture_number": capture_num
            }

            logger.info(f"📤 Sending capture #{capture_num}: OCR='{ocr_text}' → {reading_data.get('pressure', 0.0)} PSI")
            response = self.session.post(BACKEND_URL, json=payload)

            if response.status_code in [200, 201]:
                logger.info(f"✅ Individual capture #{capture_num} sent successfully")
                return True
            else:
                logger.warning(f"❌ Failed to send capture #{capture_num}: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Error sending individual capture #{capture_num}: {e}")
            return False

    def send_readings_to_backend(self, readings: Dict[str, any]) -> bool:
        """Send comprehensive readings to backend with images"""
        try:
            timestamp = int(datetime.now(timezone.utc).timestamp())

            # Capture fresh image for upload
            image_array = self.capture_image()
            if image_array is None:
                logger.error("Failed to capture image for backend upload")
                return False

            # Convert to PIL Image
            full_image = Image.fromarray(image_array)

            # Create cropped image
            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            cropped_image = full_image.crop((x, y, x + w, y + h))

            # Convert images to base64
            def image_to_base64(img):
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=95)
                return base64.b64encode(buffer.getvalue()).decode('utf-8')

            full_image_b64 = image_to_base64(full_image)
            cropped_image_b64 = image_to_base64(cropped_image)

            payload = {
                "site_id": SITE_ID,
                "timestamp": timestamp,
                "source": "smart_mri_monitor_with_calibration",
                "water_temperature": readings.get('temperature'),
                "eco_pressure": readings.get('eco_pressure'),
                "scan_pressure": readings.get('scan_pressure'),
                "eco_mode_detected": readings.get('eco_detected', False),
                "scan_mode_detected": readings.get('scan_detected', False),
                "monitoring_session": f"smart_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "full_image_base64": full_image_b64,
                "cropped_image_base64": cropped_image_b64,
                "crop_coordinates": json.dumps(OCR_CROP_COORDS)
            }

            # For backward compatibility, use scan_pressure as main return_pressure
            if readings.get('scan_pressure'):
                payload["return_pressure"] = readings['scan_pressure']
                payload["confidence"] = 0.95
            elif readings.get('eco_pressure'):
                payload["return_pressure"] = readings['eco_pressure']
                payload["confidence"] = 0.90
            else:
                payload["return_pressure"] = 0.0
                payload["confidence"] = 0.0

            logger.info(f"Sending comprehensive readings with images: pressure={payload.get('return_pressure')}, temp={payload.get('water_temperature')}")
            response = self.session.post(BACKEND_URL, json=payload)

            if response.status_code in [200, 201]:
                logger.info("Comprehensive readings sent successfully")
                return True
            else:
                logger.error(f"Backend rejected readings: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send readings: {e}")
            return False

    def run_monitoring_session(self) -> Dict[str, any]:
        """Run complete monitoring session"""
        logger.info("=" * 60)
        logger.info("SMART MRI MONITORING SESSION STARTED")
        logger.info("=" * 60)

        # Reset readings
        self.captured_readings = {
            'temperature': None,
            'eco_pressure': None,
            'scan_pressure': None,
            'eco_detected': False,
            'scan_detected': False
        }

        # Run capture sequence
        readings = self.run_capture_sequence()

        # Log results
        logger.info("=" * 60)
        logger.info("MONITORING SESSION RESULTS:")
        logger.info(f"  Water Temperature: {readings.get('temperature', 'NOT DETECTED')}°C")
        logger.info(f"  ECO Pressure: {readings.get('eco_pressure', 'NOT DETECTED')} PSI")
        logger.info(f"  Scan Pressure: {readings.get('scan_pressure', 'NOT DETECTED')} PSI")
        logger.info(f"  ECO Mode Detected: {readings.get('eco_detected', False)}")
        logger.info(f"  Scan Mode Detected: {readings.get('scan_detected', False)}")
        logger.info("=" * 60)

        # Send to backend
        success = self.send_readings_to_backend(readings)

        return readings

    def cleanup(self):
        """Clean up camera resources"""
        if self.camera:
            if PICAMERA2_AVAILABLE and isinstance(self.camera, Picamera2):
                self.camera.stop()
                self.camera.close()
            elif self.camera != "libcamera":
                self.camera.release()
            logger.info("Camera resources released")

def main():
    """Main entry point"""
    monitor = SmartMRIMonitor()

    if not monitor.initialize_camera():
        logger.error("Failed to initialize camera")
        return 1

    try:
        readings = monitor.run_monitoring_session()

        # Check if we got the essential readings
        missing = []
        if readings.get('temperature') is None:
            missing.append("temperature")
        if readings.get('eco_pressure') is None and readings.get('scan_pressure') is None:
            missing.append("pressure readings")

        if missing:
            logger.warning(f"Missing readings: {', '.join(missing)}")
            logger.info("Consider running the session again or checking camera positioning")
        else:
            logger.info("✅ All essential readings captured successfully!")

        return 0

    except Exception as e:
        logger.error(f"Monitoring session failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        monitor.cleanup()

if __name__ == "__main__":
    exit(main())