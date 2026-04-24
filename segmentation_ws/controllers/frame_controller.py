import os
from PySide6.QtGui import QPixmap


class FrameController:
    def __init__(self, window):
        self.window = window

    def connect_signals(self):
        self.window.bottom_bar.back_10_btn.clicked.connect(lambda: self.move_frame(-10))
        self.window.bottom_bar.back_1_btn.clicked.connect(lambda: self.move_frame(-1))
        self.window.bottom_bar.next_1_btn.clicked.connect(lambda: self.move_frame(1))
        self.window.bottom_bar.next_10_btn.clicked.connect(lambda: self.move_frame(10))
        self.window.timeline_slider.valueChanged.connect(self.on_slider_changed)
        self.window.bottom_bar.frame_status.frameChanged.connect(self.go_to_frame)

    def move_frame(self, delta):
        self.window.frame_manager.move(delta)
        self.window.refresh_all_views()
        self.window.add_log(f"Moved to frame {self.window.frame_manager.get_current_index()}")

    def go_to_frame(self, frame_idx):
        self.window.frame_manager.jump_to(frame_idx)
        self.window.refresh_all_views()
        self.window.add_log(f"Moved to frame {self.window.frame_manager.get_current_index()}")

    def on_slider_changed(self, value):
        self.window.frame_manager.jump_to(value)
        self.window.refresh_all_views()

    def refresh_image_view(self):
        frame_path = self.window.frame_manager.get_current_frame_path()
        image_canvas = self.window.image_panel.image_canvas

        if not frame_path or not os.path.exists(frame_path):
            image_canvas.clear_image()
            return

        pixmap = QPixmap(frame_path)
        if pixmap.isNull():
            image_canvas.clear_image()
            return

        image_canvas.set_image(pixmap)
        self.refresh_current_frame_annotations()

    def refresh_current_frame_annotations(self):
        frame_idx = self.window.frame_manager.get_current_index()

        bboxes = self.window.annotation_manager.get_bboxes(frame_idx)
        polygons = self.window.annotation_manager.get_polygons(frame_idx)

        box_draw_items = []
        for box in bboxes:
            class_name = self.window.class_manager.get_class_name(box.class_id)
            color = self.window.class_manager.get_class_color(box.class_id)
            box_draw_items.append({
                "box_id": box.box_id,
                "x1": box.x1,
                "y1": box.y1,
                "x2": box.x2,
                "y2": box.y2,
                "class_id": box.class_id,
                "class_name": class_name,
                "color": color,
            })

        polygon_draw_items = []
        for poly in polygons:
            class_name = self.window.class_manager.get_class_name(poly.class_id)
            color = self.window.class_manager.get_class_color(poly.class_id)
            polygon_draw_items.append({
                "polygon_id": poly.polygon_id,
                "points": list(poly.points),
                "class_id": poly.class_id,
                "class_name": class_name,
                "color": color,
            })

        image_canvas = self.window.image_panel.image_canvas
        image_canvas.set_boxes(box_draw_items)
        image_canvas.set_polygons(polygon_draw_items)
        image_canvas.set_selected_box_ids(self.window.annotation_manager.get_selected_box_ids())
        image_canvas.set_selected_polygon_ids(self.window.annotation_manager.get_selected_polygon_ids())
