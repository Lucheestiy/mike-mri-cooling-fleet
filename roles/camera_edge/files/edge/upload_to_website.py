#!/usr/bin/env python3
"""
Upload calibration images to cam.coolmri.com via a simple endpoint
"""
import os
import json
import requests
from pathlib import Path
from datetime import datetime

def upload_calibration_images():
    """Upload the latest calibration images to the website"""
    images_dir = Path("images")

    # Check if calibration images exist
    full_image_path = images_dir / "CALIBRATION_FULL_VIEW.jpg"
    crop_image_path = images_dir / "CALIBRATION_CROP_REGION.jpg"

    if not full_image_path.exists() or not crop_image_path.exists():
        print("❌ No calibration images found. Run calibration mode first:")
        print("   python camera_ocr.py --calibrate --single")
        return False

    print("📸 Found calibration images, uploading to cam.coolmri.com...")

    try:
        # Try multiple possible endpoints
        endpoints = [
            "https://cam.coolmri.com/api/camera/calibration",
            "https://cam.coolmri.com/api/camera/debug",
            "https://cam.coolmri.com/api/camera/upload"
        ]

        # Prepare files
        with open(full_image_path, 'rb') as full_file, open(crop_image_path, 'rb') as crop_file:
            files = {
                'full_image': ('full_view.jpg', full_file, 'image/jpeg'),
                'crop_image': ('crop_region.jpg', crop_file, 'image/jpeg')
            }

            # Prepare metadata
            data = {
                'site_id': 'GMCMR2',
                'timestamp': datetime.now().isoformat(),
                'crop_coords': '{"x": 850, "y": 450, "w": 200, "h": 100}',
                'message': 'Calibration images from Pi Camera'
            }

            # Try each endpoint
            for endpoint in endpoints:
                print(f"🔗 Trying: {endpoint}")
                try:
                    response = requests.post(endpoint, files=files, data=data, timeout=10)
                    if response.status_code in [200, 201]:
                        print(f"✅ SUCCESS! Images uploaded to {endpoint}")
                        print(f"Response: {response.text}")
                        return True
                    else:
                        print(f"❌ {endpoint}: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f"❌ {endpoint}: {e}")

                # Reset file pointers for next attempt
                full_file.seek(0)
                crop_file.seek(0)

        # If all endpoints failed, try a different approach
        print("\n🔄 Trying alternative method...")

        # Convert to base64 and send as JSON
        import base64

        with open(full_image_path, 'rb') as f:
            full_b64 = base64.b64encode(f.read()).decode('utf-8')

        with open(crop_image_path, 'rb') as f:
            crop_b64 = base64.b64encode(f.read()).decode('utf-8')

        # Try sending to the pressure endpoint with image data using correct field names
        payload = {
            "site_id": "GMCMR2",
            "timestamp": int(datetime.now().timestamp()),
            "return_pressure": 0.0,  # Dummy value
            "confidence": 0.0,       # Mark as calibration
            "source": "pi5_calibration_upload",
            "full_image_base64": full_b64,
            "cropped_image_base64": crop_b64,
            "crop_coordinates": {"x": 850, "y": 450, "w": 200, "h": 100},
            "message": "Fresh calibration images from Pi Camera Module 3 Wide"
        }

        response = requests.post("https://cam.coolmri.com/api/camera/pressure", json=payload, timeout=30)
        if response.status_code in [200, 201]:
            print("✅ Images sent via pressure endpoint with calibration flag!")
            return True
        else:
            print(f"❌ Pressure endpoint: {response.status_code} - {response.text}")

        print("\n📝 All upload methods failed. Images are saved locally:")
        print(f"   {full_image_path.absolute()}")
        print(f"   {crop_image_path.absolute()}")
        print("\nYou can manually copy these files or view them locally.")
        return False

    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return False

if __name__ == "__main__":
    upload_calibration_images()