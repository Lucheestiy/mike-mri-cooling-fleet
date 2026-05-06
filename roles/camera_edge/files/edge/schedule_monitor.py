#!/usr/bin/env python3
"""
Scheduled MRI Monitor - Runs smart monitoring at 9 AM and 4 PM daily
"""
import schedule
import time
import logging
from datetime import datetime
from pathlib import Path
import subprocess
import sys

# Setup logging
log_file = Path(__file__).parent / "monitoring_schedule.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_monitoring_session():
    """Run the smart monitoring session"""
    try:
        logger.info("🕘 Scheduled monitoring session starting...")

        # Run smart_monitor.py
        script_path = Path(__file__).parent / "smart_monitor.py"

        # Activate virtual environment and run
        venv_path = Path(__file__).parent.parent / "venv" / "bin" / "activate"

        cmd = f"source {venv_path} && python {script_path}"

        logger.info(f"Executing: {cmd}")
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            logger.info("✅ Scheduled monitoring session completed successfully")
            logger.info(f"Output: {result.stdout}")
        else:
            logger.error(f"❌ Monitoring session failed with return code {result.returncode}")
            logger.error(f"Error: {result.stderr}")

    except subprocess.TimeoutExpired:
        logger.error("❌ Monitoring session timed out after 5 minutes")
    except Exception as e:
        logger.error(f"❌ Monitoring session failed: {e}")

def main():
    """Main scheduler loop"""
    logger.info("=" * 60)
    logger.info("🕘 SMART MRI MONITORING SCHEDULER STARTED")
    logger.info("📅 Schedule: 9:00 AM and 4:00 PM daily")
    logger.info(f"📝 Logs: {log_file}")
    logger.info("=" * 60)

    # Schedule monitoring sessions
    schedule.every().day.at("09:00").do(run_monitoring_session)
    schedule.every().day.at("16:00").do(run_monitoring_session)

    logger.info("⏰ Scheduled jobs:")
    logger.info("   - 09:00 AM daily: Smart MRI monitoring")
    logger.info("   - 04:00 PM daily: Smart MRI monitoring")
    logger.info("")
    logger.info("🔄 Scheduler running. Press Ctrl+C to stop.")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

    except KeyboardInterrupt:
        logger.info("🛑 Scheduler stopped by user")
    except Exception as e:
        logger.error(f"❌ Scheduler error: {e}")

if __name__ == "__main__":
    main()