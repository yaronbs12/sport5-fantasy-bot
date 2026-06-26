#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "==================================================="
echo "  Sport5 Fantasy Analytics - Mac/Linux Setup Script"
echo "==================================================="
echo

echo "[1/3] Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt

echo
echo "[2/3] Installing Playwright Chromium browser..."
playwright install chromium

echo
echo "[3/3] Running tests to verify installation integrity..."
if pytest test_scraper.py; then
    echo "Tests passed successfully!"
else
    echo "WARNING: Some tests did not pass. Check test logs."
fi

echo
echo "==================================================="
echo "  Setup completed successfully!"
echo "  To launch the dashboard, run: streamlit run app.py"
echo "==================================================="
