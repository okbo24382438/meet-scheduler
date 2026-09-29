import argparse
import json
import subprocess
import time
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


CONFIG_FILE = Path("schedule.json")
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

#
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
    for video_id, video_path in videos.items():
        if not Path(video_path).is_file():
            raise FileNotFoundError(f"동영상 파일을 찾을 수 없습니다: {video_path}")

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
    args = parser.parse_args()

    config = load_config(args.config)

    logging.basicConfig(
        filename="scheduler.log",
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    validate_config(config)

    while True:
        scheduled_at, entry = next_schedule(config)
        video_path = config["videos"][entry["video"]]
        join_at = scheduled_at - timedelta(
            seconds=before_video_seconds(config)
        )

        print(f"예정된 영상 공유 시각: {scheduled_at:%Y-%m-%d %H:%M:%S}")
        print(f"방송 프로그램 실행 시각: {join_at:%Y-%m-%d %H:%M:%S}")
        print(f"동영상 {entry['video']}: {video_path}")

        while True:
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

        try:
            subprocess.run(
                [
                    sys.executable,
                    "broadcast_runner.py",
                    "--run-now",
                    "--video",
                    entry["video"],
                ],
                check=True,
            )
        except subprocess.CalledProcessError as error:
            message = (
                f"방송 실패: 예약 시각={scheduled_at}, "
                f"영상={entry['video']}, 종료 코드={error.returncode}"
            )
            print(message)
            logging.error(message)
            continue




if __name__ == "__main__":
    main()
