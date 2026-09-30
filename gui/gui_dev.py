import json
import os
import sys
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PyQt6.QtCore import QTime, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
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


# GUI 위치를 기준으로 프로젝트 루트의 schedule.json을 찾습니다.
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

DEFAULT_VIDEO_IDS = tuple(str(number) for number in range(1, 11))


# 설정 파일을 읽고 GUI가 사용하는 기본 구조를 확인합니다.
def read_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    if not isinstance(config, dict):
        raise ValueError("JSON 최상위 데이터는 객체여야 합니다.")

    for key in ("timing", "videos", "schedule"):
        if not isinstance(config.get(key), dict):
            raise ValueError(f"'{key}' 항목이 없거나 객체가 아닙니다.")

    return config


# 설정 파일 저장 중 문제가 생겨도 기존 파일을 보존합니다.
def write_config_atomically(path: Path, config: dict[str, Any]) -> None:
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(
                config,
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)

        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


# 시간 입력 문자열을 검증하고 HH:MM:SS로 통일합니다.
def normalize_time(value: str) -> str:
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            parsed_time = datetime.strptime(value, time_format)
            return parsed_time.strftime("%H:%M:%S")
        except ValueError:
            continue

    raise ValueError(
        f"시간 형식이 올바르지 않습니다: {value} (HH:MM 또는 HH:MM:SS)"
    )


