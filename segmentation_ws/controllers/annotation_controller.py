from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu

from dialogs.class_dialog import ClassDialog
from dialogs.class_select_dialog import ClassSelectDialog
from dialogs.propagate_dialog import PropagateDialog
from dialogs.auto_seg_dialog import AutoSegDialog
from annotation.propagate_shape import propagate_selected_annotations_to_range


class AnnotationController:
    def __init__(self, window):
        self.window = window
        self.auto_seg_dialog = None

    def connect_signals(self):
        image_canvas = self.window.image_panel.image_canvas
        class_panel = self.window.class_panel

        image_canvas.boxCreated.connect(self.on_box_created)
        image_canvas.boxClicked.connect(self.on_box_clicked_in_canvas)
        image_canvas.boxMoved.connect(self.on_box_moved)
        image_canvas.boxResized.connect(self.on_box_resized)

        image_canvas.polygonCreated.connect(self.on_polygon_created)
        image_canvas.polygonClicked.connect(self.on_polygon_clicked_in_canvas)
        image_canvas.polygonMoved.connect(self.on_polygon_moved)
        image_canvas.polygonPointMoved.connect(self.on_polygon_point_moved)
        image_canvas.autoSegPointClicked.connect(self.on_auto_seg_point_clicked)

        class_panel.object_list.itemClicked.connect(self.on_object_item_clicked)
        class_panel.object_list.customContextMenuRequested.connect(self.open_object_context_menu)

        self.window.segmentation_panel.box_btn.clicked.connect(self.activate_box_mode)
        self.window.segmentation_panel.polygon_btn.clicked.connect(self.activate_polygon_mode)
        self.window.segmentation_panel.auto_seg_btn.clicked.connect(self.activate_auto_seg_mode)
        self.window.annotation_panel.propagate_btn.clicked.connect(self.on_propagate_clicked)

    def activate_box_mode(self):
        self.cancel_auto_seg(quiet=True)
        self.window.current_tool_mode = "box"
        self.window.image_panel.image_canvas.set_mode("box")
        self.window.add_log("Box mode activated. Drag on the image to create a box.")

    def activate_polygon_mode(self):
        self.cancel_auto_seg(quiet=True)
        self.window.current_tool_mode = "polygon"
        self.window.image_panel.image_canvas.set_mode("polygon")
        self.window.add_log(
            "Polygon mode activated. Left-click to add points, double-click/right-click/first point to finish."
        )

    def activate_auto_seg_mode(self):
        self.cancel_auto_seg(quiet=True)

        if self.auto_seg_dialog is None:
            self.auto_seg_dialog = AutoSegDialog(parent=self.window)
            self.auto_seg_dialog.acceptedClicked.connect(self.accept_auto_seg)
            self.auto_seg_dialog.cancelledClicked.connect(self.cancel_auto_seg)
            self.auto_seg_dialog.algorithmChanged.connect(self.on_auto_seg_algorithm_changed)

        algorithm_name = self.auto_seg_dialog.get_selected_algorithm()
        self.window.auto_seg_engine.start_session(algorithm_name)
        self.window.current_tool_mode = "auto_seg"
        self.window.image_panel.image_canvas.set_mode("auto_seg")
        self.window.image_panel.image_canvas.clear_auto_seg_preview()
        self.auto_seg_dialog.show()
        self.auto_seg_dialog.raise_()
        self.auto_seg_dialog.activateWindow()
        self.window.add_log(
            f"Auto Seg mode activated with {algorithm_name}. Click points on the image, then press Accept or Cancel."
        )

    def on_auto_seg_algorithm_changed(self, algorithm_name):
        if self.window.current_tool_mode != "auto_seg":
            return
        self.window.auto_seg_engine.set_algorithm(algorithm_name)
        self._refresh_auto_seg_preview()
        self.window.add_log(f"Auto Seg algorithm changed to {algorithm_name}")

    def on_auto_seg_point_clicked(self, x, y):
        if self.window.current_tool_mode != "auto_seg":
            return

        self.window.auto_seg_engine.add_positive_point(x, y)
        self._refresh_auto_seg_preview()
        self.window.add_log(f"Auto Seg point added at ({x}, {y})")

    def _refresh_auto_seg_preview(self):
        image_canvas = self.window.image_panel.image_canvas
        image_canvas.set_auto_seg_points(
            positive_points=self.window.auto_seg_engine.get_positive_points(),
            negative_points=self.window.auto_seg_engine.get_negative_points(),
        )
        image_canvas.set_auto_seg_preview_polygon(
            self.window.auto_seg_engine.get_preview_polygon()
        )

    def accept_auto_seg(self):
        if self.window.current_tool_mode != "auto_seg":
            return

        points = self.window.auto_seg_engine.get_preview_polygon()
        if len(points) < 3:
            self.window.simple_info("Please add at least one point to build a preview polygon.")
            return

        class_id = self._select_or_create_class("Enter Class Name for Auto Seg")
        if class_id is None:
            self.window.add_log("Auto segmentation accept cancelled during class selection.")
            return

        self.window.class_manager.select_class(class_id)
        polygon = self.window.annotation_manager.create_polygon(points, class_id)
        if not polygon.is_valid():
            self.window.simple_info("Generated polygon is invalid.")
            return

        frame_idx = self.window.frame_manager.get_current_index()
        self.window.annotation_manager.add_polygon(frame_idx, polygon)
        self.window.class_controller.refresh_class_table()
        self.window.class_controller.refresh_object_list()
        self.window.refresh_all_views()

        class_name = self.window.class_manager.get_class_name(class_id)
        algorithm_name = self.window.auto_seg_engine.get_algorithm()
        self.window.add_log(
            f"Auto segmented polygon added on frame {frame_idx} with class '[{class_id}] {class_name}' using {algorithm_name}"
        )
        self._finish_auto_seg_session()

    def cancel_auto_seg(self, quiet=False):
        if self.window.current_tool_mode != "auto_seg" and not self.window.auto_seg_engine.get_positive_points():
            if self.auto_seg_dialog is not None:
                self.auto_seg_dialog.hide()
            return

        if not quiet:
            self.window.add_log("Auto segmentation cancelled.")
        self._finish_auto_seg_session()

    def _finish_auto_seg_session(self):
        self.window.auto_seg_engine.clear_session()
        self.window.image_panel.image_canvas.clear_auto_seg_preview()
        self.window.image_panel.image_canvas.clear_mode()
        self.window.current_tool_mode = None
        self.window.image_panel.image_canvas.setFocus()
        if self.auto_seg_dialog is not None:
            self.auto_seg_dialog.hide()
        self.window.refresh_all_views()

    def _select_or_create_class(self, create_title="Enter Class Name"):
        class_items = self.window.class_manager.get_classes()
        if class_items:
            dialog = ClassSelectDialog(class_items, parent=self.window)
            if not dialog.exec():
                return None
            return dialog.get_selected_class_id()

        dialog = ClassDialog(title=create_title, parent=self.window)
        if not dialog.exec():
            return None

        class_name = dialog.get_name().strip()
        if not class_name:
            self.window.simple_info("Class name is empty.")
            return None

        ok, class_id, err = self.window.class_manager.add_class(class_name)
        if not ok:
            self.window.simple_info(err)
            return None
        return class_id

    def _finish_create_mode(self):
        self.window.image_panel.image_canvas.clear_mode()
        self.window.current_tool_mode = None
        self.window.image_panel.image_canvas.setFocus()

    def on_box_created(self, x1, y1, x2, y2):
        class_id = self._select_or_create_class()
        if class_id is None:
            self._finish_create_mode()
            self.window.add_log("Box creation cancelled.")
            return

        self.window.class_manager.select_class(class_id)
        bbox = self.window.annotation_manager.create_bbox(x1, y1, x2, y2, class_id)
        if not bbox.is_valid():
            self._finish_create_mode()
            self.window.simple_info("Bounding box is too small.")
            return

        frame_idx = self.window.frame_manager.get_current_index()
        self.window.annotation_manager.add_bbox(frame_idx, bbox)
        self.window.class_controller.refresh_class_table()
        self.window.class_controller.refresh_object_list()
        self.window.refresh_all_views()
        self._finish_create_mode()
        class_name = self.window.class_manager.get_class_name(class_id)
        self.window.add_log(
            f"Box added on frame {frame_idx} with class '[{class_id}] {class_name}'"
        )

    def on_polygon_created(self, points):
        class_id = self._select_or_create_class()
        if class_id is None:
            self._finish_create_mode()
            self.window.add_log("Polygon creation cancelled.")
            return

        self.window.class_manager.select_class(class_id)
        polygon = self.window.annotation_manager.create_polygon(points, class_id)
        if not polygon.is_valid():
            self._finish_create_mode()
            self.window.simple_info("Polygon requires at least 3 points.")
            return

        frame_idx = self.window.frame_manager.get_current_index()
        self.window.annotation_manager.add_polygon(frame_idx, polygon)
        self.window.class_controller.refresh_class_table()
        self.window.class_controller.refresh_object_list()
        self.window.refresh_all_views()
        self._finish_create_mode()
        class_name = self.window.class_manager.get_class_name(class_id)
        self.window.add_log(
            f"Polygon added on frame {frame_idx} with class '[{class_id}] {class_name}'"
        )

    def on_box_clicked_in_canvas(self, x, y, ctrl_pressed):
        frame_idx = self.window.frame_manager.get_current_index()
        box = self.window.annotation_manager.find_box_at_point(frame_idx, x, y)

        if box is None:
            if not ctrl_pressed:
                self.window.annotation_manager.clear_selected_annotations()
                self.window.refresh_all_views()
            return

        if ctrl_pressed:
            self.window.annotation_manager.toggle_selected_box(box.box_id)
        else:
            self.window.annotation_manager.set_selected_box(box.box_id)

        selected_ids = self.window.annotation_manager.get_selected_box_ids()
        if len(selected_ids) == 1:
            self.window.class_manager.select_class(box.class_id)

        self.window.class_controller.refresh_class_table()
        self.window.class_controller.refresh_object_list()
        self.window.refresh_all_views()

        class_name = self.window.class_manager.get_class_name(box.class_id)
        self.window.add_log(
            f"Selected box {box.box_id} in frame {frame_idx} ([{box.class_id}] {class_name})"
        )

    def on_polygon_clicked_in_canvas(self, x, y, ctrl_pressed):
        frame_idx = self.window.frame_manager.get_current_index()
        polygon = self.window.annotation_manager.find_polygon_at_point(frame_idx, x, y)

        if polygon is None:
            if not ctrl_pressed:
                self.window.annotation_manager.clear_selected_annotations()
                self.window.refresh_all_views()
            return

        if ctrl_pressed:
            self.window.annotation_manager.toggle_selected_polygon(polygon.polygon_id)
        else:
            self.window.annotation_manager.set_selected_polygon(polygon.polygon_id)

        selected_ids = self.window.annotation_manager.get_selected_polygon_ids()
        if len(selected_ids) == 1:
            self.window.class_manager.select_class(polygon.class_id)

        self.window.class_controller.refresh_class_table()
        self.window.class_controller.refresh_object_list()
        self.window.refresh_all_views()

        class_name = self.window.class_manager.get_class_name(polygon.class_id)
        self.window.add_log(
            f"Selected polygon {polygon.polygon_id} in frame {frame_idx} ([{polygon.class_id}] {class_name})"
        )

    def on_box_moved(self, box_id, dx, dy):
        pixmap = self.window.image_panel.image_canvas.original_pixmap
        image_width = pixmap.width() if pixmap else None
        image_height = pixmap.height() if pixmap else None
        ok = self.window.annotation_manager.update_box_position(
            box_id=box_id,
            dx=dx,
            dy=dy,
            image_width=image_width,
            image_height=image_height,
        )
        if ok:
            self.window.refresh_all_views()

    def on_box_resized(self, box_id, x1, y1, x2, y2):
        pixmap = self.window.image_panel.image_canvas.original_pixmap
        image_width = pixmap.width() if pixmap else None
        image_height = pixmap.height() if pixmap else None
        ok = self.window.annotation_manager.update_box_coordinates(
            box_id=box_id,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            image_width=image_width,
            image_height=image_height,
        )
        if ok:
            self.window.refresh_all_views()

    def on_polygon_moved(self, polygon_id, dx, dy):
        pixmap = self.window.image_panel.image_canvas.original_pixmap
        image_width = pixmap.width() if pixmap else None
        image_height = pixmap.height() if pixmap else None
        ok = self.window.annotation_manager.move_polygon(
            polygon_id=polygon_id,
            dx=dx,
            dy=dy,
            image_width=image_width,
            image_height=image_height,
        )
        if ok:
            self.window.refresh_all_views()

    def on_polygon_point_moved(self, polygon_id, point_idx, x, y):
        pixmap = self.window.image_panel.image_canvas.original_pixmap
        image_width = pixmap.width() if pixmap else None
        image_height = pixmap.height() if pixmap else None
        ok = self.window.annotation_manager.update_polygon_point(
            polygon_id=polygon_id,
            point_idx=point_idx,
            x=x,
            y=y,
            image_width=image_width,
            image_height=image_height,
        )
        if ok:
            self.window.refresh_all_views()

    def on_propagate_clicked(self):
        selected_box_ids = self.window.annotation_manager.get_selected_box_ids()
        selected_polygon_ids = self.window.annotation_manager.get_selected_polygon_ids()

        if not selected_box_ids and not selected_polygon_ids:
            self.window.simple_info("Please select one or more annotations first.")
            return

        current_frame = self.window.frame_manager.get_current_index()
        total_frames = self.window.frame_manager.get_total_frames()
        if total_frames <= 0:
            self.window.simple_info("No frames loaded.")
            return

        dialog = PropagateDialog(
            current_frame=current_frame,
            max_frame=total_frames - 1,
            parent=self.window,
        )
        if not dialog.exec():
            return

        start_frame, end_frame = dialog.get_range()
        created_box_count, created_polygon_count = propagate_selected_annotations_to_range(
            annotation_manager=self.window.annotation_manager,
            source_frame_idx=current_frame,
            selected_box_ids=selected_box_ids,
            selected_polygon_ids=selected_polygon_ids,
            start_frame_idx=start_frame,
            end_frame_idx=end_frame,
        )

        self.window.refresh_all_views()
        self.window.add_log(
            f"Propagated selected annotations from frame {current_frame} to range "
            f"[{min(start_frame, end_frame)} ~ {max(start_frame, end_frame)}], excluding current frame. "
            f"Created {created_box_count} box(es), {created_polygon_count} polygon(s)."
        )

    def open_object_context_menu(self, position):
        item = self.window.class_panel.object_list.itemAt(position)
        if item is None:
            return

        menu = QMenu(self.window)
        rename_action = menu.addAction("Change Class")
        selected_action = menu.exec(self.window.class_panel.object_list.mapToGlobal(position))

        if selected_action == rename_action:
            self.change_object_class(item)

    def change_object_class(self, item):
        data = item.data(Qt.UserRole)
        item_type = data["item_type"]
        item_id = data["item_id"]

        frame_idx, anno = self.window.annotation_manager.get_item_by_id(item_type, item_id)
        if anno is None:
            self.window.simple_info("Object not found.")
            return

        class_id = self._select_or_create_class("Enter New Class Name")
        if class_id is None:
            return

        ok = self.window.annotation_manager.update_item_class(item_type, item_id, class_id)
        if not ok:
            self.window.simple_info("Failed to update object class.")
            return

        self.window.class_manager.select_class(class_id)
        self.window.class_controller.refresh_class_table()
        self.window.class_controller.refresh_object_list()
        self.window.refresh_all_views()

        class_name = self.window.class_manager.get_class_name(class_id)
        label = "box" if item_type == "box" else "polygon"
        self.window.add_log(
            f"Changed {label} {item_id} class to '[{class_id}] {class_name}'"
        )

    def on_object_item_clicked(self, item):
        data = item.data(Qt.UserRole)
        item_type = data["item_type"]
        item_id = data["item_id"]

        frame_idx, anno = self.window.annotation_manager.get_item_by_id(item_type, item_id)
        if anno is None:
            return

        if item_type == "box":
            self.window.annotation_manager.set_selected_box(item_id)
            self.window.class_manager.select_class(anno.class_id)
        else:
            self.window.annotation_manager.set_selected_polygon(item_id)
            self.window.class_manager.select_class(anno.class_id)

        self.window.frame_manager.jump_to(frame_idx)
        self.window.class_controller.refresh_object_list()
        self.window.refresh_all_views()

        label = "box" if item_type == "box" else "polygon"
        self.window.add_log(f"Moved to frame {frame_idx} and selected {label} {item_id}")

    def delete_selected_box(self):
        selected_box_ids = self.window.annotation_manager.get_selected_box_ids()
        selected_polygon_ids = self.window.annotation_manager.get_selected_polygon_ids()

        if not selected_box_ids and not selected_polygon_ids:
            self.window.add_log("No selected annotation to delete.")
            return

        ok_box = True
        ok_polygon = True
        if selected_box_ids:
            ok_box = self.window.annotation_manager.remove_boxes_by_ids(selected_box_ids)
        if selected_polygon_ids:
            ok_polygon = self.window.annotation_manager.remove_polygons_by_ids(selected_polygon_ids)

        if not ok_box and not ok_polygon:
            self.window.simple_info("Failed to delete selected annotation.")
            return

        deleted_boxes = sorted(selected_box_ids)
        deleted_polygons = sorted(selected_polygon_ids)
        self.window.annotation_manager.clear_selected_annotations()
        self.window.class_controller.refresh_object_list()
        self.window.refresh_all_views()

        parts = []
        if deleted_boxes:
            parts.append(f"boxes: {deleted_boxes}")
        if deleted_polygons:
            parts.append(f"polygons: {deleted_polygons}")
        self.window.add_log("Deleted selected annotations -> " + ", ".join(parts))
