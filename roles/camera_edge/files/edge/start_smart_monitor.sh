#!/bin/bash
# Start Smart MRI Monitor

echo "========================================"
echo "🧠 SMART MRI COOLING MONITOR"
echo "========================================"
echo ""
echo "This intelligent system will:"
echo "1. Capture LCD display for 30 seconds"
echo "2. Extract temperature (4-25°C)"
echo "3. Extract ECO pressure (0.5-1.7 PSI)"
echo "4. Extract scan pressure (0.5-1.7 PSI)"
echo "5. Send all readings to cam.coolmri.com"
echo ""

# Navigate to project directory
cd "$(dirname "$0")"
cd ..

# Activate virtual environment
source venv/bin/activate

# Run smart monitor
cd edge
python smart_monitor.py