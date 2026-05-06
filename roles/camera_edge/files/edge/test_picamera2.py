#!/usr/bin/env python3
import time
from picamera2 import Picamera2
from datetime import datetime

print("Testing Picamera2...")

try:
    # Create camera instance
    picam2 = Picamera2()

    # Print camera info
    print(f"Camera Model: {picam2.camera_properties.get('Model', 'Unknown')}")

    # Configure camera
    config = picam2.create_still_configuration(
        main={"size": (1920, 1080)}
    )
    picam2.configure(config)

    # Start camera
    picam2.start()
    time.sleep(2)  # Let camera warm up

    # Capture image
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"picamera2_test_{timestamp}.jpg"
    picam2.capture_file(filename)
    print(f"Image captured: {filename}")

    # Stop camera
    picam2.stop()
    picam2.close()

    print("SUCCESS! Camera is working with Picamera2")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
