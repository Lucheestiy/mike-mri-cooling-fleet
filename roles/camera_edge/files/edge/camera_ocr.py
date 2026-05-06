#!/usr/bin/env python3
"""
Camera OCR using Picamera2 for Raspberry Pi Camera Module 3
"""
import os
import time
import logging
import json
import re
import base64
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
import requests
from dotenv import load_dotenv
import pytesseract
from PIL import Image, ImageEnhance, ImageDraw
import numpy as np

# Try to import picamera2
try:
    from picamera2 import Picamera2
    PICAMERA2_AVAILABLE = True
except ImportError:
    # Try adding system packages path
    import sys
    if '/usr/lib/python3/dist-packages' not in sys.path:
        sys.path.append('/usr/lib/python3/dist-packages')
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
BACKEND_URL = os.getenv("CAMERA_BACKEND_URL", "http://localhost:8001/api/camera/pressure")
SITE_ID = os.getenv("SITE_ID", "GMCMR2")
CAPTURE_INTERVAL = int(os.getenv("CAPTURE_INTERVAL", "60"))
IMAGE_WIDTH = int(os.getenv("IMAGE_WIDTH", "1920"))
IMAGE_HEIGHT = int(os.getenv("IMAGE_HEIGHT", "1080"))
OCR_CROP_COORDS = json.loads(os.getenv("OCR_CROP_COORDS", '{"x": 850, "y": 450, "w": 200, "h": 100}'))
DEBUG_SAVE_IMAGES = os.getenv("DEBUG_SAVE_IMAGES", "true").lower() == "true"
CALIBRATION_MODE = os.getenv("CALIBRATION_MODE", "false").lower() == "true"
CALIBRATION_URL = os.getenv("CALIBRATION_URL", "https://cam.coolmri.com/api/camera/images")
SHUTTER_SPEED = os.getenv("SHUTTER_SPEED")
GAIN = os.getenv("GAIN")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Try to import tesseract (after logger is defined)
try:
    import pytesseract
    # Test if tesseract binary is available
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
    logger.info("Tesseract OCR available")
except (ImportError, pytesseract.TesseractNotFoundError):
    TESSERACT_AVAILABLE = False
    logger.warning("Tesseract OCR not available - using mock OCR for testing")


