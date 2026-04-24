from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QSlider,
    QVBoxLayout,
    QWidget,
    QSplitter,
)
from PySide6.QtCore import Qt
from ui.image_panel import ImagePanel
from ui.class_panel import ClassPanel
from ui.segmentation_panel import SegmentationPanel
from ui.annotation_panel import AnnotationPanel
from ui.log_panel import LogPanel
from ui.bottom_bar import BottomBar

from managers.frame_manager import FrameManager
from managers.class_manager import ClassManager
from managers.annotation_manager import AnnotationManager
from label.auto_segmentation import AutoSegmentationEngine

from controllers.frame_controller import FrameController
from controllers.class_controller import ClassController
from controllers.annotation_controller import AnnotationController
from controllers.io_controller import IOController


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Segmentation UI")
        self.resize(1600, 900)

        self.frame_manager = FrameManager()
        self.class_manager = ClassManager()
        self.annotation_manager = AnnotationManager()
        self.auto_seg_engine = AutoSegmentationEngine()

        self.current_file = "No file loaded."
        self.current_tool_mode = None

        self._build_ui()
        self._apply_style()

        self.frame_controller = FrameController(self)
        self.class_controller = ClassController(self)
        self.annotation_controller = AnnotationController(self)
        self.io_controller = IOController(self)

        self.frame_controller.connect_signals()
        self.class_controller.connect_signals()
        self.annotation_controller.connect_signals()
        self.io_controller.connect_signals()

        self.refresh_all_views()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(6)

        self.image_panel = ImagePanel()
        self.class_panel = ClassPanel()
        self.segmentation_panel = SegmentationPanel()
        self.annotation_panel = AnnotationPanel()
        self.log_panel = LogPanel()
        self.bottom_bar = BottomBar()

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        right_layout.addWidget(self.class_panel)
        right_layout.addWidget(self.segmentation_panel)
        right_layout.addWidget(self.annotation_panel)
        right_layout.addWidget(self.log_panel)
        right_layout.addStretch()

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.image_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([1200, 320])

        main_layout.addWidget(splitter, stretch=1)

        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setRange(0, 0)
        main_layout.addWidget(self.timeline_slider)

        main_layout.addWidget(self.bottom_bar)

    def _apply_style(self):
        self.setStyleSheet(
            """
            QWidget {
                background: #d8d6d2;
                color: #4f4f4f;
                font-size: 13px;
            }
            QGroupBox {
                border: 1px solid #8b8b8b;
                margin-top: 10px;
                padding-top: 8px;
                background: #d8d6d2;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel#frameValueLabel {
                border: 1px solid #8f8f8f;
                background: #eceae6;
                padding: 4px 10px;
                min-width: 42px;
            }
            QPushButton {
                background: #5f5f60;
                color: #e7e7e7;
                border: 1px solid #4f4f50;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background: #6d6d6e;
            }
            QPushButton:pressed {
                background: #4f4f50;
            }
            QLineEdit, QSpinBox, QListWidget, QTableWidget {
                background: #eceae6;
                border: 1px solid #8f8f8f;
                selection-background-color: #8aa9c2;
            }
            QHeaderView::section {
                background: #c9c7c3;
                border: 1px solid #8f8f8f;
                padding: 4px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #8f8f8f;
                height: 8px;
                background: #eceae6;
            }
            QSlider::handle:horizontal {
                background: #5f5f60;
                border: 1px solid #4f4f50;
                width: 16px;
                margin: -5px 0;
            }
            """
        )

    def add_log(self, text):
        self.log_panel.add_log(text)

    def update_status_only(self):
        current_frame = self.frame_manager.get_current_index()
        total_frames = self.frame_manager.get_total_frames()

        self.bottom_bar.frame_status.set_frame_info(current_frame, total_frames)

        self.timeline_slider.blockSignals(True)
        max_frame = max(0, total_frames - 1)
        self.timeline_slider.setRange(0, max_frame)
        self.timeline_slider.setValue(current_frame)
        self.timeline_slider.blockSignals(False)

        self.bottom_bar.class_status_label.setText(
            f"Selected Class: {self.class_manager.get_selected_class_display()}"
        )
        self.bottom_bar.file_status_label.setText(f"File: {self.current_file}")

    def refresh_all_views(self):
        self.update_status_only()
        self.class_controller.refresh_class_table()
        self.class_controller.refresh_object_list()
        self.frame_controller.refresh_image_view()

    def simple_info(self, text):
        QMessageBox.information(self, "Info", text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            class_table = self.class_panel.class_table
            if class_table.hasFocus() or class_table.viewport().hasFocus():
                row = self.class_controller.get_selected_class_row()
                if row is not None:
                    self.class_controller.remove_selected_class()
                    event.accept()
                    return

            self.annotation_controller.delete_selected_box()
            event.accept()
            return

        super().keyPressEvent(event)
