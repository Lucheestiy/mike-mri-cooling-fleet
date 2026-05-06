#!/usr/bin/env python3
"""
Scheduled production script for capturing and uploading images WITHOUT OCR processing.
All OCR will be handled on the server side.
Designed to run automatically via cron at scheduled times (9AM and 3PM daily).
"""

import os
import sys
import json
import base64
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import subprocess
import tempfile
from PIL import Image
import numpy as np
import logging
import pickle

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/gmcmr2c/mri-cooling-camera/edge/logs/scheduled_capture.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Ensure logs directory exists
os.makedirs('/home/gmcmr2c/mri-cooling-camera/edge/logs', exist_ok=True)

# Load environment variables
load_dotenv()

# Configuration from environment
SITE_ID = os.getenv('SITE_ID', 'GMCMR2')
CAMERA_BACKEND_URL = os.getenv('CAMERA_BACKEND_URL', 'https://cam.coolmri.com/api/camera/pressure')

# Image dimensions from .env
IMAGE_WIDTH = int(os.getenv('IMAGE_WIDTH', '1920'))
IMAGE_HEIGHT = int(os.getenv('IMAGE_HEIGHT', '1080'))

# OCR crop coordinates from .env
crop_coords_str = os.getenv('OCR_CROP_COORDS', '{"x": 708, "y": 520, "w": 364, "h": 182}')
CROP_COORDS = json.loads(crop_coords_str)

# Camera settings (from improved_ocr.py)
SHUTTER_SPEED = '1500'  # 1.5ms
GAIN = '2.5'

# Number of captures per session
CAPTURES_PER_SESSION = 10

# Extended retry configuration
EXTENDED_RETRY_INTERVAL = 300  # 5 minutes in seconds
EXTENDED_RETRY_DURATION = 3600  # 1 hour in seconds
FAILED_SESSIONS_DIR = '/home/gmcmr2c/mri-cooling-camera/edge/failed_sessions'

# Ensure failed sessions directory exists
os.makedirs(FAILED_SESSIONS_DIR, exist_ok=True)

