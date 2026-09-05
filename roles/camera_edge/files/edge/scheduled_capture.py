#!/usr/bin/env python3
"""Bounded, retry-safe CoolMRI camera capture agent."""

from __future__ import annotations

import base64
import fcntl
import io
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import requests
from dotenv import load_dotenv
from PIL import Image


CAMERA_AGENT_VERSION = "3.0.0"
BASE_DIR = Path(os.getenv("CAMERA_BASE_DIR", str(Path.home() / "mri-cooling-camera")))
EDGE_DIR = BASE_DIR / "edge"
LOG_DIR = EDGE_DIR / "logs"
FAILED_DIR = EDGE_DIR / "failed_sessions"
DEBUG_DIR = EDGE_DIR / "debug_captures"
LOCK_PATH = Path("/dev/shm") / f"coolmri-camera-{os.getuid()}.lock"

LOG_DIR.mkdir(parents=True, exist_ok=True)
FAILED_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(EDGE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


SITE_ID = os.getenv("SITE_ID", "").strip()
CAMERA_BACKEND_URL = os.getenv(
    "CAMERA_BACKEND_URL", "https://cam.coolmri.com/api/camera/pressure"
).strip()
UPLOAD_ENABLED = env_bool("UPLOAD_ENABLED", True)
UPLOAD_MODE = os.getenv("UPLOAD_MODE", "full_and_crop").strip()
IMAGE_WIDTH = env_int("IMAGE_WIDTH", 1920, 320, 8192)
IMAGE_HEIGHT = env_int("IMAGE_HEIGHT", 1080, 240, 8192)
CAPTURES_PER_SESSION = env_int("CAPTURES_PER_SESSION", 10, 1, 100)
INTER_CAPTURE_DELAY_SEC = env_int("INTER_CAPTURE_DELAY_SEC", 2, 0, 300)
SHUTTER_SPEED = os.getenv(
    "SHUTTER_SPEED", os.getenv("CAMERA_SHUTTER_US", "1500")
).strip()
GAIN = os.getenv("GAIN", os.getenv("CAMERA_GAIN", "2.5")).strip()
DEBUG_SAVE_IMAGES = env_bool("DEBUG_SAVE_IMAGES", False)
DEBUG_RETAIN_IMAGES = env_int("DEBUG_RETAIN_IMAGES", 20, 0, 500)
RETRY_INTERVAL_SEC = env_int("RETRY_INTERVAL_SEC", 300, 30, 86400)
RETRY_WINDOW_SEC = env_int("RETRY_WINDOW_SEC", 3600, 300, 604800)
RETRY_MAX_FILES = env_int("RETRY_MAX_FILES", 20, 1, 1000)
RETRY_MAX_BYTES = env_int("RETRY_MAX_BYTES", 134217728, 1048576, 10737418240)
HTTP_TIMEOUT_SEC = env_int("HTTP_TIMEOUT_SEC", 180, 5, 600)
HTTP_ATTEMPTS = env_int("HTTP_ATTEMPTS", 3, 1, 10)

try:
    CROP_COORDS = json.loads(
        os.getenv("OCR_CROP_COORDS", '{"x":708,"y":520,"w":364,"h":182}')
    )
except json.JSONDecodeError as exc:
    raise ValueError("OCR_CROP_COORDS must be valid JSON") from exc

if not SITE_ID:
    raise ValueError("SITE_ID is required")
if UPLOAD_MODE not in {"full_and_crop", "cropped_only"}:
    raise ValueError("UPLOAD_MODE must be full_and_crop or cropped_only")
for key in ("x", "y", "w", "h"):
    if not isinstance(CROP_COORDS.get(key), int):
        raise ValueError(f"OCR_CROP_COORDS.{key} must be an integer")
if (
    CROP_COORDS["x"] < 0
    or CROP_COORDS["y"] < 0
    or CROP_COORDS["w"] <= 0
    or CROP_COORDS["h"] <= 0
    or CROP_COORDS["x"] + CROP_COORDS["w"] > IMAGE_WIDTH
    or CROP_COORDS["y"] + CROP_COORDS["h"] > IMAGE_HEIGHT
):
    raise ValueError("OCR_CROP_COORDS is outside the configured image dimensions")

logger = logging.getLogger("coolmri-camera")
logger.setLevel(logging.INFO)
logger.handlers.clear()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
file_handler = logging.FileHandler(LOG_DIR / "camera-agent.log")
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def image_b64(image: Image.Image, quality: int) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def capture_command(output_path: str) -> list[str]:
    binary = shutil.which("rpicam-still") or shutil.which("libcamera-still")
    if not binary:
        raise RuntimeError("Neither rpicam-still nor libcamera-still is installed")
    return [
        binary,
        "--shutter", SHUTTER_SPEED,
        "--gain", GAIN,
        "--awb", "daylight",
        "--denoise", "off",
        "--width", str(IMAGE_WIDTH),
        "--height", str(IMAGE_HEIGHT),
        "--immediate",
        "-n",
        "-t", "1",
        "-o", output_path,
    ]


def capture_image() -> tuple[Image.Image, Image.Image, dict[str, Any]]:
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            temp_path = handle.name
        result = subprocess.run(
            capture_command(temp_path), capture_output=True, text=True, timeout=180
        )
        if result.returncode:
            raise RuntimeError(f"camera command failed: {result.stderr[-400:]}")
        with Image.open(temp_path) as opened:
            full = opened.convert("RGB").copy()
        x, y, width, height = (CROP_COORDS[key] for key in ("x", "y", "w", "h"))
        cropped = full.crop((x, y, x + width, y + height))
        pixels = np.asarray(cropped)
        stats = {
            "brightness": int(np.mean(pixels)),
            "p95": int(np.percentile(pixels, 95)),
            "saturation": round(float(np.count_nonzero(pixels >= 255) / pixels.size * 100), 1),
        }
        return full, cropped, stats
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


def build_payload(
    full: Image.Image,
    cropped: Image.Image,
    capture_id: str,
    timestamp: int,
    stats: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "site_id": capture_id,
        "cropped_image_base64": image_b64(cropped, 90),
        "return_pressure": None,
        "confidence": None,
        "source": "camera_edge_v3",
        "timestamp": timestamp,
        "crop_coordinates": json.dumps(CROP_COORDS, separators=(",", ":")),
    }
    if UPLOAD_MODE == "full_and_crop":
        payload["full_image_base64"] = image_b64(full, 85)
    return payload


def post_payload(payload: dict[str, Any]) -> tuple[bool, str | None]:
    for attempt in range(HTTP_ATTEMPTS):
        try:
            response = requests.post(
                CAMERA_BACKEND_URL, json=payload, timeout=HTTP_TIMEOUT_SEC
            )
            if response.status_code in {200, 201}:
                return True, None
            if response.status_code not in {500, 502, 503, 504}:
                return False, f"HTTP {response.status_code}"
            error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            error = type(exc).__name__
        if attempt < HTTP_ATTEMPTS - 1:
            time.sleep(2 ** (attempt + 1))
    return False, error


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def enforce_failed_limit() -> None:
    files = sorted(FAILED_DIR.glob("capture-*.json"), key=lambda path: path.stat().st_mtime)
    total_bytes = sum(path.stat().st_size for path in files)
    while files and (len(files) > RETRY_MAX_FILES or total_bytes > RETRY_MAX_BYTES):
        path = files.pop(0)
        size = path.stat().st_size
        logger.error(
            "Dropping oldest retry record to enforce queue bounds: %s (%s bytes)",
            path.name,
            size,
        )
        path.unlink(missing_ok=True)
        total_bytes -= size


def save_failed_payload(payload: dict[str, Any], error: str) -> None:
    now = utc_now()
    record = {
        "version": 1,
        "created_at": now.isoformat(),
        "last_attempt_at": now.isoformat(),
        "attempts": 1,
        "last_error": error,
        "payload": payload,
    }
    path = FAILED_DIR / f"capture-{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    atomic_json(path, record)
    enforce_failed_limit()


def process_failed_sessions(now: datetime | None = None) -> tuple[int, int]:
    if not UPLOAD_ENABLED:
        return 0, 0
    now = now or utc_now()
    recovered = attempted = 0
    for path in sorted(FAILED_DIR.glob("capture-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(record["created_at"])
            last_attempt = datetime.fromisoformat(record["last_attempt_at"])
            if (now - created).total_seconds() > RETRY_WINDOW_SEC:
                logger.error("Retry window expired; preserving record for operator review: %s", path.name)
                continue
            if (now - last_attempt).total_seconds() < RETRY_INTERVAL_SEC:
                continue
            attempted += 1
            success, error = post_payload(record["payload"])
            if success:
                recovered += 1
                path.unlink(missing_ok=True)
            else:
                record["attempts"] = int(record.get("attempts", 0)) + 1
                record["last_attempt_at"] = now.isoformat()
                record["last_error"] = error
                atomic_json(path, record)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            logger.error("Invalid retry record %s: %s", path.name, exc)
    return recovered, attempted


def retain_debug_image(image: Image.Image, capture_id: str) -> None:
    if not DEBUG_SAVE_IMAGES or DEBUG_RETAIN_IMAGES == 0:
        return
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    image.save(DEBUG_DIR / f"{capture_id}.jpg", format="JPEG", quality=85)
    files = sorted(DEBUG_DIR.glob("*.jpg"), key=lambda path: path.stat().st_mtime)
    for path in files[:-DEBUG_RETAIN_IMAGES]:
        path.unlink(missing_ok=True)


def run_scheduled_session() -> tuple[int, int]:
    captured = uploaded = 0
    session_id = utc_now().strftime("%Y%m%dT%H%M%SZ")
    for index in range(1, CAPTURES_PER_SESSION + 1):
        capture_id = f"{SITE_ID}_SCHED_{session_id}_{index:02d}"
        try:
            full, cropped, stats = capture_image()
            captured += 1
            retain_debug_image(cropped, capture_id)
            if UPLOAD_ENABLED:
                payload = build_payload(full, cropped, capture_id, int(time.time()), stats)
                success, error = post_payload(payload)
                if success:
                    uploaded += 1
                else:
                    logger.error("Upload failed for %s: %s", capture_id, error)
                    save_failed_payload(payload, error or "unknown")
            logger.info("capture=%s quality=%s", capture_id, stats)
        except Exception as exc:
            logger.exception("Capture failed for %s: %s", capture_id, exc)
        if index < CAPTURES_PER_SESSION and INTER_CAPTURE_DELAY_SEC:
            time.sleep(INTER_CAPTURE_DELAY_SEC)
    return captured, uploaded


def successful_session(captured: int, uploaded: int) -> bool:
    required = math.ceil(CAPTURES_PER_SESSION * 0.9)
    if captured < required:
        return False
    return not UPLOAD_ENABLED or uploaded >= required


def main() -> int:
    with LOCK_PATH.open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.error("Another camera capture or retry process is active")
            return 75
        recovered, attempted = process_failed_sessions()
        logger.info("version=%s retry_recovered=%s retry_attempted=%s", CAMERA_AGENT_VERSION, recovered, attempted)
        captured, uploaded = run_scheduled_session()
        logger.info("captured=%s uploaded=%s requested=%s", captured, uploaded, CAPTURES_PER_SESSION)
        return 0 if successful_session(captured, uploaded) else 1


if __name__ == "__main__":
    sys.exit(main())
