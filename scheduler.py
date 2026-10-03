import argparse
import json
import subprocess
import time
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from log_manage import write_event


# 요일 상수
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

# 애플리케이션 디렉토리와 설정 파일 경로를 결정합니다.
def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()
CONFIG_FILE = APP_DIR / "schedule.json"

# 설정 파일을 읽는 함수
def load_config(path: Path = CONFIG_FILE) -> dict[str, Any]:
    with path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


# 방송 시간을 파싱하는 유틸 함수
def parse_schedule_time(time_text: str):
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(time_text, time_format).time()
        except ValueError:
            pass

    raise ValueError(f"잘못된 방송 시간 형식입니다: {time_text}")


# 스케줄 JSON 파일을 검증하는 함수
def validate_config(config: dict[str, Any]) -> None:
    videos = config["videos"]

    for day_name, entries in config["schedule"].items():
        times = [entry["time"] for entry in entries]
        if len(times) != len(set(times)):
            raise ValueError(f"{day_name}에 중복된 방송 시간이 있습니다.")
        for entry in entries:
            if entry["video"] not in videos:
                raise ValueError(
                    f"{day_name}의 동영상 번호가 없습니다: {entry['video']}"
                )
            parse_schedule_time(entry["time"])

# 선택 영상 경로가 유효한지 검증하는 함수
def validate_video_path(
    config: dict[str, Any],
    video_id: str,
) -> Path:
    path_text = str(config.get("videos", {}).get(video_id, "")).strip()
    if not path_text:
        raise ValueError(f"영상 {video_id}의 경로가 등록되지 않았습니다.")

    video_path = Path(path_text)
    if not video_path.is_file():
        raise FileNotFoundError(
            f"영상 {video_id} 파일을 찾을 수 없습니다: {video_path}"
        )

    return video_path.resolve()

# 다음 방송 일정을 계산하는 함수
def next_schedule(
    config: dict[str, Any], now: datetime | None = None
) -> tuple[datetime, dict[str, str]]:
    current_time = now or datetime.now()

    for day_offset in range(8):
        candidate_date = current_time.date() + timedelta(days=day_offset)
        day_name = WEEKDAYS[candidate_date.weekday()]
        entries = config["schedule"].get(day_name, [])

        for entry in sorted(entries, key=lambda item: item["time"]):
            scheduled_time = parse_schedule_time(entry["time"])
            candidate = datetime.combine(candidate_date, scheduled_time)
            if candidate >= current_time:
                return candidate, entry

    raise RuntimeError("일주일 안에 예정된 방송이 없습니다.")

# 방송 시작 전 대기 시간을 계산하는 함수
def before_video_seconds(config: dict[str, Any]) -> int:
    mode = config.get("mode")

    if mode == "test":
        return config["timing"]["test"]["before_video_seconds"]

    if mode == "real":
        return config["timing"]["real"]["before_video_minutes"] * 60

    raise ValueError(f"지원하지 않는 mode입니다: {mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Meet 방송 스케줄 확인")
    parser.add_argument(
        "--config", type=Path, default=CONFIG_FILE, help="스케줄 JSON 경로"
    )
    parser.add_argument(
        "--stop-file", type=Path, help="스케줄러 중지 요청 파일"
    )

    args = parser.parse_args()

    stop_file = args.stop_file.resolve() if args.stop_file else None

    def stop_requested() -> bool:
        return stop_file is not None and stop_file.exists()

    config_path = args.config.resolve()
    config = load_config(config_path)

    validate_config(config)

    while True:
        if stop_requested():
            print("스케줄러 중지 요청을 확인했습니다.")
            return
                
        scheduled_at, entry = next_schedule(config)
        video_path = config["videos"][entry["video"]]
        join_at = scheduled_at - timedelta(
            seconds=before_video_seconds(config)
        )

        print(f"예정된 영상 공유 시각: {scheduled_at:%Y-%m-%d %H:%M:%S}")
        print(f"방송 프로그램 실행 시각: {join_at:%Y-%m-%d %H:%M:%S}")
        print(f"동영상 {entry['video']}: {video_path}")

        while True:
            if stop_requested():
                print("스케줄러 중지 요청을 확인했습니다.")
                return

            remaining = (join_at - datetime.now()).total_seconds()
            if remaining <= 0:
                break

            total_seconds = int(remaining)
            days, remainder = divmod(total_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)

            print(
                f"Meet 입장 까지 {days}일 "
                f"{hours:02d}시간 "
                f"{minutes:02d}분 "
                f"{seconds:02d}초 남았습니다."
            )
            time.sleep(1)

        print("Meet 입장 준비 시각이 되었습니다.")
        print(f"동영상 {entry['video']} 방송을 준비합니다.")

        if stop_requested():
            return
        try:
            broadcast_id = uuid.uuid4().hex
            video_path = validate_video_path(config, entry["video"])
            print(f"동영상 {entry['video']}: {video_path}")

            runner_path = APP_DIR / (
                "broadcast_runner.exe"
                if getattr(sys, "frozen", False)
                else "broadcast_runner.py"
            )

            if getattr(sys, "frozen", False):
                command = [str(runner_path)]
            else:
                command = [sys.executable, str(runner_path)]

            command.extend(
                [
                    "--config",
                    str(config_path),
                    "--run-now",
                    "--video",
                    entry["video"],
                    "--broadcast-id",
                    broadcast_id,
                ]
            )

            subprocess.run(
                command,
                check=True,
                cwd=APP_DIR,
            )
        except (FileNotFoundError, ValueError) as error:
            write_event(
                "errors",
                "video_validation_failed",
                "scheduler",
                phase="video_validation",
                broadcast_id=broadcast_id,
                video_id=entry["video"],
                error_type=type(error).__name__,
                error_message=str(error),
            )            
            message = (
                f"방송 건너뜀: 예약 시각={scheduled_at}, "
                f"영상={entry['video']}, 사유={error}"
            )
            print(message, flush=True)
            continue            
        except subprocess.CalledProcessError as error:
            write_event(
                "errors",
                "broadcast_runner_failed",
                "scheduler",
                phase="broadcast_runner",
                broadcast_id=broadcast_id,
                video_id=entry["video"],
                exit_code=error.returncode,
                error_message=str(error),
            )            
            message = (
                f"방송 실패: 예약 시각={scheduled_at}, "
                f"영상={entry['video']}, 종료 코드={error.returncode}"
            )
            print(message, flush=True)
            continue




if __name__ == "__main__":
    main()
