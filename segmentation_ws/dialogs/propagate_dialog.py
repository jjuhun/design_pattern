from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSpinBox,
)


class PropagateDialog(QDialog):
    def __init__(self, current_frame, max_frame, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Propagate Range")
        self.setModal(True)
        self.resize(300, 140)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Current Frame: {current_frame}"))

        start_row = QHBoxLayout()
        start_row.addWidget(QLabel("Start Frame"))
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, max_frame)
        self.start_spin.setValue(current_frame)
        start_row.addWidget(self.start_spin)
        layout.addLayout(start_row)

        end_row = QHBoxLayout()
        end_row.addWidget(QLabel("End Frame"))
        self.end_spin = QSpinBox()
        self.end_spin.setRange(0, max_frame)
        self.end_spin.setValue(current_frame)
        end_row.addWidget(self.end_spin)
        layout.addLayout(end_row)

        button_row = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        button_row.addStretch()
        button_row.addWidget(self.ok_btn)
        button_row.addWidget(self.cancel_btn)
        layout.addLayout(button_row)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def get_range(self):
        return self.start_spin.value(), self.end_spin.value()