from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QSizePolicy
from widgets.image_canvas import ImageCanvas


class ImagePanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Image View", parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 18, 8, 8)

        self.image_canvas = ImageCanvas()
        self.image_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addWidget(self.image_canvas)