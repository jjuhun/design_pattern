# AI 트랙킹 실행 흐름을 관리하는 파일입니다.
# 트랙킹 작업 객체, 진행률, 중지 요청, 결과를 객체 표시 정보에 반영하는 일을 담당합니다.
import gc
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import QDialog, QMessageBox

from core.annotation.models import Annotation
from core.common.utils import clamp, natural_key
from features.ai_tracking.ai_tracking_dialogs import SelectSAMModelDialog, TrackingRangeDialog


class TrackingWorker(QObject):
    DEFAULT_CHUNK_SIZE = 8
    LARGE_CHUNK_SIZE = 4

    progress = pyqtSignal(int, int, int)
    resultReady = pyqtSignal(object)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        model_type,
        device,
        media_input,
        mask,
        start_frame,
        end_frame,
        shape_type,
        label_id,
        track_id,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        polygon_simplification: float = 0.005,
        keypoint_infos: Optional[List[Dict[str, object]]] = None,
    ):
        """트랙킹을 백그라운드에서 실행할 작업 객체 상태를 초기화한다."""
        super().__init__()
        self.model_type = model_type
        self.device = device
        self.media_input = media_input
        self.mask = mask
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.shape_type = shape_type
        self.label_id = label_id
        self.track_id = track_id
        self.chunk_size = max(4, int(chunk_size))
        self.polygon_simplification = max(0.0, float(polygon_simplification))
        self.keypoint_infos = list(keypoint_infos or [])
        self._stop_requested = False
        self.engine = None
        self._temp_subset_dir: Optional[Path] = None

    @classmethod
    def chunk_size_for_model(cls, model_type: str) -> int:
        """메모리 사용량이 큰 모델일수록 더 작은 트랙킹 청크를 사용한다."""
        return cls.LARGE_CHUNK_SIZE if model_type in ("sam2_large", "sam3") else cls.DEFAULT_CHUNK_SIZE
    def stop(self):
        """작업 루프가 안전하게 멈추도록 중지 요청 상태를 켠다."""
        self._stop_requested = True

    def _cleanup_temp_subset_dir(self):
        """청크 트랙킹에 사용한 임시 프레임 폴더를 삭제한다."""
        if self._temp_subset_dir is not None and self._temp_subset_dir.exists():
            shutil.rmtree(self._temp_subset_dir, ignore_errors=True)
        self._temp_subset_dir = None

    # 여기서부터 수정하고: 정방향/역방향 frame index 목록을 그대로 임시 트랙킹 입력으로 준비하게 했다.
    def _load_frames_from_media_input(self, frame_indices: List[int]):
        """요청한 프레임 순서대로 임시 폴더를 만들어 트랙킹 입력을 준비한다."""
        self._cleanup_temp_subset_dir()
        if not frame_indices:
            raise RuntimeError("선택한 트래킹 범위에 프레임이 없습니다.")

        kind = self.media_input.get("kind")
        value = self.media_input.get("value")
        if kind != "frame_dir":
            raise ValueError("지원하지 않는 media_input 형식입니다. frame_dir만 지원합니다.")

        frame_dir = Path(str(value))
        if not frame_dir.exists() or not frame_dir.is_dir():
            raise RuntimeError("프레임 디렉터리를 찾을 수 없습니다.")

        image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        frame_files = sorted(
            [p for p in frame_dir.iterdir() if p.is_file() and p.suffix.lower() in image_exts],
            key=lambda p: natural_key(p.name),
        )
        if not frame_files:
            raise RuntimeError("프레임 디렉터리에 이미지가 없습니다.")

        invalid_indices = [idx for idx in frame_indices if idx < 0 or idx >= len(frame_files)]
        if invalid_indices:
            raise RuntimeError(
                f"요청한 프레임({invalid_indices[0]})이 없습니다. "
                f"실제 마지막 프레임 인덱스는 {len(frame_files) - 1}입니다."
            )

        selected = [frame_files[idx] for idx in frame_indices]

        subset_dir = Path(tempfile.mkdtemp(prefix="tracking_subset_frames_"))
        self._temp_subset_dir = subset_dir
        for rel_idx, src in enumerate(selected):
            dst = subset_dir / f"frame_{rel_idx:06d}.jpg"
            try:
                os.symlink(str(src.resolve()), str(dst))
                continue
            except OSError:
                pass
            try:
                os.link(str(src), str(dst))
                continue
            except OSError:
                pass
            shutil.copy2(str(src), str(dst))

        subset_end = len(selected) - 1
        return str(subset_dir), subset_end, list(frame_indices)
    # 여기까지 수정했다: 정방향/역방향 frame index 목록을 그대로 임시 트랙킹 입력으로 준비하게 했다.

    def _tracking_result_to_mask(self, result, mask_shape):
        """트랙킹 결과 도형을 다음 청크의 초기 마스크로 변환한다."""
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise ImportError("cv2, numpy가 필요합니다") from exc

        h, w = mask_shape
        mask = np.zeros((h, w), dtype=np.uint8)
        if result is None:
            return mask

        if result.shape_type == "polygon":
            points = np.asarray(result.data, dtype=np.int32)
            if points.size > 0:
                cv2.fillPoly(mask, [points], 255)
            return mask

        x, y, bw, bh = result.data
        x1 = max(0, min(int(round(x)), w - 1))
        y1 = max(0, min(int(round(y)), h - 1))
        x2 = max(0, min(int(round(x + bw - 1)), w - 1))
        y2 = max(0, min(int(round(y + bh - 1)), h - 1))
        if x2 >= x1 and y2 >= y1:
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        return mask

    def _tracking_result_to_bbox(self, result, mask_shape):
        """트랙킹 결과에서 keypoint 재배치에 사용할 bbox를 계산한다."""
        if result is None:
            return None
        h, w = mask_shape
        if result.shape_type == "polygon":
            points = list(result.data or [])
            if not points:
                return None
            xs = [float(x) for x, _y in points]
            ys = [float(y) for _x, y in points]
            x1 = clamp(min(xs), 0.0, max(0.0, float(w - 1)))
            y1 = clamp(min(ys), 0.0, max(0.0, float(h - 1)))
            x2 = clamp(max(xs), 0.0, max(0.0, float(w - 1)))
            y2 = clamp(max(ys), 0.0, max(0.0, float(h - 1)))
            return (x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1))

        try:
            x, y, bw, bh = result.data
        except Exception:
            return None
        x1 = clamp(float(x), 0.0, max(0.0, float(w - 1)))
        y1 = clamp(float(y), 0.0, max(0.0, float(h - 1)))
        x2 = clamp(float(x) + max(1.0, float(bw)), 0.0, max(0.0, float(w - 1)))
        y2 = clamp(float(y) + max(1.0, float(bh)), 0.0, max(0.0, float(h - 1)))
        return (x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1))

    def _keypoint_payload_from_result(self, frame_idx: int, result, mask_shape):
        """트랙킹 bbox 안의 상대좌표로 keypoint 결과 payload를 만든다."""
        bbox = self._tracking_result_to_bbox(result, mask_shape)
        if bbox is None:
            return None
        x, y, bw, bh = bbox
        h, w = mask_shape
        points = []
        for info in self.keypoint_infos:
            rel_x = float(info.get("rel_x", 0.0))
            rel_y = float(info.get("rel_y", 0.0))
            px = clamp(x + rel_x * bw, 0.0, max(0.0, float(w - 1)))
            py = clamp(y + rel_y * bh, 0.0, max(0.0, float(h - 1)))
            points.append(
                {
                    "track_id": int(info["track_id"]),
                    "label_id": info.get("label_id"),
                    "data": (px, py),
                }
            )
        if not points:
            return None
        return {
            "type": "keypoints",
            "frame_idx": int(frame_idx),
            "points": points,
        }

    def _release_engine_resources(self):
        """트랙킹 엔진과 GPU 메모리, 임시 폴더를 정리한다."""
        if self.engine is not None:
            try:
                self.engine.stop_tracking()
            except Exception:
                pass
        self.engine = None
        self._cleanup_temp_subset_dir()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        gc.collect()

    def _reset_chunk_resources(self):
        """다음 청크를 위해 추론 상태만 정리하고 로드된 모델은 유지한다."""
        if self.engine is not None:
            try:
                self.engine.stop_tracking()
            except Exception:
                pass
        self._cleanup_temp_subset_dir()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        gc.collect()

    def run(self):
        """청크 단위로 트랙킹을 수행하고 진행률과 결과를 신호로 보낸다."""
        saved_count = 0
        saved_keypoint_count = 0
        stopped = False
        try:
            import numpy as np
            if self.model_type == "sam3":
                from features.ai_tracking.ai_tracking_engine_sam3 import SAM3TrackingEngine
            else:
                from features.ai_tracking.ai_tracking_engine import SAM2TrackingEngine

            if self._stop_requested:
                self.finished.emit(
                    {
                        "saved_count": 0,
                        "saved_keypoint_count": 0,
                        "stopped": True,
                        "mode": "keypoint" if self.keypoint_infos else "annotation",
                    }
                )
                return

            # 여기서부터 수정하고: 시작/종료 프레임 관계로 트랙킹 방향을 계산한다.
            direction = 1 if self.end_frame >= self.start_frame else -1
            total_steps = max(1, abs(self.end_frame - self.start_frame))
            mask_shape = tuple(self.mask.shape[:2])
            current_seed_mask = self.mask.copy()
            chunk_start = int(self.start_frame)
            # 여기까지 수정했다: 시작/종료 프레임 관계로 트랙킹 방향을 계산한다.

            # 여기서부터 수정하고: 역순 트랙킹도 같은 청크 루프로 처리한다.
            while chunk_start != self.end_frame:
                if self._stop_requested:
                    stopped = True
                    break

                if direction > 0:
                    chunk_end = min(chunk_start + self.chunk_size, self.end_frame)
                    frame_indices = list(range(chunk_start, chunk_end + 1))
                else:
                    chunk_end = max(chunk_start - self.chunk_size, self.end_frame)
                    frame_indices = list(range(chunk_start, chunk_end - 1, -1))

                if self.engine is None:
                    if self.model_type == "sam3":
                        self.engine = SAM3TrackingEngine(
                            device=self.device,
                            polygon_simplification=self.polygon_simplification,
                        )
                    else:
                        self.engine = SAM2TrackingEngine(
                            model_type=self.model_type,
                            device=self.device,
                            polygon_simplification=self.polygon_simplification,
                        )

                loaded_input, subset_end_frame, original_frame_indices = self._load_frames_from_media_input(frame_indices)
                self.engine.initialize_tracking(
                    loaded_input,
                    current_seed_mask,
                    start_frame_idx=0,
                    shape_type=self.shape_type,
                )

                last_nonempty_result = None
                last_nonempty_frame_idx = chunk_start
                for relative_idx in range(1, subset_end_frame + 1):
                    if self._stop_requested:
                        stopped = True
                        break

                    frame_idx = original_frame_indices[relative_idx]
                    progress_steps = abs(frame_idx - self.start_frame)
                    percent = int((progress_steps / total_steps) * 100)
                    self.progress.emit(percent, frame_idx, self.end_frame)

                    result = self.engine.track_frame(relative_idx)
                    if result is None:
                        continue

                    result.frame_idx = frame_idx
                    result_mask = self._tracking_result_to_mask(result, mask_shape)
                    if int(np.count_nonzero(result_mask)) == 0:
                        continue

                    if self.keypoint_infos:
                        keypoint_payload = self._keypoint_payload_from_result(frame_idx, result, mask_shape)
                        if keypoint_payload is None:
                            continue
                        self.resultReady.emit(keypoint_payload)
                        saved_count += 1
                        saved_keypoint_count += len(keypoint_payload["points"])
                    else:
                        self.resultReady.emit((frame_idx, result, self.label_id, self.track_id))
                        saved_count += 1
                    last_nonempty_result = result
                    last_nonempty_frame_idx = frame_idx

                self._reset_chunk_resources()

                if stopped or chunk_end == self.end_frame:
                    break

                if last_nonempty_result is None:
                    raise RuntimeError(
                        f"프레임 {chunk_start}~{chunk_end} 구간에서 유효한 결과를 얻지 못해 더 이어서 트래킹할 수 없습니다."
                    )

                current_seed_mask = self._tracking_result_to_mask(last_nonempty_result, mask_shape)
                if int(np.count_nonzero(current_seed_mask)) == 0:
                    raise RuntimeError(
                        f"프레임 {last_nonempty_frame_idx}의 마지막 유효 결과를 다음 청크 시드로 만들 수 없습니다."
                    )

                missed_chunk_tail = (
                    last_nonempty_frame_idx < chunk_end
                    if direction > 0
                    else last_nonempty_frame_idx > chunk_end
                )
                if missed_chunk_tail:
                    print(
                        f"! 프레임 {last_nonempty_frame_idx + direction}~{chunk_end} 결과가 비어 있어 "
                        f"마지막 유효 프레임 {last_nonempty_frame_idx}부터 다시 이어서 트래킹합니다."
                    )

                no_progress = (
                    last_nonempty_frame_idx <= chunk_start
                    if direction > 0
                    else last_nonempty_frame_idx >= chunk_start
                )
                if no_progress:
                    raise RuntimeError(
                        f"프레임 {chunk_start} 이후 유효한 결과가 없어 더 진행할 수 없습니다."
                    )

                chunk_start = last_nonempty_frame_idx
            # 여기까지 수정했다: 역순 트랙킹도 같은 청크 루프로 처리한다.

            self.finished.emit(
                {
                    "saved_count": saved_count,
                    "saved_keypoint_count": saved_keypoint_count,
                    "stopped": stopped,
                    "mode": "keypoint" if self.keypoint_infos else "annotation",
                }
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self._release_engine_resources()


class AITrackingControllerMixin:
    def _set_tracking_status(self, status_text: str):
        """오른쪽 AI 도구 패널의 트랙킹 상태 문구를 갱신한다."""
        if self.ai_tracking_status_label is not None:
            self.ai_tracking_status_label.setText(f"상태: {status_text}")

    def _update_tracking_progress_ui(self, percent: int, current_frame: int, end_frame: int):
        """상단과 오른쪽 패널의 트랙킹 진행률 표시를 갱신한다."""
        percent = max(0, min(100, int(percent)))
        progress_text = f"Tracking {percent}% ({current_frame}/{end_frame})"
        self.tracking_progress_bar.setVisible(True)
        self.tracking_progress_bar.setRange(0, 100)
        self.tracking_progress_bar.setValue(percent)
        self.tracking_progress_bar.setFormat(progress_text)
        if self.ai_tracking_progress_bar is not None:
            self.ai_tracking_progress_bar.setValue(percent)
            self.ai_tracking_progress_bar.setFormat("Tracking %p%")
        if self.ai_tracking_progress_label is not None:
            self.ai_tracking_progress_label.setText(progress_text)

    def _reset_tracking_progress_ui(self):
        """트랙킹 진행률 표시를 초기 상태로 되돌린다."""
        self.tracking_progress_bar.setRange(0, 100)
        self.tracking_progress_bar.setValue(0)
        self.tracking_progress_bar.setFormat("Tracking %p%")
        self.tracking_progress_bar.setVisible(False)
        if self.ai_tracking_progress_bar is not None:
            self.ai_tracking_progress_bar.setValue(0)
            self.ai_tracking_progress_bar.setFormat("Tracking %p%")
        if self.ai_tracking_progress_label is not None:
            self.ai_tracking_progress_label.setText("Tracking 0% (0/0)")

    def _set_tracking_button_states(self, running: bool):
        """트랙킹 시작/중지 버튼의 활성화 상태를 현재 실행 여부에 맞춘다."""
        can_start = bool(self.source is not None and self.source.frame_count() > 0 and not running)
        self.tracking_start_btn.setEnabled(can_start)
        self.tracking_stop_btn.setEnabled(running)
        if self.ai_tracking_stop_btn is not None:
            self.ai_tracking_stop_btn.setEnabled(running)

    def on_start_tracking(self):
        """트랙킹 시작 클릭"""
        if self.is_tracking:
            QMessageBox.information(self, "안내", "이미 트랙킹이 진행 중입니다.")
            return
        if not self._ensure_cuda_ready():
            return
        if self.source is None:
            QMessageBox.warning(self, "경고", "먼저 미디어를 열어주세요.")
            return
        
        if self.current_index < 0:
            QMessageBox.warning(self, "경고", "먼저 프레임을 선택하세요.")
            return
        
        # 현재 프레임의 객체 표시 정보 확인
        current_anns = self.store.get_annotations(self.current_index, include_hidden=False)
        if not current_anns:
            QMessageBox.warning(self, "경고", "현재 프레임에 annotation이 없습니다.\n먼저 annotation을 그려주세요.")
            return
        selected_anns = self._get_selected_current_annotations(current_anns)
        keypoint_anns = []
        seed_ann = None
        if selected_anns and all(ann.shape_type == "keypoint" for ann in selected_anns):
            if len(selected_anns) < 2:
                QMessageBox.warning(self, "경고", "Keypoint 트랙킹은 keypoint를 2개 이상 선택해야 합니다.")
                return
            keypoint_anns = sorted(selected_anns, key=lambda ann: ann.ann_id)
        elif selected_anns and any(ann.shape_type == "keypoint" for ann in selected_anns):
            QMessageBox.warning(
                self,
                "경고",
                "Keypoint 트랙킹은 keypoint만 여러 개 선택해서 실행하세요.\n"
                "Box/Polygon 트랙킹은 keypoint 선택을 해제한 뒤 실행하세요.",
            )
            return
        else:
            seed_ann = self._get_tracking_seed_annotation(current_anns)
            if seed_ann is None:
                QMessageBox.warning(self, "경고", "트랙킹 시작 기준 annotation을 찾을 수 없습니다.")
                return
            if seed_ann.shape_type == "keypoint":
                QMessageBox.warning(self, "경고", "Keypoint는 단독 트랙킹 대상이 아닙니다.\nKeypoint를 2개 이상 선택하세요.")
                return
        
        # SAM 모델 선택
        model_dialog = SelectSAMModelDialog(self)
        if model_dialog.exec_() != QDialog.Accepted:
            return
        
        selected_model = model_dialog.get_selected_model()
        
        # 종료 프레임 선택
        range_dialog = TrackingRangeDialog(
            self,
            start_frame=self.current_index,
            max_frame=self.source.frame_count()
        )
        if range_dialog.exec_() != QDialog.Accepted:
            return
        
        end_frame = range_dialog.get_end_frame()
        
        # 트랙킹 시작
        if keypoint_anns:
            self.push_undo_state("Keypoint Tracking")
            self._perform_keypoint_tracking(selected_model, end_frame, keypoint_anns)
        else:
            self.push_undo_state("SAM Tracking")
            self._perform_tracking(selected_model, end_frame, seed_ann)

    def on_stop_tracking(self):
        """트랙킹 중지 클릭"""
        if not self.is_tracking or self.tracking_worker is None:
            return
        self.show_status_message("트랙킹 중지 요청...")
        self._set_tracking_status("중지 요청됨")
        self.tracking_worker.stop()
        self.tracking_stop_btn.setEnabled(False)
        if self.ai_tracking_stop_btn is not None:
            self.ai_tracking_stop_btn.setEnabled(False)

    def _get_tracking_seed_annotation(self, current_anns: List[Annotation]) -> Optional[Annotation]:
        """트랙킹을 시작할 기준 객체 표시 정보를 선택 상태에서 고른다."""
        selected_ids = set(self.get_selected_annotation_ids())
        for ann in current_anns:
            if ann.ann_id in selected_ids:
                return ann
        return current_anns[-1] if current_anns else None

    def _get_selected_current_annotations(self, current_anns: List[Annotation]) -> List[Annotation]:
        """현재 프레임에서 선택된 표시 정보를 프레임 저장 순서대로 반환한다."""
        selected_ids = set(self.get_selected_annotation_ids())
        if not selected_ids:
            return []
        return [ann for ann in current_anns if ann.ann_id in selected_ids]

    def _build_tracking_media_input(self):
        """트랙킹 워커가 읽을 프레임 디렉터리 입력 정보를 만든다."""
        if self.source is None:
            raise RuntimeError("미디어 소스가 없습니다.")
        return {"kind": "frame_dir", "value": self.source.frame_dir_path()}

    def _perform_tracking(self, model_type: str, end_frame: int, seed_ann: Annotation):
        """백그라운드 워커로 트랙킹 수행"""
        if not self._ensure_cuda_ready():
            return
        try:
            import numpy as np
        except ImportError as ex:
            QMessageBox.critical(
                self,
                "오류",
                f"{str(ex)}"
            )
            return

        try:
            pixmap = self.source.get_pixmap(self.current_index)
            if pixmap.isNull():
                QMessageBox.warning(self, "오류", "현재 프레임을 읽을 수 없습니다.")
                return
            frame_shape = (pixmap.height(), pixmap.width())
            mask = self._annotation_to_mask(seed_ann, frame_shape)
            if int(np.count_nonzero(mask)) == 0:
                QMessageBox.warning(self, "오류", "선택한 annotation으로 유효한 초기 마스크를 만들 수 없습니다.")
                return

            media_input = self._build_tracking_media_input()
            polygon_simplification = self._tracking_polygon_simplification_value()

            self.tracking_start_frame = self.current_index
            self.tracking_end_frame = end_frame
            # 여기서부터 수정하고: live follow와 완료 판정을 위해 트랙킹 방향을 저장한다.
            self.tracking_direction = 1 if self.tracking_end_frame >= self.tracking_start_frame else -1
            # 여기까지 수정했다: live follow와 완료 판정을 위해 트랙킹 방향을 저장한다.
            self.tracking_seed_track_id = seed_ann.track_id
            self.tracking_seed_label_id = seed_ann.label_id

            self.is_tracking = True
            if self.timer.isActive():
                self.timer.stop()
                self.play_button.setText("Play")
            self._set_tracking_button_states(True)
            self._set_tracking_status("준비 중")
            self._update_tracking_progress_ui(0, self.tracking_start_frame, self.tracking_end_frame)
            self.canvas.set_tracking_mode(True)

            self.tracking_thread = QThread(self)
            self.tracking_worker = TrackingWorker(
                model_type=model_type,
                device="cuda",
                media_input=media_input,
                mask=mask,
                start_frame=self.tracking_start_frame,
                end_frame=self.tracking_end_frame,
                shape_type=seed_ann.shape_type,
                label_id=seed_ann.label_id,
                track_id=seed_ann.track_id,
                chunk_size=TrackingWorker.chunk_size_for_model(model_type),
                polygon_simplification=polygon_simplification,
            )
            self.tracking_worker.moveToThread(self.tracking_thread)
            self.tracking_thread.started.connect(self.tracking_worker.run)
            self.tracking_worker.progress.connect(self._on_tracking_worker_progress)
            self.tracking_worker.resultReady.connect(self._on_tracking_worker_result_ready)
            self.tracking_worker.finished.connect(self._on_tracking_worker_finished)
            self.tracking_worker.error.connect(self._on_tracking_worker_error)
            self.tracking_worker.finished.connect(self.tracking_thread.quit)
            self.tracking_worker.error.connect(self.tracking_thread.quit)
            self.tracking_thread.finished.connect(self._on_tracking_thread_finished)
            self.tracking_thread.start()
            self.show_status_message("트랙킹 시작")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"트랙킹 중 오류가 발생했습니다:\n{str(e)}")
            self._finalize_tracking_ui("오류")

    def _build_keypoint_tracking_seed(self, keypoint_anns: List[Annotation], frame_shape: tuple):
        """선택 keypoint들을 감싸는 임시 mask와 상대좌표 정보를 만든다."""
        try:
            import numpy as np
        except ImportError as ex:
            raise ImportError("numpy가 필요합니다") from ex

        h, w = int(frame_shape[0]), int(frame_shape[1])
        if h <= 0 or w <= 0:
            raise RuntimeError("현재 프레임 크기를 확인할 수 없습니다.")

        points = []
        for ann in keypoint_anns:
            x, y = ann.data  # type: ignore[misc]
            points.append((float(x), float(y)))
        if len(points) < 2:
            raise RuntimeError("Keypoint 트랙킹은 keypoint를 2개 이상 선택해야 합니다.")

        xs = [x for x, _y in points]
        ys = [y for _x, y in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        point_w = max_x - min_x
        point_h = max_y - min_y
        padding = max(6.0, max(point_w, point_h) * 0.08)

        x1 = min_x - padding
        y1 = min_y - padding
        x2 = max_x + padding
        y2 = max_y + padding

        min_size = 8.0
        if x2 - x1 < min_size:
            center_x = (x1 + x2) / 2.0
            x1 = center_x - min_size / 2.0
            x2 = center_x + min_size / 2.0
        if y2 - y1 < min_size:
            center_y = (y1 + y2) / 2.0
            y1 = center_y - min_size / 2.0
            y2 = center_y + min_size / 2.0

        max_x_bound = max(0.0, float(w - 1))
        max_y_bound = max(0.0, float(h - 1))
        x1 = clamp(x1, 0.0, max_x_bound)
        y1 = clamp(y1, 0.0, max_y_bound)
        x2 = clamp(x2, 0.0, max_x_bound)
        y2 = clamp(y2, 0.0, max_y_bound)
        if x2 <= x1:
            x2 = clamp(x1 + min_size, 0.0, max_x_bound)
            x1 = clamp(x2 - min_size, 0.0, max_x_bound)
        if y2 <= y1:
            y2 = clamp(y1 + min_size, 0.0, max_y_bound)
            y1 = clamp(y2 - min_size, 0.0, max_y_bound)

        seed_w = max(1.0, x2 - x1)
        seed_h = max(1.0, y2 - y1)
        mask = np.zeros((h, w), dtype=np.uint8)
        ix1 = max(0, min(w - 1, int(round(x1))))
        iy1 = max(0, min(h - 1, int(round(y1))))
        ix2 = max(0, min(w - 1, int(round(x2))))
        iy2 = max(0, min(h - 1, int(round(y2))))
        mask[iy1:iy2 + 1, ix1:ix2 + 1] = 255

        keypoint_infos = []
        for ann in keypoint_anns:
            x, y = ann.data  # type: ignore[misc]
            label_id = ann.label_id if ann.label_id in self.labels_by_id else None
            keypoint_infos.append(
                {
                    "track_id": int(ann.track_id),
                    "label_id": label_id,
                    "rel_x": (float(x) - x1) / seed_w,
                    "rel_y": (float(y) - y1) / seed_h,
                }
            )

        return mask, (x1, y1, seed_w, seed_h), keypoint_infos

    def _perform_keypoint_tracking(self, model_type: str, end_frame: int, keypoint_anns: List[Annotation]):
        """선택 keypoint들을 감싼 임시 영역을 추적하고 keypoint만 프레임별로 저장한다."""
        if not self._ensure_cuda_ready():
            return
        try:
            import numpy as np
        except ImportError as ex:
            QMessageBox.critical(self, "오류", f"{str(ex)}")
            return

        try:
            pixmap = self.source.get_pixmap(self.current_index)
            if pixmap.isNull():
                QMessageBox.warning(self, "오류", "현재 프레임을 읽을 수 없습니다.")
                return
            frame_shape = (pixmap.height(), pixmap.width())
            mask, _seed_box, keypoint_infos = self._build_keypoint_tracking_seed(keypoint_anns, frame_shape)
            if int(np.count_nonzero(mask)) == 0:
                QMessageBox.warning(self, "오류", "선택한 keypoint들로 유효한 초기 트랙킹 영역을 만들 수 없습니다.")
                return

            media_input = self._build_tracking_media_input()
            polygon_simplification = self._tracking_polygon_simplification_value()

            self.tracking_start_frame = self.current_index
            self.tracking_end_frame = end_frame
            self.tracking_direction = 1 if self.tracking_end_frame >= self.tracking_start_frame else -1
            self.tracking_seed_track_id = None
            self.tracking_seed_label_id = None

            self.is_tracking = True
            if self.timer.isActive():
                self.timer.stop()
                self.play_button.setText("Play")
            self._set_tracking_button_states(True)
            self._set_tracking_status("Keypoint 준비 중")
            self._update_tracking_progress_ui(0, self.tracking_start_frame, self.tracking_end_frame)
            self.canvas.set_tracking_mode(True)

            self.tracking_thread = QThread(self)
            self.tracking_worker = TrackingWorker(
                model_type=model_type,
                device="cuda",
                media_input=media_input,
                mask=mask,
                start_frame=self.tracking_start_frame,
                end_frame=self.tracking_end_frame,
                shape_type="box",
                label_id=None,
                track_id=0,
                chunk_size=TrackingWorker.chunk_size_for_model(model_type),
                polygon_simplification=polygon_simplification,
                keypoint_infos=keypoint_infos,
            )
            self.tracking_worker.moveToThread(self.tracking_thread)
            self.tracking_thread.started.connect(self.tracking_worker.run)
            self.tracking_worker.progress.connect(self._on_tracking_worker_progress)
            self.tracking_worker.resultReady.connect(self._on_tracking_worker_result_ready)
            self.tracking_worker.finished.connect(self._on_tracking_worker_finished)
            self.tracking_worker.error.connect(self._on_tracking_worker_error)
            self.tracking_worker.finished.connect(self.tracking_thread.quit)
            self.tracking_worker.error.connect(self.tracking_thread.quit)
            self.tracking_thread.finished.connect(self._on_tracking_thread_finished)
            self.tracking_thread.start()
            self.show_status_message(f"Keypoint 트랙킹 시작: {len(keypoint_anns)}개 keypoint")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"Keypoint 트랙킹 중 오류가 발생했습니다:\n{str(e)}")
            self._finalize_tracking_ui("오류")

    def _tracking_polygon_simplification_value(self) -> float:
        """AI Tracking UI에서 선택한 polygon 단순화 강도를 읽는다."""
        value = float(getattr(self, "tracking_polygon_simplification", 0.005))
        spin = getattr(self, "ai_tracking_simplification_spin", None)
        if spin is not None:
            value = float(spin.value())
            self.tracking_polygon_simplification = value
        return max(0.0, value)

    def _on_tracking_worker_progress(self, percent: int, frame_idx: int, end_frame: int):
        """워커가 보낸 진행률을 화면 상태와 작업 화면에 반영한다."""
        if not self.is_tracking:
            return
        self._set_tracking_status("트랙킹 중")
        self._update_tracking_progress_ui(percent, frame_idx, end_frame)
        self.canvas.update_tracking_progress(frame_idx, end_frame)

    def _is_valid_tracking_result(self, result) -> bool:
        """트랙킹 결과가 저장할 수 있는 유효한 도형인지 확인한다."""
        if result is None:
            return False
        if result.shape_type == "polygon":
            points = list(result.data or [])
            return len(points) >= 3
        try:
            _x, _y, w, h = result.data
        except Exception:
            return False
        return float(w) > 0 and float(h) > 0

    def _on_tracking_worker_result_ready(self, payload):
        """워커가 보낸 트랙킹 결과를 객체 표시 정보 저장소에 반영한다."""
        if self.source is None:
            return
        if isinstance(payload, dict) and payload.get("type") == "keypoints":
            self._on_tracking_worker_keypoints_ready(payload)
            return
        frame_idx, result, label_id, track_id = payload
        if not self._is_valid_tracking_result(result):
            self.show_status_message(f"프레임 {frame_idx}: 유효하지 않은 트랙킹 결과를 건너뜁니다.")
            return

        if result.shape_type == "polygon":
            ann, _ = self.store.upsert_annotation(
                frame_idx,
                "polygon",
                result.data,
                label_id,
                track_id=track_id,
                hidden=False,
            )
        else:
            ann, _ = self.store.upsert_annotation(
                frame_idx,
                "box",
                result.data,
                label_id,
                track_id=track_id,
                hidden=False,
            )

        # 여기서부터 수정하고: 역순 트랙킹에서도 live follow가 정상 동작하도록 거리와 종료 판정을 방향 독립적으로 계산한다.
        tracking_direction = getattr(self, "tracking_direction", 1)
        frame_distance = abs(frame_idx - self.tracking_start_frame)
        reached_end_frame = (
            frame_idx >= self.tracking_end_frame
            if tracking_direction > 0
            else frame_idx <= self.tracking_end_frame
        )
        should_follow_live = (
            self.follow_tracking_frames_live
            and max(1, int(self.tracking_live_follow_stride)) > 0
            and (
                (frame_distance % max(1, int(self.tracking_live_follow_stride)) == 0)
                or reached_end_frame
            )
        )
        # 여기까지 수정했다: 역순 트랙킹에서도 live follow가 정상 동작하도록 거리와 종료 판정을 방향 독립적으로 계산한다.

        if should_follow_live:
            self.current_index = clamp(frame_idx, 0, self.source.frame_count() - 1)
            self.update_frame_view(refresh_timeline=False)
            self.canvas.set_selected_annotations([ann.ann_id])
            self.sync_object_tree_selection([ann.ann_id])
            self.sync_label_list_view([ann.ann_id])
            return

        if self.current_index == frame_idx:
            self.refresh_annotations_for_current_frame([ann.ann_id])
            self.canvas.set_selected_annotations([ann.ann_id])
            self.sync_object_tree_selection([ann.ann_id])
            self.sync_label_list_view([ann.ann_id])

    def _on_tracking_worker_keypoints_ready(self, payload: Dict[str, object]):
        """워커가 보낸 keypoint 트랙킹 결과를 저장소에 반영한다."""
        if self.source is None:
            return
        frame_idx = int(payload.get("frame_idx", -1))
        if frame_idx < 0:
            return
        point_payloads = list(payload.get("points") or [])
        if not point_payloads:
            return

        ann_ids = []
        for point_info in point_payloads:
            try:
                track_id = int(point_info["track_id"])
                label_id = point_info.get("label_id")
                x, y = point_info["data"]
            except Exception:
                continue
            ann, _ = self.store.upsert_annotation(
                frame_idx,
                "keypoint",
                (float(x), float(y)),
                label_id,
                track_id=track_id,
                hidden=False,
            )
            ann_ids.append(ann.ann_id)

        if not ann_ids:
            return

        tracking_direction = getattr(self, "tracking_direction", 1)
        frame_distance = abs(frame_idx - self.tracking_start_frame)
        reached_end_frame = (
            frame_idx >= self.tracking_end_frame
            if tracking_direction > 0
            else frame_idx <= self.tracking_end_frame
        )
        should_follow_live = (
            self.follow_tracking_frames_live
            and max(1, int(self.tracking_live_follow_stride)) > 0
            and (
                (frame_distance % max(1, int(self.tracking_live_follow_stride)) == 0)
                or reached_end_frame
            )
        )

        if should_follow_live:
            self.current_index = clamp(frame_idx, 0, self.source.frame_count() - 1)
            self.update_frame_view(refresh_timeline=False)
            self.canvas.set_selected_annotations(ann_ids)
            self.sync_object_tree_selection(ann_ids)
            self.sync_label_list_view(ann_ids)
            return

        if self.current_index == frame_idx:
            self.refresh_annotations_for_current_frame(ann_ids)
            self.canvas.set_selected_annotations(ann_ids)
            self.sync_object_tree_selection(ann_ids)
            self.sync_label_list_view(ann_ids)

    def _on_tracking_worker_finished(self, result_info):
        """트랙킹 워커 완료 결과를 사용자에게 알리고 화면을 정리한다."""
        saved_count = int(result_info.get("saved_count", 0))
        saved_keypoint_count = int(result_info.get("saved_keypoint_count", 0))
        stopped = bool(result_info.get("stopped", False))
        mode = str(result_info.get("mode", "annotation"))

        if stopped:
            self._set_tracking_status("중지됨")
            self.show_status_message("트랙킹 중지 완료")
            if mode == "keypoint":
                message = (
                    f"Keypoint 트랙킹이 중지되었습니다.\n"
                    f"지금까지 {saved_count}개 프레임에 {saved_keypoint_count}개 keypoint를 저장했습니다."
                )
            else:
                message = f"트랙킹이 중지되었습니다.\n지금까지 {saved_count}개 프레임 결과를 저장했습니다."
            QMessageBox.information(
                self,
                "중지됨",
                message
            )
        else:
            self._set_tracking_status("완료")
            self.show_status_message("트랙킹 완료")
            if mode == "keypoint":
                message = (
                    f"Keypoint 트랙킹 완료!\n"
                    f"{saved_count}개 프레임에 {saved_keypoint_count}개 keypoint를 저장했습니다."
                )
            else:
                message = f"트랙킹 완료!\n{saved_count}개 프레임 결과를 저장했습니다."
            QMessageBox.information(
                self,
                "완료",
                message
            )

        self._finalize_tracking_ui("완료" if not stopped else "중지됨")
        self.refresh_timeline_tree()

    def _on_tracking_worker_error(self, err_msg: str):
        """트랙킹 워커 오류를 표시하고 트랙킹 화면 상태를 정리한다."""
        self._set_tracking_status("오류")
        self._finalize_tracking_ui("오류")
        QMessageBox.critical(self, "오류", f"트랙킹 중 오류가 발생했습니다:\n{err_msg}")

    def _on_tracking_thread_finished(self):
        """트랙킹 스레드가 끝난 뒤 워커와 스레드 참조를 정리한다."""
        if self.tracking_worker is not None:
            self.tracking_worker.deleteLater()
        if self.tracking_thread is not None:
            self.tracking_thread.deleteLater()
        self.tracking_worker = None
        self.tracking_thread = None

    def _finalize_tracking_ui(self, final_status: str):
        """트랙킹 종료 후 버튼, 진행률, 작업 화면 상태를 마무리한다."""
        self.is_tracking = False
        self._set_tracking_button_states(False)
        self.canvas.end_tracking()
        self._reset_tracking_progress_ui()
        self._set_tracking_status(final_status)

    def _ensure_cuda_ready(self) -> bool:
        """AI 기능 실행 전에 CUDA GPU 사용 가능 여부를 확인한다."""
        try:
            import torch
        except ImportError:
            QMessageBox.critical(self, "오류", "torch가 설치되지 않아 CUDA를 확인할 수 없습니다.")
            return False

        if not torch.cuda.is_available():
            QMessageBox.critical(
                self,
                "오류",
                "CUDA GPU를 사용할 수 없습니다.\n"
                "이 앱의 SAM 기능은 GPU 전용이며 CPU 실행은 지원하지 않습니다."
            )
            return False
        return True

    def _annotation_to_mask(self, ann: Annotation, frame_shape: tuple):
        """객체 표시 정보를 이진 마스크로 변환한다."""
        try:
            import cv2
            import numpy as np
        except ImportError:
            raise ImportError("cv2, numpy가 필요합니다")
        
        h, w = frame_shape
        mask = np.zeros((h, w), dtype=np.uint8)
        
        if ann.shape_type == "polygon":
            points = np.array(ann.data, dtype=np.int32)
            cv2.fillPoly(mask, [points], 255)
        elif ann.shape_type == "box":
            x, y, bw, bh = ann.data
            x, y, bw, bh = int(x), int(y), int(bw), int(bh)
            cv2.rectangle(mask, (x, y), (x + bw, y + bh), 255, -1)
        elif ann.shape_type == "keypoint":
            raise RuntimeError("Keypoint는 트랙킹 대상이 아닙니다. Box 또는 Polygon annotation을 선택하세요.")
        
        return mask
