# 가운데 작업 화면을 만드는 파일입니다.
# 이미지 표시, 기본 보기 설정, 작업 화면 신호 정의를 담당합니다.
from typing import Dict, List, Optional, Tuple, Union

from PyQt5.QtCore import QPointF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QSizePolicy,
)

from core.annotation.models import RenderAnnotation
from features.mouse_event.controller import MouseEventControllerMixin
from features.shape_annotation.controller import ShapeCanvasMixin


Point = Tuple[float, float]
BoxData = Tuple[float, float, float, float]
PolygonData = List[Point]
ShapeData = Union[BoxData, PolygonData]


class AnnotationCanvas(
    MouseEventControllerMixin,
    ShapeCanvasMixin,
    QGraphicsView,
):
    modeChanged = pyqtSignal(str)
    annotationCreateRequested = pyqtSignal(str, object)
    aiPromptPointRequested = pyqtSignal(float, float, int)
    selectionChanged = pyqtSignal(object)  # 선택된 객체 표시 정보 ID 목록
    annotationsDataUpdateRequested = pyqtSignal(object)  # 수정할 객체 표시 정보 ID와 도형 데이터 목록
    statusMessage = pyqtSignal(str)
    trackingStartRequested = pyqtSignal()  # 트랙킹 시작
    trackingStopRequested = pyqtSignal()  # 트랙킹 중지

    def __init__(self):
        """작업 화면의 장면, 보기 옵션, 임시 상태를 초기화한다."""
        super().__init__()
        self.scene_obj = QGraphicsScene(self)
        self.setScene(self.scene_obj)
        self.pixmap_item = None

        self.setStyleSheet("background-color: #2b2b2b;")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        self._mode = "select"
        self._selected_ann_ids: List[int] = []
        
        # 트랙킹 관련
        self._is_tracking = False
        self._tracking_progress_text = ""

        self.annotation_models: Dict[int, RenderAnnotation] = {}
        self.annotation_items: Dict[int, object] = {}
        self.annotation_label_items: Dict[int, QGraphicsSimpleTextItem] = {}
        self.annotation_vertex_items: Dict[int, List[QGraphicsEllipseItem]] = {}

        self._box_start_scene: Optional[QPointF] = None
        self._temp_box_item: Optional[QGraphicsRectItem] = None

        self._polygon_points: List[Point] = []
        self._polygon_preview_item: Optional[QGraphicsPathItem] = None
        self._polygon_vertex_preview_items: List[QGraphicsEllipseItem] = []
        self._current_mouse_scene: Optional[QPointF] = None

        self._ai_mask_preview_item: Optional[QGraphicsPathItem] = None
        self._ai_point_preview_items: List[QGraphicsEllipseItem] = []

        self._dragging_ann_ids: List[int] = []
        self._drag_start_scene: Optional[QPointF] = None
        self._drag_original_data_map: Dict[int, ShapeData] = {}

        self._hover_vertex_key: Optional[Tuple[int, int]] = None
        self._editing_vertex_key: Optional[Tuple[int, int]] = None
        self._editing_vertex_original_data: Optional[ShapeData] = None

        self._manual_view = False
        # panning state for right-button drag
        self._panning = False
        self._pan_start = None
        # whether a right-button press may start panning when moved
        self._pan_possible = False
        self._last_pixmap_size: Optional[Tuple[int, int]] = None

        self.show_placeholder("Open Frames 또는 Open Video로 미디어를 선택하세요.")

    # ---------- 기본 상태 ----------

    def selected_annotation_ids(self):
        """현재 선택된 객체 표시 정보 ID 목록을 반환한다."""
        return list(self._selected_ann_ids)

    def selected_annotation_id(self):
        """현재 선택된 첫 번째 객체 표시 정보 ID를 반환한다."""
        return self._selected_ann_ids[0] if self._selected_ann_ids else None

    def set_mode(self, mode: str):
        """작업 화면의 입력 모드를 변경하고 필요한 임시 표시를 정리한다."""
        if mode not in ("select", "box", "polygon", "ai_point", "ai_refine"):
            mode = "select"
        if self._mode != mode:
            self._mode = mode
            self.modeChanged.emit(mode)
            if mode != "select":
                self._set_hover_vertex_key(None)
            if mode != "ai_refine":
                self.clear_ai_interact_preview()

    def show_placeholder(self, text: str):
        """미디어가 없거나 표시할 수 없을 때 안내 문구만 보여준다."""
        self.scene_obj.clear()
        self.pixmap_item = None
        self.annotation_models.clear()
        self.annotation_items.clear()
        self.annotation_label_items.clear()
        self.annotation_vertex_items.clear()
        self._temp_box_item = None
        self._box_start_scene = None
        self._polygon_points.clear()
        self._polygon_preview_item = None
        self._polygon_vertex_preview_items.clear()
        self._current_mouse_scene = None
        self._ai_mask_preview_item = None
        self._ai_point_preview_items.clear()
        self._selected_ann_ids.clear()
        self._hover_vertex_key = None
        self._editing_vertex_key = None
        self._editing_vertex_original_data = None
        self.resetTransform()
        self._manual_view = False
        self.scene_obj.setSceneRect(0, 0, 1200, 800)
        item = self.scene_obj.addText(text)
        item.setDefaultTextColor(QColor("#DDDDDD"))
        item.setPos(30, 30)

    def fit_to_image(self):
        """현재 이미지 또는 장면 전체가 화면에 맞도록 배율을 조정한다."""
        if self.pixmap_item is not None:
            self.resetTransform()
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            self._manual_view = False
        else:
            self.resetTransform()
            self.fitInView(self.scene_obj.sceneRect(), Qt.KeepAspectRatio)
            self._manual_view = False

    def refresh_fit(self):
        """사용자가 직접 확대/이동하지 않은 상태일 때 화면 맞춤을 갱신한다."""
        if not self._manual_view:
            self.fit_to_image()

    def set_pixmap(self, pixmap):
        """새 프레임 이미지를 작업 화면에 표시하고 기존 임시 표시를 정리한다."""
        preserve_manual = (
            self._manual_view
            and self.pixmap_item is not None
            and self._last_pixmap_size == (pixmap.width(), pixmap.height())
        )
        old_transform = self.transform()
        old_h = self.horizontalScrollBar().value()
        old_v = self.verticalScrollBar().value()

        # scene.clear() 전에 임시 미리보기 항목을 지워 이미 삭제된 C++ 객체 참조를 피한다.
        self._clear_temp_box()
        self._polygon_points.clear()
        self._clear_polygon_preview()
        self.clear_ai_interact_preview()
        self.scene_obj.clear()
        self.pixmap_item = None
        self.annotation_models.clear()
        self.annotation_items.clear()
        self.annotation_label_items.clear()
        self.annotation_vertex_items.clear()
        self._hover_vertex_key = None
        self._editing_vertex_key = None
        self._editing_vertex_original_data = None

        if pixmap.isNull():
            self.show_placeholder("현재 프레임을 표시할 수 없습니다.")
            return

        self.pixmap_item = self.scene_obj.addPixmap(pixmap)
        self.pixmap_item.setZValue(0)
        self.scene_obj.setSceneRect(self.pixmap_item.boundingRect())
        self._last_pixmap_size = (pixmap.width(), pixmap.height())

        if preserve_manual:
            self.setTransform(old_transform)
            QTimer.singleShot(0, lambda: self._restore_scrollbars(old_h, old_v))
        else:
            self.fit_to_image()

    def _restore_scrollbars(self, h, v):
        """프레임 교체 후 이전 스크롤 위치를 되돌린다."""
        self.horizontalScrollBar().setValue(h)
        self.verticalScrollBar().setValue(v)

    def resizeEvent(self, event):
        """작업 화면 크기가 바뀔 때 자동 맞춤 상태를 유지한다."""
        super().resizeEvent(event)
        if not self._manual_view:
            self.fit_to_image()
