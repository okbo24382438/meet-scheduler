from playwright.sync_api import sync_playwright


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("data:text/html,<title>Playwright test</title>")
    print(f"Page title: {page.title()}")
    page.wait_for_timeout(1500)
    browser.close()

print("Playwright smoke test passed.")
