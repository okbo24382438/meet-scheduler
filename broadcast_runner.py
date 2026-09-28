import argparse
import subprocess
import re
import time
import urllib.request
import os
import psutil

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import quote
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from scheduler import load_config, next_schedule, validate_config


CONFIG_FILE = Path("schedule.json")
AUTH_FILE = Path(".auth/google_state.json")

# 기존 자동화 Chrome 프로세스를 종료하는 함수
# 크롬 생성전에 기존의 잔재 프로세스를 종료합니다.
def stop_existing_automation_chrome(profile_path: Path) -> None:
    expected_profile = os.path.normcase(
        os.path.normpath(str(profile_path.resolve()))
    )
    targets: dict[int, psutil.Process] = {}

    for process in psutil.process_iter(["name", "cmdline"]):
        info = process.info
        if (info["name"] or "").casefold() != "chrome.exe":
            continue

        command_line = info["cmdline"] or []
        if any(argument.startswith("--type=") for argument in command_line):
            continue

        profile_argument = next(
            (
                argument.split("=", 1)[1].strip('"')
                for argument in command_line
                if argument.startswith("--user-data-dir=")
            ),
            None,
        )
        if profile_argument is None:
            continue

        actual_profile = os.path.normcase(os.path.normpath(profile_argument))
        if actual_profile != expected_profile:
            continue

        targets[process.pid] = process
        try:
            for child in process.children(recursive=True):
                targets[child.pid] = child
        except psutil.NoSuchProcess:
            pass

    if not targets:
        return

    processes = list(targets.values())
    for process in processes:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass

    _, still_running = psutil.wait_procs(processes, timeout=5)

    for process in still_running:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass

    _, still_running = psutil.wait_procs(still_running, timeout=5)
    if still_running:
        raise RuntimeError("자동화 Chrome 프로세스를 종료하지 못했습니다.")

    print("기존 자동화 Chrome을 종료했습니다.")

# 파이썬에서 자동화용 Chrome을 실행하는 함수
def start_chrome_for_automation(capture_title: str) -> None:
    chrome_path = Path(
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    )
    profile_path = Path("OKBO_automation").resolve()

    stop_existing_automation_chrome(profile_path)

    subprocess.Popen(
        [
            str(chrome_path),
            "--remote-debugging-port=9222",
            "--autoplay-policy=no-user-gesture-required",
            f"--user-data-dir={profile_path}",
            f"--auto-select-tab-capture-source-by-title={capture_title}",
        ]
    )

    print("자동화용 Chrome을 실행했습니다.")

# Chrome 원격 디버깅 포트가 준비될 때까지 대기하는 함수
def wait_for_chrome_debug_port(timeout_seconds: int = 15) -> None:
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:9222/json/version",
                timeout=1,
            ):
                print("Chrome 원격 디버깅 포트가 준비되었습니다.")
                return
        except Exception:
            time.sleep(0.5)

    raise RuntimeError(
        "Chrome 원격 디버깅 포트(9222)가 준비되지 않았습니다."
    )

# 활성화 타이밍을 계산하는 함수
def active_timing(config: dict[str, Any]) -> tuple[int, int, int, int, bool]:
    if config["mode"] == "test":
        timing = config["timing"]["test"]
        return (
            timing["start_delay_seconds"],
            timing["before_video_seconds"],
            timing["video_max_seconds"],
            timing["after_video_seconds"],
            True,
        )

    timing = config["timing"]["production"]
    return (
        0,
        timing["before_video_minutes"] * 60,
        0,
        timing["after_video_minutes"] * 60,
        timing["use_full_video_duration"],
    )

# 진행 상황을 표시하며 대기하는 함수
def wait_with_progress(seconds: int, label: str) -> None:
    for remaining in range(seconds, 0, -1):
        if remaining == seconds or remaining <= 5 or remaining % 10 == 0:
            print(f"{label}: {remaining}초 남음")
        time.sleep(1)

# 게스트 이름 입력란에 이름을 입력하는 함수
def enter_guest_name(page: Any, name: str) -> None:
    name_input = page.get_by_role(
        "textbox", name=re.compile(r"이름|Name", re.IGNORECASE)
    ).first

    try:
        name_input.wait_for(state="visible", timeout=10000)
        name_input.fill(name)
        print(f"참여 이름을 입력했습니다: {name}")
    except PlaywrightTimeoutError as error:
        raise RuntimeError("참여 이름 입력란을 찾지 못했습니다.") from error


