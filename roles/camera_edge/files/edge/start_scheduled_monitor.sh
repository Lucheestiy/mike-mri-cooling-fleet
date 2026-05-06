#!/bin/bash
# Start Scheduled MRI Monitor (9 AM and 4 PM daily)

echo "========================================"
echo "⏰ SCHEDULED MRI MONITOR"
echo "========================================"
echo ""
echo "📅 Monitoring Schedule:"
echo "   - 9:00 AM daily"
echo "   - 4:00 PM daily"
echo ""
echo "📊 Each session captures:"
echo "   - Water temperature (4-25°C)"
echo "   - ECO pressure (0.5-1.7 PSI)"
echo "   - Scan pressure (0.5-1.7 PSI)"
echo ""
echo "📝 Logs saved to: monitoring_schedule.log"
echo "🌐 Data sent to: cam.coolmri.com"
echo ""
echo "Press Ctrl+C to stop"
echo "========================================"
echo ""

# Navigate to project directory
cd "$(dirname "$0")"
cd ..

# Activate virtual environment
source venv/bin/activate

# Install schedule if not present
pip show schedule >/dev/null 2>&1 || pip install schedule

# Run scheduled monitor
cd edge
python schedule_monitor.py