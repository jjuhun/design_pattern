# 전체 프로그램 창을 조립하는 파일입니다.
# 실제 기능은 기능별 조합 클래스들이 맡고, 이 파일은 상태 초기화와 연결만 담당합니다.
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import QThread, Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QMainWindow,
    QShortcut,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTreeWidget,
    QHeaderView,
)

from canvas import AnnotationCanvas
from core.annotation.models import AnnotationStore, ClipboardAnnotation, LabelDef
from features.ai_interact.controller import AIInteractControllerMixin
from features.ai_tracking.controller import AITrackingControllerMixin, TrackingWorker
# 여기서부터 수정하고: 연속 복붙 기능 mixin import를 추가했다.
from features.copy_sequence.controller import CopySequenceControllerMixin
# 여기까지 수정했다: 연속 복붙 기능 mixin import를 추가했다.
from features.frame_panel.controller import FramePanelControllerMixin
from features.frame_panel.sources import FrameSourceBase
from features.right_panel.controller import RightPanelControllerMixin
from features.shape_annotation.controller import ShapeAnnotationControllerMixin
from features.top_panel.controller import TopPanelControllerMixin


class MainWindow(
    TopPanelControllerMixin,
    FramePanelControllerMixin,
    RightPanelControllerMixin,
    AIInteractControllerMixin,
    AITrackingControllerMixin,
    # 여기서부터 수정하고: 연속 복붙 기능 mixin을 MainWindow에 연결했다.
    CopySequenceControllerMixin,
    # 여기까지 수정했다: 연속 복붙 기능 mixin을 MainWindow에 연결했다.
    ShapeAnnotationControllerMixin,
    QMainWindow,
):
    def __init__(self):
        """메인 창의 기본 상태와 주요 위젯을 초기화한다."""
        super().__init__()
        self.setWindowTitle("Segment Labeling UI")
        self.resize(1600, 900)
        # auto_save 관련 변수 : 자동 저장 타이머 상태를 추가.
        self.auto_save_timer = None
        self.auto_save(n=1)
        
        self.source: Optional[FrameSourceBase] = None
        self.current_index = -1
        self.current_mode = "select"
        self.current_working_label_id: Optional[int] = None
        self.annotation_clipboard: List[ClipboardAnnotation] = []
        self.undo_stack: List[Tuple[str, dict]] = []
        self.redo_stack: List[Tuple[str, dict]] = []
        self.max_undo_steps = 100

        self._syncing_object_tree = False
        self._syncing_label_list = False
        self._syncing_timeline = False
        self._timeline_anchor_pair: Optional[Tuple[int, int]] = None

        self.store = AnnotationStore()
        self.labels_by_id: Dict[int, LabelDef] = {}
        self.label_order: List[int] = []
        self.next_label_id = 1

        # 타임라인 라벨 필터 상태: None은 미지정, 그 외에는 정수 라벨 ID를 뜻한다.
        self.timeline_filter_state: Dict[Optional[int], bool] = {None: True}
        
        # 트랙킹 관련
        self.tracking_engine = None
        self.is_tracking = False
        self.tracking_start_frame = -1
        self.tracking_end_frame = -1
        self.tracking_thread: Optional[QThread] = None
        self.tracking_worker: Optional[TrackingWorker] = None
        self.tracking_seed_track_id: Optional[int] = None
        self.tracking_seed_label_id: Optional[int] = None
        self.follow_tracking_frames_live = True
        self.tracking_live_follow_stride = 1
        
        # AI 단일 프레임 상호작용 입력 대기 상태
        self.ai_interact_pending = False
        self.ai_prompt_mode: Optional[str] = None  # 가능한 값: "box", "point", "refine"
        self.ai_pending_model_type = "sam2"
        self.ai_pending_box = None
        self.ai_refinement_points = []
        self.ai_refinement_labels = []
        self.ai_pending_mask = None
        self.ai_pending_polygon = None

        self.canvas = AnnotationCanvas()

        self.object_tree = QTreeWidget()
        self.object_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.object_tree.setRootIsDecorated(False)
        self.object_tree.setAlternatingRowColors(True)
        self.object_tree.setHeaderLabels(["Object", "Label", "Show"])
        self.object_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.object_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.object_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.label_list = QListWidget()
        self.label_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.timeline_tree = QTreeWidget()
        self.timeline_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.timeline_tree.setRootIsDecorated(False)
        self.timeline_tree.setAlternatingRowColors(True)
        self.timeline_tree.setHeaderLabels(["Frame", "Class", "ID"])
        self.timeline_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.timeline_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.timeline_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.timeline_tree.itemClicked.connect(self.on_timeline_item_clicked)

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setEnabled(False)
        self.frame_slider.valueChanged.connect(self.go_to_frame)

        self.frame_spin = QSpinBox()
        self.frame_spin.setEnabled(False)
        self.frame_spin.valueChanged.connect(self.go_to_frame)
        self.total_frames_label = QLabel("/ 0")

        self.media_label = QLabel("소스 없음")
        self.frame_name_label = QLabel("프레임 없음")
        self.mode_label = QLabel("현재 상태: 기본 선택")

        self.undo_button = None
        self.redo_button = None
        self.first_button = None
        self.back10_button = None
        self.prev_button = None
        self.play_button = None
        self.next_button = None
        self.forward10_button = None
        self.last_button = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance_playback)

        self.right_tabs: Optional[QTabWidget] = None
        self.objects_tab = None
        self.labels_tab = None
        self.timeline_tab = None
        self.ai_tools_tab = None
        # 여기서부터 수정하고: 오른쪽 패널의 Copy Sequence 전용 탭 상태를 추가했다.
        self.copy_sequence_tab = None
        # 여기까지 수정했다: 오른쪽 패널의 Copy Sequence 전용 탭 상태를 추가했다.
        self.timeline_filter_button = None
        self.timeline_filter_menu = None
        # 여기서부터 수정하고: AI Tools 입력 방식과 SAM3 text prompt 위젯 상태를 추가했다.
        self.ai_interactor_combo = None
        self.ai_label_selector = None
        self.ai_create_label_button = None
        self.ai_start_with_bbox_checkbox = None
        self.ai_prompt_mode_button_group = None
        self.ai_bbox_prompt_checkbox = None
        self.ai_pointer_prompt_checkbox = None
        self.ai_text_prompt_container = None
        self.ai_text_prompt_input = None
        self.ai_interact_button = None
        # 여기까지 수정했다: AI Tools 입력 방식과 SAM3 text prompt 위젯 상태를 추가했다.
        self.ai_tracking_status_label = None
        self.ai_tracking_progress_label = None
        self.ai_tracking_progress_bar = None
        self.ai_tracking_stop_btn = None
        # 여기서부터 수정하고: 오른쪽 패널의 연속 복붙 버튼 상태를 추가했다.
        self.copy_sequence_button = None
        # 여기까지 수정했다: 오른쪽 패널의 연속 복붙 버튼 상태를 추가했다.

        self.create_top_toolbar()
        self.build_ui()
        self.create_shortcuts()
        self.connect_canvas_signals()
        self.connect_widget_signals()

        self.statusBar().showMessage("준비 완료")
        self._refresh_transport_enabled(False)
        self.refresh_label_list()
        self.refresh_timeline_filter_menu()
        self.refresh_timeline_tree()

    # ---------- 화면 구성 ----------

    def create_shortcuts(self):
        """전역 단축키와 연결될 동작을 등록한다."""
        QShortcut(QKeySequence.Delete, self, activated=self.handle_delete_key)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.cancel_current_drawing)
        QShortcut(QKeySequence.Copy, self, activated=self.copy_selected_annotations)
        QShortcut(QKeySequence.Paste, self, activated=self.paste_annotations)
        QShortcut(QKeySequence.Undo, self, activated=self.undo_last_action)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo_last_action)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.redo_last_action)

    def connect_canvas_signals(self):
        """작업 화면에서 발생하는 신호를 메인 창 동작에 연결한다."""
        self.canvas.modeChanged.connect(self.on_canvas_mode_changed)
        self.canvas.annotationCreateRequested.connect(self.on_annotation_create_requested)
        self.canvas.aiPromptPointRequested.connect(self.on_canvas_ai_prompt_point_requested)
        self.canvas.selectionChanged.connect(self.on_canvas_selection_changed)
        self.canvas.annotationsDataUpdateRequested.connect(self.on_annotations_data_update_requested)
        self.canvas.statusMessage.connect(self.show_status_message)

    def connect_widget_signals(self):
        """오른쪽 패널 위젯의 선택 변경 신호를 연결한다."""
        self.object_tree.itemSelectionChanged.connect(self.on_object_tree_selection_changed)
        self.label_list.itemSelectionChanged.connect(self.on_label_list_selection_changed)
        self.timeline_tree.itemSelectionChanged.connect(self.on_timeline_tree_selection_changed)

    def show_status_message(self, text):
        """상태 표시줄에 짧은 안내 메시지를 보여준다."""
        self.statusBar().showMessage(text, 4000)

    def closeEvent(self, event):
        """창이 닫힐 때 재생과 열린 프레임 소스를 정리한다."""
        if self.timer.isActive():
            self.timer.stop()
        self.close_current_source()
        super().closeEvent(event)
