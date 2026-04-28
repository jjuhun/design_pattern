# 맨 위 도구 모음과 공통 작업 버튼들을 관리하는 파일입니다.
# 열기, 내보내기, 되돌리기, 다시 실행, 복사/붙여넣기 흐름을 담당합니다.
from copy import deepcopy
from pathlib import Path
from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox, QPushButton, QProgressBar, QToolBar

from core.annotation.models import Annotation, ClipboardAnnotation
from core.common.utils import clamp


class TopPanelControllerMixin:
    def create_top_toolbar(self):
        """맨 위 도구 모음을 만들고 버튼을 기존 동작에 연결한다."""
        toolbar = QToolBar("Top Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        open_frames_btn = QPushButton("Open Frames")
        open_frames_btn.clicked.connect(self.open_frames_folder)
        toolbar.addWidget(open_frames_btn)

        open_video_btn = QPushButton("Open Video")
        open_video_btn.clicked.connect(self.open_video_file)
        toolbar.addWidget(open_video_btn)

        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self.on_save_clicked)
        toolbar.addWidget(export_btn)

        self.undo_button = QPushButton("Undo")
        self.undo_button.clicked.connect(self.undo_last_action)
        self.undo_button.setEnabled(False)
        toolbar.addWidget(self.undo_button)

        self.redo_button = QPushButton("Redo")
        self.redo_button.clicked.connect(self.redo_last_action)
        self.redo_button.setEnabled(False)
        toolbar.addWidget(self.redo_button)

        toolbar.addSeparator()

        self.tracking_progress_bar = QProgressBar()
        self.tracking_progress_bar.setMinimum(0)
        self.tracking_progress_bar.setMaximum(100)
        self.tracking_progress_bar.setValue(0)
        self.tracking_progress_bar.setTextVisible(True)
        self.tracking_progress_bar.setFormat("Tracking %p%")
        self.tracking_progress_bar.setVisible(False)
        self.tracking_progress_bar.setFixedWidth(260)
        toolbar.addWidget(self.tracking_progress_bar)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("미디어: "))
        toolbar.addWidget(self.media_label)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("프레임명: "))
        toolbar.addWidget(self.frame_name_label)

        toolbar.addSeparator()
        toolbar.addWidget(self.mode_label)

    def _annotation_points_for_yolo_segment(self, ann: Annotation):
        """YOLO 세그먼트 저장에 사용할 객체 표시 정보의 점 목록을 만든다."""
        if ann.shape_type == "polygon":
            points = [(float(x), float(y)) for x, y in ann.data]  # type: ignore[arg-type]
            return points if len(points) >= 3 else []
        if ann.shape_type == "box":
            x, y, w, h = ann.data  # type: ignore[misc]
            x = float(x)
            y = float(y)
            w = float(w)
            h = float(h)
            if w <= 0.0 or h <= 0.0:
                return []
            return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return []

    def _build_yolo_classes_lines(self):
        """classes.txt에 들어갈 클래스 이름 목록을 클래스 번호 순서로 만든다."""
        class_name_by_idx = {}
        for label in self.labels_by_id.values():
            idx = int(label.class_index)
            if idx < 0:
                continue
            name = str(label.class_name or "").strip()
            class_name_by_idx[idx] = name if name else f"class_{idx}"

        if not class_name_by_idx:
            return []

        max_idx = max(class_name_by_idx.keys())
        lines = []
        for idx in range(max_idx + 1):
            lines.append(class_name_by_idx.get(idx, f"unused_{idx}"))
        return lines

    def on_save_clicked(self):
        """현재 객체 표시 정보를 YOLO 세그먼트 형식으로 내보낸다."""
        if self.source is None or self.current_index < 0:
            QMessageBox.warning(self, "경고", "먼저 프레임 소스를 열어주세요.")
            return

        export_dir = QFileDialog.getExistingDirectory(self, "YOLO Segment 저장 폴더 선택", "")
        if not export_dir:
            return

        total = int(self.source.frame_count())
        if total <= 0:
            QMessageBox.warning(self, "경고", "내보낼 프레임이 없습니다.")
            return

        output_root = Path(export_dir)
        output_root.mkdir(parents=True, exist_ok=True)

        exported_files = 0
        exported_segments = 0
        skipped_unlabeled = 0
        skipped_invalid = 0
        used_txt_names = set()
        classes_txt_path = output_root / "classes.txt"
        class_lines = self._build_yolo_classes_lines()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for frame_idx in range(total):
                frame_name = str(self.source.frame_name(frame_idx) or "")
                stem = Path(frame_name).stem or f"frame_{frame_idx:06d}"
                txt_name = f"{stem}.txt"
                if txt_name in used_txt_names:
                    txt_name = f"{stem}_{frame_idx:06d}.txt"
                used_txt_names.add(txt_name)
                txt_path = output_root / txt_name

                pixmap = self.source.get_pixmap(frame_idx)
                width = int(pixmap.width())
                height = int(pixmap.height())
                lines = []

                if width > 0 and height > 0:
                    anns = self.store.get_annotations(frame_idx, include_hidden=False)
                    for ann in anns:
                        if ann.label_id is None:
                            skipped_unlabeled += 1
                            continue
                        label = self.labels_by_id.get(ann.label_id)
                        if label is None:
                            skipped_unlabeled += 1
                            continue

                        points = self._annotation_points_for_yolo_segment(ann)
                        if len(points) < 3:
                            skipped_invalid += 1
                            continue

                        normalized_xy = []
                        for x, y in points:
                            nx = clamp(float(x) / float(width), 0.0, 1.0)
                            ny = clamp(float(y) / float(height), 0.0, 1.0)
                            normalized_xy.append(f"{nx:.6f}")
                            normalized_xy.append(f"{ny:.6f}")

                        if not normalized_xy:
                            skipped_invalid += 1
                            continue

                        lines.append(f"{int(label.class_index)} {' '.join(normalized_xy)}")
                        exported_segments += 1

                txt_path.write_text("\n".join(lines), encoding="utf-8")
                exported_files += 1

            classes_txt_path.write_text("\n".join(class_lines), encoding="utf-8")
        except Exception as ex:
            QMessageBox.critical(self, "오류", f"YOLO Segment export 중 오류가 발생했습니다:\n{str(ex)}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.show_status_message(
            f"YOLO Segment export 완료: {exported_files}개 txt, {exported_segments}개 세그먼트"
        )
        QMessageBox.information(
            self,
            "Export 완료",
            (
                f"저장 폴더: {output_root}\n"
                f"TXT 파일 수: {exported_files}\n"
                f"세그먼트 수: {exported_segments}\n"
                f"classes.txt 항목 수: {len(class_lines)}\n"
                f"스킵(라벨 없음): {skipped_unlabeled}\n"
                f"스킵(유효하지 않은 도형): {skipped_invalid}"
            ),
        )

    def update_undo_button_state(self):
        """되돌리기와 다시 실행 버튼의 활성화 상태를 갱신한다."""
        if self.undo_button is not None:
            self.undo_button.setEnabled(bool(self.undo_stack))
        if self.redo_button is not None:
            self.redo_button.setEnabled(bool(self.redo_stack))

    def clear_undo_history(self):
        """되돌리기와 다시 실행 기록을 모두 비운다."""
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.update_undo_button_state()

    def capture_app_state(self):
        """되돌리기에 필요한 현재 앱 상태를 복사한다."""
        return {
            "store": self.store.snapshot(),
            "labels_by_id": deepcopy(self.labels_by_id),
            "label_order": list(self.label_order),
            "next_label_id": self.next_label_id,
            "current_working_label_id": self.current_working_label_id,
            "timeline_filter_state": deepcopy(self.timeline_filter_state),
            "current_index": self.current_index,
            "selected_ann_ids": list(self.get_selected_annotation_ids()),
            "ai_interact_state": self._capture_ai_interact_state(),
        }

    def restore_app_state(self, state):
        """복사해 둔 앱 상태를 화면과 데이터에 다시 적용한다."""
        self.store.restore(state["store"])
        self.labels_by_id = deepcopy(state["labels_by_id"])
        self.label_order = list(state["label_order"])
        self.next_label_id = int(state["next_label_id"])
        self.current_working_label_id = state["current_working_label_id"]
        self.timeline_filter_state = deepcopy(state["timeline_filter_state"])
        ai_state = state.get("ai_interact_state")
        self.refresh_label_list()
        self.refresh_timeline_filter_menu()

        if self.source is None:
            self.object_tree.clear()
            self.timeline_tree.clear()
            self.canvas.redraw_annotations([])
            self._restore_ai_interact_state(ai_state)
            self.update_undo_button_state()
            return

        total = self.source.frame_count()
        if total <= 0:
            self.current_index = -1
            self.canvas.show_placeholder("현재 프레임을 표시할 수 없습니다.")
            self._restore_ai_interact_state(ai_state)
            self.update_undo_button_state()
            return

        self.current_index = clamp(int(state.get("current_index", 0)), 0, total - 1)
        self.canvas.set_selected_annotations([])
        self.sync_object_tree_selection([])
        self.update_frame_view()

        selected_ids = [int(ann_id) for ann_id in state.get("selected_ann_ids", [])]
        if selected_ids:
            self.refresh_annotations_for_current_frame(selected_ids)
            self.canvas.set_selected_annotations(selected_ids)
            self.sync_object_tree_selection(selected_ids)
            self.sync_label_list_view(selected_ids)

        self._restore_ai_interact_state(ai_state)
        self.update_undo_button_state()

    def push_undo_state(self, description: str):
        """현재 상태를 되돌리기 기록에 추가한다."""
        self.undo_stack.append((description, self.capture_app_state()))
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.update_undo_button_state()

    def undo_last_action(self):
        """가장 최근 작업을 되돌리고 다시 실행 기록에 넣는다."""
        if not self.undo_stack:
            self.show_status_message("되돌릴 작업이 없습니다.")
            return
        description, state = self.undo_stack.pop()
        self.redo_stack.append((description, self.capture_app_state()))
        if len(self.redo_stack) > self.max_undo_steps:
            self.redo_stack.pop(0)
        self.restore_app_state(state)
        self.show_status_message(f"되돌리기 완료: {description}")

    def redo_last_action(self):
        """가장 최근 되돌리기 작업을 다시 적용한다."""
        if not self.redo_stack:
            self.show_status_message("다시 실행할 작업이 없습니다.")
            return
        description, state = self.redo_stack.pop()
        self.undo_stack.append((description, self.capture_app_state()))
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        self.restore_app_state(state)
        self.show_status_message(f"다시 실행 완료: {description}")

    def copy_selected_annotations(self):
        """현재 선택한 객체 표시 정보를 내부 클립보드에 복사한다."""
        if self.current_index < 0:
            return
        ann_ids = self.get_selected_annotation_ids()
        if not ann_ids:
            self.show_status_message("복사할 객체를 먼저 선택하세요.")
            return

        clipboard: List[ClipboardAnnotation] = []
        for ann_id in ann_ids:
            ann = self.store.get_annotation(self.current_index, ann_id)
            if ann is None:
                continue
            label_id = ann.label_id if ann.label_id in self.labels_by_id else None
            clipboard.append(
                ClipboardAnnotation(
                    source_frame_idx=self.current_index,
                    track_id=ann.track_id,
                    shape_type=ann.shape_type,
                    label_id=label_id,
                    data=deepcopy(ann.data),
                )
            )

        if not clipboard:
            self.show_status_message("복사할 객체를 찾지 못했습니다.")
            return

        self.annotation_clipboard = clipboard
        self.show_status_message(f"{len(clipboard)}개 객체 복사 완료")

    def paste_annotations(self):
        """내부 클립보드의 객체 표시 정보를 현재 프레임에 붙여넣는다."""
        if self.current_index < 0 or self.source is None:
            return
        if not self.annotation_clipboard:
            self.show_status_message("먼저 Ctrl+C로 복사할 객체를 선택하세요.")
            return

        self.push_undo_state("객체 붙여넣기")

        affected_ann_ids: List[int] = []
        for copied in self.annotation_clipboard:
            label_id = copied.label_id if copied.label_id in self.labels_by_id else None
            payload = deepcopy(copied.data)
            ann = self.store.add_annotation(self.current_index, copied.shape_type, payload, label_id)
            affected_ann_ids.append(ann.ann_id)

        self.refresh_annotations_for_current_frame(affected_ann_ids)
        self.canvas.set_selected_annotations(affected_ann_ids)
        self.sync_object_tree_selection(affected_ann_ids)
        self.sync_label_list_view(affected_ann_ids)
        self.show_status_message(f"붙여넣기 완료: {len(affected_ann_ids)}개 객체 생성")

    # ---------- 라벨 관리 ----------
