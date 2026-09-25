from pathlib import Path
import subprocess
import time

from playwright.sync_api import sync_playwright


AUTH_DIR = Path(".auth")
PROFILE_DIR = Path("browser_profile")
AUTH_FILE = AUTH_DIR / "google_state.json"
CHROME_PATH = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DEBUGGING_PORT = 9222

AUTH_DIR.mkdir(exist_ok=True)

if not CHROME_PATH.exists():
    raise SystemExit(f"Chrome를 찾을 수 없습니다: {CHROME_PATH}")

chrome_process = subprocess.Popen(
    [
        str(CHROME_PATH),
        f"--remote-debugging-port={DEBUGGING_PORT}",
        f"--user-data-dir={PROFILE_DIR.resolve()}",
    ]
)

with sync_playwright() as playwright:
    browser = None
    for _ in range(20):
        try:
            browser = playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{DEBUGGING_PORT}"
            )
            break
        except Exception:
            time.sleep(0.5)

    if browser is None:
        chrome_process.terminate()
        raise SystemExit("Chrome 디버깅 연결을 열 수 없습니다.")

    context = browser.contexts[0]
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://accounts.google.com/", wait_until="domcontentloaded")

    print("Google 계정에 직접 로그인한 뒤 이 터미널에서 Enter를 누르세요.")
    input()

    context.storage_state(path=str(AUTH_FILE))
    browser.close()

print(f"로그인 상태를 저장했습니다: {AUTH_FILE}")
