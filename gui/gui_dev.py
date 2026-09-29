import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from PyQt6.QtGui import QColor

from PyQt6.QtCore import QTime, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


# GUI 파일 위치를 기준으로 프로젝트 루트의 JSON 경로를 정합니다.
CONFIG_PATH = Path(__file__).resolve().parent.parent / "schedule.json"

WEEKDAYS = (
    ("monday", "월요일"),
    ("tuesday", "화요일"),
    ("wednesday", "수요일"),
    ("thursday", "목요일"),
    ("friday", "금요일"),
    ("saturday", "토요일"),
    ("sunday", "일요일"),
)


# 메인 창과 최초 UI 상태를 준비합니다.
class MeetSchedulerWindow(QMainWindow):
    # 24시간 형식의 시각을 한국어 오전/오후 형식으로 바꿉니다.
    @staticmethod
    def format_display_time(value: str) -> str:
        for time_format in ("%H:%M:%S", "%H:%M"):
            try:
                parsed_time = datetime.strptime(value, time_format)
                period = "오전" if parsed_time.hour < 12 else "오후"
                hour = parsed_time.hour % 12 or 12
                return f"{period} {hour}시 {parsed_time.minute:02d}분"
            except ValueError:
                continue

        return value
    
    # 창을 초기화하고 첫 화면에 JSON 일정을 표시합니다.
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Meet 방송 스케줄러")
        self.setMinimumSize(1050, 700)
        self.resize(1200, 820)
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f2f5f4;
            }

            QListWidget {
                background: #202b35;
                color: #f4f6f8;
                border: 0;
                padding: 8px;
                font-size: 14px;
            }

            QListWidget::item {
                padding: 13px 10px;
                border-radius: 4px;
            }

            QListWidget::item:selected {
                background: #D9ECF5;
                color: #20343B;
            }

            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccd5d1;
                border-radius: 5px;
                margin-top: 10px;
                padding: 12px;
                background: white;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }

            QPushButton {
                padding: 7px 12px;
            }

            QLineEdit, QSpinBox, QComboBox, QTimeEdit {
                padding: 5px;
            }

            QTableWidget, QTreeWidget {
                background: white;
                alternate-background-color: #f6f8f7;
                gridline-color: #e1e6e3;
            }
            """
        )

        self.build_ui()
        self.load_schedule_preview()

    # 왼쪽 메뉴와 세 개의 화면을 구성합니다.
    def build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(190)
        self.navigation.addItems(
            [
                "방송 일정",
                "방송 변경",
                "방송 설정",
            ]
        )
        root_layout.addWidget(self.navigation)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 16, 22, 14)

        header_layout = QHBoxLayout()
        self.page_title = QLabel("방송 일정")
        self.page_title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
        )
        header_layout.addWidget(self.page_title)
        header_layout.addStretch()

        self.save_button = QPushButton("설정 저장")
        self.reload_button = QPushButton("새로 고침")
        self.save_button.setStyleSheet(
            "background-color: #39715c; color: white; font-weight: bold;"
        )

        header_layout.addWidget(self.save_button)
        header_layout.addWidget(self.reload_button)
        content_layout.addLayout(header_layout)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.build_schedule_overview_page())
        self.pages.addWidget(self.build_schedule_editor_page())
        self.pages.addWidget(self.build_settings_page())
        content_layout.addWidget(self.pages, 1)

        root_layout.addWidget(content, 1)

        # 선택한 메뉴에 따라 표시 페이지와 상단 제목을 바꿉니다.
        self.navigation.currentRowChanged.connect(
            self.pages.setCurrentIndex
        )
        self.navigation.currentRowChanged.connect(
            self.update_page_title
        )
        self.navigation.setCurrentRow(0)

        # 새로고침만 실제로 연결하며, 저장 버튼은 UI 시안으로 둡니다.
        self.reload_button.clicked.connect(self.load_schedule_preview)
        self.statusBar().showMessage("UI 시안")

    # 첫 번째 화면의 요일별 일정 트리를 만듭니다.
    def build_schedule_overview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self.overview_tree = QTreeWidget()
        self.overview_tree.setColumnCount(3)
        self.overview_tree.setHeaderLabels(
            ["방송 이름 / 요일", "방송 시각", "영상 이름"]
        )
        self.overview_tree.setAlternatingRowColors(True)
        self.overview_tree.setRootIsDecorated(True)
        self.overview_tree.setIndentation(18)
        self.overview_tree.setUniformRowHeights(True)
        self.overview_tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.overview_tree.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.overview_tree.header().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )

        layout.addWidget(self.overview_tree, 1)
        return page

    # JSON을 읽고 첫 번째 화면의 일정을 갱신합니다.
    def load_schedule_preview(self) -> None:
        self.overview_tree.clear()

        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
                config = json.load(config_file)

            if not isinstance(config, dict):
                raise ValueError("JSON 최상위 데이터가 객체가 아닙니다.")

            schedule = config.get("schedule")
            videos = config.get("videos")

            if not isinstance(schedule, dict):
                raise ValueError("'schedule' 항목이 없거나 객체가 아닙니다.")

            if not isinstance(videos, dict):
                raise ValueError("'videos' 항목이 없거나 객체가 아닙니다.")

            self.populate_schedule_tree(schedule, videos)
            self.statusBar().showMessage(
                f"일정을 불러왔습니다: {CONFIG_PATH}",
                6000,
            )

        except (OSError, json.JSONDecodeError, ValueError) as error:
            message = f"schedule.json을 불러오지 못했습니다.\n{error}"
            self.overview_tree.addTopLevelItem(
                QTreeWidgetItem([message, "", ""])
            )
            self.statusBar().showMessage("일정 불러오기 실패", 6000)
            QMessageBox.warning(self, "일정 불러오기 실패", message)

    # 요일을 상위 항목으로 만들고 각 방송을 그 아래 표시합니다.
    def populate_schedule_tree(
        self,
        schedule: dict[str, Any],
        videos: dict[str, Any],
    ) -> None:
        for day_key, day_label in WEEKDAYS:
            day_item = QTreeWidgetItem([day_label, "", ""])
            day_font = day_item.font(0)
            day_font.setBold(True)

            for column in range(3):
                day_item.setFont(column, day_font)
                day_item.setBackground(column, QColor("#D9ECF5"))
                
            self.overview_tree.addTopLevelItem(day_item)

            entries = schedule.get(day_key, [])
            if not isinstance(entries, list):
                day_item.addChild(
                    QTreeWidgetItem(
                        ["일정 데이터 형식을 확인하세요.", "", ""]
                    )
                )
                day_item.setExpanded(True)
                continue

            # 일정 목록을 시간순으로 표시합니다.
            sorted_entries = sorted(
                entries,
                key=lambda entry: (
                    str(entry.get("time", ""))
                    if isinstance(entry, dict)
                    else ""
                ),
            )

            if not sorted_entries:
                day_item.addChild(
                    QTreeWidgetItem(
                        ["등록된 방송 일정이 없습니다.", "", ""]
                    )
                )
                day_item.setExpanded(True)
                continue

            for entry in sorted_entries:
                if not isinstance(entry, dict):
                    day_item.addChild(
                        QTreeWidgetItem(
                            ["일정 데이터 형식을 확인하세요.", "", ""]
                     
                        )
                    )
                    continue

                broadcast_name = (
                    str(entry.get("broadcast_name", "")).strip()
                    or "방송 이름 미입력"
                )
                raw_time = str(entry.get("time", "-"))
                broadcast_time = self.format_display_time(raw_time)
                video_id = str(entry.get("video", ""))
                video_path = videos.get(video_id)

                # 영상 번호에 연결된 경로에서 파일명을 표시합니다.
                if video_path:
                    video_name = Path(str(video_path)).name
                elif video_id:
                    video_name = f"영상 {video_id} 경로 미등록"
                else:
                    video_name = "영상 미선택"

                day_item.addChild(
                    QTreeWidgetItem(
                        [broadcast_name, broadcast_time, video_name]
                    )
                )

            day_item.setExpanded(True)

    # 두 번째 화면의 요일별 일정 편집 UI를 만듭니다.
    def build_schedule_editor_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)

        description = QLabel(
            "체크박스는 삭제할 일정을 표시하기 위한 UI 시안입니다."
        )
        description.setStyleSheet("color: #52615b;")
        page_layout.addWidget(description)

        schedule_scroll = QScrollArea()
        schedule_scroll.setWidgetResizable(True)
        schedule_scroll.setFrameShape(QFrame.Shape.NoFrame)

        schedule_content = QWidget()
        schedule_layout = QVBoxLayout(schedule_content)
        schedule_layout.setContentsMargins(2, 4, 2, 4)

        for _, weekday_label in WEEKDAYS:
            schedule_layout.addWidget(
                self.build_weekday_editor_group(weekday_label)
            )

        schedule_layout.addStretch()
        schedule_scroll.setWidget(schedule_content)
        page_layout.addWidget(schedule_scroll, 1)

        return page

    # 요일별 입력 행과 삭제 선택 체크박스를 배치합니다.
    def build_weekday_editor_group(self, weekday: str) -> QGroupBox:
        group = QGroupBox(weekday)
        layout = QVBoxLayout(group)

        table = QTableWidget(1, 4)
        table.setHorizontalHeaderLabels(
            ["삭제 선택", "방송 이름", "방송 시각", "동영상"]
        )
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        table.verticalHeader().setVisible(False)
        table.setMinimumHeight(82)
        table.setMaximumHeight(100)
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )

        # 체크박스는 삭제 대상을 표시하기 위한 UI로만 배치합니다.
        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(
            checkbox_item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
        )
        checkbox_item.setCheckState(Qt.CheckState.Unchecked)
        table.setItem(0, 0, checkbox_item)

        name_input = QLineEdit()
        name_input.setPlaceholderText("방송 이름")
        table.setCellWidget(0, 1, name_input)

        time_input = QTimeEdit()
        time_input.setDisplayFormat("HH:mm:ss")
        time_input.setTime(QTime(0, 0, 0))
        table.setCellWidget(0, 2, time_input)

        video_input = QComboBox()
        video_input.addItem("동영상 선택")
        for video_number in range(1, 11):
            video_input.addItem(f"영상 {video_number}")
        table.setCellWidget(0, 3, video_input)

        layout.addWidget(table)

        # 추가·삭제 버튼은 아직 동작을 연결하지 않습니다.
        button_layout = QHBoxLayout()
        button_layout.addWidget(QPushButton("일정 추가"))
        button_layout.addWidget(QPushButton("체크한 일정 삭제"))
        button_layout.addStretch()
        layout.addLayout(button_layout)

        return group

    # 세 번째 화면의 방송 설정 입력 UI를 만듭니다.
    def build_settings_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)

        settings_content = QWidget()
        settings_layout = QVBoxLayout(settings_content)
        settings_layout.setContentsMargins(2, 4, 2, 4)

        mode_group = QGroupBox("실행 모드")
        mode_form = QFormLayout(mode_group)

        mode_input = QComboBox()
        mode_input.addItems(["테스트 모드", "실제 운영 모드"])
        mode_form.addRow("모드", mode_input)

        meeting_group = QGroupBox("회의 및 대화 시간")
        meeting_form = QFormLayout(meeting_group)

        meeting_url = QLineEdit()
        meeting_url.setPlaceholderText("https://meet.google.com/...")
        meeting_form.addRow("운영 Meet 주소", meeting_url)

        before_layout, _ = self.make_minute_input()
        meeting_form.addRow("방송 시작 전 대화", before_layout)

        after_layout, _ = self.make_minute_input()
        meeting_form.addRow("방송 종료 후 대화", after_layout)

        videos_group = QGroupBox("미리 등록한 동영상")
        videos_layout = QVBoxLayout(videos_group)

        for video_number in range(1, 11):
            row_layout = QHBoxLayout()
            row_layout.addWidget(QLabel(f"영상 {video_number}"))

            path_input = QLineEdit()
            path_input.setPlaceholderText("동영상 파일 경로")
            row_layout.addWidget(path_input, 1)

            # 찾아보기 버튼은 UI 배치만 하고 동작은 연결하지 않습니다.
            row_layout.addWidget(QPushButton("찾아보기"))
            videos_layout.addLayout(row_layout)

        settings_layout.addWidget(mode_group)
        settings_layout.addWidget(meeting_group)
        settings_layout.addWidget(videos_group)
        settings_layout.addStretch()

        settings_scroll.setWidget(settings_content)
        page_layout.addWidget(settings_scroll, 1)

        return page

    # 분 단위 대기 시간 입력 UI를 만듭니다.
    @staticmethod
    def make_minute_input() -> tuple[QWidget, QSpinBox]:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        minute_input = QSpinBox()
        minute_input.setRange(0, 1440)
        minute_input.setValue(10)

        layout.addWidget(minute_input)
        layout.addWidget(QLabel("분"))
        layout.addStretch()

        return container, minute_input

    # 선택한 왼쪽 메뉴에 맞춰 상단 제목을 바꿉니다.
    def update_page_title(self, page_index: int) -> None:
        item = self.navigation.item(page_index)
        if item is not None:
            self.page_title.setText(item.text())
            self.save_button.setVisible(page_index in (1, 2))


# QApplication을 만들고 메인 창을 실행합니다.
def main() -> int:
    app = QApplication(sys.argv)
    window = MeetSchedulerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())