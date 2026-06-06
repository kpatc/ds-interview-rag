"""
Glassdoor Session Saver — run ONCE to capture your logged-in session.

Usage:
    python save_glassdoor_session.py

A browser window opens. Log in with your Indeed account, navigate to any
Glassdoor interview page to confirm you're logged in, then press Enter in
this terminal. The session is saved and all future scraping runs are automatic.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_FILE = Path(__file__).parent.parent.parent / "glassdoor_session.json"


def main():
    print("=" * 60)
    print("Glassdoor Session Setup")
    print("=" * 60)
    print()
    print("A browser window will open.")
    print("→ Click 'Sign In with Indeed' (or Google)")
    print("→ Complete the login")
    print("→ Make sure you see Glassdoor reviews (not a login wall)")
    print("→ Come back here and press ENTER")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = ctx.new_page()

        # Go directly to a BCG X interview page to test login
        # Page avec beaucoup d'avis (97 reviews QuantumBlack DS)
        page.goto(
            "https://www.glassdoor.com/Interview/"
            "QuantumBlack-Data-Scientist-Interview-Questions-EI_IE1508182.0,12_KO13,27.htm",
            wait_until="domcontentloaded",
            timeout=40000,
        )

        print("⏳ Si tu n'es pas connecté, clique 'Sign in with Indeed' dans le navigateur.")
        print("   La session sera sauvegardée automatiquement dans 90 secondes...")
        page.wait_for_timeout(90_000)

        # Save the full session (cookies + localStorage)
        ctx.storage_state(path=str(SESSION_FILE))
        browser.close()

    print(f"\n✅ Session saved → {SESSION_FILE}")
    print("You can now run: python run_all.py --glassdoor")
    print("(Re-run this script only if the session expires ~30 days)")


if __name__ == "__main__":
    main()
