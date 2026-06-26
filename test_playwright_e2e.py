import os
import subprocess
import time
import requests
import socket
from playwright.sync_api import sync_playwright

def wait_for_server(url, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    return False

def test_app_e2e():
    # Start streamlit app in the background
    port = 8503
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    # We will test the login screen and some texts to ensure no HTML tags are rendered as text
    process = subprocess.Popen(
        ["streamlit", "run", "app.py", "--server.port", str(port), "--server.headless", "true"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    url = f"http://localhost:{port}"
    try:
        assert wait_for_server(url), "Streamlit server did not start in time."
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            # Grant clipboard permissions for copy testing
            context.grant_permissions(["clipboard-read", "clipboard-write"])
            page = context.new_page()
            
            # 1. Test Login Screen
            page.goto(url)
            page.wait_for_selector("text=נדרשת התחברות ל-Sport5", timeout=15000)
            
            # Check that HTML is not rendered as text
            content = page.content()
            assert "<div style=" not in page.locator("body").inner_text(), "Raw HTML is visible in the page!"
            assert "לא ניתן להתחבר עם חשבון Google" in content, "Google login warning missing."
            
            print("SUCCESS: Login screen rendered correctly without raw HTML tags.")
            
            # Since the app requires valid sport5 authentication to proceed to the report generation,
            # we will test the copy script logic independently if we cannot bypass login.
            # But we can at least assert the login page is clean.
            browser.close()
            
    finally:
        process.terminate()
        process.wait()

if __name__ == "__main__":
    test_app_e2e()
    print("All E2E tests passed.")
