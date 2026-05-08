# 맨 위 도구 모음과 공통 작업 버튼들을 관리하는 파일입니다.
# 열기, 가져오기, 내보내기, 자동 저장, 되돌리기, 다시 실행, 복사/붙여넣기 흐름을 담당합니다.
import shutil
from copy import deepcopy
from pathlib import Path
from typing import List

from PyQt5.QtCore import Qt, QTimer
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

        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self.on_import_clicked)
        toolbar.addWidget(import_btn)

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

    def _current_media_export_name(self) -> str:
        """현재 열린 미디어 이름을 export/autosave 폴더명으로 사용할 수 있게 만든다."""
        base_name = "export"

        if self.source is not None:
            try:
                # ImageFolderSource / CachedFrameSource 기준
                display_name = self.source.display_name()
                if display_name:
                    base_name = Path(display_name).stem
            except Exception:
                pass

        # 파일/폴더명으로 부적절한 문자 정리
        safe_name = "".join(
            ch if (ch.isalnum() or ch in ("-", "_")) else "_"
            for ch in base_name
        ).strip("_")

        return safe_name or "export"


    def _make_unique_result_dir(self, parent_dir: Path) -> Path:
        """현재 열린 미디어 이름 기반으로 저장 폴더를 만든다."""
        base_name = self._current_media_export_name()

        base = parent_dir / base_name
        if not base.exists():
            base.mkdir(parents=True, exist_ok=False)
            return base

        idx = 1
        while True:
            candidate = parent_dir / f"{base_name}_{idx}"
            if not candidate.exists():
                candidate.mkdir(parents=True, exist_ok=False)
                return candidate
            idx += 1

    def _build_data_yaml_lines(self):
        """data.yaml에 저장할 클래스 이름 정보를 만든다."""
        labels_sorted = sorted(
            self.labels_by_id.values(),
            key=lambda label: int(label.class_index),
        )
        yaml_lines = ["names:"]
        for label in labels_sorted: 
            name = str(label.class_name or "").strip() or f"class_{int(label.class_index)}"
            yaml_lines.append(f"  {int(label.class_index)}: {name}")
        yaml_lines.append("path: .")
        yaml_lines.append("train: train.txt")
        return yaml_lines

    def _export_yolo_dataset_to_dir(self, output_root: Path, overwrite: bool = False):
        """지정 폴더에 YOLO Segment 구조로 저장한다."""
        if self.source is None or self.current_index < 0:
            raise RuntimeError("먼저 프레임 소스를 열어주세요.")

        total = int(self.source.frame_count())
        if total <= 0:
            raise RuntimeError("내보낼 프레임이 없습니다.")

        if overwrite and output_root.exists():
            shutil.rmtree(output_root, ignore_errors=True)

        output_root.mkdir(parents=True, exist_ok=True)
        labels_train_dir = output_root / "labels" / "train"
        labels_train_dir.mkdir(parents=True, exist_ok=True)

        data_yaml_path = output_root / "data.yaml"
        train_txt_path = output_root / "train.txt"

        exported_files = 0
        exported_segments = 0
        skipped_unlabeled = 0
        skipped_invalid = 0
        train_lines = []

        for frame_idx in range(total):
            frame_name = str(self.source.frame_name(frame_idx) or f"frame_{frame_idx:06d}.png")
            stem = Path(frame_name).stem or f"frame_{frame_idx:06d}"
            image_suffix = Path(frame_name).suffix or ".png"

            train_lines.append(f"./train/{stem}{image_suffix}")
            label_txt_path = labels_train_dir / f"{stem}.txt"

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

            label_txt_path.write_text("\n".join(lines), encoding="utf-8")
            exported_files += 1

        train_txt_path.write_text("\n".join(train_lines), encoding="utf-8")
        data_yaml_path.write_text("\n".join(self._build_data_yaml_lines()), encoding="utf-8")

        return {
            "output_root": output_root,
            "exported_files": exported_files,
            "exported_segments": exported_segments,
            "skipped_unlabeled": skipped_unlabeled,
            "skipped_invalid": skipped_invalid,
        }

    def on_save_clicked(self):
        """수동 Export: 선택 폴더 아래 result, result_1, result_2 ... 형태로 새 저장 폴더를 만든다."""
        if self.source is None or self.current_index < 0:
            QMessageBox.warning(self, "경고", "먼저 프레임 소스를 열어주세요.")
            return

        selected_dir = QFileDialog.getExistingDirectory(self, "Export 저장 위치 선택", "")
        if not selected_dir:
            return

        output_parent = Path(selected_dir)
        output_root = self._make_unique_result_dir(output_parent)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = self._export_yolo_dataset_to_dir(output_root, overwrite=False)
        except Exception as ex:
            QMessageBox.critical(self, "오류", f"YOLO Dataset export 중 오류가 발생했습니다:\n{str(ex)}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.show_status_message(
            f"Export 완료: {output_root.name}, {result['exported_files']}개 txt, {result['exported_segments']}개 세그먼트"
        )
        QMessageBox.information(
            self,
            "Export 완료",
            (
                f"저장 폴더: {result['output_root']}\n"
                f"Label TXT 파일 수: {result['exported_files']}\n"
                f"세그먼트 수: {result['exported_segments']}\n"
                f"data.yaml 생성 완료\n"
                f"train.txt 생성 완료\n"
                f"스킵(라벨 없음): {result['skipped_unlabeled']}\n"
                f"스킵(유효하지 않은 도형): {result['skipped_invalid']}"
            ),
        )

    def auto_save(self, n=10):
        """n분마다 autosave_result 폴더에 자동 저장한다. 같은 폴더에 계속 덮어쓴다."""
        if not hasattr(self, "auto_save_timer") or self.auto_save_timer is None:
            self.auto_save_timer = QTimer(self)
            self.auto_save_timer.timeout.connect(self.run_auto_save)

        minutes = max(1, int(n))
        self.auto_save_timer.start(minutes * 60 * 1000)
        self.show_status_message(f"Auto Save 시작: {minutes}분마다 저장")

    def stop_auto_save(self):
        """자동 저장을 중지한다."""
        if hasattr(self, "auto_save_timer") and self.auto_save_timer is not None:
            self.auto_save_timer.stop()
            self.show_status_message("Auto Save 중지")

    def run_auto_save(self):
        """자동 저장 타이머가 호출하는 실제 저장 함수."""
        if self.source is None or self.current_index < 0:
            return

        # import 경로가 없으면 자동저장 안 함
        if not hasattr(self, "last_import_dir") or self.last_import_dir is None:
            return

        try:
            base_name = self._current_media_export_name()

            parent_dir = self.last_import_dir.parent

            # 실제 autosave 폴더
            output_root = parent_dir / f"{base_name}_autosave"

            # 임시 저장 폴더
            temp_output_root = parent_dir / f".{base_name}_autosave_tmp"

            # 기존 temp 폴더 정리
            if temp_output_root.exists():
                shutil.rmtree(temp_output_root, ignore_errors=True)

            # 1. 임시 폴더에 먼저 저장
            self._export_yolo_dataset_to_dir(
                temp_output_root,
                overwrite=False,
            )

            # 2. 필수 파일 생성 확인
            data_yaml_path = temp_output_root / "data.yaml"
            train_txt_path = temp_output_root / "train.txt"

            if not data_yaml_path.exists():
                raise RuntimeError("data.yaml 생성 실패")

            if not train_txt_path.exists():
                raise RuntimeError("train.txt 생성 실패")

            # 3. 기존 autosave 삭제
            if output_root.exists():
                shutil.rmtree(output_root, ignore_errors=True)

            # 4. temp → 실제 autosave 교체
            temp_output_root.rename(output_root)

            self.show_status_message(f"Auto Save 완료: {output_root}")

        except Exception as ex:
            self.show_status_message(f"Auto Save 실패: {str(ex)}")

    def on_import_clicked(self):
        """YOLO Segment export 결과 폴더를 불러와 현재 열린 프레임에 annotation을 복원한다."""
        if self.source is None or self.current_index < 0:
            QMessageBox.warning(self, "경고", "먼저 Open Frames 또는 Open Video로 원본 프레임을 열어주세요.")
            return

        import_dir = QFileDialog.getExistingDirectory(self, "Import result 폴더 선택", "")
        if not import_dir:
            return

        result_dir = Path(import_dir)
        data_yaml_path = result_dir / "data.yaml"
        labels_train_dir = result_dir / "labels" / "train"
        train_txt_path = result_dir / "train.txt"

        if not data_yaml_path.exists():
            QMessageBox.warning(self, "경고", "data.yaml 파일을 찾을 수 없습니다.")
            return
        if not labels_train_dir.exists() or not labels_train_dir.is_dir():
            QMessageBox.warning(self, "경고", "labels/train 폴더를 찾을 수 없습니다.")
            return
        if not train_txt_path.exists():
            QMessageBox.warning(self, "경고", "train.txt 파일을 찾을 수 없습니다.")
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            imported_info = self._import_yolo_dataset_from_dir(result_dir)
        except Exception as ex:
            QMessageBox.critical(self, "오류", f"Import 중 오류가 발생했습니다:\n{str(ex)}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.show_status_message(
            f"Import 완료: 라벨 {imported_info['label_count']}개, 객체 {imported_info['annotation_count']}개"
        )
        QMessageBox.information(
            self,
            "Import 완료",
            (
                f"불러온 폴더: {result_dir}\n"
                f"라벨 수: {imported_info['label_count']}\n"
                f"객체 수: {imported_info['annotation_count']}\n"
                f"매칭된 label txt: {imported_info['matched_label_files']}개\n"
                f"스킵된 줄: {imported_info['skipped_lines']}개"
            ),
        )

    def _parse_data_yaml_names(self, data_yaml_path: Path):
        """data.yaml에서 names 항목을 읽어 {class_index: class_name} 딕셔너리로 반환한다."""
        names = {}
        in_names = False

        for raw_line in data_yaml_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped == "names:" or stripped.startswith("names:"):
                in_names = True
                inline = stripped[len("names:"):].strip()
                if inline.startswith("[") and inline.endswith("]"):
                    items = [v.strip().strip("'\"") for v in inline[1:-1].split(",") if v.strip()]
                    for idx, name in enumerate(items):
                        names[idx] = name
                continue

            if in_names:
                if not raw_line.startswith((" ", "\t")) and ":" in stripped:
                    break
                if ":" not in stripped:
                    continue
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip().strip("'\"")
                if key.isdigit() and value:
                    names[int(key)] = value

        if not names:
            raise RuntimeError("data.yaml에서 names 정보를 읽지 못했습니다.")
        return names

    def _import_yolo_dataset_from_dir(self, result_dir: Path):
        """result 폴더의 data.yaml과 labels/train/*.txt를 읽어 annotation을 복원한다."""
        if self.source is None:
            raise RuntimeError("미디어 소스가 없습니다.")

        data_yaml_path = result_dir / "data.yaml"
        labels_train_dir = result_dir / "labels" / "train"
        names_by_class_idx = self._parse_data_yaml_names(data_yaml_path)

        self.push_undo_state("YOLO Dataset Import")

        self.store.clear()
        self.labels_by_id.clear()
        self.label_order.clear()
        self.next_label_id = 1
        self.current_working_label_id = None
        self.timeline_filter_state = {None: True}

        class_idx_to_label_id = {}
        for class_idx in sorted(names_by_class_idx.keys()):
            label = self.create_label(str(names_by_class_idx[class_idx]), int(class_idx))
            class_idx_to_label_id[int(class_idx)] = label.label_id

        total = int(self.source.frame_count())
        annotation_count = 0
        matched_label_files = 0
        skipped_lines = 0

        for frame_idx in range(total):
            frame_name = str(self.source.frame_name(frame_idx) or f"frame_{frame_idx:06d}.png")
            stem = Path(frame_name).stem or f"frame_{frame_idx:06d}"
            label_txt_path = labels_train_dir / f"{stem}.txt"
            if not label_txt_path.exists():
                continue

            matched_label_files += 1
            pixmap = self.source.get_pixmap(frame_idx)
            width = int(pixmap.width())
            height = int(pixmap.height())
            if width <= 0 or height <= 0:
                continue

            for raw_line in label_txt_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) < 7:
                    skipped_lines += 1
                    continue

                try:
                    class_idx = int(float(parts[0]))
                    coords = [float(v) for v in parts[1:]]
                except ValueError:
                    skipped_lines += 1
                    continue

                if len(coords) < 6 or len(coords) % 2 != 0:
                    skipped_lines += 1
                    continue

                label_id = class_idx_to_label_id.get(class_idx)
                if label_id is None:
                    skipped_lines += 1
                    continue

                points = []
                for i in range(0, len(coords), 2):
                    x = clamp(coords[i], 0.0, 1.0) * width
                    y = clamp(coords[i + 1], 0.0, 1.0) * height
                    points.append((float(x), float(y)))

                if len(points) < 3:
                    skipped_lines += 1
                    continue

                self.store.add_polygon(frame_idx, points, label_id)
                annotation_count += 1

        self.refresh_label_list()
        self.refresh_timeline_filter_menu()
        self.refresh_timeline_tree()
        self.refresh_annotations_for_current_frame([])

        return {
            "label_count": len(class_idx_to_label_id),
            "annotation_count": annotation_count,
            "matched_label_files": matched_label_files,
            "skipped_lines": skipped_lines,
        }

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