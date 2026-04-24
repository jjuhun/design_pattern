from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
)


class AnnotationPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Annotation", parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 18, 8, 8)
        layout.setSpacing(8)

        action_grid = QGridLayout()
        self.propagate_btn = QPushButton("Propagate")
        self.tracker_btn = QPushButton("Tracker")

        action_grid.addWidget(self.propagate_btn, 0, 0)
        action_grid.addWidget(self.tracker_btn, 0, 1)
        layout.addLayout(action_grid)
