#!/bin/bash
# Production OCR Script - Fixed LCD Overexposure & 99% Upload Reliability
cd $(dirname $0)
cd ..
# Use virtual environment with all dependencies
source venv/bin/activate
cd edge
python improved_ocr.py "$@"
