# 오른쪽 패널 전체를 관리하는 파일입니다.
# 객체, 라벨, 타임라인, AI 도구 탭의 목록 갱신과 선택 동기화를 담당합니다.
from functools import partial
from typing import Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.annotation.models import Annotation, LabelDef, RenderAnnotation
from core.common.constants import LABEL_COLOR_PALETTE
from core.dialogs.dialogs import LabelEditDialog


class RightPanelControllerMixin:
    def build_right_panel(self):
        """오른쪽 탭 패널을 만들고 각 탭의 버튼과 목록을 배치한다."""
        self.right_tabs = QTabWidget()
        self.right_tabs.setFixedWidth(420)
        self.right_tabs.currentChanged.connect(self.on_right_tab_changed)

        # 객체 목록 탭
        self.objects_tab = QWidget()
        objects_layout = QVBoxLayout(self.objects_tab)
        objects_layout.addWidget(QLabel("Objects"))
        objects_layout.addWidget(self.object_tree)

        delete_obj_btn = QPushButton("Delete Selected Object")
        delete_obj_btn.clicked.connect(self.delete_selected_object)
        objects_layout.addWidget(delete_obj_btn)

        object_help = QLabel("객체 행에서 라벨 드롭다운으로 바로 변경하고, 눈 버튼으로 보이기/숨기기를 전환할 수 있습니다.")
        object_help.setWordWrap(True)
        objects_layout.addWidget(object_help)

        # 라벨 목록 탭
        self.labels_tab = QWidget()
        labels_layout = QVBoxLayout(self.labels_tab)
        labels_layout.addWidget(QLabel("Labels"))
        labels_layout.addWidget(self.label_list)

        add_label_btn = QPushButton("Add Label")
        add_label_btn.clicked.connect(self.add_label)
        labels_layout.addWidget(add_label_btn)

        edit_label_btn = QPushButton("Edit Selected Label")
        edit_label_btn.clicked.connect(self.edit_selected_label)
        labels_layout.addWidget(edit_label_btn)

        delete_label_btn = QPushButton("Delete Selected Label")
        delete_label_btn.clicked.connect(self.delete_selected_label)
        labels_layout.addWidget(delete_label_btn)

        label_help = QLabel("도형 없이 라벨만 선택하면 기본 작업 라벨이 유지되고, 선택 객체가 있으면 라벨 변경 확인창 후 적용됩니다.")
        label_help.setWordWrap(True)
        labels_layout.addWidget(label_help)
        labels_layout.addStretch()

        # 타임라인 탭
        self.timeline_tab = QWidget()
        timeline_layout = QVBoxLayout(self.timeline_tab)
        top_filter_layout = QHBoxLayout()
        top_filter_layout.addWidget(QLabel("Filter"))
        self.timeline_filter_button = QToolButton()
        self.timeline_filter_button.setText("라벨 필터 ▼")
        self.timeline_filter_button.setPopupMode(QToolButton.InstantPopup)
        self.timeline_filter_menu = QMenu(self)
        self.timeline_filter_button.setMenu(self.timeline_filter_menu)
        top_filter_layout.addWidget(self.timeline_filter_button)
        top_filter_layout.addStretch()
        timeline_layout.addLayout(top_filter_layout)
        timeline_layout.addWidget(self.timeline_tree)

        timeline_delete_btn = QPushButton("Delete Selected Annotation")
        timeline_delete_btn.clicked.connect(self.delete_selected_timeline_annotations)
        timeline_layout.addWidget(timeline_delete_btn)

        timeline_help = QLabel("프레임별 annotation 목록입니다. 삭제만 지원하며, 라벨 필터는 펼침 메뉴에서 제어합니다.")
        timeline_help.setWordWrap(True)
        timeline_layout.addWidget(timeline_help)

        # AI 도구 탭(단일 프레임 상호작용)
        self.ai_tools_tab = QWidget()
        ai_layout = QVBoxLayout(self.ai_tools_tab)
        ai_layout.addWidget(QLabel("AI Tools"))

        # 여기서부터 수정하고: Interact 영역을 별도 그룹으로 묶고 bbox/pointer/text prompt UI를 추가했다.
        interact_group = QGroupBox("Interact")
        interact_layout = QVBoxLayout(interact_group)

        interact_layout.addWidget(QLabel("Interactor"))
        self.ai_interactor_combo = QComboBox()
        self.ai_interactor_combo.addItem("Segment Anything 2.0", "sam2")
        self.ai_interactor_combo.addItem("Segment Anything 3.0", "sam3")
        interact_layout.addWidget(self.ai_interactor_combo)

        interact_layout.addWidget(QLabel("작업 라벨"))
        label_select_layout = QHBoxLayout()
        self.ai_label_selector = QComboBox()
        label_select_layout.addWidget(self.ai_label_selector)
        self.ai_create_label_button = QPushButton("새 라벨")
        label_select_layout.addWidget(self.ai_create_label_button)
        interact_layout.addLayout(label_select_layout)

        interact_layout.addWidget(QLabel("Prompt input"))
        prompt_input_layout = QHBoxLayout()
        self.ai_prompt_mode_button_group = QButtonGroup(self)
        self.ai_prompt_mode_button_group.setExclusive(True)
        self.ai_bbox_prompt_checkbox = QCheckBox("bbox")
        self.ai_pointer_prompt_checkbox = QCheckBox("pointer")
        self.ai_bbox_prompt_checkbox.setChecked(True)
        self.ai_prompt_mode_button_group.addButton(self.ai_bbox_prompt_checkbox)
        self.ai_prompt_mode_button_group.addButton(self.ai_pointer_prompt_checkbox)
        prompt_input_layout.addWidget(self.ai_bbox_prompt_checkbox)
        prompt_input_layout.addWidget(self.ai_pointer_prompt_checkbox)
        prompt_input_layout.addStretch()
        interact_layout.addLayout(prompt_input_layout)

        self.ai_text_prompt_container = QWidget()
        text_prompt_layout = QVBoxLayout(self.ai_text_prompt_container)
        text_prompt_layout.setContentsMargins(0, 0, 0, 0)
        text_prompt_layout.addWidget(QLabel("Text prompt"))
        self.ai_text_prompt_input = QLineEdit()
        self.ai_text_prompt_input.setPlaceholderText("SAM3 prompt")
        text_prompt_layout.addWidget(self.ai_text_prompt_input)
        self.ai_text_prompt_container.setVisible(False)
        interact_layout.addWidget(self.ai_text_prompt_container)

        self.ai_interact_button = QPushButton("Interact")
        self.ai_interact_button.clicked.connect(self.on_ai_interact_clicked)
        self.ai_label_selector.currentIndexChanged.connect(self.on_ai_label_selector_changed)
        self.ai_create_label_button.clicked.connect(self.on_ai_create_label_clicked)
        self.ai_interactor_combo.currentIndexChanged.connect(self.on_ai_interactor_changed)
        interact_layout.addWidget(self.ai_interact_button)

        ai_help = QLabel("Interact 클릭 후 메인 화면에서 박스를 그리거나 점을 찍으면 자동 분할됩니다.")
        ai_help.setWordWrap(True)
        interact_layout.addWidget(ai_help)
        ai_layout.addWidget(interact_group)
        self.on_ai_interactor_changed(self.ai_interactor_combo.currentIndex())
        # 여기까지 수정했다: Interact 영역을 별도 그룹으로 묶고 bbox/pointer/text prompt UI를 추가했다.

        # 여기서부터 수정하고: Tracking 영역을 Interact와 시각적으로 분리했다.
        tracking_group = QGroupBox("Tracking")
        tracking_layout = QVBoxLayout(tracking_group)

        tracking_button_layout = QHBoxLayout()
        self.tracking_start_btn = QPushButton("▶ Start Tracking")
        self.tracking_start_btn.clicked.connect(self.on_start_tracking)
        self.tracking_start_btn.setEnabled(False)
        tracking_button_layout.addWidget(self.tracking_start_btn)

        self.tracking_stop_btn = QPushButton("⏹ Stop Tracking")
        self.tracking_stop_btn.clicked.connect(self.on_stop_tracking)
        self.tracking_stop_btn.setEnabled(False)
        tracking_button_layout.addWidget(self.tracking_stop_btn)
        tracking_layout.addLayout(tracking_button_layout)
        self.ai_tracking_stop_btn = self.tracking_stop_btn

        self.ai_tracking_status_label = QLabel("상태: 준비 중")
        tracking_layout.addWidget(self.ai_tracking_status_label)

        self.ai_tracking_progress_label = QLabel("Tracking 0% (0/0)")
        tracking_layout.addWidget(self.ai_tracking_progress_label)

        self.ai_tracking_progress_bar = QProgressBar()
        self.ai_tracking_progress_bar.setRange(0, 100)
        self.ai_tracking_progress_bar.setValue(0)
        self.ai_tracking_progress_bar.setFormat("Tracking %p%")
        self.ai_tracking_progress_bar.setTextVisible(True)
        tracking_layout.addWidget(self.ai_tracking_progress_bar)
        ai_layout.addWidget(tracking_group)
        # 여기까지 수정했다: Tracking 영역을 Interact와 시각적으로 분리했다.

        ai_layout.addStretch()

        # 여기서부터 수정하고: 연속 복붙 기능을 AI Tools 내부가 아닌 오른쪽 패널의 별도 탭으로 옮겼다.
        self.copy_sequence_tab = QWidget()
        copy_sequence_layout = QVBoxLayout(self.copy_sequence_tab)
        copy_sequence_layout.addWidget(QLabel("Copy Sequence"))
        self.copy_sequence_button = QPushButton("Paste Range")
        self.copy_sequence_button.clicked.connect(self.on_copy_sequence_clicked)
        copy_sequence_layout.addWidget(self.copy_sequence_button)
        copy_sequence_help = QLabel("Ctrl+C로 복사한 객체를 종료 프레임까지 같은 위치와 라벨로 연속 붙여넣습니다.")
        copy_sequence_help.setWordWrap(True)
        copy_sequence_layout.addWidget(copy_sequence_help)
        copy_sequence_layout.addStretch()
        # 여기까지 수정했다: 연속 복붙 기능을 AI Tools 내부가 아닌 오른쪽 패널의 별도 탭으로 옮겼다.

        self.right_tabs.addTab(self.objects_tab, "Objects")
        self.right_tabs.addTab(self.labels_tab, "Labels")
        self.right_tabs.addTab(self.timeline_tab, "Timeline")
        self.right_tabs.addTab(self.ai_tools_tab, "AI Tools")
        # 여기서부터 수정하고: Copy 탭을 오른쪽 패널 탭 목록에 추가했다.
        self.right_tabs.addTab(self.copy_sequence_tab, "Copy")
        # 여기까지 수정했다: Copy 탭을 오른쪽 패널 탭 목록에 추가했다.
        return self.right_tabs

    # ---------- 신호 처리 ----------

    def on_right_tab_changed(self, index):
        """오른쪽 탭 변경 후 작업 화면 맞춤 상태를 갱신한다."""
        self.canvas.refresh_fit()

    # 여기서부터 수정하고: SAM3 선택 여부에 따라 text prompt 입력창 표시를 갱신한다.
    def on_ai_interactor_changed(self, index):
        """SAM3 interactor를 선택했을 때 text prompt 입력창을 보여준다."""
        if self.ai_interactor_combo is None or self.ai_text_prompt_container is None:
            return
        model_type = str(self.ai_interactor_combo.currentData() or "sam2")
        self.ai_text_prompt_container.setVisible(model_type == "sam3")
    # 여기까지 수정했다: SAM3 선택 여부에 따라 text prompt 입력창 표시를 갱신한다.

    def next_default_class_index(self):
        """아직 쓰이지 않은 가장 작은 클래스 번호를 반환한다."""
        used = {label.class_index for label in self.labels_by_id.values()}
        idx = 0
        while idx in used:
            idx += 1
        return idx

    def next_label_color(self):
        """새 라벨에 사용할 색상을 기존 색상과 겹치지 않게 고른다."""
        used = {label.color_hex for label in self.labels_by_id.values()}
        for color in LABEL_COLOR_PALETTE:
            if color not in used:
                return color
        return LABEL_COLOR_PALETTE[len(self.labels_by_id) % len(LABEL_COLOR_PALETTE)]

    def get_label_by_id(self, label_id: Optional[int]) -> Optional[LabelDef]:
        """라벨 ID로 라벨 정의를 찾는다."""
        if label_id is None:
            return None
        return self.labels_by_id.get(label_id)

    def annotation_display_id(self, ann: Optional[Annotation]) -> int:
        """화면에 표시할 객체 표시 정보 ID를 반환한다."""
        if ann is None:
            return -1
        # 화면 표시에는 객체 표시 정보마다 고유한 ID를 사용해 중복 없이 계속 증가하게 한다.
        return ann.ann_id

    def annotation_display_text(self, ann: Optional[Annotation]) -> str:
        """객체 목록과 상태 메시지에 사용할 표시 문구를 만든다."""
        if ann is None:
            return "객체"
        label = self.get_label_by_id(ann.label_id)
        display_id = self.annotation_display_id(ann)
        if label is None:
            return f"ID {display_id}"
        return f"{label.class_name}#{display_id}"

    def _show_label_dialog(self, title="새 라벨", class_name="", class_index=None):
        """라벨 입력 대화창을 띄우고 입력 결과를 반환한다."""
        if class_index is None:
            class_index = self.next_default_class_index()
        dialog = LabelEditDialog(self, title=title, class_name=class_name, class_index=class_index)
        if dialog.exec_() != QDialog.Accepted:
            return None
        class_name, class_index = dialog.values()
        if not class_name:
            return None
        return class_name, class_index

    def validate_label_values(self, class_name: str, class_index: int, ignore_label_id: Optional[int] = None):
        """라벨 이름과 클래스 번호가 중복되지 않는지 확인한다."""
        for label in self.labels_by_id.values():
            if ignore_label_id is not None and label.label_id == ignore_label_id:
                continue
            if label.class_name == class_name:
                QMessageBox.warning(self, "경고", "같은 클래스 이름이 이미 존재합니다.")
                return False
            if label.class_index == class_index:
                QMessageBox.warning(self, "경고", "같은 클래스 번호가 이미 존재합니다.")
                return False
        return True

    def create_label(self, class_name: str, class_index: int):
        """새 라벨을 만들고 라벨 목록과 타임라인 필터 상태에 추가한다."""
        label = LabelDef(
            label_id=self.next_label_id,
            class_name=class_name,
            class_index=class_index,
            color_hex=self.next_label_color(),
        )
        self.next_label_id += 1
        self.labels_by_id[label.label_id] = label
        self.label_order.append(label.label_id)
        self.timeline_filter_state.setdefault(label.label_id, True)
        self.current_working_label_id = label.label_id
        self.refresh_label_list()
        self.refresh_timeline_filter_menu()
        self.refresh_timeline_tree()
        return label

    def find_label_item_by_id(self, label_id: int):
        """라벨 목록 위젯에서 지정한 라벨 ID의 항목을 찾는다."""
        for row in range(self.label_list.count()):
            item = self.label_list.item(row)
            if item.data(Qt.UserRole) == label_id:
                return item
        return None

    def get_selected_label_ids(self):
        """라벨 목록에서 현재 선택된 라벨 ID 목록을 반환한다."""
        ids = []
        for item in self.label_list.selectedItems():
            label_id = item.data(Qt.UserRole)
            if label_id is not None and label_id not in ids:
                ids.append(int(label_id))
        return ids

    def get_primary_selected_label_id(self):
        """현재 라벨 목록에서 대표로 사용할 선택 라벨 ID를 반환한다."""
        current_item = self.label_list.currentItem()
        if current_item is not None:
            label_id = current_item.data(Qt.UserRole)
            if label_id is not None:
                return int(label_id)
        ids = self.get_selected_label_ids()
        return ids[0] if ids else None

    def _set_label_list_selection(self, label_ids):
        """라벨 목록 위젯의 선택 상태를 지정한 라벨 ID 목록으로 맞춘다."""
        self._syncing_label_list = True
        try:
            self.label_list.clearSelection()
            self.label_list.setCurrentItem(None)
            first_item = None
            for label_id in label_ids or []:
                item = self.find_label_item_by_id(label_id)
                if item is not None:
                    item.setSelected(True)
                    if first_item is None:
                        first_item = item
            if first_item is not None:
                self.label_list.setCurrentItem(first_item)
        finally:
            self._syncing_label_list = False

    def refresh_label_list(self):
        """라벨 목록 위젯을 현재 라벨 데이터에 맞춰 다시 채운다."""
        selected_ids = self.get_selected_label_ids() if self.label_list.count() else []
        if not selected_ids and self.current_working_label_id is not None:
            selected_ids = [self.current_working_label_id]

        self._syncing_label_list = True
        try:
            self.label_list.clear()
            for label_id in self.label_order:
                label = self.labels_by_id[label_id]
                item = QListWidgetItem(f"{label.class_index} | {label.class_name}")
                item.setData(Qt.UserRole, label.label_id)
                item.setForeground(QColor(label.color_hex))
                self.label_list.addItem(item)

            first_item = None
            for label_id in selected_ids:
                item = self.find_label_item_by_id(label_id)
                if item is not None:
                    item.setSelected(True)
                    if first_item is None:
                        first_item = item
            if first_item is not None:
                self.label_list.setCurrentItem(first_item)
        finally:
            self._syncing_label_list = False
        self.refresh_ai_label_selector()

    def add_label(self):
        """새 라벨을 추가하고 선택된 객체가 있으면 바로 적용한다."""
        result = self._show_label_dialog(title="새 라벨", class_index=self.next_default_class_index())
        if result is None:
            return
        class_name, class_index = result
        if not self.validate_label_values(class_name, class_index):
            return
        self.push_undo_state("라벨 추가")
        label = self.create_label(class_name, class_index)
        ann_ids = self.get_selected_annotation_ids()
        if ann_ids:
            self.assign_label_to_annotations(
                ann_ids,
                label.label_id,
                show_message=False,
                set_working=True,
                record_undo=False,
            )
            self.show_status_message(f"라벨 '{class_name}' 추가 후 선택 객체에 적용 완료")
        else:
            self._set_label_list_selection([label.label_id])
            self.show_status_message(f"라벨 '{class_name}' 추가 완료")

    def edit_selected_label(self):
        """선택된 라벨 하나의 이름과 클래스 번호를 수정한다."""
        label_ids = self.get_selected_label_ids()
        if len(label_ids) != 1:
            QMessageBox.information(self, "안내", "수정할 라벨을 하나만 선택하세요.")
            return
        label_id = label_ids[0]
        label = self.labels_by_id[label_id]
        result = self._show_label_dialog(title="라벨 수정", class_name=label.class_name, class_index=label.class_index)
        if result is None:
            return
        class_name, class_index = result
        if not self.validate_label_values(class_name, class_index, ignore_label_id=label_id):
            return
        self.push_undo_state("라벨 수정")
        label.class_name = class_name
        label.class_index = class_index
        self.refresh_label_list()
        self._set_label_list_selection([label_id])
        self.refresh_annotations_for_current_frame(
            self.get_selected_annotation_ids(),
            refresh_timeline=refresh_timeline,
        )
        self.refresh_timeline_filter_menu()
        self.refresh_timeline_tree()
        self.show_status_message("라벨 수정 완료")

    def delete_selected_label(self):
        """선택된 라벨을 삭제하고 연결된 객체 표시 정보의 라벨을 해제한다."""
        label_ids = self.get_selected_label_ids()
        if not label_ids:
            return
        label_names = [self.labels_by_id[label_id].class_name for label_id in label_ids if label_id in self.labels_by_id]
        msg = f"선택한 {len(label_names)}개 라벨을 삭제할까요?" if len(label_names) > 1 else f"라벨 '{label_names[0]}' 을(를) 삭제할까요?"
        reply = QMessageBox.question(self, "라벨 삭제 확인", msg, QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply != QMessageBox.Ok:
            return

        self.push_undo_state("라벨 삭제")

        deleted_set = set(label_ids)
        for label_id in deleted_set:
            self.store.clear_label_from_annotations(label_id)
            self.labels_by_id.pop(label_id, None)
            self.timeline_filter_state.pop(label_id, None)
        self.label_order = [lid for lid in self.label_order if lid not in deleted_set]
        if self.current_working_label_id in deleted_set:
            self.current_working_label_id = None
        self.refresh_label_list()
        self.refresh_annotations_for_current_frame(self.get_selected_annotation_ids())
        self.refresh_timeline_filter_menu()
        self.refresh_timeline_tree()
        self.show_status_message("선택 라벨 삭제 완료")

    # ---------- 객체 표시 정보 그리기 ----------

    def render_annotation(self, ann: Annotation) -> RenderAnnotation:
        """저장된 객체 표시 정보를 작업 화면 표시용 데이터로 변환한다."""
        label = self.get_label_by_id(ann.label_id)
        display_id = self.annotation_display_id(ann)
        if label is None:
            return RenderAnnotation(
                ann_id=ann.ann_id,
                track_id=display_id,
                shape_type=ann.shape_type,
                data=ann.data,
                color_hex="#A0A0A0",
                overlay_text=f"ID#{display_id}",
                object_list_text=f"ID {display_id} | (미지정)",
                label_name="(미지정)",
                label_id=None,
                hidden=ann.hidden,
            )

        overlay_text = f"{label.class_name}#{display_id}"
        object_list_text = f"{label.class_index} {overlay_text}"
        return RenderAnnotation(
            ann_id=ann.ann_id,
            track_id=display_id,
            shape_type=ann.shape_type,
            data=ann.data,
            color_hex=label.color_hex,
            overlay_text=overlay_text,
            object_list_text=object_list_text,
            label_name=label.class_name,
            label_id=label.label_id,
            hidden=ann.hidden,
        )

    # ---------- 현재 프레임 갱신 ----------

    def refresh_annotations_for_current_frame(self, keep_selected_ann_ids=None, refresh_timeline: bool = True):
        """현재 프레임의 객체 표시 정보를 작업 화면과 오른쪽 목록에 반영한다."""
        if self.current_index < 0:
            self.object_tree.clear()
            self.canvas.redraw_annotations([])
            if refresh_timeline:
                self.refresh_timeline_tree()
            return

        all_frame_anns = self.store.get_annotations(self.current_index, include_hidden=True)
        visible_renders = [self.render_annotation(ann) for ann in all_frame_anns if not ann.hidden]
        rendered_map = {ann.ann_id: self.render_annotation(ann) for ann in all_frame_anns}
        all_ann_ids = [ann.ann_id for ann in all_frame_anns]

        prev_selected_ids = keep_selected_ann_ids
        if prev_selected_ids is None:
            prev_selected_ids = self.get_selected_annotation_ids()
        prev_selected_ids = [ann_id for ann_id in (prev_selected_ids or []) if ann_id in all_ann_ids]

        self.canvas.redraw_annotations(visible_renders)
        self.canvas.set_selected_annotations(prev_selected_ids)

        self.refresh_object_tree(rendered_map, prev_selected_ids)
        self.sync_label_list_view(prev_selected_ids)
        if refresh_timeline:
            self.refresh_timeline_tree()

    def refresh_object_tree(self, rendered_map: Dict[int, RenderAnnotation], selected_ids: List[int]):
        """현재 프레임의 객체 목록 탭을 다시 채운다."""
        anns = self.store.get_annotations(self.current_index, include_hidden=True) if self.current_index >= 0 else []
        selected_set = set(selected_ids or [])

        self._syncing_object_tree = True
        try:
            self.object_tree.clear()
            for ann in anns:
                render = rendered_map[ann.ann_id]
                item = QTreeWidgetItem([render.object_list_text, "", ""])
                item.setData(0, Qt.UserRole, ann.ann_id)
                item.setForeground(0, QColor(render.color_hex if not ann.hidden else "#888888"))
                self.object_tree.addTopLevelItem(item)

                combo = QComboBox()
                combo.addItem("(미지정)", None)
                for label_id in self.label_order:
                    label = self.labels_by_id[label_id]
                    combo.addItem(label.class_name, label.label_id)
                combo.blockSignals(True)
                combo.setCurrentIndex(self._combo_index_for_label(combo, ann.label_id))
                combo.blockSignals(False)
                combo.currentIndexChanged.connect(partial(self.on_object_label_combo_changed, ann.ann_id, combo))
                self.object_tree.setItemWidget(item, 1, combo)

                vis_btn = QToolButton()
                vis_btn.setCheckable(True)
                vis_btn.setChecked(not ann.hidden)
                self._apply_visibility_button_style(vis_btn, not ann.hidden)
                vis_btn.clicked.connect(partial(self.on_object_visibility_toggled, ann.ann_id, vis_btn))
                self.object_tree.setItemWidget(item, 2, vis_btn)

                if ann.ann_id in selected_set:
                    item.setSelected(True)
        finally:
            self._syncing_object_tree = False

    def _combo_index_for_label(self, combo: QComboBox, label_id: Optional[int]) -> int:
        """라벨 콤보박스에서 지정한 라벨 ID의 인덱스를 찾는다."""
        for idx in range(combo.count()):
            if combo.itemData(idx) == label_id:
                return idx
        return 0

    def _apply_visibility_button_style(self, button: QToolButton, visible: bool):
        """객체 보이기/숨기기 버튼의 표시를 현재 상태에 맞춘다."""
        button.setText("👁" if visible else "🚫")
        button.setToolTip("보이기" if visible else "숨기기")

    def sync_label_list_view(self, ann_ids):
        """선택된 객체 표시 정보와 라벨 목록 선택 상태를 맞춘다."""
        self._syncing_label_list = True
        try:
            self.label_list.clearSelection()
            self.label_list.setCurrentItem(None)

            label_ids = []
            if ann_ids and self.current_index >= 0:
                for ann_id in ann_ids:
                    ann = self.store.get_annotation(self.current_index, ann_id)
                    if ann is not None and ann.label_id is not None and ann.label_id not in label_ids:
                        label_ids.append(ann.label_id)
            elif self.current_working_label_id is not None and self.current_working_label_id in self.labels_by_id:
                label_ids = [self.current_working_label_id]

            first_item = None
            for label_id in label_ids:
                item = self.find_label_item_by_id(label_id)
                if item is not None:
                    item.setSelected(True)
                    if first_item is None:
                        first_item = item
            if first_item is not None:
                self.label_list.setCurrentItem(first_item)
        finally:
            self._syncing_label_list = False

    # ---------- 타임라인 ----------

    def refresh_timeline_filter_menu(self):
        """타임라인 라벨 필터 메뉴를 현재 라벨 목록 기준으로 다시 만든다."""
        if self.timeline_filter_menu is None:
            return
        self.timeline_filter_menu.clear()

        select_all_action = self.timeline_filter_menu.addAction("전체 보이기")
        select_all_action.triggered.connect(self.timeline_select_all_filters)
        hide_all_action = self.timeline_filter_menu.addAction("전체 숨기기")
        hide_all_action.triggered.connect(self.timeline_hide_all_filters)
        self.timeline_filter_menu.addSeparator()

        none_action = self.timeline_filter_menu.addAction("(미지정)")
        none_action.setCheckable(True)
        none_action.setChecked(self.timeline_filter_state.get(None, True))
        none_action.toggled.connect(partial(self.on_timeline_filter_toggled, None))

        for label_id in self.label_order:
            label = self.labels_by_id[label_id]
            action = self.timeline_filter_menu.addAction(f"{label.class_index} | {label.class_name}")
            action.setCheckable(True)
            action.setChecked(self.timeline_filter_state.get(label_id, True))
            action.toggled.connect(partial(self.on_timeline_filter_toggled, label_id))

    def timeline_select_all_filters(self):
        """타임라인 라벨 필터를 모두 보이도록 설정한다."""
        self.timeline_filter_state[None] = True
        for label_id in self.label_order:
            self.timeline_filter_state[label_id] = True
        self.refresh_timeline_filter_menu()
        self.refresh_timeline_tree()

    def timeline_hide_all_filters(self):
        """타임라인 라벨 필터를 모두 숨기도록 설정한다."""
        self.timeline_filter_state[None] = False
        for label_id in self.label_order:
            self.timeline_filter_state[label_id] = False
        self.refresh_timeline_filter_menu()
        self.refresh_timeline_tree()

    def on_timeline_filter_toggled(self, label_id, checked):
        """개별 타임라인 라벨 필터 변경을 저장하고 목록을 갱신한다."""
        self.timeline_filter_state[label_id] = bool(checked)
        self.refresh_timeline_tree()

    def is_timeline_label_visible(self, label_id: Optional[int]) -> bool:
        """해당 라벨이 타임라인에서 보이는 상태인지 반환한다."""
        return self.timeline_filter_state.get(label_id, True)

    def refresh_timeline_tree(self):
        """전체 프레임의 객체 표시 정보를 타임라인 목록에 다시 채운다."""
        self._syncing_timeline = True
        try:
            self.timeline_tree.clear()
            for ann in self.store.all_annotations():
                if not self.is_timeline_label_visible(ann.label_id):
                    continue
                label = self.get_label_by_id(ann.label_id)
                class_text = label.class_name if label is not None else "(미지정)"
                color = QColor(label.color_hex if label is not None else "#888888")
                display_id = self.annotation_display_id(ann)
                item = QTreeWidgetItem([str(ann.frame_idx), class_text, str(display_id)])
                item.setData(0, Qt.UserRole, (ann.frame_idx, ann.ann_id))
                item.setForeground(1, color)
                self.timeline_tree.addTopLevelItem(item)
        finally:
            self._syncing_timeline = False

    def on_timeline_item_clicked(self, item):
        """타임라인에서 아이템을 클릭하면 해당 프레임으로 이동한다."""
        data = item.data(0, Qt.UserRole)
        if data:
            frame_idx, ann_id = data
            self.go_to_frame_index(frame_idx)

    def delete_selected_timeline_annotations(self):
        """타임라인에서 선택된 객체 표시 정보를 삭제한다."""
        selected = self.timeline_tree.selectedItems()
        if not selected:
            return
        pairs = []
        seen = set()
        for item in selected:
            pair = item.data(0, Qt.UserRole)
            if pair and pair not in seen:
                seen.add(pair)
                pairs.append(pair)
        if not pairs:
            return
        msg = f"선택한 {len(pairs)}개 annotation을 삭제할까요?"
        reply = QMessageBox.question(self, "삭제 확인", msg, QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply != QMessageBox.Ok:
            return
        self.push_undo_state("Timeline annotation 삭제")
        current_selected = self.get_selected_annotation_ids()
        for frame_idx, ann_id in pairs:
            self.store.delete_annotation(frame_idx, ann_id)
            if ann_id in current_selected:
                current_selected.remove(ann_id)
        self.refresh_annotations_for_current_frame(current_selected)
        self.show_status_message("Timeline 선택 annotation 삭제 완료")

    # ---------- 라벨 적용 ----------

    def confirm_label_change(self, ann_ids, new_label_id):
        """선택 객체의 라벨 변경 전에 사용자 확인을 받는다."""
        new_label = self.get_label_by_id(new_label_id)
        anns = []
        if self.current_index >= 0:
            for ann_id in ann_ids:
                ann = self.store.get_annotation(self.current_index, ann_id)
                if ann is not None:
                    anns.append(ann)
        changed = [ann for ann in anns if ann.label_id != new_label_id]
        if not changed:
            return True

        if len(changed) == 1:
            old_label = self.get_label_by_id(changed[0].label_id)
            old_name = old_label.class_name if old_label is not None else "(미지정)"
            new_name = new_label.class_name if new_label is not None else "(미지정)"
            msg = f"이 라벨이 '{old_name}'에서 '{new_name}'로 변경됩니다."
        else:
            new_name = new_label.class_name if new_label is not None else "(미지정)"
            msg = f"선택한 {len(changed)}개 객체의 라벨이 '{new_name}'로 변경됩니다."

        reply = QMessageBox.question(self, "라벨 변경 확인", msg, QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        return reply == QMessageBox.Ok

    def assign_label_to_annotations(
        self,
        ann_ids,
        label_id: Optional[int],
        show_message=True,
        set_working=True,
        record_undo=True,
    ):
        """지정한 객체 표시 정보들에 라벨을 적용하거나 해제한다."""
        if self.current_index < 0:
            return False

        target_ids = []
        for ann_id in ann_ids or []:
            ann = self.store.get_annotation(self.current_index, int(ann_id))
            if ann is not None and ann.label_id != label_id:
                target_ids.append(int(ann_id))

        if not target_ids:
            return False

        target_ids = sorted(set(target_ids))

        if record_undo:
            self.push_undo_state("라벨 변경")

        updated_ids = []
        for ann_id in target_ids:
            if self.store.update_annotation_label(self.current_index, ann_id, label_id):
                updated_ids.append(ann_id)

        if not updated_ids:
            return False

        if set_working:
            self.current_working_label_id = label_id
        self.refresh_annotations_for_current_frame(updated_ids)
        if show_message:
            label = self.get_label_by_id(label_id)
            if label is None:
                self.show_status_message("선택 객체 라벨 해제 완료")
            elif len(updated_ids) == 1:
                ann = self.store.get_annotation(self.current_index, updated_ids[0])
                display_text = self.annotation_display_text(ann)
                self.show_status_message(f"{display_text}에 라벨 '{label.class_name}' 적용 완료")
            else:
                self.show_status_message(f"선택한 {len(updated_ids)}개 객체에 라벨 '{label.class_name}' 적용 완료")
        return True

    def prompt_create_label_for_annotations(self, ann_ids, record_undo=True):
        """새 라벨을 만들고 지정한 객체 표시 정보에 적용하도록 요청한다."""
        result = self._show_label_dialog(title="라벨 지정", class_index=self.next_default_class_index())
        if result is None:
            return None
        class_name, class_index = result
        if not self.validate_label_values(class_name, class_index):
            return None
        if record_undo:
            self.push_undo_state("라벨 생성 후 적용")
        label = self.create_label(class_name, class_index)
        self.assign_label_to_annotations(
            ann_ids,
            label.label_id,
            show_message=False,
            set_working=True,
            record_undo=False,
        )
        self.show_status_message(f"라벨 '{class_name}' 생성 후 선택 객체에 적용 완료")
        return label.label_id

    # ---------- 위젯 콜백 ----------

    def on_canvas_selection_changed(self, ann_ids):
        """작업 화면 선택 변경을 오른쪽 객체/라벨 목록에 반영한다."""
        self.sync_object_tree_selection(ann_ids)
        self.sync_label_list_view(ann_ids)

    def on_object_tree_selection_changed(self):
        """객체 목록 선택 변경을 작업 화면과 라벨 목록에 반영한다."""
        if self._syncing_object_tree:
            return
        ann_ids = []
        for item in self.object_tree.selectedItems():
            ann_id = item.data(0, Qt.UserRole)
            if ann_id is not None and ann_id not in ann_ids:
                ann_ids.append(int(ann_id))
        self.canvas.set_selected_annotations(ann_ids)
        self.sync_label_list_view(ann_ids)

    def on_object_label_combo_changed(self, ann_id: int, combo: QComboBox, index: int):
        """객체 목록의 라벨 콤보박스 변경을 저장소에 반영한다."""
        if self.current_index < 0:
            return
        new_label_id = combo.itemData(index)
        ann = self.store.get_annotation(self.current_index, ann_id)
        if ann is None:
            return
        if ann.label_id == new_label_id:
            return
        if not self.confirm_label_change([ann_id], new_label_id):
            self.refresh_annotations_for_current_frame(self.get_selected_annotation_ids())
            return
        self.current_working_label_id = new_label_id
        self.assign_label_to_annotations([ann_id], new_label_id, show_message=True, set_working=False)

    def on_object_visibility_toggled(self, ann_id: int, button: QToolButton, checked: bool):
        """객체 목록의 보이기/숨기기 버튼 변경을 저장소에 반영한다."""
        if self.current_index < 0:
            return

        ann = self.store.get_annotation(self.current_index, ann_id)
        if ann is None:
            return

        visible = bool(checked)
        new_hidden = not visible
        if ann.hidden == new_hidden:
            self._apply_visibility_button_style(button, visible)
            return

        self.push_undo_state("객체 보이기/숨기기 변경")
        self._apply_visibility_button_style(button, visible)
        self.store.update_annotation_visibility(self.current_index, ann_id, hidden=new_hidden)
        keep_selected = self.get_selected_annotation_ids()
        self.refresh_annotations_for_current_frame(keep_selected)
        self.show_status_message("객체 보이기/숨기기 변경 완료")

    def on_label_list_selection_changed(self):
        """라벨 목록 선택 변경을 작업 라벨 또는 선택 객체 라벨 변경에 반영한다."""
        if self._syncing_label_list:
            return
        selected_label_ids = self.get_selected_label_ids()
        if len(selected_label_ids) == 1:
            self.current_working_label_id = selected_label_ids[0]
        ann_ids = self.get_selected_annotation_ids()
        if not ann_ids:
            if len(selected_label_ids) == 1:
                label = self.get_label_by_id(selected_label_ids[0])
                if label is not None:
                    self.show_status_message(f"기본 작업 라벨: '{label.class_name}'")
            return
        if len(selected_label_ids) != 1:
            return
        label_id = selected_label_ids[0]
        if not self.confirm_label_change(ann_ids, label_id):
            self.sync_label_list_view(ann_ids)
            return
        self.assign_label_to_annotations(ann_ids, label_id, show_message=True, set_working=False)

    # ---------- 선택 보조 함수 ----------

    def get_selected_annotation_ids(self):
        """작업 화면 또는 객체 목록에서 선택된 객체 표시 정보 ID를 반환한다."""
        canvas_ids = self.canvas.selected_annotation_ids()
        if canvas_ids:
            return list(canvas_ids)
        ids = []
        for item in self.object_tree.selectedItems():
            ann_id = item.data(0, Qt.UserRole)
            if ann_id is not None and ann_id not in ids:
                ids.append(int(ann_id))
        return ids

    def sync_object_tree_selection(self, ann_ids):
        """객체 목록 선택 상태를 지정한 객체 표시 정보 ID 목록과 맞춘다."""
        self._syncing_object_tree = True
        try:
            self.object_tree.clearSelection()
            first_item = None
            ann_id_set = set(ann_ids or [])
            for row in range(self.object_tree.topLevelItemCount()):
                item = self.object_tree.topLevelItem(row)
                if item.data(0, Qt.UserRole) in ann_id_set:
                    item.setSelected(True)
                    if first_item is None:
                        first_item = item
            if first_item is not None:
                self.object_tree.setCurrentItem(first_item)
            else:
                self.object_tree.setCurrentItem(None)
        finally:
            self._syncing_object_tree = False

    # ---------- 삭제 ----------

    def handle_delete_key(self):
        """현재 포커스 위치에 따라 Delete 키 동작을 분기한다."""
        focus = QApplication.focusWidget()
        if focus is self.label_list or (focus is not None and self.label_list.isAncestorOf(focus)):
            self.delete_selected_label()
            return
        if focus is self.timeline_tree or (focus is not None and self.timeline_tree.isAncestorOf(focus)):
            self.delete_selected_timeline_annotations()
            return
        self.delete_selected_object()

    def delete_selected_object(self):
        """현재 프레임에서 선택된 객체 표시 정보를 삭제한다."""
        ann_ids = self.get_selected_annotation_ids()
        if self.current_index < 0 or not ann_ids:
            return

        ann_infos = []
        for ann_id in ann_ids:
            ann = self.store.get_annotation(self.current_index, ann_id)
            if ann is not None:
                ann_infos.append((ann_id, self.annotation_display_text(ann)))
        if not ann_infos:
            return

        msg = (
            f"선택한 {len(ann_infos)}개 객체를 삭제할까요?"
            if len(ann_infos) > 1
            else f"{ann_infos[0][1]} 를 삭제할까요?"
        )
        reply = QMessageBox.question(self, "객체 삭제 확인", msg, QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if reply != QMessageBox.Ok:
            return

        self.push_undo_state("객체 삭제")
        for ann_id, _display_text in ann_infos:
            self.store.delete_annotation(self.current_index, ann_id)
        self.refresh_annotations_for_current_frame([])
        self.show_status_message("선택 객체 삭제 완료")

    # ---------- 모드 취소 ----------
