# 박스와 폴리곤 객체 표시 정보를 만들고 화면에 그리는 기능을 관리하는 파일입니다.
# 왼쪽 도구 버튼, 객체 표시 정보 생성 요청, 임시 그리기 미리보기를 담당합니다.
from typing import Dict, List, Optional, Tuple, Union

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
    QToolButton,
    QVBoxLayout,
)

from core.annotation.models import RenderAnnotation


Point = Tuple[float, float]
BoxData = Tuple[float, float, float, float]
PolygonData = List[Point]
ShapeData = Union[BoxData, PolygonData]


class ShapeAnnotationControllerMixin:
    def build_left_toolbar(self):
        """왼쪽 도구 패널에 박스와 폴리곤 생성 버튼을 만든다."""
        panel = QFrame()
        panel.setFixedWidth(110)
        panel.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.box_button = QToolButton()
        self.box_button.setText("Box")
        self.box_button.setCheckable(True)
        self.box_button.setMinimumHeight(54)
        self.box_button.clicked.connect(lambda checked: self.on_shape_tool_clicked("box", checked))
        layout.addWidget(self.box_button)

        self.polygon_button = QToolButton()
        self.polygon_button.setText("Polygon")
        self.polygon_button.setCheckable(True)
        self.polygon_button.setMinimumHeight(54)
        self.polygon_button.clicked.connect(lambda checked: self.on_shape_tool_clicked("polygon", checked))
        layout.addWidget(self.polygon_button)

        layout.addStretch()
        return panel

    def on_shape_tool_clicked(self, tool_name, checked):
        """도형 도구 버튼 선택 상태에 따라 작업 모드를 바꾼다."""
        self.set_tool_mode(tool_name if checked else "select")

    def set_tool_mode(self, mode):
        """작업 화면의 도형 생성 모드를 설정한다."""
        self.canvas.set_mode(mode)

    def on_canvas_mode_changed(self, mode):
        """작업 화면 모드 변경을 왼쪽 버튼과 상태 문구에 반영한다."""
        self.current_mode = mode
        self.box_button.blockSignals(True)
        self.polygon_button.blockSignals(True)
        self.box_button.setChecked(mode == "box")
        self.polygon_button.setChecked(mode == "polygon")
        self.box_button.blockSignals(False)
        self.polygon_button.blockSignals(False)

        if mode == "box":
            self.mode_label.setText("현재 상태: Box 생성 모드")
            self.show_status_message("Box 모드: 드래그해서 박스를 생성하세요.")
        elif mode == "polygon":
            self.mode_label.setText("현재 상태: Polygon 생성 모드")
            self.show_status_message("Polygon 모드: 좌클릭 점 추가, 우클릭 완료, Esc 취소")
        elif mode == "ai_point":
            self.mode_label.setText("현재 상태: AI Point 입력 모드")
            self.show_status_message("AI Point 모드: 대상 물체 위를 좌클릭하세요. (우클릭 취소)")
        elif mode == "ai_refine":
            self.mode_label.setText("현재 상태: AI Refine 모드")
            self.show_status_message("AI Refine 모드: 좌클릭 추가, 우클릭 제거")
        else:
            self.mode_label.setText("현재 상태: 기본 선택")

    def on_annotation_create_requested(self, shape_type, payload):
        """작업 화면에서 요청한 도형 생성을 실제 객체 표시 정보로 저장한다."""
        if self.source is None or self.current_index < 0:
            return

        # AI 상호작용 입력 기준 처리(임시 입력이며 객체 표시 정보로 저장하지 않음)
        if self.ai_interact_pending and self.ai_prompt_mode == "box" and shape_type == "box":
            self._run_ai_interact_with_box_prompt(payload)
            return

        label_id = self.current_working_label_id
        if label_id is not None and label_id not in self.labels_by_id:
            label_id = None
            self.current_working_label_id = None

        self.push_undo_state("객체 생성")

        if shape_type == "box":
            ann = self.store.add_box(self.current_index, payload, label_id)
        elif shape_type == "polygon":
            ann = self.store.add_polygon(self.current_index, payload, label_id)
        else:
            return

        self.refresh_annotations_for_current_frame([ann.ann_id])
        self.canvas.set_selected_annotations([ann.ann_id])
        self.sync_object_tree_selection([ann.ann_id])
        self.sync_label_list_view([ann.ann_id])
        self.canvas.set_mode("select")

        if label_id is None:
            self.show_status_message("객체 생성 완료. 라벨을 지정하세요.")
            self.prompt_create_label_for_annotations([ann.ann_id], record_undo=False)
        else:
            self.show_status_message(f"{self.annotation_display_text(ann)} 생성 완료")

    def on_annotations_data_update_requested(self, payload):
        """작업 화면에서 수정된 객체 표시 정보 좌표를 저장소에 반영한다."""
        if self.current_index < 0:
            return

        valid_payload = []
        for ann_id, new_data in payload or []:
            if self.store.get_annotation(self.current_index, ann_id) is not None:
                valid_payload.append((ann_id, new_data))

        if not valid_payload:
            return

        self.push_undo_state("객체 위치/형태 수정")

        selected_ids = self.get_selected_annotation_ids()
        updated_ids = []
        for ann_id, new_data in valid_payload:
            if self.store.update_annotation_data(self.current_index, ann_id, new_data):
                updated_ids.append(ann_id)
        if updated_ids:
            keep = list(dict.fromkeys(selected_ids + updated_ids))
            self.refresh_annotations_for_current_frame(keep)

    def cancel_current_drawing(self):
        """현재 진행 중인 그리기나 AI 상호작용 입력을 취소한다."""
        if self.ai_interact_pending:
            self._reset_ai_interact_prompt_state()
            self.show_status_message("AI Interact 입력 대기를 취소했습니다.")
            return
        if self.current_mode in ("box", "polygon", "ai_point"):
            self.canvas.cancel_temporary_drawing()
            self.canvas.set_mode("select")
            self.show_status_message("현재 생성 작업을 취소했습니다.")

    # ---------- 작업 화면 도형 ----------


