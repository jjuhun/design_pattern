# AI 상호작용 버튼을 눌렀을 때의 화면 흐름을 관리하는 파일입니다.
# 입력 기준 받기, 미리보기 표시, 결과 확정, AI 작업 라벨 선택을 담당합니다.
from copy import deepcopy

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QInputDialog, QMessageBox

from core.common.utils import box_to_polygon


class AIInteractControllerMixin:
    def _capture_ai_interact_state(self):
        """되돌리기용으로 현재 AI 상호작용 상태를 복사한다."""
        return {
            "ai_interact_pending": bool(self.ai_interact_pending),
            "ai_prompt_mode": self.ai_prompt_mode,
            "ai_pending_model_type": str(self.ai_pending_model_type or "sam2"),
            "ai_pending_box": tuple(self.ai_pending_box) if self.ai_pending_box is not None else None,
            "ai_refinement_points": [tuple(p) for p in self.ai_refinement_points],
            "ai_refinement_labels": [int(v) for v in self.ai_refinement_labels],
            "ai_pending_mask": deepcopy(self.ai_pending_mask),
            "ai_pending_polygon": deepcopy(self.ai_pending_polygon),
        }

    def _restore_ai_interact_state(self, ai_state):
        """복사해 둔 AI 상호작용 상태를 화면과 내부 상태에 다시 적용한다."""
        ai_state = ai_state or {}
        self.ai_interact_pending = bool(ai_state.get("ai_interact_pending", False))
        self.ai_prompt_mode = ai_state.get("ai_prompt_mode")
        self.ai_pending_model_type = str(ai_state.get("ai_pending_model_type") or "sam2")

        pending_box = ai_state.get("ai_pending_box")
        self.ai_pending_box = tuple(pending_box) if pending_box is not None else None

        restored_points = []
        for pt in ai_state.get("ai_refinement_points", []):
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                restored_points.append((float(pt[0]), float(pt[1])))
        restored_labels = [int(v) for v in ai_state.get("ai_refinement_labels", [])]
        if len(restored_labels) < len(restored_points):
            restored_labels.extend([1] * (len(restored_points) - len(restored_labels)))
        self.ai_refinement_points = restored_points
        self.ai_refinement_labels = restored_labels[: len(restored_points)]

        self.ai_pending_mask = deepcopy(ai_state.get("ai_pending_mask"))
        self.ai_pending_polygon = deepcopy(ai_state.get("ai_pending_polygon"))

        if self.ai_interact_button is not None:
            self.ai_interact_button.setText("Confirm" if self.ai_interact_pending else "Interact")

        if self.canvas is None:
            return

        self.canvas.clear_ai_interact_preview()
        preview_polygon = self.ai_pending_polygon if self.ai_pending_polygon is not None else []
        preview_points = list(zip(self.ai_refinement_points, self.ai_refinement_labels))
        if preview_polygon or preview_points:
            self.canvas.show_ai_interact_preview(preview_polygon, preview_points)

        if self.ai_interact_pending:
            if self.ai_prompt_mode == "box":
                self.canvas.set_mode("box")
            elif self.ai_prompt_mode == "point":
                self.canvas.set_mode("ai_point")
            elif self.ai_prompt_mode == "refine":
                self.canvas.set_mode("ai_refine")
            else:
                self.canvas.set_mode("select")
        elif self.current_mode in ("ai_point", "ai_refine"):
            self.canvas.set_mode("select")

    def refresh_ai_label_selector(self):
        """AI 작업 라벨 선택 목록을 현재 라벨 목록과 맞춘다."""
        if not hasattr(self, "ai_label_selector") or self.ai_label_selector is None:
            return

        current_label_id = self.current_working_label_id if self.current_working_label_id in self.labels_by_id else None
        self.ai_label_selector.blockSignals(True)
        self.ai_label_selector.clear()
        self.ai_label_selector.addItem("None", None)
        for label_id in self.label_order:
            label = self.labels_by_id[label_id]
            self.ai_label_selector.addItem(f"{label.class_index} | {label.class_name}", label.label_id)

        if current_label_id is not None:
            for idx in range(self.ai_label_selector.count()):
                if self.ai_label_selector.itemData(idx) == current_label_id:
                    self.ai_label_selector.setCurrentIndex(idx)
                    break
        else:
            self.ai_label_selector.setCurrentIndex(0)
        self.ai_label_selector.blockSignals(False)

    def on_ai_label_selector_changed(self, index: int):
        """AI 작업 라벨 선택 변경을 현재 작업 라벨 상태에 반영한다."""
        if self.ai_label_selector is None:
            return
        label_id = self.ai_label_selector.itemData(index)
        if label_id is None or label_id not in self.labels_by_id:
            self.current_working_label_id = None
            self.show_status_message("AI 작업 라벨이 해제되었습니다.")
            return
        self.current_working_label_id = int(label_id)
        label = self.labels_by_id[self.current_working_label_id]
        self.show_status_message(f"AI 작업 라벨: '{label.class_name}'")

    def on_ai_create_label_clicked(self):
        """AI 도구에서 새 라벨을 만들고 작업 라벨로 선택한다."""
        result = self._show_label_dialog(title="새 라벨", class_index=self.next_default_class_index())
        if result is None:
            return
        class_name, class_index = result
        if not self.validate_label_values(class_name, class_index):
            return
        self.push_undo_state("라벨 추가")
        label = self.create_label(class_name, class_index)
        self.current_working_label_id = label.label_id
        self.refresh_label_list()
        self.refresh_ai_label_selector()
        self.show_status_message(f"AI 작업 라벨 '{label.class_name}' 생성 및 선택됨")

    # 여기서부터 수정하고: AI Tools의 bbox/pointer 선택 UI에서 초기 prompt mode를 읽는다.
    def _selected_ai_initial_prompt_mode(self) -> str:
        """AI Interact 시작 시 사용할 초기 입력 방식을 반환한다."""
        if getattr(self, "ai_pointer_prompt_checkbox", None) is not None:
            return "point" if self.ai_pointer_prompt_checkbox.isChecked() else "box"

        start_with_bbox = True
        if getattr(self, "ai_start_with_bbox_checkbox", None) is not None:
            start_with_bbox = bool(self.ai_start_with_bbox_checkbox.isChecked())
        return "box" if start_with_bbox else "point"
    # 여기까지 수정했다: AI Tools의 bbox/pointer 선택 UI에서 초기 prompt mode를 읽는다.

    def on_ai_interact_clicked(self):
        """현재 프레임 단일 SAM 상호작용 입력 대기를 시작하거나 결과를 확정한다."""
        if self.ai_interact_pending and self.ai_pending_mask is not None:
            self._confirm_ai_interact_annotation()
            return

        if not self._ensure_cuda_ready():
            return
        if self.source is None or self.current_index < 0:
            QMessageBox.warning(self, "경고", "먼저 미디어를 열고 프레임을 선택하세요.")
            return

        model_type = "sam2"
        if self.ai_interactor_combo is not None:
            model_type = str(self.ai_interactor_combo.currentData() or "sam2")

        # 여기서부터 수정하고: 기존 단일 checkbox 대신 bbox/pointer 선택값으로 시작 방식을 정한다.
        prompt_mode = self._selected_ai_initial_prompt_mode()

        self.ai_interact_pending = True
        self.ai_prompt_mode = prompt_mode
        self.ai_pending_model_type = model_type
        self.ai_pending_box = None
        self.ai_refinement_points = []
        self.ai_refinement_labels = []
        self.ai_pending_mask = None
        self.ai_pending_polygon = None

        if prompt_mode == "box":
            self.canvas.set_mode("box")
            self.show_status_message("AI Interact 대기: 대상 물체를 박스로 드래그하세요.")
        else:
            self.canvas.set_mode("ai_point")
            self.show_status_message("AI Interact 대기: 대상 물체를 점으로 클릭하세요.")
        # 여기까지 수정했다: 기존 단일 checkbox 대신 bbox/pointer 선택값으로 시작 방식을 정한다.
        if self.ai_interact_button is not None:
            self.ai_interact_button.setText("Confirm")

    def on_canvas_ai_prompt_point_requested(self, x: float, y: float, label: int):
        """작업 화면에서 들어온 AI 점 입력 요청을 처리한다."""
        if not self.ai_interact_pending or self.ai_prompt_mode not in ("point", "refine"):
            return
        self._run_ai_interact_with_point_prompt(x, y, label)

    def _run_ai_interact_with_box_prompt(self, box_payload):
        """사용자가 그린 박스를 AI 상호작용 입력 기준으로 실행한다."""
        try:
            import numpy as np
        except ImportError as ex:
            self._reset_ai_interact_prompt_state()
            QMessageBox.critical(self, "오류", f"필요한 라이브러리를 불러올 수 없습니다:\n{str(ex)}")
            return

        pixmap = self.source.get_pixmap(self.current_index)
        if pixmap.isNull():
            self._reset_ai_interact_prompt_state()
            QMessageBox.warning(self, "오류", "현재 프레임을 읽을 수 없습니다.")
            return

        image = pixmap.toImage()
        width, height = image.width(), image.height()
        x, y, bw, bh = box_payload
        x1 = max(0, min(int(x), width - 1))
        y1 = max(0, min(int(y), height - 1))
        x2 = max(0, min(int(x + bw), width - 1))
        y2 = max(0, min(int(y + bh), height - 1))
        if x2 <= x1 or y2 <= y1:
            self._reset_ai_interact_prompt_state()
            QMessageBox.warning(self, "오류", "유효한 박스 프롬프트가 아닙니다.")
            return

        self.push_undo_state("AI Box 프롬프트")
        self.ai_pending_box = (float(x1), float(y1), float(x2), float(y2))
        self.ai_refinement_points = []
        self.ai_refinement_labels = []
        self.ai_pending_polygon = box_to_polygon(self.ai_pending_box)
        if self.canvas is not None:
            self.canvas.show_ai_interact_preview(self.ai_pending_polygon, [])
        self._execute_ai_single_frame_interact(
            prompt_box=self.ai_pending_box,
        )

    def _run_ai_interact_with_point_prompt(self, x: float, y: float, label: int):
        """사용자가 찍은 점을 AI 상호작용 입력 기준으로 실행한다."""
        try:
            import numpy as np
        except ImportError as ex:
            self._reset_ai_interact_prompt_state()
            QMessageBox.critical(self, "오류", f"필요한 라이브러리를 불러올 수 없습니다:\n{str(ex)}")
            return

        pixmap = self.source.get_pixmap(self.current_index)
        if pixmap.isNull():
            self._reset_ai_interact_prompt_state()
            QMessageBox.warning(self, "오류", "현재 프레임을 읽을 수 없습니다.")
            return

        image = pixmap.toImage()
        width, height = image.width(), image.height()
        px = max(0, min(int(round(x)), width - 1))
        py = max(0, min(int(round(y)), height - 1))

        if self.ai_prompt_mode == "point":
            self.push_undo_state("AI Point 입력")
        else:
            self.push_undo_state("AI Refine 점 추가" if int(label) == 1 else "AI Refine 점 제거")
        self.ai_refinement_points.append((float(px), float(py)))
        self.ai_refinement_labels.append(int(label))
        points = np.array(self.ai_refinement_points, dtype=np.float32)
        labels = np.array(self.ai_refinement_labels, dtype=np.int32)
        # 박스로 초기화한 뒤 보정 단계에서는 박스 제약을 해제해야
        # 좌/우클릭 점 보정이 점 입력 모드처럼 실제로 반영된다.
        prompt_box = self.ai_pending_box if self.ai_prompt_mode != "refine" else None

        self._execute_ai_single_frame_interact(
            prompt_points=points,
            prompt_labels=labels,
            prompt_box=prompt_box,
        )

    def _execute_ai_single_frame_interact(
        self,
        prompt_points=None,
        prompt_labels=None,
        prompt_box=None,
    ):
        """현재 프레임에서 SAM 단일 프레임 상호작용을 실행하고 미리보기를 만든다."""
        try:
            import cv2
            import numpy as np
            from features.ai_interact.engine import SAMImageInteractEngine
        except ImportError as ex:
            self._reset_ai_interact_prompt_state()
            QMessageBox.critical(self, "오류", f"필요한 라이브러리를 불러올 수 없습니다:\n{str(ex)}")
            return

        pixmap = self.source.get_pixmap(self.current_index)
        if pixmap.isNull():
            self._reset_ai_interact_prompt_state()
            QMessageBox.warning(self, "오류", "현재 프레임을 읽을 수 없습니다.")
            return

        image = pixmap.toImage()
        width, height = image.width(), image.height()
        ptr = image.bits()
        ptr.setsize(image.byteCount())
        arr = np.array(ptr).reshape(height, width, 4)
        frame = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)

        self.show_status_message(f"{self.ai_pending_model_type.upper()} 단일 프레임 interact 실행 중...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            engine = SAMImageInteractEngine(model_type=self.ai_pending_model_type, device="cuda")
            # 박스로 시작한 보정 단계에서는 박스와 점을 함께 사용해 범위 보정을 반영한다.
            if prompt_box is not None and prompt_points is not None and prompt_labels is not None:
                mask = engine.segment_with_box_and_points(frame, prompt_box, prompt_points, prompt_labels)
            elif prompt_points is not None and prompt_labels is not None:
                mask = engine.segment_with_points(frame, prompt_points, prompt_labels)
            elif prompt_box is not None:
                mask = engine.segment_with_box(frame, prompt_box)
            else:
                raise RuntimeError("프롬프트가 없어 SAM interact를 실행할 수 없습니다.")

            result_shape_type = "polygon"
            result_data = engine.mask_to_polygon(mask)
        except Exception as e:
            err_text = str(e)
            if self.ai_pending_model_type == "sam3" and (
                "SAM3 predictor" in err_text
                or "SAM checkpoint 파일을 찾을 수 없습니다." in err_text
                or "SAM2 config 파일을 찾을 수 없습니다." in err_text
            ):
                # SAM3 지원이나 체크포인트가 없는 환경에서는 SAM2로 자연스럽게 전환한다.
                self.ai_pending_model_type = "sam2"
                self.show_status_message("SAM3를 사용할 수 없어 SAM2로 자동 전환합니다.")
                self._execute_ai_single_frame_interact(
                    prompt_points=prompt_points,
                    prompt_labels=prompt_labels,
                    prompt_box=prompt_box,
                )
                return
            self._reset_ai_interact_prompt_state()
            QMessageBox.critical(self, "오류", f"SAM interact 중 오류가 발생했습니다:\n{err_text}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        points = result_data
        if len(points) < 3:
            if prompt_box is not None:
                points = box_to_polygon(prompt_box)
                mask = None  # SAM 마스크가 없으므로 박스를 대신 사용한다.
            else:
                self._reset_ai_interact_prompt_state()
                QMessageBox.warning(self, "오류", "유효한 polygon 결과를 얻지 못했습니다.")
                return

        self.ai_pending_mask = mask
        self.ai_pending_polygon = points
        self.ai_prompt_mode = "refine"
        self.canvas.set_mode("ai_refine")
        if self.canvas is not None:
            self.canvas.show_ai_interact_preview(points, list(zip(self.ai_refinement_points, self.ai_refinement_labels)))
        self.show_status_message("AI Interact: 좌클릭으로 추가, 우클릭으로 제거하세요. 완료하려면 Interact 버튼을 다시 누르세요.")

    def _confirm_ai_interact_annotation(self):
        """AI 상호작용 미리보기 결과를 실제 객체 표시 정보로 확정한다."""
        if self.ai_pending_mask is None or self.ai_pending_polygon is None:
            self.show_status_message("AI Interact 결과가 없습니다. 먼저 초기 영역을 만드세요.")
            return

        label_id = self.current_working_label_id if self.current_working_label_id in self.labels_by_id else None
        if label_id is None:
            label_id = self._ask_label_for_ai_annotation()
            if label_id is None:
                return

        if self.current_index < 0 or self.source is None:
            return

        self.push_undo_state("SAM Single-Frame Interact")
        ann = self.store.add_polygon(self.current_index, self.ai_pending_polygon, label_id)
        self.refresh_annotations_for_current_frame([ann.ann_id])
        self.canvas.set_selected_annotations([ann.ann_id])
        self.sync_object_tree_selection([ann.ann_id])
        self.sync_label_list_view([ann.ann_id])
        self.show_status_message(f"{self.annotation_display_text(ann)} 생성 완료 (SAM interact)")
        self._reset_ai_interact_prompt_state()

    def _ask_label_for_ai_annotation(self):
        """AI 상호작용 결과에 적용할 라벨을 사용자에게 묻는다."""
        label_items = []
        label_map = {}
        for label_id in self.label_order:
            label = self.labels_by_id[label_id]
            text = f"{label.class_index} | {label.class_name}"
            label_items.append(text)
            label_map[text] = label_id

        while True:
            selected_text, ok = QInputDialog.getItem(
                self,
                "AI 라벨 지정",
                "기존 라벨 선택하거나 새 라벨 이름을 입력하세요:",
                label_items,
                0,
                True,
            )
            if not ok:
                return None

            value = selected_text.strip()
            if not value:
                QMessageBox.warning(self, "경고", "라벨 이름을 입력하거나 목록에서 선택하세요.")
                continue

            if value in label_map:
                self.current_working_label_id = int(label_map[value])
                return self.current_working_label_id

            existing_label_id = None
            for label_id in self.label_order:
                if self.labels_by_id[label_id].class_name == value:
                    existing_label_id = label_id
                    break
            if existing_label_id is not None:
                self.current_working_label_id = int(existing_label_id)
                return self.current_working_label_id

            class_index = self.next_default_class_index()
            if not self.validate_label_values(value, class_index):
                continue
            label = self.create_label(value, class_index)
            self.refresh_label_list()
            self.refresh_ai_label_selector()
            self.current_working_label_id = label.label_id
            return self.current_working_label_id

    def _ask_label_for_new_ai_annotation(self, ann_id: int):
        """새 AI 결과 객체 표시 정보에 적용할 라벨을 사용자에게 묻는다."""
        if self.current_index < 0:
            return
        ann = self.store.get_annotation(self.current_index, ann_id)
        if ann is None:
            return

        # 기존 라벨을 고르거나 새 라벨 이름을 입력하도록 명확한 선택지를 보여준다.
        label_items = []
        label_map = {}
        for label_id in self.label_order:
            label = self.labels_by_id[label_id]
            text = f"{label.class_index} | {label.class_name}"
            label_items.append(text)
            label_map[text] = label_id

        while True:
            selected_text, ok = QInputDialog.getItem(
                self,
                "라벨 지정",
                "라벨을 선택하거나 새 라벨 이름을 입력하세요:",
                label_items,
                0,
                True,
            )
            if not ok:
                return

            value = selected_text.strip()
            if not value:
                QMessageBox.warning(self, "경고", "라벨 이름을 입력하거나 목록에서 선택하세요.")
                continue

            if value in label_map:
                target_label_id = int(label_map[value])
                self.assign_label_to_annotations(
                    [ann_id],
                    target_label_id,
                    show_message=False,
                    set_working=True,
                    record_undo=False,
                )
                return

            # 사용자가 기존 클래스 이름을 입력했다면 그 라벨을 다시 사용한다.
            existing_label_id = None
            for label_id in self.label_order:
                if self.labels_by_id[label_id].class_name == value:
                    existing_label_id = label_id
                    break
            if existing_label_id is not None:
                self.assign_label_to_annotations(
                    [ann_id],
                    int(existing_label_id),
                    show_message=False,
                    set_working=True,
                    record_undo=False,
                )
                return

            # 다음 클래스 번호로 새 라벨을 만들고 해당 객체에 적용한다.
            class_index = self.next_default_class_index()
            if not self.validate_label_values(value, class_index):
                continue
            label = self.create_label(value, class_index)
            self.assign_label_to_annotations(
                [ann_id],
                label.label_id,
                show_message=False,
                set_working=True,
                record_undo=False,
            )
            return

    def _reset_ai_interact_prompt_state(self):
        """AI 상호작용 입력 대기와 미리보기 상태를 초기화한다."""
        self.ai_interact_pending = False
        self.ai_prompt_mode = None
        self.ai_pending_box = None
        self.ai_refinement_points = []
        self.ai_refinement_labels = []
        self.ai_pending_mask = None
        self.ai_pending_polygon = None
        if self.canvas is not None:
            self.canvas.clear_ai_interact_preview()
            self.canvas.set_mode("select")
        if self.ai_interact_button is not None:
            self.ai_interact_button.setText("Interact")

    def _is_sam3_available(self) -> bool:
        """현재 설치 환경에서 SAM3 비디오 예측기 불러오기가 가능한지 확인한다."""
        try:
            from sam2.build_sam import build_sam3_video_predictor  # noqa: F401
            return True
        except Exception:
            return False
