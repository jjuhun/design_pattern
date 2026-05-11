# 작업 화면 위에서 일어나는 마우스 입력을 처리하는 파일입니다.
# 클릭 선택, 드래그 이동, 꼭짓점 편집, 우클릭 메뉴를 담당합니다.
from typing import List, Optional, Tuple, Union

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtWidgets import QGraphicsView, QMenu

from core.annotation.models import RenderAnnotation
from core.common.utils import clamp


Point = Tuple[float, float]
BoxData = Tuple[float, float, float, float]
PolygonData = List[Point]
ShapeData = Union[Point, BoxData, PolygonData]


class MouseEventControllerMixin:
    def wheelEvent(self, event):
        """마우스 휠로 확대/축소 또는 스크롤 이동을 처리한다."""
        if self.pixmap_item is None:
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            event.accept()
            return
        # Shift + wheel -> horizontal scroll
        if event.modifiers() & Qt.ShiftModifier:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - delta)
            self._manual_view = True
            event.accept()
            return

        # Default: wheel for zoom (wheel up -> zoom in, wheel down -> zoom out)
        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scale(factor, factor)
        self._manual_view = True
        event.accept()
        return

    def mouseDoubleClickEvent(self, event):
        """왼쪽 더블클릭 시 이미지를 화면에 다시 맞춘다."""
        if event.button() == Qt.LeftButton:
            self.fit_to_image()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ---------- 모양 계산 ----------

    def _image_rect(self):
        """현재 이미지가 차지하는 작업 화면 좌표 영역을 반환한다."""
        if self.pixmap_item is None:
            return QRectF()
        return self.pixmap_item.boundingRect()

    def _clamp_point_to_image(self, scene_pos: QPointF):
        """마우스 좌표가 이미지 영역 밖으로 나가지 않도록 제한한다."""
        rect = self._image_rect()
        if rect.isNull():
            return scene_pos
        x = clamp(scene_pos.x(), rect.left(), rect.right())
        y = clamp(scene_pos.y(), rect.top(), rect.bottom())
        return QPointF(x, y)

    def _vertex_hit_radius_scene(self):
        """현재 확대 배율에서 꼭짓점을 잡을 수 있는 반경을 계산한다."""
        scale = abs(self.transform().m11())
        if scale <= 1e-6:
            scale = 1.0
        return 8.0 / scale

    def _annotation_id_at_scene_pos(self, scene_pos: QPointF):
        """지정한 좌표 아래에 있는 객체 표시 정보 ID를 찾는다."""
        for item in self.scene_obj.items(scene_pos):
            ann_id = item.data(0)
            if ann_id is not None:
                return int(ann_id)
        return None

    def _vertex_key_at_scene_pos(self, scene_pos: QPointF) -> Optional[Tuple[int, int]]:
        """지정한 좌표에서 선택된 객체의 가까운 꼭짓점을 찾는다."""
        if len(self._selected_ann_ids) != 1:
            return None
        ann_id = self._selected_ann_ids[0]
        ann = self.annotation_models.get(ann_id)
        if ann is None:
            return None
        radius = self._vertex_hit_radius_scene()
        best = None
        best_d2 = None
        for idx, (vx, vy) in enumerate(self._vertex_points_for_annotation(ann)):
            d2 = (vx - scene_pos.x()) ** 2 + (vy - scene_pos.y()) ** 2
            if d2 <= radius * radius and (best_d2 is None or d2 < best_d2):
                best = (ann_id, idx)
                best_d2 = d2
        return best

    def _set_hover_vertex_key(self, key: Optional[Tuple[int, int]]):
        """마우스가 올라간 꼭짓점 상태를 갱신한다."""
        if key == self._hover_vertex_key:
            return
        self._hover_vertex_key = key
        self._apply_selection_styles()

    def _opposite_box_corner_index(self, idx: int) -> int:
        """박스 꼭짓점 편집 시 기준이 되는 반대편 꼭짓점 번호를 반환한다."""
        return {0: 2, 1: 3, 2: 0, 3: 1}[idx]

    def _box_data_from_corner_drag(self, original_data: ShapeData, vertex_index: int, new_pos: QPointF) -> ShapeData:
        """박스 꼭짓점 드래그 결과를 새 박스 좌표로 계산한다."""
        x, y, w, h = original_data  # type: ignore[misc]
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        opp_idx = self._opposite_box_corner_index(vertex_index)
        ox, oy = corners[opp_idx]
        nx, ny = new_pos.x(), new_pos.y()
        rx = min(ox, nx)
        ry = min(oy, ny)
        rw = max(1.0, abs(nx - ox))
        rh = max(1.0, abs(ny - oy))
        return (rx, ry, rw, rh)

    def _polygon_data_from_vertex_drag(self, original_data: ShapeData, vertex_index: int, new_pos: QPointF) -> ShapeData:
        """폴리곤 꼭짓점 드래그 결과를 새 폴리곤 좌표로 계산한다."""
        points = list(original_data)  # type: ignore[arg-type]
        points[vertex_index] = (new_pos.x(), new_pos.y())
        return points

    def _edited_data_for_vertex_drag(self, ann: RenderAnnotation, original_data: ShapeData, vertex_index: int, new_pos: QPointF) -> ShapeData:
        """도형 종류에 맞는 꼭짓점 편집 결과 좌표를 계산한다."""
        if ann.shape_type == "box":
            return self._box_data_from_corner_drag(original_data, vertex_index, new_pos)
        return self._polygon_data_from_vertex_drag(original_data, vertex_index, new_pos)

    def _translate_data(self, ann: RenderAnnotation, data: ShapeData, dx: float, dy: float) -> ShapeData:
        """객체 표시 정보 좌표 전체를 지정한 거리만큼 이동한다."""
        if ann.shape_type == "box":
            x, y, w, h = data  # type: ignore[misc]
            return (x + dx, y + dy, w, h)
        if ann.shape_type == "keypoint":
            x, y = data  # type: ignore[misc]
            return (x + dx, y + dy)
        points = data  # type: ignore[assignment]
        return [(x + dx, y + dy) for x, y in points]

    def _clip_box_data_to_image(self, data: ShapeData) -> Optional[ShapeData]:
        """박스를 이미지 영역 안에 남은 부분만 보존하도록 자른다."""
        rect = self._image_rect()
        if rect.isNull():
            return data
        x, y, w, h = data  # type: ignore[misc]
        x1 = min(float(x), float(x + w))
        y1 = min(float(y), float(y + h))
        x2 = max(float(x), float(x + w))
        y2 = max(float(y), float(y + h))

        clipped_left = max(x1, rect.left())
        clipped_top = max(y1, rect.top())
        clipped_right = min(x2, rect.right())
        clipped_bottom = min(y2, rect.bottom())
        clipped_w = clipped_right - clipped_left
        clipped_h = clipped_bottom - clipped_top
        if clipped_w <= 1e-6 or clipped_h <= 1e-6:
            return None
        return (clipped_left, clipped_top, clipped_w, clipped_h)

    def _line_intersection_with_vertical(self, p1: Point, p2: Point, x_edge: float) -> Point:
        """선분이 수직 경계와 만나는 점을 계산한다."""
        x1, y1 = p1
        x2, y2 = p2
        if abs(x2 - x1) <= 1e-12:
            return (x_edge, y1)
        t = (x_edge - x1) / (x2 - x1)
        return (x_edge, y1 + t * (y2 - y1))

    def _line_intersection_with_horizontal(self, p1: Point, p2: Point, y_edge: float) -> Point:
        """선분이 수평 경계와 만나는 점을 계산한다."""
        x1, y1 = p1
        x2, y2 = p2
        if abs(y2 - y1) <= 1e-12:
            return (x1, y_edge)
        t = (y_edge - y1) / (y2 - y1)
        return (x1 + t * (x2 - x1), y_edge)

    def _clip_polygon_edge(self, points: PolygonData, inside_fn, intersect_fn) -> PolygonData:
        """Sutherland-Hodgman 방식으로 폴리곤을 한 경계선에 대해 자른다."""
        if not points:
            return []
        clipped: PolygonData = []
        prev = points[-1]
        prev_inside = inside_fn(prev)
        for curr in points:
            curr_inside = inside_fn(curr)
            if curr_inside:
                if not prev_inside:
                    clipped.append(intersect_fn(prev, curr))
                clipped.append(curr)
            elif prev_inside:
                clipped.append(intersect_fn(prev, curr))
            prev = curr
            prev_inside = curr_inside
        return clipped

    def _dedupe_polygon_points(self, points: PolygonData) -> PolygonData:
        """클리핑 과정에서 생긴 중복 꼭짓점을 정리한다."""
        deduped: PolygonData = []
        for x, y in points:
            point = (float(x), float(y))
            if not deduped or abs(deduped[-1][0] - point[0]) > 1e-6 or abs(deduped[-1][1] - point[1]) > 1e-6:
                deduped.append(point)
        if (
            len(deduped) > 1
            and abs(deduped[0][0] - deduped[-1][0]) <= 1e-6
            and abs(deduped[0][1] - deduped[-1][1]) <= 1e-6
        ):
            deduped.pop()
        return deduped

    def _polygon_area(self, points: PolygonData) -> float:
        """폴리곤 면적을 계산한다."""
        if len(points) < 3:
            return 0.0
        area = 0.0
        for idx, (x1, y1) in enumerate(points):
            x2, y2 = points[(idx + 1) % len(points)]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    def _clip_polygon_data_to_image(self, data: ShapeData) -> Optional[ShapeData]:
        """폴리곤을 이미지 영역과 겹치는 부분만 남기도록 자른다."""
        rect = self._image_rect()
        if rect.isNull():
            return data
        points = [(float(x), float(y)) for x, y in data]  # type: ignore[arg-type]
        left = rect.left()
        right = rect.right()
        top = rect.top()
        bottom = rect.bottom()

        points = self._clip_polygon_edge(
            points,
            lambda p: p[0] >= left,
            lambda p1, p2: self._line_intersection_with_vertical(p1, p2, left),
        )
        points = self._clip_polygon_edge(
            points,
            lambda p: p[0] <= right,
            lambda p1, p2: self._line_intersection_with_vertical(p1, p2, right),
        )
        points = self._clip_polygon_edge(
            points,
            lambda p: p[1] >= top,
            lambda p1, p2: self._line_intersection_with_horizontal(p1, p2, top),
        )
        points = self._clip_polygon_edge(
            points,
            lambda p: p[1] <= bottom,
            lambda p1, p2: self._line_intersection_with_horizontal(p1, p2, bottom),
        )

        points = self._dedupe_polygon_points(points)
        if len(points) < 3 or self._polygon_area(points) <= 1e-6:
            return None
        return points

    def _clip_keypoint_data_to_image(self, data: ShapeData) -> Optional[ShapeData]:
        """키포인트 좌표를 이미지 영역 안으로 제한한다."""
        rect = self._image_rect()
        if rect.isNull():
            return data
        x, y = data  # type: ignore[misc]
        return (
            clamp(float(x), rect.left(), rect.right()),
            clamp(float(y), rect.top(), rect.bottom()),
        )

    def _clip_shape_data_to_image(self, ann: RenderAnnotation, data: ShapeData) -> Optional[ShapeData]:
        """객체 표시 정보를 이미지 영역으로 자르고 남은 부분이 없으면 None을 반환한다."""
        if ann.shape_type == "box":
            return self._clip_box_data_to_image(data)
        if ann.shape_type == "keypoint":
            return self._clip_keypoint_data_to_image(data)
        return self._clip_polygon_data_to_image(data)

    # ---------- 다시 그리기 ----------

    def _show_vertex_context_menu(self, global_pos, ann_id: int, vertex_index: int):
        """폴리곤 꼭짓점에서 우클릭 메뉴를 띄워 점 추가/삭제를 처리한다."""
        ann = self.annotation_models.get(ann_id)
        if ann is None or ann.shape_type != "polygon":
            return
        points = list(ann.data)  # type: ignore[arg-type]

        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; color: #000000; border: 1px solid #CFCFCF; }"
            "QMenu::item { padding: 6px 18px; background: transparent; color: #000000; }"
            "QMenu::item:selected { background: #D8E9FF; color: #000000; }"
        )
        delete_action = menu.addAction("Delete point")
        add_action = menu.addAction("Add point")
        if len(points) <= 3:
            delete_action.setEnabled(False)
        action = menu.exec_(global_pos)
        if action is None:
            return
        if action == add_action:
            next_idx = (vertex_index + 1) % len(points)
            x1, y1 = points[vertex_index]
            x2, y2 = points[next_idx]
            new_pt = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            points.insert(vertex_index + 1, new_pt)
            self.annotationsDataUpdateRequested.emit([(ann_id, points)])
            return
        if action == delete_action and len(points) > 3:
            del points[vertex_index]
            self.annotationsDataUpdateRequested.emit([(ann_id, points)])

    # ---------- 이벤트 처리 ----------

    def mousePressEvent(self, event):
        """마우스 누름 입력으로 생성, 선택, 드래그, 꼭짓점 편집을 시작한다."""
        if self.pixmap_item is None:
            super().mousePressEvent(event)
            return

        scene_pos = self._clamp_point_to_image(self.mapToScene(event.pos()))

        if self._mode == "box":
            if event.button() == Qt.LeftButton:
                self._box_start_scene = scene_pos
                self._update_box_preview(scene_pos)
                event.accept()
                return

        if self._mode == "polygon":
            if event.button() == Qt.LeftButton:
                self._polygon_points.append((scene_pos.x(), scene_pos.y()))
                self._current_mouse_scene = scene_pos
                self._update_polygon_preview()
                event.accept()
                return

        if self._mode == "keypoint":
            if event.button() == Qt.LeftButton:
                self.annotationCreateRequested.emit("keypoint", (scene_pos.x(), scene_pos.y()))
                event.accept()
                return
            if event.button() == Qt.RightButton:
                # Remove the last added vertex when right-clicking during polygon drawing
                if self._polygon_points:
                    self._polygon_points.pop()
                    self._update_polygon_preview()
                event.accept()
                return
            
        if self._mode == "ai_refine":
            if event.button() == Qt.LeftButton:
                self.aiPromptPointRequested.emit(scene_pos.x(), scene_pos.y(), 1)
                event.accept()
                return
            if event.button() == Qt.RightButton:
                self.aiPromptPointRequested.emit(scene_pos.x(), scene_pos.y(), 0)
                event.accept()
                return

        if self._mode == "ai_point":
            if event.button() == Qt.LeftButton:
                self.aiPromptPointRequested.emit(scene_pos.x(), scene_pos.y(), 1)
                event.accept()
                return
            if event.button() == Qt.RightButton:
                self.set_mode("select")
                self.statusMessage.emit("AI 포인트 입력 취소")
                event.accept()
                return

        if self._mode == "select":
            if event.button() == Qt.RightButton:
                vertex_key = self._vertex_key_at_scene_pos(scene_pos)
                if vertex_key is not None:
                    ann_id, vertex_index = vertex_key
                    ann = self.annotation_models.get(ann_id)
                    if ann is not None and ann.shape_type == "polygon":
                        self._show_vertex_context_menu(event.globalPos(), ann_id, vertex_index)
                        event.accept()
                        return

            # prepare for possible panning: only start when mouse moves while right button held
            if event.button() == Qt.RightButton:
                self._pan_possible = True
                self._pan_start = event.pos()
                event.accept()
                return
            
            if event.button() == Qt.LeftButton:
                vertex_key = self._vertex_key_at_scene_pos(scene_pos)
                ctrl_pressed = bool(event.modifiers() & Qt.ControlModifier)

                if vertex_key is not None and not ctrl_pressed:
                    ann_id, vertex_index = vertex_key
                    ann = self.annotation_models.get(ann_id)
                    if ann is not None:
                        self.set_selected_annotations([ann_id])
                        self._editing_vertex_key = vertex_key
                        if ann.shape_type == "box":
                            x, y, w, h = ann.data  # type: ignore[misc]
                            self._editing_vertex_original_data = (x, y, w, h)
                        else:
                            self._editing_vertex_original_data = list(ann.data)  # type: ignore[arg-type]
                        event.accept()
                        return

                ann_id = self._annotation_id_at_scene_pos(scene_pos)
                if ctrl_pressed:
                    if ann_id is not None:
                        selected = list(self._selected_ann_ids)
                        if ann_id in selected:
                            selected = [x for x in selected if x != ann_id]
                        else:
                            selected.append(ann_id)
                        self.set_selected_annotations(selected)
                    event.accept()
                    return

                if ann_id is None:
                    self.set_selected_annotations([])
                    event.accept()
                    return

                if ann_id not in self._selected_ann_ids or len(self._selected_ann_ids) != 1:
                    self.set_selected_annotations([ann_id])

                visible_selected = [aid for aid in self._selected_ann_ids if aid in self.annotation_models]
                if ann_id in visible_selected:
                    self._dragging_ann_ids = list(visible_selected)
                    self._drag_start_scene = scene_pos
                    self._drag_original_data_map = {
                        selected_id: self.annotation_models[selected_id].data
                        for selected_id in self._dragging_ann_ids
                        if selected_id in self.annotation_models
                    }
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """마우스 이동 중 임시 도형, 드래그, 꼭짓점 편집 미리보기를 갱신한다."""
        raw_scene_pos = self.mapToScene(event.pos())
        scene_pos = self._clamp_point_to_image(raw_scene_pos)

        # handle right-button press-then-drag panning
        if event.buttons() & Qt.RightButton and getattr(self, "_pan_possible", False):
            cur = event.pos()
            # if not already panning, start when moved beyond a small threshold
            if not getattr(self, "_panning", False):
                dx0 = cur.x() - self._pan_start.x()
                dy0 = cur.y() - self._pan_start.y()
                if (dx0 * dx0 + dy0 * dy0) >= 9:  # threshold ~3 px
                    self._panning = True
                    self.setCursor(Qt.ClosedHandCursor)
            if getattr(self, "_panning", False):
                dx = cur.x() - self._pan_start.x()
                dy = cur.y() - self._pan_start.y()
                hbar = self.horizontalScrollBar()
                vbar = self.verticalScrollBar()
                hbar.setValue(hbar.value() - dx)
                vbar.setValue(vbar.value() - dy)
                self._pan_start = cur
                self._manual_view = True
                event.accept()
                return
            
        if self._mode == "box" and self._box_start_scene is not None:
            self._update_box_preview(scene_pos)
            event.accept()
            return

        if self._mode == "polygon":
            self._current_mouse_scene = scene_pos
            self._update_polygon_preview()
            event.accept()
            return

        if self._mode == "select" and self._editing_vertex_key is not None and self._editing_vertex_original_data is not None:
            ann_id, vertex_index = self._editing_vertex_key
            ann = self.annotation_models.get(ann_id)
            if ann is not None:
                new_data = self._edited_data_for_vertex_drag(ann, self._editing_vertex_original_data, vertex_index, scene_pos)
                self._update_annotation_visual(ann_id, new_data, update_model=True)
                self._set_hover_vertex_key((ann_id, vertex_index))
                event.accept()
                return

        if (
            self._mode == "select"
            and self._dragging_ann_ids
            and self._drag_start_scene is not None
            and self._drag_original_data_map
        ):
            dx = raw_scene_pos.x() - self._drag_start_scene.x()
            dy = raw_scene_pos.y() - self._drag_start_scene.y()
            for ann_id in self._dragging_ann_ids:
                ann = self.annotation_models.get(ann_id)
                original_data = self._drag_original_data_map.get(ann_id)
                if ann is None or original_data is None:
                    continue
                moved_data = self._translate_data(ann, original_data, dx, dy)
                self._update_annotation_visual(ann_id, moved_data, update_model=True)
            event.accept()
            return

        if self._mode == "select":
            self._set_hover_vertex_key(self._vertex_key_at_scene_pos(scene_pos))

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """마우스 버튼을 놓을 때 생성이나 편집 결과를 확정한다."""
        if self.pixmap_item is None:
            super().mouseReleaseEvent(event)
            return

        raw_scene_pos = self.mapToScene(event.pos())
        scene_pos = self._clamp_point_to_image(raw_scene_pos)

        if event.button() == Qt.RightButton:
            if getattr(self, "_panning", False):
                self._panning = False
                self.setCursor(Qt.ArrowCursor)
                self._manual_view = True
            self._pan_possible = False
            self._pan_start = None
            event.accept()
            return

        if self._mode == "box" and self._box_start_scene is not None and event.button() == Qt.LeftButton:
            rect = QRectF(self._box_start_scene, scene_pos).normalized()
            self._clear_temp_box()
            if rect.width() >= 3 and rect.height() >= 3:
                self.annotationCreateRequested.emit("box", (rect.x(), rect.y(), rect.width(), rect.height()))
                # 객체 생성 요청 슬롯에서 AI 박스 흐름일 경우 모드를 ai_refine으로 전환할 수 있다.
                # 해당 전환을 유지하기 위해 신호 발생 이후에도 박스 모드일 때만 select로 복귀한다.
                if self._mode == "box":
                    self.set_mode("select")
            else:
                self.statusMessage.emit("너무 작은 Box는 생성하지 않습니다.")
            event.accept()
            return

        if self._mode == "select" and self._editing_vertex_key is not None and self._editing_vertex_original_data is not None and event.button() == Qt.LeftButton:
            ann_id, vertex_index = self._editing_vertex_key
            ann = self.annotation_models.get(ann_id)
            if ann is not None:
                final_data = self._edited_data_for_vertex_drag(ann, self._editing_vertex_original_data, vertex_index, scene_pos)
                self.annotationsDataUpdateRequested.emit([(ann_id, final_data)])
            self._editing_vertex_key = None
            self._editing_vertex_original_data = None
            self._set_hover_vertex_key(self._vertex_key_at_scene_pos(scene_pos))
            event.accept()
            return

        if (
            self._mode == "select"
            and self._dragging_ann_ids
            and self._drag_start_scene is not None
            and self._drag_original_data_map
            and event.button() == Qt.LeftButton
        ):
            dx = raw_scene_pos.x() - self._drag_start_scene.x()
            dy = raw_scene_pos.y() - self._drag_start_scene.y()
            moved_payload = []
            if abs(dx) > 1e-6 or abs(dy) > 1e-6:
                for ann_id in self._dragging_ann_ids:
                    ann = self.annotation_models.get(ann_id)
                    original_data = self._drag_original_data_map.get(ann_id)
                    if ann is None or original_data is None:
                        continue
                    moved_data = self._translate_data(ann, original_data, dx, dy)
                    moved_payload.append((ann_id, self._clip_shape_data_to_image(ann, moved_data)))
                if moved_payload:
                    self.annotationsDataUpdateRequested.emit(moved_payload)

            self._dragging_ann_ids = []
            self._drag_start_scene = None
            self._drag_original_data_map = {}
            self._set_hover_vertex_key(self._vertex_key_at_scene_pos(scene_pos))
            event.accept()
            return

    def keyPressEvent(self, event):
        """키 입력 처리: Polygon 모드에서 Enter로 폴리곤 확정 처리한다."""
        # Handle Enter/Return to finalize polygon drawing
        try:
            key = event.key()
        except Exception:
            key = None
        if self._mode == "polygon" and key in (Qt.Key_Return, Qt.Key_Enter):
            if len(self._polygon_points) >= 3:
                pts = list(self._polygon_points)
                # clear temporary preview before emitting creation
                self._clear_polygon_preview()
                self._polygon_points.clear()
                self.annotationCreateRequested.emit("polygon", pts)
                # after creation, leave mode handling to the receiver (usually set to select)
            else:
                try:
                    self.statusMessage.emit("폴리곤은 최소 3개의 점이 필요합니다.")
                except Exception:
                    pass
            event.accept()
            return

        super().keyPressEvent(event)
        
    # ---------- 트랙킹 관련 메서드 ----------