class CameraOCR:
    def __init__(self):
        self.camera = None
        self.session = requests.Session()
        self.session.timeout = 120
        self.image_dir = Path(__file__).parent / "images"
        if DEBUG_SAVE_IMAGES:
            self.image_dir.mkdir(exist_ok=True)

    def initialize_camera(self) -> bool:
        """Initialize camera (Picamera2, libcamera, or OpenCV)"""
        # When manual exposure is configured, prefer rpicam-still so test captures
        # match the production scheduled uploader path.
        if (SHUTTER_SPEED or GAIN) and self._check_libcamera_tools():
            return self._init_libcamera()
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
        """Initialize using rpicam-still with manual exposure control"""
        try:
            # Check if rpicam-still is available
            import subprocess
            result = subprocess.run(['which', 'rpicam-still'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logger.info("Using rpicam-still with manual exposure control...")
                self.camera = "rpicam-still"  # Flag to indicate rpicam mode
                logger.info("rpicam-still initialized with optimal LCD exposure settings")
                return True
            else:
                # Fall back to old libcamera method
                logger.info("rpicam-still not found, using libcamera command-line tools...")
                self.camera = "libcamera"  # Flag to indicate libcamera mode
                logger.info("Libcamera tools initialized")
                return True
        except Exception as e:
            logger.error(f"Camera initialization failed: {e}")
            return False

    def _init_picamera2(self) -> bool:
        """Initialize Picamera2"""
        try:
            logger.info("Initializing Picamera2...")
            self.camera = Picamera2()

            # Get camera info
            camera_info = self.camera.camera_properties
            logger.info(f"Camera model: {camera_info.get('Model', 'Unknown')}")

            # Create configuration
            config = self.camera.create_preview_configuration(
                main={"size": (IMAGE_WIDTH, IMAGE_HEIGHT), "format": "RGB888"}
            )
            self.camera.configure(config)

            # Start camera
            self.camera.start()
            time.sleep(2)  # Warmup

            logger.info(f"Picamera2 initialized: {IMAGE_WIDTH}x{IMAGE_HEIGHT}")
            return True

        except Exception as e:
            logger.error(f"Picamera2 initialization failed: {e}")
            return False

    def _init_opencv(self) -> bool:
        """Fallback to OpenCV with better device handling"""
        try:
            logger.info("Falling back to OpenCV...")

            # Try different backends and devices
            backends = [cv2.CAP_V4L2, cv2.CAP_ANY]
            devices = [0, 1, 2, 3]

            for backend in backends:
                for device in devices:
                    logger.info(f"Trying device {device} with backend {backend}")
                    cap = cv2.VideoCapture(device, backend)
                    if cap.isOpened():
                        # Set properties
                        cap.set(cv2.CAP_PROP_FRAME_WIDTH, IMAGE_WIDTH)
                        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, IMAGE_HEIGHT)
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))

                        # Give the camera time to initialize
                        time.sleep(1)

                        # Test multiple captures to ensure stability
                        success_count = 0
                        for i in range(5):
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.size > 0:
                                success_count += 1

                        if success_count >= 3:
                            self.camera = cap
                            logger.info(f"OpenCV camera initialized - Device: {device}, Backend: {backend}")
                            logger.info(f"Frame size: {frame.shape[1]}x{frame.shape[0]}")
                            return True

                        cap.release()

            # Try without setting specific formats
            logger.info("Trying cameras with default settings...")
            for device in devices:
                cap = cv2.VideoCapture(device)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        self.camera = cap
                        logger.info(f"OpenCV camera at device {device} with default settings: {frame.shape[1]}x{frame.shape[0]}")
                        return True
                    cap.release()

            logger.error("No working camera found with OpenCV")
            return False

        except Exception as e:
            logger.error(f"OpenCV initialization failed: {e}")
            return False

    def capture_image(self) -> Optional[np.ndarray]:
        """Capture a single frame"""
        try:
            if PICAMERA2_AVAILABLE and isinstance(self.camera, Picamera2):
                # Capture with Picamera2
                array = self.camera.capture_array("main")
                logger.debug(f"Captured image shape: {array.shape}")
                return array
            elif self.camera == "libcamera" or self.camera == "rpicam-still":
                # Capture with libcamera tools or rpicam-still
                return self._capture_with_libcamera()
            else:
                # Capture with OpenCV
                ret, frame = self.camera.read()
                if ret:
                    # Convert BGR to RGB
                    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return None

        except Exception as e:
            logger.error(f"Image capture failed: {e}")
            return None

    def _capture_with_libcamera(self) -> Optional[np.ndarray]:
        """Capture image using rpicam-still or libcamera command-line tools"""
        import subprocess
        import tempfile
        import os

        try:
            # Create temporary file for capture
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                tmp_path = tmp_file.name

            if self.camera == "rpicam-still":
                # Use rpicam-still with optimal exposure settings for LCD
                shutter_speed = SHUTTER_SPEED or '3000'
                gain = GAIN or '8.0'
                cmd = [
                    'rpicam-still',
                    '--shutter', shutter_speed,
                    '--gain', gain,
                    '--awb', 'daylight',  # Fixed white balance
                    '--denoise', 'off',   # No denoise for sharper segments
                    '-o', tmp_path,
                    '--width', str(IMAGE_WIDTH),
                    '--height', str(IMAGE_HEIGHT),
                    '--immediate',
                    '-n',  # No preview
                    '-t', '1'  # 1ms timeout
                ]

                logger.debug(f"Running: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)

                if result.returncode == 0 and os.path.exists(tmp_path):
                    # Load JPEG image and convert to array
                    with Image.open(tmp_path) as img:
                        array = np.array(img.convert('RGB'))
                        logger.debug(f"rpicam-still captured image shape: {array.shape}")
                        return array
                else:
                    logger.error(f"rpicam-still capture failed: {result.stderr[:200]}")
                    return None
            else:
                # Fall back to cam command
                ppm_path = tmp_path.replace('.jpg', '.ppm')
                cmd = [
                    'cam',
                    '-c', '1',  # Camera 1 (our detected imx708_wide)
                    '--capture=1',  # Capture 1 frame
                    f'--file={ppm_path}',  # Output file as PPM
                    '--stream', f'width={IMAGE_WIDTH},height={IMAGE_HEIGHT},role=still,pixelformat=BGR888'
                ]

                logger.debug(f"Running: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, timeout=10, text=True)

                if result.returncode == 0 and os.path.exists(ppm_path):
                    # Load PPM image and convert to array
                    with Image.open(ppm_path) as img:
                        array = np.array(img.convert('RGB'))
                        logger.debug(f"Libcamera captured image shape: {array.shape}")
                        return array
                else:
                    logger.error(f"Libcamera capture failed: {result.stderr}")
                    return None

        except subprocess.TimeoutExpired:
            logger.error("Camera capture timed out")
            return None
        except Exception as e:
            logger.error(f"Camera capture error: {e}")
            return None
        finally:
            # Clean up temp files
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            if 'ppm_path' in locals() and os.path.exists(ppm_path):
                os.unlink(ppm_path)

    def preprocess_for_ocr(self, image: np.ndarray) -> Image.Image:
        """Preprocess image for better OCR accuracy"""
        # Convert to PIL Image
        pil_image = Image.fromarray(image)

        # Save full image with crop region marked (debug)
        if DEBUG_SAVE_IMAGES:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            full_copy = pil_image.copy()
            draw = ImageDraw.Draw(full_copy)
            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            draw.rectangle([x, y, x+w, y+h], outline="red", width=3)
            full_path = self.image_dir / f"ocr_full_{timestamp}.jpg"
            full_copy.save(full_path)
            logger.info(f"Full image saved: {full_path}")

        # Crop to region of interest
        x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
        cropped = pil_image.crop((x, y, x + w, y + h))

        # Convert to grayscale
        gray = cropped.convert('L')

        # Enhance contrast
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(2.0)

        # Save debug image
        if DEBUG_SAVE_IMAGES:
            debug_path = self.image_dir / f"ocr_debug_{timestamp}.png"
            enhanced.save(debug_path)
            logger.info(f"Debug crop saved: {debug_path}")

        return enhanced

    def extract_pressure(self, image: Image.Image) -> Tuple[Optional[float], float]:
        """Extract return pressure value using OCR or fallback method"""
        try:
            if TESSERACT_AVAILABLE:
                return self._extract_with_tesseract(image)
            else:
                return self._extract_mock_ocr(image)

        except Exception as e:
            logger.error(f"Pressure extraction failed: {e}")
            return None, 0.0

    def _extract_with_tesseract(self, image: Image.Image) -> Tuple[Optional[float], float]:
        """Extract pressure using real tesseract OCR"""
        # Try multiple OCR configurations
        configs = [
            r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.',
            r'--oem 3 --psm 8',
            r'--psm 7'
        ]

        best_text = ""
        for config in configs:
            text = pytesseract.image_to_string(image, config=config).strip()
            if text:
                logger.debug(f"OCR config '{config}' got: '{text}'")
                if re.search(r'\d+\.?\d*', text):
                    best_text = text
                    break

        # Extract number
        if best_text:
            match = re.search(r'(\d+\.?\d*)', best_text)
            if match:
                pressure = float(match.group(1))
                confidence = 0.95
                logger.info(f"Extracted pressure: {pressure} PSI (confidence: {confidence})")
                return pressure, confidence

        logger.warning(f"No pressure value found in OCR text")
        return None, 0.0

    def _extract_mock_ocr(self, image: Image.Image) -> Tuple[Optional[float], float]:
        """Mock OCR for testing when tesseract is not available"""
        logger.info("Using mock OCR for testing (tesseract not available)")

        # Convert to grayscale array for analysis
        if image.mode != 'L':
            image = image.convert('L')
        img_array = np.array(image)

        # Get image statistics
        mean_val = np.mean(img_array)
        std_val = np.std(img_array)
        height, width = img_array.shape

        # Simple heuristic: if image has reasonable contrast
        logger.debug(f"Image stats: {width}x{height}, mean={mean_val:.1f}, std={std_val:.1f}")
        if width > 20 and height > 10 and std_val > 10:
            # Mock values based on typical pressure readings
            mock_values = [35.7, 42.3, 28.9, 31.2, 45.6, 38.1, 33.4, 40.8]

            # Use image characteristics to select a consistent value
            selected_idx = int(mean_val + std_val) % len(mock_values)
            pressure = mock_values[selected_idx]
            confidence = 0.75  # Lower confidence for mock

            logger.info(f"Mock OCR result: {pressure} PSI (confidence: {confidence})")
            return pressure, confidence

        logger.warning("Mock OCR: Image doesn't meet criteria for pressure reading")
        return None, 0.0

    def send_calibration_images(self, full_image: np.ndarray, cropped_image: Image.Image,
                                ocr_text: str = "", pressure: Optional[float] = None) -> bool:
        """Send images to calibration endpoint for remote viewing"""
        try:
            import requests

            # Save images temporarily
            full_pil = Image.fromarray(full_image)
            full_buffer = BytesIO()
            full_pil.save(full_buffer, format='JPEG', quality=85)
            full_buffer.seek(0)

            crop_buffer = BytesIO()
            cropped_image.save(crop_buffer, format='JPEG', quality=85)
            crop_buffer.seek(0)

            # Try posting to a debug endpoint first
            debug_url = "https://cam.coolmri.com/api/camera/debug"

            # Prepare files for multipart upload
            files = {
                'full_image': ('full.jpg', full_buffer, 'image/jpeg'),
                'cropped_image': ('crop.jpg', crop_buffer, 'image/jpeg')
            }

            # Prepare form data
            data = {
                'site_id': SITE_ID,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'crop_coords': json.dumps(OCR_CROP_COORDS),
                'ocr_text': ocr_text,
                'image_width': IMAGE_WIDTH,
                'image_height': IMAGE_HEIGHT
            }

            logger.info(f"Sending calibration images to {debug_url}")
            response = requests.post(debug_url, files=files, data=data, timeout=10)

            if response.status_code in [200, 201]:
                logger.info("✅ Calibration images sent successfully")
                return True
            elif response.status_code == 404:
                # Endpoint doesn't exist, save locally instead
                logger.info("📁 Debug endpoint not found, saving images locally")
                self._save_calibration_images_locally(full_image, cropped_image, ocr_text)
                return True
            else:
                logger.warning(f"Calibration endpoint returned: {response.status_code}")
                logger.warning(f"Response: {response.text}")
                # Fallback to local save
                self._save_calibration_images_locally(full_image, cropped_image, ocr_text)
                return True

        except Exception as e:
            logger.error(f"Failed to send calibration images: {e}")
            # Fallback to local save
            self._save_calibration_images_locally(full_image, cropped_image, ocr_text)
            return True

    def _save_calibration_images_locally(self, full_image: np.ndarray, cropped_image: Image.Image, ocr_text: str):
        """Save calibration images locally with clear names"""
        try:
            from PIL import ImageDraw

            # Create images directory
            images_dir = self.image_dir
            images_dir.mkdir(exist_ok=True)

            # Save full image with crop region marked
            full_pil = Image.fromarray(full_image)
            draw = ImageDraw.Draw(full_pil)
            x, y, w, h = OCR_CROP_COORDS['x'], OCR_CROP_COORDS['y'], OCR_CROP_COORDS['w'], OCR_CROP_COORDS['h']
            draw.rectangle([x, y, x+w, y+h], outline="red", width=5)

            # Save with clear names
            full_path = images_dir / "CALIBRATION_FULL_VIEW.jpg"
            full_pil.save(full_path, quality=95)

            crop_path = images_dir / "CALIBRATION_CROP_REGION.jpg"
            cropped_image.save(crop_path, quality=95)

            logger.info(f"📸 Calibration images saved locally:")
            logger.info(f"   Full view: {full_path}")
            logger.info(f"   Crop region: {crop_path}")
            logger.info(f"   OCR result: {ocr_text}")
            logger.info(f"   Crop coords: {OCR_CROP_COORDS}")

        except Exception as e:
            logger.error(f"Failed to save calibration images locally: {e}")

    def send_to_backend(self, pressure: float, confidence: float) -> bool:
        """Send pressure reading to backend"""
        try:
            payload = {
                "site_id": SITE_ID,
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "return_pressure": pressure,
                "confidence": confidence,
                "source": "camera_ocr"
            }

            logger.info(f"Sending to backend: {payload}")
            response = self.session.post(BACKEND_URL, json=payload)

            if response.status_code in [200, 201]:
                logger.info(f"Data sent successfully")
                return True
            else:
                logger.error(f"Backend rejected: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send data: {e}")
            return False

    def run_single_capture(self) -> bool:
        """Run a single capture cycle for testing"""
        logger.info("Running single capture test...")

        # Capture image
        image = self.capture_image()
        if image is None:
            logger.error("Failed to capture image")
            return False

        logger.info(f"Image captured: shape={image.shape}")

        # Preprocess for OCR
        processed = self.preprocess_for_ocr(image)

        # Extract pressure
        pressure, confidence = self.extract_pressure(processed)

        if pressure is not None:
            logger.info(f"OCR Result: {pressure} PSI (confidence: {confidence})")

            # In calibration mode, send images to website for viewing (don't send fake pressure data)
            if CALIBRATION_MODE:
                ocr_text = f"Detected: {pressure} PSI" if pressure else "No reading"
                self.send_calibration_images(image, processed, ocr_text, pressure)
                logger.info("📷 CALIBRATION MODE: Images sent for crop adjustment - not sending pressure data")

            # Send to backend if confidence is high and not in calibration mode
            elif confidence >= 0.9:
                self.send_to_backend(pressure, confidence)
        else:
            logger.warning("No pressure value extracted")
            # Still send images in calibration mode even if no text extracted
            if CALIBRATION_MODE:
                self.send_calibration_images(image, processed, "No text detected", None)

        return True

    def run_capture_loop(self):
        """Main capture and OCR loop"""
        interval = 5 if CALIBRATION_MODE else CAPTURE_INTERVAL  # Faster updates in calibration mode
        logger.info(f"Starting OCR capture loop - interval: {interval}s")

        while True:
            try:
                success = self.run_single_capture()

                if not success:
                    logger.warning("Capture cycle failed")

                # Wait for next cycle
                logger.info(f"Waiting {interval}s for next capture...")
                time.sleep(interval)

            except KeyboardInterrupt:
                logger.info("Shutting down camera OCR")
                break
            except Exception as e:
                logger.error(f"Unexpected error in capture loop: {e}")
                time.sleep(interval)

    def cleanup(self):
        """Clean up camera resources"""
        if self.camera:
            if PICAMERA2_AVAILABLE and isinstance(self.camera, Picamera2):
                self.camera.stop()
                self.camera.close()
            elif self.camera == "libcamera" or self.camera == "rpicam-still":
                # No cleanup needed for command-line tools
                pass
            else:
                # OpenCV camera
                self.camera.release()
            logger.info("Camera resources released")


def main():
    """Main entry point"""
    import sys

    # Check if single capture mode requested
    single_capture = "--single" in sys.argv
    calibration_requested = "--calibrate" in sys.argv

    # Override calibration mode if --calibrate flag is used
    if calibration_requested:
        global CALIBRATION_MODE
        CALIBRATION_MODE = True

    if CALIBRATION_MODE:
        logger.info("=" * 60)
        logger.info("CALIBRATION MODE ENABLED")
        logger.info(f"Images will be sent to: {CALIBRATION_URL}")
        logger.info("Adjust OCR_CROP_COORDS in .env file to fine-tune")
        logger.info("=" * 60)

    ocr = CameraOCR()

    if not ocr.initialize_camera():
        logger.error("Failed to initialize camera")
        return 1

    try:
        if single_capture:
            # Run single capture for testing
            success = ocr.run_single_capture()
            return 0 if success else 1
        else:
            # Run continuous loop
            ocr.run_capture_loop()
            return 0
    except Exception as e:
        logger.error(f"Application error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        ocr.cleanup()


if __name__ == "__main__":
    exit(main())
