#!/usr/bin/env python3
"""
Camera capture using libcamera system commands as fallback
"""
import subprocess
import tempfile
import os
from pathlib import Path
import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)

class LibCameraCapture:
    """Simple wrapper for libcamera system commands"""

    def __init__(self, width=1920, height=1080):
        self.width = width
        self.height = height
        self.available_tools = self._check_available_tools()

    def _check_available_tools(self):
        """Check which libcamera tools are available"""
        tools = {}

        # Check for various camera capture tools
        candidates = [
            'libcamera-still',
            'libcamera-jpeg',
            'libcamera-raw',
            'rpicam-still',
            'rpicam-jpeg'
        ]

        for tool in candidates:
            try:
                # Check if command exists
                result = subprocess.run(['which', tool],
                                      capture_output=True,
                                      text=True,
                                      timeout=5)
                if result.returncode == 0:
                    tools[tool] = result.stdout.strip()
                    logger.info(f"Found camera tool: {tool}")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        # Also try direct execution test
        for tool in candidates:
            if tool not in tools:
                try:
                    result = subprocess.run([tool, '--help'],
                                          capture_output=True,
                                          timeout=5)
                    if result.returncode == 0 or result.returncode == 1:  # Help might return 1
                        tools[tool] = tool
                        logger.info(f"Found camera tool (direct): {tool}")
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue

        return tools

    def is_available(self):
        """Check if any camera tools are available"""
        return len(self.available_tools) > 0

    def capture_to_file(self, output_path):
        """Capture image directly to file"""
        if not self.available_tools:
            logger.error("No camera capture tools available")
            return False

        # Try each available tool
        for tool_name in self.available_tools:
            try:
                cmd = [
                    tool_name,
                    '-o', str(output_path),
                    '--width', str(self.width),
                    '--height', str(self.height),
                    '--timeout', '1000',  # 1 second timeout
                    '--nopreview'  # Don't show preview
                ]

                logger.info(f"Trying capture with: {' '.join(cmd)}")

                result = subprocess.run(cmd,
                                      capture_output=True,
                                      text=True,
                                      timeout=10)

                if result.returncode == 0 and os.path.exists(output_path):
                    logger.info(f"Successfully captured image with {tool_name}")
                    return True
                else:
                    logger.warning(f"{tool_name} failed: {result.stderr}")

            except subprocess.TimeoutExpired:
                logger.warning(f"{tool_name} timed out")
            except Exception as e:
                logger.warning(f"{tool_name} error: {e}")

        return False

    def capture_array(self):
        """Capture image and return as numpy array"""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            if self.capture_to_file(tmp_path):
                # Load image and convert to array
                with Image.open(tmp_path) as img:
                    return np.array(img)
            return None
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

def test_libcamera():
    """Test libcamera capture functionality"""
    print("Testing libcamera capture...")

    capture = LibCameraCapture()
    print(f"Available tools: {capture.available_tools}")

    if not capture.is_available():
        print("No camera tools available")
        return False

    # Test capture
    test_path = "/home/gmcmr2c/mri-cooling-camera/edge/libcamera_test.jpg"
    if capture.capture_to_file(test_path):
        print(f"Success! Image captured to {test_path}")

        # Test array capture
        array = capture.capture_array()
        if array is not None:
            print(f"Array capture success: shape={array.shape}")
            return True

    return False

if __name__ == "__main__":
    success = test_libcamera()
    exit(0 if success else 1)