class ShapeCanvasMixin:
    def _base_color_for_ann(self, ann: RenderAnnotation) -> QColor:
        """객체 표시 정보에 사용할 기본 색상을 반환한다."""
        return QColor(ann.color_hex or "#B0B0B0")

    def _shape_pen(self, ann: RenderAnnotation, selected=False):
        """도형 외곽선을 그릴 펜을 만든다."""
        color = QColor("#FFD84D") if selected else self._base_color_for_ann(ann)
        pen = QPen(color)
        pen.setWidthF(1.1 if selected else 0.85)
        pen.setCosmetic(True)
        return pen

    def _shape_brush(self, ann: RenderAnnotation, selected=False):
        """도형 내부를 옅게 채울 브러시를 만든다."""
        color = QColor("#FFD84D") if selected else self._base_color_for_ann(ann)
        alpha = 56 if selected else 38
        return QBrush(QColor(color.red(), color.green(), color.blue(), alpha))

    def _vertex_pen(self, ann: RenderAnnotation, selected=False, hovered=False):
        """꼭짓점 외곽선을 그릴 펜을 만든다."""
        if hovered:
            pen = QPen(QColor("#000000"))
            pen.setWidthF(1.05)
            pen.setCosmetic(True)
            return pen
        color = QColor("#FFD84D") if selected else self._base_color_for_ann(ann)
        pen = QPen(color)
        pen.setWidthF(0.95)
        pen.setCosmetic(True)
        return pen

    def _vertex_brush(self, ann: RenderAnnotation, selected=False, hovered=False):
        """꼭짓점 내부를 채울 브러시를 만든다."""
        if hovered:
            return QBrush(QColor("#FFFFFF"))
        color = QColor("#FFD84D") if selected else self._base_color_for_ann(ann)
        return QBrush(color)

    def _label_brush(self, ann: RenderAnnotation, selected=False):
        """객체 이름 텍스트를 칠할 브러시를 만든다."""
        return QBrush(QColor("#FFD84D") if selected else QColor("#FFFFFF"))

    # ---------- 좌표 계산 보조 함수 ----------

    def _label_position_for_annotation(self, ann: RenderAnnotation, data: ShapeData = None):
        """객체 이름 텍스트가 놓일 좌표를 계산한다."""
        data = ann.data if data is None else data
        if ann.shape_type == "box":
            x, y, w, h = data  # type: ignore[misc]
            return x, max(0, y - 18)
        pts = list(data)  # type: ignore[arg-type]
        if not pts:
            return 0.0, 0.0
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), max(0, min(ys) - 18)

    def _vertex_points_for_annotation(self, ann: RenderAnnotation, data: ShapeData = None):
        """박스나 폴리곤의 편집 가능한 꼭짓점 좌표를 반환한다."""
        data = ann.data if data is None else data
        if ann.shape_type == "box":
            x, y, w, h = data  # type: ignore[misc]
            return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return list(data)  # type: ignore[arg-type]

    def _create_vertex_item(self, x, y, ann_id: int, vertex_index: int):
        """작업 화면에 표시할 꼭짓점 그래픽 항목을 만든다."""
        radius = 2.6
        item = QGraphicsEllipseItem(x - radius, y - radius, radius * 2, radius * 2)
        item.setData(0, ann_id)
        item.setData(1, vertex_index)
        item.setZValue(15)
        return item

    def redraw_annotations(self, annotations: List[RenderAnnotation]):
        """현재 프레임의 모든 객체 표시 정보를 다시 그린다."""
        for item in list(self.annotation_items.values()):
            self.scene_obj.removeItem(item)
        for item in list(self.annotation_label_items.values()):
            self.scene_obj.removeItem(item)
        for vertex_items in list(self.annotation_vertex_items.values()):
            for item in vertex_items:
                self.scene_obj.removeItem(item)

        self.annotation_models = {ann.ann_id: ann for ann in annotations}
        self.annotation_items.clear()
        self.annotation_label_items.clear()
        self.annotation_vertex_items.clear()
        self._hover_vertex_key = None
        self._editing_vertex_key = None
        self._editing_vertex_original_data = None
        self._dragging_ann_ids = []
        self._drag_start_scene = None
        self._drag_original_data_map = {}

        for ann in annotations:
            if ann.shape_type == "box":
                x, y, w, h = ann.data  # type: ignore[misc]
                shape_item = QGraphicsRectItem(x, y, w, h)
            else:
                polygon = QPolygonF([QPointF(x, y) for x, y in ann.data])  # type: ignore[arg-type]
                shape_item = QGraphicsPolygonItem(polygon)
            shape_item.setData(0, ann.ann_id)
            shape_item.setZValue(10)
            self.scene_obj.addItem(shape_item)
            self.annotation_items[ann.ann_id] = shape_item

            text_item = QGraphicsSimpleTextItem(ann.overlay_text)
            text_item.setData(0, ann.ann_id)
            text_item.setZValue(20)
            self.scene_obj.addItem(text_item)
            self.annotation_label_items[ann.ann_id] = text_item

            vertex_items: List[QGraphicsEllipseItem] = []
            for idx, (vx, vy) in enumerate(self._vertex_points_for_annotation(ann)):
                vertex_item = self._create_vertex_item(vx, vy, ann.ann_id, idx)
                self.scene_obj.addItem(vertex_item)
                vertex_items.append(vertex_item)
            self.annotation_vertex_items[ann.ann_id] = vertex_items

        self._apply_selection_styles()

    def _update_annotation_visual(self, ann_id: int, data: ShapeData, update_model: bool = True):
        """한 객체 표시 정보의 도형, 라벨 위치, 꼭짓점을 갱신한다."""
        ann = self.annotation_models.get(ann_id)
        item = self.annotation_items.get(ann_id)
        text_item = self.annotation_label_items.get(ann_id)
        vertex_items = self.annotation_vertex_items.get(ann_id)
        if ann is None or item is None or text_item is None or vertex_items is None:
            return
        if update_model:
            ann.data = data
        if ann.shape_type == "box":
            x, y, w, h = data  # type: ignore[misc]
            item.setRect(x, y, w, h)
        else:
            polygon = QPolygonF([QPointF(x, y) for x, y in data])  # type: ignore[arg-type]
            item.setPolygon(polygon)

        tx, ty = self._label_position_for_annotation(ann, data)
        text_item.setPos(tx, ty)

        points = self._vertex_points_for_annotation(ann, data)
        radius = 2.6
        for i, (vx, vy) in enumerate(points):
            if i < len(vertex_items):
                vertex_items[i].setRect(vx - radius, vy - radius, radius * 2, radius * 2)

    def _apply_selection_styles(self):
        """선택 여부와 마우스 올림 상태에 맞춰 도형 스타일을 적용한다."""
        selected_set = set(self._selected_ann_ids)
        for ann_id, item in self.annotation_items.items():
            ann = self.annotation_models[ann_id]
            selected = ann_id in selected_set
            item.setPen(self._shape_pen(ann, selected))
            item.setBrush(self._shape_brush(ann, selected))

        for ann_id, text_item in self.annotation_label_items.items():
            ann = self.annotation_models[ann_id]
            text_item.setBrush(self._label_brush(ann, ann_id in selected_set))
            tx, ty = self._label_position_for_annotation(ann)
            text_item.setPos(tx, ty)

        for ann_id, vertex_items in self.annotation_vertex_items.items():
            ann = self.annotation_models[ann_id]
            selected = ann_id in selected_set
            for idx, vertex_item in enumerate(vertex_items):
                hovered = (ann_id, idx) == self._hover_vertex_key
                vertex_item.setPen(self._vertex_pen(ann, selected, hovered))
                vertex_item.setBrush(self._vertex_brush(ann, selected, hovered))

    def set_selected_annotations(self, ann_ids):
        """선택된 객체 표시 정보 ID 목록을 설정하고 화면 스타일을 갱신한다."""
        filtered: List[int] = []
        for ann_id in ann_ids or []:
            ann_id = int(ann_id)
            if ann_id not in filtered:
                filtered.append(ann_id)
        if filtered == self._selected_ann_ids:
            self._apply_selection_styles()
            return
        self._selected_ann_ids = filtered
        self._set_hover_vertex_key(None)
        self._apply_selection_styles()
        self.selectionChanged.emit(list(self._selected_ann_ids))

    def select_annotation(self, ann_id: Optional[int]):
        """단일 객체 표시 정보를 선택하거나 선택을 해제한다."""
        self.set_selected_annotations([] if ann_id is None else [ann_id])

    # ---------- 임시 그리기 ----------

    def _remove_graphics_item_safe(self, item):
        """이미 삭제되었을 수 있는 그래픽 항목을 안전하게 제거한다."""
        if item is None:
            return
        try:
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)
        except RuntimeError:
            # scene.clear() 처리 중에는 감싸진 C++ 항목이 이미 삭제되었을 수 있다.
            pass

    def _clear_temp_box(self):
        """임시 박스 미리보기를 지운다."""
        if self._temp_box_item is not None:
            self._remove_graphics_item_safe(self._temp_box_item)
            self._temp_box_item = None
        self._box_start_scene = None

    def _clear_polygon_preview(self):
        """임시 폴리곤 미리보기를 지운다."""
        if self._polygon_preview_item is not None:
            self._remove_graphics_item_safe(self._polygon_preview_item)
            self._polygon_preview_item = None
        for item in self._polygon_vertex_preview_items:
            self._remove_graphics_item_safe(item)
        self._polygon_vertex_preview_items.clear()
        self._current_mouse_scene = None

    def cancel_temporary_drawing(self):
        """박스, 폴리곤, AI 미리보기 등 임시 그리기를 모두 취소한다."""
        self._clear_temp_box()
        self._polygon_points.clear()
        self._clear_polygon_preview()
        self.clear_ai_interact_preview()

    def clear_ai_interact_preview(self):
        """AI 상호작용 결과 미리보기와 입력 점 표시를 지운다."""
        if self._ai_mask_preview_item is not None:
            self._remove_graphics_item_safe(self._ai_mask_preview_item)
            self._ai_mask_preview_item = None
        for item in self._ai_point_preview_items:
            self._remove_graphics_item_safe(item)
        self._ai_point_preview_items.clear()

    def show_ai_interact_preview(self, polygon: List[Point], prompt_points: List[Tuple[Point, int]]):
        """AI 상호작용 결과 폴리곤과 입력 점을 작업 화면에 미리 표시한다."""
        self.clear_ai_interact_preview()
        if polygon:
            path = QPainterPath()
            first = polygon[0]
            path.moveTo(first[0], first[1])
            for x, y in polygon[1:]:
                path.lineTo(x, y)
            path.closeSubpath()
            self._ai_mask_preview_item = QGraphicsPathItem(path)
            preview_pen = QPen(QColor("#4CAF50"))
            preview_pen.setWidthF(1.2)
            preview_pen.setCosmetic(True)
            preview_pen.setStyle(Qt.DashLine)
            self._ai_mask_preview_item.setPen(preview_pen)
            self._ai_mask_preview_item.setBrush(QBrush(QColor(76, 175, 80, 40)))
            self._ai_mask_preview_item.setZValue(28)
            self.scene_obj.addItem(self._ai_mask_preview_item)

        for (x, y), label in prompt_points:
            color = QColor("#00FF00") if label == 1 else QColor("#FF4444")
            item = QGraphicsEllipseItem(x - 4, y - 4, 8, 8)
            item.setPen(QPen(QColor("#000000")))
            item.setBrush(QBrush(color))
            item.setZValue(29)
            self.scene_obj.addItem(item)
            self._ai_point_preview_items.append(item)

    def _update_box_preview(self, end_scene: QPointF):
        """박스 드래그 중 임시 박스 크기를 갱신한다."""
        if self._box_start_scene is None:
            return
        start = self._box_start_scene
        rect = QRectF(start, end_scene).normalized()
        if self._temp_box_item is None:
            self._temp_box_item = QGraphicsRectItem(rect)
            preview_pen = QPen(QColor("#47A3FF"))
            preview_pen.setWidthF(0.95)
            preview_pen.setCosmetic(True)
            self._temp_box_item.setPen(preview_pen)
            self._temp_box_item.setBrush(QBrush(QColor(71, 163, 255, 30)))
            self._temp_box_item.setZValue(30)
            self.scene_obj.addItem(self._temp_box_item)
        else:
            self._temp_box_item.setRect(rect)

    def _update_polygon_preview(self):
        """폴리곤 생성 중 점과 선 미리보기를 갱신한다."""
        if not self._polygon_points:
            self._clear_polygon_preview()
            return

        if self._polygon_preview_item is None:
            self._polygon_preview_item = QGraphicsPathItem()
            preview_pen = QPen(QColor("#47A3FF"))
            preview_pen.setWidthF(0.95)
            preview_pen.setCosmetic(True)
            self._polygon_preview_item.setPen(preview_pen)
            self._polygon_preview_item.setBrush(QBrush(QColor(71, 163, 255, 22)))
            self._polygon_preview_item.setZValue(30)
            self.scene_obj.addItem(self._polygon_preview_item)

        path = QPainterPath()
        first = self._polygon_points[0]
        path.moveTo(first[0], first[1])
        for x, y in self._polygon_points[1:]:
            path.lineTo(x, y)
        if self._current_mouse_scene is not None:
            path.lineTo(self._current_mouse_scene.x(), self._current_mouse_scene.y())
        self._polygon_preview_item.setPath(path)

        for item in self._polygon_vertex_preview_items:
            self.scene_obj.removeItem(item)
        self._polygon_vertex_preview_items.clear()

        radius = 2.6
        for x, y in self._polygon_points:
            item = QGraphicsEllipseItem(x - radius, y - radius, radius * 2, radius * 2)
            item.setPen(QPen(QColor("#47A3FF")))
            item.setBrush(QBrush(QColor("#47A3FF")))
            item.setZValue(31)
            self.scene_obj.addItem(item)
            self._polygon_vertex_preview_items.append(item)

    # ---------- 우클릭 메뉴 ----------

    def set_tracking_mode(self, is_tracking: bool):
        """트랙킹 모드 설정"""
        self._is_tracking = is_tracking
        self.statusMessage.emit(
            "트랙킹 진행 중... (중지 버튼 누르면 저장됨)" if is_tracking else "트랙킹 준비 완료"
        )

    def update_tracking_progress(self, current_frame: int, end_frame: int):
        """트랙킹 진행률 업데이트"""
        if self._is_tracking:
            progress_text = f"트랙킹 중: {current_frame}/{end_frame}"
            self._tracking_progress_text = progress_text
            self.statusMessage.emit(progress_text)

    def end_tracking(self):
        """트랙킹 종료"""
        self._is_tracking = False
        self._tracking_progress_text = ""
        self.statusMessage.emit("트랙킹 완료")