#
def click_join_button(page: Any) -> None:
    page.wait_for_timeout(1000)
    join_pattern = re.compile(
        r"^\s*(?:지금 참여하기|다시 참여|재참여|참여하기|참여 요청|참가|참여|Join now|Join|Ask to join|Request to join)\s*$",
        re.IGNORECASE,
    )
    join_candidates = (
        page.get_by_role("button", name=join_pattern).first,
        page.locator("button").filter(has_text=join_pattern).first,
        page.get_by_role("link", name=join_pattern).first,
        page.locator("[role='button']").filter(has_text=join_pattern).first,
        page.get_by_text(join_pattern).last,
    )
    leave_indicator = page.get_by_role(
        "button", name=re.compile(r"나가기|Leave call|전화 끊기", re.IGNORECASE)
    ).first

    for join_button in join_candidates:
        try:
            page.bring_to_front()
            join_button.scroll_into_view_if_needed(timeout=3000)

            join_button.focus()
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)

            leave_indicator.wait_for(state="visible", timeout=8000)
            print("참여하기 버튼을 눌렀고 회의 입장을 확인했습니다.")
            return
        except PlaywrightTimeoutError:
            continue

    print(f"참여 버튼을 찾지 못했습니다. 현재 주소: {page.url}")
    print(f"현재 페이지 제목: {page.title()}")
    page.screenshot(path="join_failure.png", full_page=True)
    print(f"참여 실패 화면을 저장했습니다: {Path('join_failure.png').resolve()}")
    print(f"현재 보이는 버튼: {page.locator('button:visible').all_inner_texts()}")
    raise RuntimeError("Meet 참여에 실패했습니다. 회의 입장 화면을 확인하세요.")


def switch_to_current_device(page: Any) -> None:
    switch_pattern = re.compile(
        r"현재 기기로 전환|이 기기로 전환|Switch to this device|Use this device",
        re.IGNORECASE,
    )
    switch_candidates = (
        page.get_by_role("button", name=switch_pattern).first,
        page.locator("[role='button']").filter(has_text=switch_pattern).first,
    )

    for switch_button in switch_candidates:
        try:
            if page.is_closed() or not switch_button.is_visible():
                continue
            switch_button.click(timeout=5000)
            print("이전 세션에서 현재 기기로 전환했습니다.")
            page.wait_for_timeout(1500)
            return
        except PlaywrightTimeoutError:
            continue

# 카메라를 끄는 함수
def turn_camera_off(page: Any) -> None:
    camera_off_button = page.get_by_role(
        "button",
        name=re.compile(r"카메라 끄기|Turn off camera|Turn camera off", re.IGNORECASE),
    ).first
    try:
        camera_off_button.click(timeout=5000)
        print("카메라를 껐습니다. 기본 프로필 이미지 상태로 참여합니다.")
    except PlaywrightTimeoutError:
        print("카메라가 이미 꺼져 있거나 카메라 버튼을 찾지 못했습니다.")


# 탭 발표를 시작하는 함수
def start_tab_presentation(page: Any, capture_title: str) -> None:
    present_button = page.get_by_role(
        "button", name=re.compile(r"발표 시작|Present now|화면 공유", re.IGNORECASE)
    ).first
    try:
        present_button.click(timeout=10000)
    except PlaywrightTimeoutError as error:
        raise RuntimeError("Meet의 발표 시작 버튼을 찾지 못했습니다.") from error
    
    print("공유 선택 화면의 버튼:", page.locator("button:visible").all_inner_texts())
    print("공유 선택 화면의 텍스트:", page.locator("body").inner_text()[:3000])

    stop_button = page.get_by_role(
        "button", name=re.compile(r"발표 중지|Stop presenting", re.IGNORECASE)
    ).first
    try:
        stop_button.wait_for(state="visible", timeout=15000)
    except PlaywrightTimeoutError as error:
        raise RuntimeError("동영상 탭 자동 공유가 시작되지 않았습니다.") from error

# 회의에서 나가기 버튼을 클릭하는 함수
def click_leave_button(page: Any) -> None:
    leave_button = page.get_by_role(
        "button", name=re.compile(r"나가기|Leave call|전화 끊기", re.IGNORECASE)
    ).last
    try:
        leave_button.click(timeout=10000)
        print("본인만 회의에서 나갔습니다.")
    except PlaywrightTimeoutError:
        print("퇴장 버튼을 찾지 못했습니다. 현재 화면을 확인하세요.")

