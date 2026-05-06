#!/usr/bin/env python3
"""
Standalone script to retry failed capture sessions.
Runs every 5 minutes via cron to check for and retry failed uploads.
"""

import sys
import os
from pathlib import Path

# Add the project edge directory to Python path dynamically
EDGE_DIR = str(Path.home() / 'mri-cooling-camera' / 'edge')
sys.path.insert(0, EDGE_DIR)

from scheduled_capture import process_extended_retries, logger

def main():
    """Main entry point for retry processing."""
    try:
        logger.info("🔄 FAILED SESSION RETRY CHECK")
        process_extended_retries()

    except Exception as e:
        logger.error(f"Error in retry processing: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