# 주요 GUI 화면과 설정 편집 동작을 관리합니다.
class MeetSchedulerWindow(QMainWindow):
    # 저장된 24시간 표기 시간을 화면용 오전·오후 표기로 바꿉니다.
    @staticmethod
    def format_display_time(value: str) -> str:
        try:
            normalized = normalize_time(value)
            parsed_time = datetime.strptime(normalized, "%H:%M:%S")
        except ValueError:
            return value

        period = "오전" if parsed_time.hour < 12 else "오후"
        hour = parsed_time.hour % 12 or 12
        return f"{period} {hour}시 {parsed_time.minute:02d}분"

    # 설정을 읽고 화면 컨트롤을 생성합니다.
    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        super().__init__()

        self.config_path = config_path
        self.config = read_config(config_path)

        self.schedule_tables: dict[str, QTableWidget] = {}
        self.video_path_edits: dict[str, QLineEdit] = {}
        self.video_combos: list[QComboBox] = []

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
        self.populate_ui(self.config)

    # 왼쪽 메뉴와 세 개의 화면을 구성하고 버튼을 연결합니다.
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

        self.save_button = QPushButton("방송 저장")
        self.save_button.setStyleSheet(
            "background-color: #D9ECF5; color: black; font-weight: bold;"
        )
        self.reload_button = QPushButton("새로 고침")
        self.reload_button.setStyleSheet(
            "background-color: #D9ECF5; color: black; font-weight: bold;"
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

        # 왼쪽 메뉴 선택과 화면 전환을 연결합니다.
        self.navigation.currentRowChanged.connect(
            self.pages.setCurrentIndex
        )
        self.navigation.currentRowChanged.connect(
            self.update_page_title
        )
        self.navigation.setCurrentRow(0)

        # 새로고침과 저장 버튼에 각각 실제 처리를 연결합니다.
        self.reload_button.clicked.connect(self.reload_config)
        self.save_button.clicked.connect(self.save_config)
        self.statusBar().showMessage(str(self.config_path))

    # 첫 번째 메뉴의 읽기 전용 주간 일정 화면을 만듭니다.
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

        header = self.overview_tree.header()
        header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.Interactive
        )
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.overview_tree.setColumnWidth(1, 150)

        layout.addWidget(self.overview_tree, 1)
        return page

    # 두 번째 메뉴의 요일별 일정 편집 화면을 만듭니다.
    def build_schedule_editor_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)

        description = QLabel(
            "일정을 추가하거나 수정하고, 삭제할 항목은 체크하세요."
        )
        description.setStyleSheet("color: #52615b;")
        page_layout.addWidget(description)

        schedule_scroll = QScrollArea()
        schedule_scroll.setWidgetResizable(True)
        schedule_scroll.setFrameShape(QFrame.Shape.NoFrame)

        schedule_content = QWidget()
        schedule_layout = QVBoxLayout(schedule_content)
        schedule_layout.setContentsMargins(2, 4, 2, 4)

        for day_key, day_label in WEEKDAYS:
            schedule_layout.addWidget(
                self.build_weekday_editor_group(day_key, day_label)
            )

        schedule_layout.addStretch()
        schedule_scroll.setWidget(schedule_content)
        page_layout.addWidget(schedule_scroll, 1)
        return page

    # 요일별 일정 표와 추가·삭제 버튼을 구성합니다.
    def build_weekday_editor_group(
        self,
        day_key: str,
        day_label: str,
    ) -> QGroupBox:
        group = QGroupBox(day_label)
        layout = QVBoxLayout(group)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(
            ["삭제 선택", "방송 이름", "방송 시각", "동영상"]
        )
        table.horizontalHeader().setStyleSheet(
            """
            QHeaderView::section {
                background-color: #D9ECF5;
                color: #20343B;
                padding: 5px;
                border: 1px solid #ccd5d1;
            }
            """
        )        
        for column in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(column)
            if header_item is not None:
                header_item.setBackground(QColor("#D9ECF5"))

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
        table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )        
        table.setMinimumHeight(82)
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection
        )

        self.schedule_tables[day_key] = table
        layout.addWidget(table)

        button_layout = QHBoxLayout()
        add_button = QPushButton("일정 추가")
        delete_button = QPushButton("체크한 일정 삭제")
        button_layout.addWidget(add_button)
        button_layout.addWidget(delete_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # 각 버튼은 현재 요일 표에만 적용됩니다.
        add_button.clicked.connect(
            lambda checked=False, key=day_key: self.add_schedule_row(key)
        )
        delete_button.clicked.connect(
            lambda checked=False, key=day_key: self.delete_checked_rows(key)
        )

        return group

    # 일정 행을 모두 표시하도록 표 높이를 행 수에 맞춥니다.
    @staticmethod
    def resize_schedule_table(table: QTableWidget) -> None:
        table.resizeRowsToContents()
        rows_height = sum(
            table.rowHeight(row) for row in range(table.rowCount())
        )
        content_height = (
            table.horizontalHeader().height()
            + rows_height
            + table.frameWidth() * 2
        )
        table.setFixedHeight(max(82, content_height))    

    # 세 번째 메뉴의 운영 설정 화면을 만듭니다.
    def build_settings_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)

        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setFrameShape(QFrame.Shape.NoFrame)

        settings_content = QWidget()
        settings_layout = QVBoxLayout(settings_content)
        settings_layout.setContentsMargins(2, 4, 2, 4)

        meeting_group = QGroupBox("회의 및 대화 시간")
        meeting_form = QFormLayout(meeting_group)

        self.meeting_url_edit = QLineEdit()
        self.meeting_url_edit.setPlaceholderText(
            "https://meet.google.com/..."
        )
        meeting_form.addRow("운영 Meet 주소", self.meeting_url_edit)

        self.before_minutes_spin = self.make_minute_input()
        meeting_form.addRow(
            "방송 시작 전 대화",
            self.wrap_minute_input(self.before_minutes_spin),
        )

        self.after_minutes_spin = self.make_minute_input()
        meeting_form.addRow(
            "방송 종료 후 대화",
            self.wrap_minute_input(self.after_minutes_spin),
        )

        videos_group = QGroupBox("미리 등록한 동영상")
        videos_layout = QVBoxLayout(videos_group)

        for video_id in self.get_video_ids():
            row_layout = QHBoxLayout()
            row_layout.addWidget(QLabel(f"영상 {video_id}"))

            path_edit = QLineEdit()
            path_edit.setPlaceholderText("동영상 파일 경로")
            self.video_path_edits[video_id] = path_edit
            row_layout.addWidget(path_edit, 1)

            browse_button = QPushButton("찾아보기")
            browse_button.clicked.connect(
                lambda checked=False, key=video_id: self.browse_video(key)
            )
            row_layout.addWidget(browse_button)
            videos_layout.addLayout(row_layout)

            # 경로를 바꾸면 일정 편집 화면의 영상 선택 항목도 갱신합니다.
            path_edit.textChanged.connect(self.refresh_video_combos)

        settings_layout.addWidget(meeting_group)
        settings_layout.addWidget(videos_group)
        settings_layout.addStretch()

        settings_scroll.setWidget(settings_content)
        page_layout.addWidget(settings_scroll, 1)
        return page

    # JSON에 있는 영상 키와 기본 10개 키를 합쳐 UI 목록을 만듭니다.
    def get_video_ids(self) -> list[str]:
        configured_ids = {
            str(video_id) for video_id in self.config.get("videos", {})
        }
        video_ids = configured_ids.union(DEFAULT_VIDEO_IDS)

        return sorted(
            video_ids,
            key=lambda value: (
                not value.isdigit(),
                int(value) if value.isdigit() else value,
            ),
        )

    # 영상 번호와 파일명을 선택 목록에 표시할 문구로 만듭니다.
    def video_label(self, video_id: str) -> str:
        path_edit = self.video_path_edits.get(video_id)
        path_text = path_edit.text().strip() if path_edit else ""
        if not path_text:
            path_text = str(self.config.get("videos", {}).get(video_id, ""))

        file_name = Path(path_text).name if path_text else "경로 미등록"
        return f"영상 {video_id} - {file_name}"

    # 일정 편집 화면의 영상 선택 목록을 현재 경로에 맞춰 갱신합니다.
    def refresh_video_combos(self) -> None:
        for combo in self.video_combos:
            selected_id = combo.currentData()
            combo.blockSignals(True)
            combo.clear()

            for video_id in self.get_video_ids():
                combo.addItem(self.video_label(video_id), video_id)

            selected_index = combo.findData(selected_id)
            if selected_index >= 0:
                combo.setCurrentIndex(selected_index)

            combo.blockSignals(False)

    # 새 일정 입력 행을 지정한 요일 표에 추가합니다.
    def add_schedule_row(
        self,
        day_key: str,
        entry: dict[str, Any] | None = None,
    ) -> None:
        entry = entry or {}
        table = self.schedule_tables[day_key]
        row = table.rowCount()
        table.insertRow(row)

        checkbox_item = QTableWidgetItem()
        checkbox_item.setFlags(
            checkbox_item.flags()
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
        )
        checkbox_item.setCheckState(Qt.CheckState.Unchecked)
        checkbox_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        table.setItem(row, 0, checkbox_item)

        name_edit = QLineEdit(str(entry.get("broadcast_name", "")))
        name_edit.setPlaceholderText("방송 이름")
        table.setCellWidget(row, 1, name_edit)

        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH:mm:ss")
        raw_time = str(entry.get("time", "12:00:00"))
        time_edit.setTime(self.parse_qtime(raw_time))
        table.setCellWidget(row, 2, time_edit)

        video_combo = QComboBox()
        for video_id in self.get_video_ids():
            video_combo.addItem(self.video_label(video_id), video_id)

        selected_video = str(entry.get("video", ""))
        selected_index = video_combo.findData(selected_video)
        if selected_index >= 0:
            video_combo.setCurrentIndex(selected_index)
        elif selected_video:
            video_combo.addItem(
                f"등록되지 않은 영상 {selected_video}",
                selected_video,
            )
            video_combo.setCurrentIndex(video_combo.count() - 1)
        elif video_combo.count():
            video_combo.setCurrentIndex(0)

        self.video_combos.append(video_combo)
        table.setCellWidget(row, 3, video_combo)
        self.resize_schedule_table(table)

    # HH:MM과 HH:MM:SS 둘 다 편집기 시간으로 변환합니다.
    @staticmethod
    def parse_qtime(value: str) -> QTime:
        parsed_time = QTime.fromString(value, "HH:mm:ss")
        if not parsed_time.isValid():
            parsed_time = QTime.fromString(value, "HH:mm")

        if not parsed_time.isValid():
            raise ValueError(f"시간 형식이 올바르지 않습니다: {value}")

        return parsed_time

    # 체크된 일정 행을 현재 요일 표에서 제거합니다.
    def delete_checked_rows(self, day_key: str) -> None:
        table = self.schedule_tables[day_key]
        rows_to_delete = [
            row
            for row in range(table.rowCount())
            if table.item(row, 0) is not None
            and table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]

        for row in reversed(rows_to_delete):
            combo = table.cellWidget(row, 3)
            if isinstance(combo, QComboBox) and combo in self.video_combos:
                self.video_combos.remove(combo)
            table.removeRow(row)
            
        self.resize_schedule_table(table)

    # 운영자가 선택한 동영상 파일 경로를 입력란에 반영합니다.
    def browse_video(self, video_id: str) -> None:
        path_edit = self.video_path_edits[video_id]
        current_path = path_edit.text().strip()
        start_directory = (
            str(Path(current_path).parent)
            if current_path and Path(current_path).parent.exists()
            else str(Path.home())
        )

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"영상 {video_id} 파일 선택",
            start_directory,
            "동영상 파일 (*.mp4 *.mov *.webm *.mkv);;모든 파일 (*.*)",
        )

        if file_path:
            path_edit.setText(file_path)

    # 분 단위 입력 컨트롤을 만듭니다.
    @staticmethod
    def make_minute_input() -> QSpinBox:
        spin_box = QSpinBox()
        spin_box.setRange(0, 1440)
        return spin_box

    # 분 입력과 단위를 한 행에 배치합니다.
    @staticmethod
    def wrap_minute_input(spin_box: QSpinBox) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(spin_box)
        layout.addWidget(QLabel("분"))
        layout.addStretch()
        return container

    # JSON을 모든 화면의 입력 컨트롤에 표시합니다.
    def populate_ui(self, config: dict[str, Any]) -> None:
        self.config = config

        timing = config.get("timing", {})
        real_timing = timing.get("real", {})
        self.meeting_url_edit.setText(
            str(config.get("meeting_url_real", ""))
        )
        self.before_minutes_spin.setValue(
            int(real_timing.get("before_video_minutes", 0))
        )
        self.after_minutes_spin.setValue(
            int(real_timing.get("after_video_minutes", 0))
        )

        videos = config.get("videos", {})
        for video_id, path_edit in self.video_path_edits.items():
            path_edit.setText(str(videos.get(video_id, "")))

        self.video_combos.clear()
        schedule = config.get("schedule", {})

        for day_key, _ in WEEKDAYS:
            table = self.schedule_tables[day_key]
            table.setRowCount(0)

            for entry in schedule.get(day_key, []):
                if isinstance(entry, dict):
                    self.add_schedule_row(day_key, entry)

        self.refresh_video_combos()
        self.populate_schedule_overview(schedule, videos)

    # 첫 번째 메뉴의 읽기 전용 요약을 현재 설정에서 다시 그립니다.
    def populate_schedule_overview(
        self,
        schedule: dict[str, Any],
        videos: dict[str, Any],
    ) -> None:
        self.overview_tree.clear()

        for day_key, day_label in WEEKDAYS:
            day_item = QTreeWidgetItem([day_label, "", ""])
            day_font = day_item.font(0)
            day_font.setBold(True)

            for column in range(3):
                day_item.setFont(column, day_font)
                day_item.setBackground(column, QColor("#D9ECF5"))

            self.overview_tree.addTopLevelItem(day_item)
            entries = schedule.get(day_key, [])

            if not isinstance(entries, list) or not entries:
                day_item.addChild(
                    QTreeWidgetItem(["등록된 방송 일정이 없습니다.", "", ""])
                )
                day_item.setExpanded(True)
                continue

            valid_entries = [
                entry for entry in entries if isinstance(entry, dict)
            ]
            valid_entries.sort(key=lambda entry: str(entry.get("time", "")))

            for entry in valid_entries:
                broadcast_name = (
                    str(entry.get("broadcast_name", "")).strip()
                    or "방송 이름 미입력"
                )
                raw_time = str(entry.get("time", "-"))

                try:
                    display_time = self.format_display_time(raw_time)
                except ValueError:
                    display_time = raw_time

                video_id = str(entry.get("video", ""))
                video_path = videos.get(video_id)
                video_name = (
                    Path(str(video_path)).name
                    if video_path
                    else f"영상 {video_id} 경로 미등록"
                    if video_id
                    else "영상 미선택"
                )

                day_item.addChild(
                    QTreeWidgetItem(
                        [broadcast_name, display_time, video_name]
                    )
                )

            day_item.setExpanded(True)

    # 입력 컨트롤을 검증하고 저장할 JSON 복사본을 구성합니다.
    def collect_config(self) -> dict[str, Any]:
        candidate = deepcopy(self.config)

        meeting_url = self.meeting_url_edit.text().strip()
        parsed_url = urlparse(meeting_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "meet.google.com"
        ):
            raise ValueError(
                "운영 Meet 주소는 https://meet.google.com/... 형식이어야 합니다."
            )

        candidate["meeting_url_real"] = meeting_url
        candidate.setdefault("timing", {}).setdefault("real", {})
        candidate["timing"]["real"]["before_video_minutes"] = (
            self.before_minutes_spin.value()
        )
        candidate["timing"]["real"]["after_video_minutes"] = (
            self.after_minutes_spin.value()
        )

        # 화면의 영상 경로를 기존 영상 설정에 반영합니다.
        candidate.setdefault("videos", {})
        for video_id, path_edit in self.video_path_edits.items():
            path_text = path_edit.text().strip()
            if not path_text:
                raise ValueError(f"영상 {video_id}의 경로를 입력하세요.")
            if not Path(path_text).is_file():
                raise FileNotFoundError(
                    f"영상 {video_id} 파일을 찾을 수 없습니다:\n{path_text}"
                )
            candidate["videos"][video_id] = path_text

        # 요일별 표에서 일정을 읽고 필수 입력과 중복 시각을 검사합니다.
        candidate.setdefault("schedule", {})
        for day_key, day_label in WEEKDAYS:
            table = self.schedule_tables[day_key]
            entries = []
            seen_times: set[str] = set()

            for row in range(table.rowCount()):
                name_edit = table.cellWidget(row, 1)
                time_edit = table.cellWidget(row, 2)
                video_combo = table.cellWidget(row, 3)

                if not isinstance(name_edit, QLineEdit):
                    raise ValueError(f"{day_label} {row + 1}번째 방송 이름이 없습니다.")
                if not isinstance(time_edit, QTimeEdit):
                    raise ValueError(f"{day_label} {row + 1}번째 시간이 없습니다.")
                if not isinstance(video_combo, QComboBox):
                    raise ValueError(f"{day_label} {row + 1}번째 영상이 없습니다.")

                broadcast_name = name_edit.text().strip()
                if not broadcast_name:
                    raise ValueError(
                        f"{day_label} {row + 1}번째 방송 이름을 입력하세요."
                    )

                time_value = time_edit.time().toString("HH:mm:ss")
                if time_value in seen_times:
                    raise ValueError(
                        f"{day_label}에 {time_value} 일정이 중복되어 있습니다."
                    )
                seen_times.add(time_value)

                video_id = str(video_combo.currentData() or "")
                if video_id not in candidate["videos"]:
                    raise ValueError(
                        f"{day_label} 일정의 영상 번호를 확인하세요."
                    )

                entries.append(
                    {
                        "broadcast_name": broadcast_name,
                        "time": time_value,
                        "video": video_id,
                    }
                )

            entries.sort(key=lambda entry: entry["time"])
            candidate["schedule"][day_key] = entries

        return candidate

    # 검증이 모두 통과한 경우에만 JSON을 저장하고 화면을 갱신합니다.
    def save_config(self) -> None:
        if self.navigation.currentRow() in (1, 2):
            answer = QMessageBox.question(
                self,
                "방송 저장",
                "변경 사항을 저장할까요?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            candidate = self.collect_config()
            write_config_atomically(self.config_path, candidate)
            self.populate_ui(candidate)
            self.statusBar().showMessage("설정을 저장했습니다.", 6000)
            QMessageBox.information(
                self,
                "저장 완료",
                f"변경 사항을 저장했습니다.^^",
            )
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "저장할 수 없습니다", str(error))

    # 저장하지 않은 변경을 버릴지 확인한 뒤 JSON을 다시 불러옵니다.
    def reload_config(self) -> None:
        if self.navigation.currentRow() != 0:
            answer = QMessageBox.question(
                self,
                "설정 다시 불러오기",
                "화면에서 수정한 내용은 사라집니다. 내용을 다시 불러올까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            config = read_config(self.config_path)
            self.populate_ui(config)
            self.statusBar().showMessage("내용을 다시 불러왔습니다.", 6000)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            QMessageBox.critical(
                self,
                "불러오기 실패",
                str(error),
            )

    # 왼쪽 메뉴에 따라 제목과 저장 버튼 표시를 바꿉니다.
    def update_page_title(self, page_index: int) -> None:
        item = self.navigation.item(page_index)
        if item is not None:
            self.page_title.setText(item.text())

        self.save_button.setVisible(page_index in (1, 2))


# GUI를 시작하고 초기 설정 오류를 표시합니다.
def main() -> int:
    app = QApplication(sys.argv)

    try:
        window = MeetSchedulerWindow()
    except (OSError, json.JSONDecodeError, ValueError) as error:
        QMessageBox.critical(
            None,
            "시작할 수 없습니다",
            f"schedule.json을 불러오지 못했습니다.\n\n{error}",
        )
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())