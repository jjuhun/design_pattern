import os
import json
from PySide6.QtWidgets import QFileDialog

from dialogs.import_dialog import ImportDialog


class IOController:
    def __init__(self, window):
        self.window = window

    def connect_signals(self):
        bottom_bar = self.window.bottom_bar
        annotation_panel = self.window.annotation_panel

        bottom_bar.import_btn.clicked.connect(self.import_data)
        bottom_bar.export_btn.clicked.connect(self.export_data)
        bottom_bar.prev_file_btn.clicked.connect(
            lambda: self.window.simple_info("Previous dataset/file action is not connected yet.")
        )
        bottom_bar.next_file_btn.clicked.connect(
            lambda: self.window.simple_info("Next dataset/file action is not connected yet.")
        )

        annotation_panel.tracker_btn.clicked.connect(
            lambda: self.window.add_log("Tracker is not connected yet")
        )

    def import_data(self):
        dialog = ImportDialog(self.window)
        if not dialog.exec():
            return

        image_type = dialog.get_image_source_type()
        image_path = dialog.get_image_path()
        label_path = dialog.get_label_path()

        if not image_path:
            self.window.simple_info("Image source is required.")
            return
        if not os.path.exists(image_path):
            self.window.simple_info("Selected image source does not exist.")
            return

        self.window.class_manager.clear()
        self.window.annotation_manager.clear()

        try:
            if image_type == "mp4":
                if not os.path.isfile(image_path):
                    self.window.simple_info("Please select a valid video file.")
                    return
                ext = os.path.splitext(image_path)[1].lower()
                if ext not in {".mp4", ".avi", ".mov"}:
                    self.window.simple_info("Selected file is not a supported video.")
                    return
                self.window.frame_manager.load_mp4(image_path)
                self.window.current_file = os.path.basename(image_path)
                self.window.add_log(f"MP4 imported: {image_path}")
                self.window.add_log(
                    f"Extracted {self.window.frame_manager.get_total_frames()} frames"
                )
            elif image_type == "dir":
                if not os.path.isdir(image_path):
                    self.window.simple_info("Please select a valid frame directory.")
                    return
                self.window.frame_manager.load_directory(image_path)
                self.window.current_file = image_path
                self.window.add_log(f"Frame directory imported: {image_path}")
                self.window.add_log(
                    f"Detected {self.window.frame_manager.get_total_frames()} frame images"
                )
            else:
                self.window.simple_info("Invalid image source type.")
                return
        except Exception as e:
            self.window.simple_info(f"Import failed: {e}")
            return

        if label_path:
            if not os.path.exists(label_path):
                self.window.simple_info("Selected label file does not exist.")
                return
            try:
                with open(label_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if "classes" not in data or "annotations" not in data:
                    self.window.simple_info("Invalid label file format.")
                    return

                self.window.class_manager.load_classes(data["classes"])
                valid_class_ids = {item["class_id"] for item in self.window.class_manager.get_classes()}
                self.window.annotation_manager.load_annotations(
                    annotations_dict=data["annotations"],
                    total_frames=self.window.frame_manager.get_total_frames(),
                    valid_class_ids=valid_class_ids,
                )
                self.window.add_log(f"Label file imported: {label_path}")
            except Exception as e:
                self.window.simple_info(f"Failed to import labels: {e}")
                return

        self.window.refresh_all_views()

    def export_data(self):
        data = {
            "classes": self.window.class_manager.get_classes(),
            "annotations": self.window.annotation_manager.export_dict(),
        }

        save_path, _ = QFileDialog.getSaveFileName(
            self.window,
            "Export Annotation",
            "annotations.json",
            "JSON Files (*.json)",
        )
        if not save_path:
            return

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.window.simple_info(f"Export failed: {e}")
            return

        self.window.add_log(f"Exported annotation to: {save_path}")
