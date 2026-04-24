from PySide6.QtCore import Qt, Signal, QRect, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QPolygon, QBrush
from PySide6.QtWidgets import QLabel


class ImageCanvas(QLabel):
    boxCreated = Signal(int, int, int, int)
    boxClicked = Signal(int, int, bool)
    boxMoved = Signal(int, int, int)
    boxResized = Signal(int, int, int, int, int)

    polygonCreated = Signal(list)
    polygonClicked = Signal(int, int, bool)
    polygonMoved = Signal(int, int, int)
    polygonPointMoved = Signal(int, int, int, int)

    autoSegPointClicked = Signal(int, int)

    EDGE_MARGIN = 8
    VERTEX_RADIUS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.setStyleSheet("background: #dfddda; border: 1px solid #9c9c9c;")
        self.setMinimumSize(400, 300)

        self.original_pixmap = None
        self.scaled_pixmap = None
        self.pixmap_draw_rect = QRect()

        self.mode = None
        self.dragging = False
        self.start_point = QPoint()
        self.end_point = QPoint()

        self.boxes = []
        self.selected_box_ids = set()

        self.polygons = []
        self.selected_polygon_ids = set()
        self.temp_polygon_points = []
        self.temp_polygon_hover_point = None

        self.auto_seg_positive_points = []
        self.auto_seg_negative_points = []
        self.auto_seg_preview_polygon = []

        self.interaction_mode = None
        self.active_box_id = None
        self.active_edge = None
        self.active_polygon_id = None
        self.active_vertex_index = None
        self.last_mouse_image_pos = None
        self.resize_anchor = None

    def set_mode(self, mode):
        self.mode = mode
        self.dragging = False
        if mode != "polygon":
            self.temp_polygon_points = []
            self.temp_polygon_hover_point = None
        self.update()

    def clear_mode(self):
        self.mode = None
        self.dragging = False
        self.interaction_mode = None
        self.active_box_id = None
        self.active_edge = None
        self.active_polygon_id = None
        self.active_vertex_index = None
        self.resize_anchor = None
        self.last_mouse_image_pos = None
        self.temp_polygon_points = []
        self.temp_polygon_hover_point = None
        self.clear_auto_seg_preview()
        self.unsetCursor()
        self.update()

    def set_image(self, pixmap: QPixmap):
        self.original_pixmap = pixmap
        self._update_scaled_pixmap()
        self.update()

    def clear_image(self):
        self.original_pixmap = None
        self.scaled_pixmap = None
        self.pixmap_draw_rect = QRect()
        self.boxes = []
        self.selected_box_ids = set()
        self.polygons = []
        self.selected_polygon_ids = set()
        self.interaction_mode = None
        self.active_box_id = None
        self.active_edge = None
        self.active_polygon_id = None
        self.active_vertex_index = None
        self.resize_anchor = None
        self.last_mouse_image_pos = None
        self.temp_polygon_points = []
        self.temp_polygon_hover_point = None
        self.clear_auto_seg_preview()
        self.unsetCursor()
        self.update()

    def set_boxes(self, boxes):
        self.boxes = boxes
        self.update()

    def set_selected_box_ids(self, box_ids):
        self.selected_box_ids = set(box_ids)
        self.update()

    def set_polygons(self, polygons):
        self.polygons = polygons
        self.update()

    def set_selected_polygon_ids(self, polygon_ids):
        self.selected_polygon_ids = set(polygon_ids)
        self.update()

    def set_auto_seg_points(self, positive_points=None, negative_points=None):
        self.auto_seg_positive_points = list(positive_points or [])
        self.auto_seg_negative_points = list(negative_points or [])
        self.update()

    def set_auto_seg_preview_polygon(self, points):
        self.auto_seg_preview_polygon = list(points or [])
        self.update()

    def clear_auto_seg_preview(self):
        self.auto_seg_positive_points = []
        self.auto_seg_negative_points = []
        self.auto_seg_preview_polygon = []
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if not self.original_pixmap or self.original_pixmap.isNull():
            self.scaled_pixmap = None
            self.pixmap_draw_rect = QRect()
            return

        scaled = self.original_pixmap.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.scaled_pixmap = scaled

        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self.pixmap_draw_rect = QRect(x, y, scaled.width(), scaled.height())

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            if self.mode == "polygon" and event.button() == Qt.RightButton:
                self._finish_polygon_if_possible()
                event.accept()
                return
            super().mousePressEvent(event)
            return

        if not self.pixmap_draw_rect.contains(event.pos()):
            super().mousePressEvent(event)
            return

        if self.mode == "box":
            self.dragging = True
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.update()
            return

        if self.mode == "polygon":
            image_point = self._widget_point_to_image_coords(event.pos())
            if len(self.temp_polygon_points) >= 3 and self._is_near_first_temp_polygon_point(event.pos()):
                self._finish_polygon_if_possible()
                event.accept()
                return

            self.temp_polygon_points.append(image_point)
            self.update()
            event.accept()
            return

        if self.mode == "auto_seg":
            x, y = self._widget_point_to_image_coords(event.pos())
            self.autoSegPointClicked.emit(x, y)
            event.accept()
            return

        hit_vertex = self._get_polygon_vertex_at_widget_pos(event.pos())
        if (
            hit_vertex is not None
            and len(self.selected_polygon_ids) == 1
            and hit_vertex["polygon_id"] in self.selected_polygon_ids
        ):
            self.interaction_mode = "move_polygon_vertex"
            self.active_polygon_id = hit_vertex["polygon_id"]
            self.active_vertex_index = hit_vertex["vertex_index"]
            event.accept()
            return

        hit_polygon = self._get_polygon_at_widget_pos(event.pos())
        if (
            hit_polygon is not None
            and len(self.selected_polygon_ids) == 1
            and hit_polygon["polygon_id"] in self.selected_polygon_ids
        ):
            self.interaction_mode = "move_polygon"
            self.active_polygon_id = hit_polygon["polygon_id"]
            self.last_mouse_image_pos = self._widget_point_to_image_coords(event.pos())
            event.accept()
            return

        hit_box = self._get_box_at_widget_pos(event.pos())
        if (
            hit_box is not None
            and len(self.selected_box_ids) == 1
            and hit_box["box_id"] in self.selected_box_ids
        ):
            rect = self._image_rect_to_widget_rect(hit_box["x1"], hit_box["y1"], hit_box["x2"], hit_box["y2"])
            edge = self._get_edge_at_point(rect, event.pos(), self.EDGE_MARGIN)

            if edge is not None:
                self.interaction_mode = "resize_box"
                self.active_box_id = hit_box["box_id"]
                self.active_edge = edge
                self.resize_anchor = self._get_resize_anchor(hit_box["box_id"], edge)
                self.last_mouse_image_pos = self._widget_point_to_image_coords(event.pos())
                event.accept()
                return

            if rect.contains(event.pos()):
                self.interaction_mode = "move_box"
                self.active_box_id = hit_box["box_id"]
                self.last_mouse_image_pos = self._widget_point_to_image_coords(event.pos())
                event.accept()
                return

        x, y = self._widget_point_to_image_coords(event.pos())
        ctrl_pressed = bool(event.modifiers() & Qt.ControlModifier)

        if hit_polygon is not None:
            self.polygonClicked.emit(x, y, ctrl_pressed)
        else:
            self.boxClicked.emit(x, y, ctrl_pressed)

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.mode == "polygon" and self.pixmap_draw_rect.contains(event.pos()):
            self._finish_polygon_if_possible()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self.mode == "box" and self.dragging:
            self.end_point = event.pos()
            self.update()
            return

        if self.mode == "polygon":
            if self.pixmap_draw_rect.contains(event.pos()):
                self.temp_polygon_hover_point = self._widget_point_to_image_coords(event.pos())
            else:
                self.temp_polygon_hover_point = None
            self.update()
            return

        if self.interaction_mode == "move_box" and self.active_box_id is not None:
            current_pos = self._widget_point_to_image_coords(event.pos())
            if self.last_mouse_image_pos is not None:
                dx = current_pos[0] - self.last_mouse_image_pos[0]
                dy = current_pos[1] - self.last_mouse_image_pos[1]
                if dx != 0 or dy != 0:
                    self.boxMoved.emit(self.active_box_id, dx, dy)
                    self.last_mouse_image_pos = current_pos
            event.accept()
            return

        if self.interaction_mode == "resize_box" and self.active_box_id is not None:
            current_pos = self._widget_point_to_image_coords(event.pos())
            if self.resize_anchor is not None and self.active_edge is not None:
                ax1, ay1, ax2, ay2 = self.resize_anchor
                cx, cy = current_pos
                if self.active_edge == "left":
                    self.boxResized.emit(self.active_box_id, cx, ay1, ax1, ay2)
                elif self.active_edge == "right":
                    self.boxResized.emit(self.active_box_id, ax1, ay1, cx, ay2)
                elif self.active_edge == "top":
                    self.boxResized.emit(self.active_box_id, ax1, cy, ax2, ay1)
                elif self.active_edge == "bottom":
                    self.boxResized.emit(self.active_box_id, ax1, ay1, ax2, cy)
            event.accept()
            return

        if self.interaction_mode == "move_polygon" and self.active_polygon_id is not None:
            current_pos = self._widget_point_to_image_coords(event.pos())
            if self.last_mouse_image_pos is not None:
                dx = current_pos[0] - self.last_mouse_image_pos[0]
                dy = current_pos[1] - self.last_mouse_image_pos[1]
                if dx != 0 or dy != 0:
                    self.polygonMoved.emit(self.active_polygon_id, dx, dy)
                    self.last_mouse_image_pos = current_pos
            event.accept()
            return

        if self.interaction_mode == "move_polygon_vertex" and self.active_polygon_id is not None:
            current_pos = self._widget_point_to_image_coords(event.pos())
            self.polygonPointMoved.emit(
                self.active_polygon_id,
                self.active_vertex_index,
                current_pos[0],
                current_pos[1],
            )
            event.accept()
            return

        self._update_cursor(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.mode == "box" and self.dragging and event.button() == Qt.LeftButton:
            self.dragging = False
            self.end_point = event.pos()
            rect = QRect(self.start_point, self.end_point).normalized()
            clipped = rect.intersected(self.pixmap_draw_rect)
            if clipped.width() > 5 and clipped.height() > 5:
                x1, y1, x2, y2 = self._widget_rect_to_image_coords(clipped)
                self.boxCreated.emit(x1, y1, x2, y2)
            self.update()
            return

        if event.button() == Qt.LeftButton and self.interaction_mode is not None:
            self.interaction_mode = None
            self.active_box_id = None
            self.active_edge = None
            self.active_polygon_id = None
            self.active_vertex_index = None
            self.last_mouse_image_pos = None
            self.resize_anchor = None
            self._update_cursor(event.pos())
            self.update()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self.interaction_mode is None:
            self.unsetCursor()
        super().leaveEvent(event)

    def _finish_polygon_if_possible(self):
        if len(self.temp_polygon_points) >= 3:
            self.polygonCreated.emit(list(self.temp_polygon_points))
        self.temp_polygon_points = []
        self.temp_polygon_hover_point = None
        self.update()

    def _is_near_first_temp_polygon_point(self, widget_pos):
        if not self.temp_polygon_points:
            return False
        first_x, first_y = self.temp_polygon_points[0]
        first_widget = self._image_point_to_widget_point(first_x, first_y)
        if first_widget is None:
            return False
        dx = widget_pos.x() - first_widget.x()
        dy = widget_pos.y() - first_widget.y()
        return (dx * dx + dy * dy) <= (self.VERTEX_RADIUS * self.VERTEX_RADIUS * 4)

    def _widget_rect_to_image_coords(self, rect: QRect):
        if not self.original_pixmap or not self.scaled_pixmap:
            return 0, 0, 0, 0

        sx = self.original_pixmap.width() / self.scaled_pixmap.width()
        sy = self.original_pixmap.height() / self.scaled_pixmap.height()

        x1 = int((rect.left() - self.pixmap_draw_rect.left()) * sx)
        y1 = int((rect.top() - self.pixmap_draw_rect.top()) * sy)
        x2 = int((rect.right() - self.pixmap_draw_rect.left()) * sx)
        y2 = int((rect.bottom() - self.pixmap_draw_rect.top()) * sy)

        x1 = max(0, min(x1, self.original_pixmap.width() - 1))
        y1 = max(0, min(y1, self.original_pixmap.height() - 1))
        x2 = max(0, min(x2, self.original_pixmap.width() - 1))
        y2 = max(0, min(y2, self.original_pixmap.height() - 1))
        return x1, y1, x2, y2

    def _widget_point_to_image_coords(self, point):
        if not self.original_pixmap or not self.scaled_pixmap:
            return 0, 0

        sx = self.original_pixmap.width() / self.scaled_pixmap.width()
        sy = self.original_pixmap.height() / self.scaled_pixmap.height()

        x = int((point.x() - self.pixmap_draw_rect.left()) * sx)
        y = int((point.y() - self.pixmap_draw_rect.top()) * sy)

        x = max(0, min(x, self.original_pixmap.width() - 1))
        y = max(0, min(y, self.original_pixmap.height() - 1))
        return x, y

    def _image_rect_to_widget_rect(self, x1, y1, x2, y2):
        if not self.original_pixmap or not self.scaled_pixmap:
            return QRect()

        sx = self.scaled_pixmap.width() / self.original_pixmap.width()
        sy = self.scaled_pixmap.height() / self.original_pixmap.height()

        wx1 = int(self.pixmap_draw_rect.left() + x1 * sx)
        wy1 = int(self.pixmap_draw_rect.top() + y1 * sy)
        wx2 = int(self.pixmap_draw_rect.left() + x2 * sx)
        wy2 = int(self.pixmap_draw_rect.top() + y2 * sy)
        return QRect(QPoint(wx1, wy1), QPoint(wx2, wy2)).normalized()

    def _image_point_to_widget_point(self, x, y):
        if not self.original_pixmap or not self.scaled_pixmap:
            return None
        sx = self.scaled_pixmap.width() / self.original_pixmap.width()
        sy = self.scaled_pixmap.height() / self.original_pixmap.height()
        wx = int(self.pixmap_draw_rect.left() + x * sx)
        wy = int(self.pixmap_draw_rect.top() + y * sy)
        return QPoint(wx, wy)

    def _image_points_to_widget_polygon(self, points):
        qpoints = []
        for x, y in points:
            p = self._image_point_to_widget_point(x, y)
            if p is not None:
                qpoints.append(p)
        return QPolygon(qpoints)

    def _get_box_at_widget_pos(self, pos):
        for item in reversed(self.boxes):
            rect = self._image_rect_to_widget_rect(item["x1"], item["y1"], item["x2"], item["y2"])
            if rect.contains(pos):
                return item
        return None

    def _get_polygon_at_widget_pos(self, pos):
        for item in reversed(self.polygons):
            polygon = self._image_points_to_widget_polygon(item["points"])
            if polygon.size() >= 3 and polygon.containsPoint(pos, Qt.OddEvenFill):
                return item
        return None

    def _get_polygon_vertex_at_widget_pos(self, pos):
        for item in reversed(self.polygons):
            for idx, (x, y) in enumerate(item["points"]):
                p = self._image_point_to_widget_point(x, y)
                if p is None:
                    continue
                dx = pos.x() - p.x()
                dy = pos.y() - p.y()
                if (dx * dx + dy * dy) <= (self.VERTEX_RADIUS * self.VERTEX_RADIUS):
                    return {
                        "polygon_id": item["polygon_id"],
                        "vertex_index": idx,
                    }
        return None

    def _get_resize_anchor(self, box_id, edge_name):
        item = next((box for box in self.boxes if box["box_id"] == box_id), None)
        if item is None:
            return None
        x1, y1, x2, y2 = item["x1"], item["y1"], item["x2"], item["y2"]
        anchor_map = {
            "left": (x2, y1, x2, y2),
            "right": (x1, y1, x1, y2),
            "top": (x1, y2, x2, y2),
            "bottom": (x1, y1, x2, y1),
        }
        return anchor_map.get(edge_name)

    def _update_cursor(self, pos):
        hit_vertex = self._get_polygon_vertex_at_widget_pos(pos)
        if (
            hit_vertex is not None
            and len(self.selected_polygon_ids) == 1
            and hit_vertex["polygon_id"] in self.selected_polygon_ids
        ):
            self.setCursor(Qt.CrossCursor)
            return

        hit_polygon = self._get_polygon_at_widget_pos(pos)
        if (
            hit_polygon is not None
            and len(self.selected_polygon_ids) == 1
            and hit_polygon["polygon_id"] in self.selected_polygon_ids
        ):
            self.setCursor(Qt.SizeAllCursor)
            return

        hit_box = self._get_box_at_widget_pos(pos)
        if (
            hit_box is not None
            and len(self.selected_box_ids) == 1
            and hit_box["box_id"] in self.selected_box_ids
        ):
            rect = self._image_rect_to_widget_rect(hit_box["x1"], hit_box["y1"], hit_box["x2"], hit_box["y2"])
            edge = self._get_edge_at_point(rect, pos, self.EDGE_MARGIN)
            if edge in ("left", "right"):
                self.setCursor(Qt.SizeHorCursor)
                return
            if edge in ("top", "bottom"):
                self.setCursor(Qt.SizeVerCursor)
                return
            if rect.contains(pos):
                self.setCursor(Qt.SizeAllCursor)
                return

        self.unsetCursor()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)

        if self.scaled_pixmap:
            painter.drawPixmap(self.pixmap_draw_rect, self.scaled_pixmap)

        for item in self.polygons:
            polygon = self._image_points_to_widget_polygon(item["points"])
            if polygon.size() < 2:
                continue

            is_selected = item["polygon_id"] in self.selected_polygon_ids

            pen = QPen(
                QColor("#ffff00") if is_selected else QColor(item["color"]),
                3 if is_selected else 2,
            )
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(polygon)

            first_wp = self._image_point_to_widget_point(
                item["points"][0][0], item["points"][0][1]
            )
            if first_wp is not None:
                painter.drawText(first_wp + QPoint(4, -4), f'{item["class_name"]} {item["polygon_id"]}')

            vertex_color = QColor("#ffff00") if is_selected else QColor(item["color"])
            painter.setPen(QPen(vertex_color, 1))
            painter.setBrush(QBrush(vertex_color))

            for px, py in item["points"]:
                wp = self._image_point_to_widget_point(px, py)
                if wp is not None:
                    painter.drawEllipse(wp, self.VERTEX_RADIUS // 2, self.VERTEX_RADIUS // 2)

            painter.setBrush(Qt.NoBrush)

        for item in self.boxes:
            rect = self._image_rect_to_widget_rect(item["x1"], item["y1"], item["x2"], item["y2"])

            is_selected = item["box_id"] in self.selected_box_ids
            painter.setBrush(Qt.NoBrush)

            pen = QPen(
                QColor("#ffff00") if is_selected else QColor(item["color"]),
                3 if is_selected else 2,
            )
            painter.setPen(pen)
            painter.drawRect(rect)
            painter.drawText(rect.topLeft() + QPoint(4, 14), f'{item["class_name"]} {item["box_id"]}')

        if self.mode == "box" and self.dragging:
            preview_rect = QRect(self.start_point, self.end_point).normalized()
            preview_rect = preview_rect.intersected(self.pixmap_draw_rect)
            painter.setPen(QPen(QColor("#00ff00"), 2, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(preview_rect)

        if self.mode == "polygon" and self.temp_polygon_points:
            painter.setPen(QPen(QColor("#00ff00"), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor("#00ff00")))

            prev_wp = None
            for px, py in self.temp_polygon_points:
                wp = self._image_point_to_widget_point(px, py)
                if wp is None:
                    continue

                painter.drawEllipse(wp, self.VERTEX_RADIUS // 2, self.VERTEX_RADIUS // 2)

                if prev_wp is not None:
                    painter.drawLine(prev_wp, wp)

                prev_wp = wp

            if prev_wp is not None and self.temp_polygon_hover_point is not None:
                hover_wp = self._image_point_to_widget_point(
                    self.temp_polygon_hover_point[0],
                    self.temp_polygon_hover_point[1],
                )
                if hover_wp is not None:
                    painter.drawLine(prev_wp, hover_wp)

            painter.setBrush(Qt.NoBrush)

        if self.auto_seg_preview_polygon:
            preview_polygon = self._image_points_to_widget_polygon(self.auto_seg_preview_polygon)
            if preview_polygon.size() >= 2:
                painter.setPen(QPen(QColor("#00d084"), 2, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawPolygon(preview_polygon)

        if self.auto_seg_positive_points:
            painter.setPen(QPen(QColor("#00d084"), 2))
            painter.setBrush(QBrush(QColor("#00d084")))
            for px, py in self.auto_seg_positive_points:
                wp = self._image_point_to_widget_point(px, py)
                if wp is not None:
                    painter.drawEllipse(wp, 5, 5)

        if self.auto_seg_negative_points:
            painter.setPen(QPen(QColor("#ff4d4f"), 2))
            painter.setBrush(QBrush(QColor("#ff4d4f")))
            for px, py in self.auto_seg_negative_points:
                wp = self._image_point_to_widget_point(px, py)
                if wp is not None:
                    painter.drawEllipse(wp, 5, 5)

    def _get_edge_at_point(self, rect, point, margin=6):
        x = point.x()
        y = point.y()
        inside_x = rect.left() <= x <= rect.right()
        inside_y = rect.top() <= y <= rect.bottom()
        near_left = abs(x - rect.left()) <= margin and inside_y
        near_right = abs(x - rect.right()) <= margin and inside_y
        near_top = abs(y - rect.top()) <= margin and inside_x
        near_bottom = abs(y - rect.bottom()) <= margin and inside_x
        if near_left:
            return "left"
        if near_right:
            return "right"
        if near_top:
            return "top"
        if near_bottom:
            return "bottom"
        return None
