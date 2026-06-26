@echo off
echo ===================================================
echo   Sport5 Fantasy Analytics - Windows Setup Script
echo ===================================================
echo.

echo [1/3] Installing Python dependencies from requirements.txt...
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to install python packages. Ensure python/pip are in your system PATH.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/3] Installing Playwright Chromium browser...
playwright install chromium
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to install Playwright browser.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [3/3] Running tests to verify installation integrity...
pytest test_scraper.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo WARNING: Some tests did not pass. Check test logs.
)

echo.
echo ===================================================
echo   Setup completed successfully!
echo   To launch the dashboard, run: streamlit run app.py
echo ===================================================
pause
