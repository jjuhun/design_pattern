from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
)


class SegmentationPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Segmentation", parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 18, 8, 8)
        layout.setSpacing(8)

        tool_grid = QGridLayout()
        self.box_btn = QPushButton("Box")
        self.polygon_btn = QPushButton("Polygon")
        self.auto_seg_btn = QPushButton("Auto Seg")

        tool_grid.addWidget(self.box_btn, 0, 0)
        tool_grid.addWidget(self.polygon_btn, 0, 1)
        tool_grid.addWidget(self.auto_seg_btn, 1, 0, 1, 2)
        layout.addLayout(tool_grid)
