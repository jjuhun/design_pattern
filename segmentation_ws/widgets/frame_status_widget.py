from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QWidget, QHBoxLayout, QSpinBox


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class FrameStatusWidget(QWidget):
    frameChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_frame = 0
        self.total_frames = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.prefix_label = QLabel("Frame:")
        self.frame_value_label = ClickableLabel("0")
        self.frame_value_label.setObjectName("frameValueLabel")
        self.frame_value_label.setCursor(Qt.PointingHandCursor)
        self.sep_label = QLabel("/")
        self.total_label = QLabel("0")

        self.frame_input = QSpinBox()
        self.frame_input.setRange(0, 0)
        self.frame_input.hide()
        self.frame_input.setButtonSymbols(QSpinBox.NoButtons)
        self.frame_input.setAlignment(Qt.AlignCenter)
        self.frame_input.setFixedWidth(70)

        layout.addWidget(self.prefix_label)
        layout.addWidget(self.frame_value_label)
        layout.addWidget(self.frame_input)
        layout.addWidget(self.sep_label)
        layout.addWidget(self.total_label)
        layout.addStretch()

        self.frame_value_label.clicked.connect(self.start_edit)
        self.frame_input.editingFinished.connect(self.finish_edit)

    def set_frame_info(self, current_frame: int, total_frames: int):
        self.total_frames = max(0, total_frames)
        max_frame = max(0, self.total_frames - 1)
        self.current_frame = max(0, min(current_frame, max_frame)) if self.total_frames else 0

        self.frame_value_label.setText(str(self.current_frame))
        self.total_label.setText(str(self.total_frames))
        self.frame_input.setRange(0, max_frame)
        self.frame_input.setValue(self.current_frame)

    def start_edit(self):
        if self.total_frames <= 0:
            return

        self.frame_value_label.hide()
        self.frame_input.show()
        self.frame_input.setFocus()
        self.frame_input.selectAll()

    def finish_edit(self):
        value = self.frame_input.value()
        self.current_frame = value
        self.frame_value_label.setText(str(value))
        self.frame_input.hide()
        self.frame_value_label.show()
        self.frameChanged.emit(value)