def capture_with_rpicam():
    """Capture an image using rpicam-still with optimal settings."""
    tmp_path = tempfile.mktemp(suffix='.jpg')

    try:
        # Optimal settings for LCD display
        cmd = [
            'rpicam-still',
            '--shutter', SHUTTER_SPEED,
            '--gain', GAIN,
            '--awb', 'daylight',
            '--denoise', 'off',
            '-o', tmp_path,
            '--width', str(IMAGE_WIDTH),
            '--height', str(IMAGE_HEIGHT),
            '--immediate',
            '-n',  # No preview
            '-t', '1'  # 1ms timeout
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            logger.error(f"Camera error: {result.stderr}")
            return None, None, None

        # Read the captured image
        img = Image.open(tmp_path)
        img_array = np.array(img)

        # Crop the OCR region
        x, y, w, h = CROP_COORDS['x'], CROP_COORDS['y'], CROP_COORDS['w'], CROP_COORDS['h']
        cropped = img_array[y:y+h, x:x+w]
        cropped_img = Image.fromarray(cropped)

        # Calculate basic image statistics for quality info
        brightness = np.mean(cropped)
        p95 = np.percentile(cropped, 95)
        saturation = np.sum(cropped >= 255) / cropped.size * 100

        return img, cropped_img, {
            'brightness': int(brightness),
            'p95': int(p95),
            'saturation': round(saturation, 1)
        }

    except Exception as e:
        logger.error(f"Capture failed: {str(e)}")
        return None, None, None

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

def upload_to_website(full_img, cropped_img, site_id, timestamp):
    """Upload images to website with robust retry logic."""

    try:
        # Convert images to base64
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_full:
            full_img.save(tmp_full.name, format='JPEG', quality=85)
            with open(tmp_full.name, 'rb') as f:
                full_base64 = base64.b64encode(f.read()).decode('utf-8')
            os.unlink(tmp_full.name)

        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_crop:
            cropped_img.save(tmp_crop.name, format='JPEG', quality=90)
            with open(tmp_crop.name, 'rb') as f:
                cropped_base64 = base64.b64encode(f.read()).decode('utf-8')
            os.unlink(tmp_crop.name)

        # Prepare upload data (no OCR data) - using correct API field names
        upload_data = {
            'site_id': site_id,
            'full_image_base64': full_base64,
            'cropped_image_base64': cropped_base64,
            'return_pressure': 0.0,  # Placeholder value - OCR on server
            'confidence': 0.1,  # Low confidence indicates server-side OCR needed
            'timestamp': timestamp,
            'metadata': {
                'reading_detected': 'SERVER_SIDE',  # Indicate server-side OCR needed
                'processing': 'server_side',  # OCR will be done server-side
                'crop_coords': CROP_COORDS,
                'camera_settings': {
                    'shutter': SHUTTER_SPEED,
                    'gain': GAIN
                },
                'upload_version': 'scheduled_v1',
                'session_type': 'automated_daily'
            }
        }

        # Try upload with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    CAMERA_BACKEND_URL,
                    json=upload_data,
                    timeout=30
                )

                if response.status_code in [200, 201]:  # 201 = Created (success)
                    return True, None
                elif response.status_code in [500, 502, 503, 504]:
                    # Server error - retry
                    if attempt < max_retries - 1:
                        wait_time = 2 ** (attempt + 1)
                        logger.warning(f"Server error {response.status_code}, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                else:
                    # Client error - don't retry
                    return False, f"HTTP {response.status_code}"

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(f"Timeout, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(f"Upload error, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                return False, str(e)[:50]

        return False, "Max retries exceeded"

    except Exception as e:
        logger.error(f"Upload preparation failed: {str(e)}")
        return False, str(e)

def save_failed_session(session_data):
    """Save failed session data for later retry."""
    try:
        session_file = os.path.join(FAILED_SESSIONS_DIR, f"failed_session_{session_data['session_id']}.pkl")
        with open(session_file, 'wb') as f:
            pickle.dump(session_data, f)
        logger.info(f"Failed session saved for retry: {session_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to save session data: {str(e)}")
        return False

def load_failed_sessions():
    """Load all failed sessions for retry."""
    failed_sessions = []
    try:
        for filename in os.listdir(FAILED_SESSIONS_DIR):
            if filename.endswith('.pkl'):
                session_file = os.path.join(FAILED_SESSIONS_DIR, filename)
                try:
                    with open(session_file, 'rb') as f:
                        session_data = pickle.load(f)
                    failed_sessions.append((session_file, session_data))
                except Exception as e:
                    logger.error(f"Failed to load session file {session_file}: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to scan failed sessions directory: {str(e)}")

    return failed_sessions

def retry_failed_session(session_data):
    """Retry uploading a failed session."""
    logger.info(f"Retrying failed session: {session_data['session_id']}")

    successful_uploads = 0
    total_captures = len(session_data['failed_captures'])

    for capture_data in session_data['failed_captures']:
        try:
            # Reconstruct images from base64
            full_img_data = base64.b64decode(capture_data['full_image_base64'])
            crop_img_data = base64.b64decode(capture_data['cropped_image_base64'])

            # Save to temporary files and reload as PIL Images
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_full:
                tmp_full.write(full_img_data)
                full_img = Image.open(tmp_full.name)

            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_crop:
                tmp_crop.write(crop_img_data)
                cropped_img = Image.open(tmp_crop.name)

            # Retry upload
            success, error = upload_to_website(
                full_img,
                cropped_img,
                capture_data['site_id'],
                capture_data['timestamp']
            )

            if success:
                successful_uploads += 1
                logger.info(f"Retry successful: {capture_data['site_id']}")
            else:
                logger.error(f"Retry failed: {capture_data['site_id']} - {error}")

            # Clean up temp files
            os.unlink(tmp_full.name)
            os.unlink(tmp_crop.name)

        except Exception as e:
            logger.error(f"Error during retry of {capture_data['site_id']}: {str(e)}")

    success_rate = successful_uploads / total_captures if total_captures > 0 else 0
    logger.info(f"Retry session results: {successful_uploads}/{total_captures} uploads ({success_rate*100:.1f}%)")

    return successful_uploads, total_captures

def process_extended_retries():
    """Process any failed sessions that need extended retries."""
    logger.info("Checking for failed sessions to retry...")

    failed_sessions = load_failed_sessions()
    if not failed_sessions:
        logger.info("No failed sessions found for retry")
        return

    current_time = datetime.now()
    sessions_retried = 0

    for session_file, session_data in failed_sessions:
        try:
            # Check if session is within retry window (1 hour from failure)
            failure_time = datetime.fromisoformat(session_data['failure_time'])
            time_since_failure = (current_time - failure_time).total_seconds()

            if time_since_failure > EXTENDED_RETRY_DURATION:
                # Session too old, remove it
                logger.info(f"Removing expired failed session: {session_data['session_id']}")
                os.remove(session_file)
                continue

            # Check if enough time has passed since last retry (5 minutes)
            last_retry = datetime.fromisoformat(session_data.get('last_retry_time', session_data['failure_time']))
            time_since_retry = (current_time - last_retry).total_seconds()

            if time_since_retry >= EXTENDED_RETRY_INTERVAL:
                logger.info(f"Retrying session {session_data['session_id']} (failed {time_since_failure/60:.1f} min ago)")

                # Update last retry time
                session_data['last_retry_time'] = current_time.isoformat()
                session_data['retry_count'] = session_data.get('retry_count', 0) + 1

                # Attempt retry
                successful_uploads, total_captures = retry_failed_session(session_data)

                if successful_uploads == total_captures:
                    # Full success - remove the failed session file
                    logger.info(f"Session {session_data['session_id']} fully recovered - removing from retry queue")
                    os.remove(session_file)
                elif successful_uploads > 0:
                    # Partial success - update session data to only include remaining failures
                    logger.info(f"Session {session_data['session_id']} partially recovered ({successful_uploads}/{total_captures})")
                    # For simplicity, we'll remove partial successes and let the remaining failures be retried next time
                    # In a more complex implementation, we could track individual capture failures
                else:
                    # No success - save updated retry info
                    with open(session_file, 'wb') as f:
                        pickle.dump(session_data, f)
                    logger.warning(f"Session {session_data['session_id']} retry failed - will try again in 5 minutes")

                sessions_retried += 1

        except Exception as e:
            logger.error(f"Error processing failed session {session_file}: {str(e)}")

    if sessions_retried > 0:
        logger.info(f"Processed {sessions_retried} failed session retries")

def run_scheduled_session():
    """Run a scheduled capture session."""
    session_start = datetime.now()
    logger.info(f"Starting scheduled capture session at {session_start.strftime('%Y-%m-%d %H:%M:%S')}")

    # Generate session ID
    session_id = session_start.strftime("%m%d_%H%M%S")

    # Track results
    successful_captures = 0
    successful_uploads = 0
    failed_captures = []

    # Run captures
    for i in range(1, CAPTURES_PER_SESSION + 1):
        logger.info(f"Capture {i}/{CAPTURES_PER_SESSION}")

        # Capture image
        full_img, cropped_img, stats = capture_with_rpicam()

        if full_img is None:
            logger.error(f"Capture {i} failed")
            continue

        successful_captures += 1

        # Generate site ID
        site_id = f"{SITE_ID}_SCHED_{session_id}_{i:02d}"
        timestamp = int(time.time())

        # Upload to website
        success, error = upload_to_website(full_img, cropped_img, site_id, timestamp)

        if success:
            successful_uploads += 1
            logger.info(f"Capture {i} uploaded successfully: {site_id}")
            if stats:
                logger.info(f"Quality - Sat: {stats['saturation']}%, Bright: {stats['brightness']}, P95: {stats['p95']}")
        else:
            logger.error(f"Upload {i} failed: {error}")

            # Store failed capture for later retry
            try:
                # Convert images to base64 for storage
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_full:
                    full_img.save(tmp_full.name, format='JPEG', quality=85)
                    with open(tmp_full.name, 'rb') as f:
                        full_base64 = base64.b64encode(f.read()).decode('utf-8')
                    os.unlink(tmp_full.name)

                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_crop:
                    cropped_img.save(tmp_crop.name, format='JPEG', quality=90)
                    with open(tmp_crop.name, 'rb') as f:
                        crop_base64 = base64.b64encode(f.read()).decode('utf-8')
                    os.unlink(tmp_crop.name)

                failed_capture = {
                    'site_id': site_id,
                    'timestamp': timestamp,
                    'full_image_base64': full_base64,
                    'cropped_image_base64': crop_base64,
                    'error': error,
                    'stats': stats
                }
                failed_captures.append(failed_capture)

            except Exception as e:
                logger.error(f"Failed to store capture {i} for retry: {str(e)}")

        # Small delay between captures (except last one)
        if i < CAPTURES_PER_SESSION:
            time.sleep(2)

    # Save failed captures for extended retry if needed
    if failed_captures:
        session_data = {
            'session_id': session_id,
            'failure_time': session_start.isoformat(),
            'failed_captures': failed_captures,
            'total_captures': successful_captures,
            'retry_count': 0
        }
        save_failed_session(session_data)

    # Log session summary
    session_end = datetime.now()
    duration = (session_end - session_start).total_seconds()

    logger.info(f"Session completed in {duration:.1f}s")
    logger.info(f"Results: {successful_captures}/{CAPTURES_PER_SESSION} captures, {successful_uploads}/{CAPTURES_PER_SESSION} uploads")

    if successful_uploads >= CAPTURES_PER_SESSION * 0.9:  # 90%+ success
        logger.info("✅ Session successful!")
    elif successful_uploads > 0:
        logger.warning(f"⚠️  Partial success: {successful_uploads}/{CAPTURES_PER_SESSION} uploads")
    else:
        logger.error("❌ Session failed - no successful uploads")

    return successful_captures, successful_uploads

def main():
    """Main entry point for scheduled execution."""
    try:
        logger.info("=" * 60)
        logger.info("🕘 SCHEDULED CAPTURE SESSION STARTING")
        logger.info("=" * 60)
        logger.info(f"Configuration:")
        logger.info(f"  - Site ID: {SITE_ID}")
        logger.info(f"  - Captures per session: {CAPTURES_PER_SESSION}")
        logger.info(f"  - Camera settings: {SHUTTER_SPEED}μs shutter, {GAIN} gain")
        logger.info(f"  - Server-side OCR processing")
        logger.info(f"  - Extended retry: Every 5 min for 1 hour on failure")
        logger.info("")

        # First, process any existing failed sessions
        process_extended_retries()

        # Then run the new scheduled session
        captures, uploads = run_scheduled_session()

        logger.info("=" * 60)
        logger.info("🏁 SCHEDULED CAPTURE SESSION COMPLETE")
        logger.info("=" * 60)

        # Exit with appropriate code
        if uploads >= captures * 0.9:  # 90%+ upload success
            sys.exit(0)
        else:
            sys.exit(1)  # Indicate failure for monitoring

    except Exception as e:
        logger.error(f"Fatal error in scheduled session: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()