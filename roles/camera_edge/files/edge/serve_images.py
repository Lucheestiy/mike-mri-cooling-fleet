#!/usr/bin/env python3
"""
Simple HTTP server to serve calibration images for remote viewing
"""
import http.server
import socketserver
import os
from pathlib import Path

class ImageServer(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="images", **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            html = """
<!DOCTYPE html>
<html>
<head>
    <title>Camera Calibration Viewer</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        h1 { color: #333; text-align: center; }
        .image-container { display: flex; justify-content: space-around; margin: 20px 0; flex-wrap: wrap; }
        .image-box { text-align: center; margin: 10px; }
        .image-box img { max-width: 600px; border: 2px solid #ddd; border-radius: 5px; }
        .info { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .refresh-btn { background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }
        .coordinates { font-family: monospace; background: #f4f4f4; padding: 10px; border-radius: 5px; }
    </style>
    <script>
        function refreshImages() {
            document.getElementById('fullImg').src = 'CURRENT_FULL_VIEW.jpg?' + new Date().getTime();
            document.getElementById('cropImg').src = 'CURRENT_CROP_REGION.jpg?' + new Date().getTime();
        }
        setInterval(refreshImages, 3000); // Auto-refresh every 3 seconds
    </script>
</head>
<body>
    <div class="container">
        <h1>📷 Camera OCR Calibration</h1>

        <div class="info">
            <h3>Current Status:</h3>
            <p>Camera is pointing at whatever is in front of it. The red box shows the OCR crop region.</p>
            <button class="refresh-btn" onclick="refreshImages()">🔄 Refresh Images</button>
            <p><small>Images auto-refresh every 3 seconds</small></p>
        </div>

        <div class="image-container">
            <div class="image-box">
                <h3>Full Camera View</h3>
                <img id="fullImg" src="CURRENT_FULL_VIEW.jpg" alt="Full camera view">
                <p>Red box shows OCR crop region</p>
            </div>

            <div class="image-box">
                <h3>OCR Crop Region</h3>
                <img id="cropImg" src="CURRENT_CROP_REGION.jpg" alt="Cropped OCR region">
                <p>This is what OCR processes</p>
            </div>
        </div>

        <div class="coordinates">
            <h3>To adjust crop coordinates:</h3>
            <p>1. SSH to Pi: <code>ssh gmcmr2c@[pi-ip]</code></p>
            <p>2. Edit: <code>nano /home/gmcmr2c/mri-cooling-camera/edge/.env</code></p>
            <p>3. Change: <code>OCR_CROP_COORDS={"x": 850, "y": 450, "w": 200, "h": 100}</code></p>
            <p>4. Save and run: <code>python save_calibration_image.py</code></p>
        </div>
    </div>
</body>
</html>
            """
            self.wfile.write(html.encode())
        else:
            super().do_GET()

def start_server(port=8080):
    """Start image server"""
    os.chdir(Path(__file__).parent)

    with socketserver.TCPServer(("", port), ImageServer) as httpd:
        print(f"🌐 Image server starting on port {port}")
        print(f"📸 View images at: http://[pi-ip-address]:{port}")
        print(f"🔧 Calibration interface: http://[pi-ip-address]:{port}")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Server stopped")

if __name__ == "__main__":
    start_server()