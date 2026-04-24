from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
)


class AutoSegDialog(QDialog):
    acceptedClicked = Signal()
    cancelledClicked = Signal()
    algorithmChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto Segmentation")
        self.setModal(False)
        self.resize(360, 150)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Algorithm"))

        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(["SAM2", "SAM3", "Custom"])
        layout.addWidget(self.algorithm_combo)

        self.guide_label = QLabel(
            "Click points on the image to build the segmentation preview.\n"
            "Accept to save as polygon, Cancel to discard."
        )
        self.guide_label.setWordWrap(True)
        layout.addWidget(self.guide_label)

        button_row = QHBoxLayout()
        self.accept_btn = QPushButton("Accept")
        self.cancel_btn = QPushButton("Cancel")
        button_row.addStretch()
        button_row.addWidget(self.accept_btn)
        button_row.addWidget(self.cancel_btn)
        layout.addLayout(button_row)

        self.accept_btn.clicked.connect(self.acceptedClicked.emit)
        self.cancel_btn.clicked.connect(self.cancelledClicked.emit)
        self.algorithm_combo.currentTextChanged.connect(self.algorithmChanged.emit)

    def get_selected_algorithm(self):
        return self.algorithm_combo.currentText().strip()

    def closeEvent(self, event):
        event.ignore()