# 비디오 서버를 시작하는 함수
def start_video_server(video_path: Path) -> tuple[ThreadingHTTPServer, str]:
    class VideoHandler(SimpleHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/":
                page = (
                    "<!doctype html><html><head>"
                    f"<title>[VIDEO ONLY] {video_path.name}</title>"
                    "</head><body style='margin:0;background:#000'>"
                    f"<video id='video' autoplay playsinline controls "
                    f"style='width:100vw;height:100vh' "
                    f"src='/video/{quote(video_path.name)}'></video>"
                    "<script>"
                    "const video = document.getElementById('video');"
                    "video.play().catch(error => {"
                    "    console.log('자동 재생 실패:', error);"
                    "});"
                    "</script>"
                    "</body></html>"
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return

            if self.path == f"/video/{quote(video_path.name)}":
                self.path = f"/{video_path.name}"
            super().do_GET()

        def log_message(self, format: str, *args: Any) -> None:
            return

    handler = partial(VideoHandler, directory=str(video_path.parent))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/"

# 방송을 실행하는 함수
def run_broadcast(config: dict[str, Any], video_id: str) -> None:

    video_path = Path(config["videos"][video_id]).resolve()
    capture_title = f"[VIDEO ONLY] {video_path.name}"
    print("화면 공유 대상 제목:", capture_title)
    start_delay_seconds, before_seconds, video_max_seconds, after_seconds, test_mode = active_timing(config)
    start_chrome_for_automation(capture_title)
    # 자동화용 Chrome을 실행하고 원격 디버깅 포트가 준비될 때까지 대기합니다.
    wait_for_chrome_debug_port()

    with sync_playwright() as playwright:
        browser_args = [
            f"--auto-select-tab-capture-source-by-title={capture_title}"
        ]

        browser = playwright.chromium.connect_over_cdp(
            "http://127.0.0.1:9222"
        )

        context = browser.contexts[0]

        meet_page = context.new_page()
        meet_page.goto(config["meeting_url"], wait_until="domcontentloaded")
        print("Meet 접속 직후 URL:", meet_page.url)

        if test_mode:
            turn_camera_off(meet_page)
        switch_to_current_device(meet_page)
        print("현재 Meet URL:", meet_page.url)
        enter_guest_name(meet_page, "옥보")
        click_join_button(meet_page)
        

        if start_delay_seconds:
            wait_with_progress(start_delay_seconds, "방송 시작 후 대기")


        video_server, video_url = start_video_server(video_path)
        video_page = context.new_page()
        video_page.goto(video_url, wait_until="domcontentloaded")

        video_element = video_page.locator("video")
        video_element.wait_for(state="visible")
        # 동영상이 준비될 때까지 대기합니다.
        video_element.evaluate(
            """
            video => new Promise(resolve => {
                if (video.readyState >= 3) {
                    resolve();
                    return;
                }

                video.addEventListener("canplay", resolve, { once: true });
            })
            """
        )

        # 디버깅 코드: 동영상 상태를 확인합니다.
        print("영상 paused 상태:", video_element.evaluate("video => video.paused"))
        print("영상 readyState:", video_element.evaluate("video => video.readyState"))
        print("영상 현재 시간:", video_element.evaluate("video => video.currentTime"))
        # 디버깅 코드: 동영상 상태를 확인합니다.

        meet_page.bring_to_front()
        print("동영상 탭을 열었습니다.")
        print("동영상 탭은 자동 재생됩니다.")
        start_tab_presentation(meet_page, capture_title)
        print("동영상 탭 자동 공유를 시작했습니다.")

        # 동영상 실제 시간만큼 재생 및 종료 처리
        print("동영상이 끝날 때까지 재생합니다.")
        video_page.locator("video").wait_for(state="visible")
        video_page.locator("video").evaluate(
            """
            video => new Promise(resolve => {
                if (video.ended) {
                    resolve();
                    return;
                }

                video.addEventListener("ended", resolve, { once: true });
            })
            """
        )
        print("동영상 재생이 끝났습니다.")

        video_page.close()
        video_server.shutdown()
        video_server.server_close()
        meet_page.bring_to_front()
        print("동영상 공유를 종료했습니다. 회의실에서 종료 전 대기를 시작합니다.")
        wait_with_progress(after_seconds, "방송 종료 전 대기")
        print("종료 전 대기가 끝났습니다. 이제 본인만 회의에서 나갑니다.")
        click_leave_button(meet_page)
        context.close()
        browser.close()

# 프로그램의 진입점
def main() -> None:
    parser = argparse.ArgumentParser(description="설정 기반 Google Meet 방송 실행기")
    parser.add_argument("--config", type=Path, default=CONFIG_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-now", action="store_true")
    parser.add_argument("--video", choices=["1", "2", "3", "4", "5"])
    args = parser.parse_args()

    config = load_config(args.config)
    validate_config(config)
    start_delay_seconds, before_seconds, video_max_seconds, after_seconds, test_mode = active_timing(config)

    if args.dry_run:
        print(f"실행 모드: {config['mode']}")
        print(f"회의 참여 후 대기: {start_delay_seconds}초")
        print(f"동영상 전 대기: {before_seconds}초")
        print(f"동영상 공유 제한: {'전체 재생' if not test_mode else f'{video_max_seconds}초'}")
        print(f"동영상 후 대기: {after_seconds}초")
        return

    if args.run_now:
        video_id = args.video or "1"
    else:
        scheduled_at, entry = next_schedule(config)
        print(f"다음 방송 시각: {scheduled_at:%Y-%m-%d %H:%M}")
        print("즉시 테스트하려면 --run-now 옵션을 사용하세요.")
        return

    print(f"동영상 {video_id} 방송을 시작합니다.")
    run_broadcast(config, video_id)


if __name__ == "__main__":
    main()
