from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from widgets.frame_status_widget import FrameStatusWidget


class BottomBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        status_box = QVBoxLayout()
        self.frame_status = FrameStatusWidget()
        self.class_status_label = QLabel("Selected Class: None")
        status_box.addWidget(self.frame_status)
        status_box.addWidget(self.class_status_label)
        layout.addLayout(status_box, stretch=4)

        nav_row = QHBoxLayout()
        self.back_10_btn = QPushButton("<<")
        self.back_1_btn = QPushButton("<")
        self.next_1_btn = QPushButton(">")
        self.next_10_btn = QPushButton(">>")

        for btn in [self.back_10_btn, self.back_1_btn, self.next_1_btn, self.next_10_btn]:
            btn.setMinimumHeight(42)
            nav_row.addWidget(btn)

        nav_container = QWidget()
        nav_container.setLayout(nav_row)
        layout.addWidget(nav_container, stretch=3)

        file_status_box = QVBoxLayout()
        self.file_status_label = QLabel("File: No file loaded.")
        self.file_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        file_status_box.addStretch()
        file_status_box.addWidget(self.file_status_label)
        file_status_box.addStretch()
        layout.addLayout(file_status_box, stretch=3)

        action_grid = QGridLayout()
        self.import_btn = QPushButton("Import")
        self.export_btn = QPushButton("Export")
        self.prev_file_btn = QPushButton("Previous")
        self.next_file_btn = QPushButton("Next")

        for btn in [self.import_btn, self.export_btn, self.prev_file_btn, self.next_file_btn]:
            btn.setMinimumHeight(32)

        action_grid.addWidget(self.import_btn, 0, 0)
        action_grid.addWidget(self.export_btn, 0, 1)
        action_grid.addWidget(self.prev_file_btn, 1, 0)
        action_grid.addWidget(self.next_file_btn, 1, 1)
        layout.addLayout(action_grid, stretch=2)
