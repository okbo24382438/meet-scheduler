from pathlib import Path
import re

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


MEET_URL = "https://meet.google.com/bax-ecap-ifm"
AUTH_FILE = Path(".auth/google_state.json")

if not AUTH_FILE.exists():
    raise SystemExit(
        "로그인 상태가 없습니다. 먼저 save_google_login.py를 실행하세요."
    )

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(storage_state=str(AUTH_FILE))
    page = context.new_page()
    page.goto(MEET_URL, wait_until="domcontentloaded")

    join_button = page.get_by_role(
        "button", name=re.compile(r"참여하기|Join now", re.IGNORECASE)
    ).first

    try:
        join_button.click(timeout=15000)
        print("참여하기 버튼을 자동으로 눌렀습니다.")
    except PlaywrightTimeoutError:
        print("참여하기 버튼을 찾지 못했습니다. 화면을 직접 확인하세요.")

    print("회의 화면을 확인한 뒤 Enter를 누르면 브라우저가 종료됩니다.")
    input()

    context.close()
    browser.close()
