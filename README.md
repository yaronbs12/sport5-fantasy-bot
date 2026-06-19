# Sport5 Fantasy Analytics Dashboard — Full-Season Intelligence Tool 🏆⚽

An advanced automation engine and analytics workspace designed to pull, compile, normalize, and report on competitor rosters within the Sport5 Dream Team Fantasy Football League.

---

## 🛠️ Core Architecture & Engineering Highlights

* **Automated Browser Pipeline:** Orchestrates Chromium browser contexts using Playwright for secure, off-screen local session management and stateful authentication, seamlessly querying Sport5 API endpoints.
* **Data Normalization Engine:** Employs a robust translation mapping dictionary resolving bilingual differences (e.g. matching tournament names like `"Haiti"`, `"Ecuador"`, and `"Cape Verde"` to hebrew entries `"האיטי"`, `"אקוודור"`, and `"קייפ ורדה"`) and sanitizing player names containing layout symbols or backticks.
* **League Analytics:** Parses and aggregates complete competitor rosters across the entire processed league to calculate dynamic player ownership rates, squad compositions, and player popularity indicators.
* **Premium UX:** Integrates a responsive dark/light mode toggle, custom fonts, a CSS-animated bouncing football loading state (`⚽`), and a one-click WhatsApp report share using URL-encoded text payloads.
* **Robust Testing Layer:** Implements a test-driven development (TDD) cycle built with `pytest` unit test suites to guarantee 100% data-join normalization integrity.

---

## 🚀 Installation & Local Usage

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/your-username/sport5-fantasy-analytics.git
   cd sport5-fantasy-analytics
   ```

2. **Install Python Packages:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Browser Web Drivers:**
   ```bash
   playwright install chromium
   ```

4. **Run Automated Test Suite:**
   ```bash
   pytest test_scraper.py
   ```

5. **Launch the Dashboard:**
   ```bash
   streamlit run app.py
   ```

---

## 🔒 Security & Environments

This application separates code logic from operational secrets and user session state:
* **Credential Isolation:** API endpoints, Discord or Slack webhooks, and private URLs are isolated via Streamlit's native secret manager (`.streamlit/secrets.toml`).
* **Session Protection:** Saved cookies, authenticated states, and profile files (`sport5_user_data/`) are strictly kept on local storage and excluded from Git version tracking via `.gitignore` to prevent leakage to public source directories.
* **Debug Isolation:** A local `DEBUG` flag is available in `config.py` to prevent structural debug files (`leagues_debug.json`, `sport5_teams_debug.json`) from generating during normal runtime execution.
