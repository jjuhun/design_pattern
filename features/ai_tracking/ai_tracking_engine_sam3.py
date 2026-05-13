# features/ai_tracking/ai_tracking_engine_sam3.py
from __future__ import annotations

import gc
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

from core.common.utils import natural_key


Point = Tuple[float, float]
BoxData = Tuple[float, float, float, float]
PolygonData = List[Point]
ShapeData = Union[BoxData, PolygonData]


@dataclass
class TrackingResult:
    frame_idx: int
    shape_type: str
    data: ShapeData
    confidence: float = 1.0


class SAM3TrackingEngine:
    DEFAULT_OFFLOAD_VIDEO_TO_CPU = True
    DEFAULT_OFFLOAD_STATE_TO_CPU = True
    DEFAULT_ASYNC_LOADING_FRAMES = False

    def __init__(
        self,
        device: str = "cuda",
        polygon_simplification: float = 0.005,
        checkpoint_path: str = "weights/sam3/sam3.pt",
    ):
        if device != "cuda":
            raise ValueError("SAM3 tracking은 CUDA 전용으로 사용합니다.")

        self.device = device
        self.polygon_simplification = max(0.0, float(polygon_simplification))
        self.checkpoint_path = checkpoint_path

        self.predictor = None
        self.inference_state = None
        self.shape_type = "polygon"
        self.is_tracking = False
        self.current_frame_idx = -1

        self._propagate_iterator = None
        self._propagated_results_by_frame: Dict[int, TrackingResult] = {}
        self._temp_frames_dir: Optional[str] = None
        self.tracking_results: List[TrackingResult] = []

    def _validate_device(self):
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("SAM3 tracking에는 torch가 필요합니다.") from exc

        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA GPU를 사용할 수 없습니다.\n"
                f"현재 Python: {sys.executable}"
            )

    def _resolve_checkpoint(self) -> str:
        project_root = Path(__file__).resolve().parents[2]
        candidates = [
            Path(self.checkpoint_path),
            Path.cwd() / self.checkpoint_path,
            project_root / self.checkpoint_path,
            project_root / "weights" / "sam3.pt",
            project_root / "weights" / "sam3" / "sam3.pt",
            project_root / "checkpoints" / "sam3.pt",
        ]

        for path in candidates:
            if path.exists():
                return str(path)

        checked = "\n".join(f"- {p}" for p in candidates)
        raise FileNotFoundError(
            "SAM3 checkpoint 파일을 찾을 수 없습니다.\n"
            f"확인한 경로:\n{checked}"
        )

    def load_model(self):
        if self.predictor is not None:
            return

        self._validate_device()
        checkpoint = self._resolve_checkpoint()

        try:
            from sam3.model_builder import build_sam3_video_predictor
        except ImportError as exc:
            raise ImportError(
                "SAM3 video predictor를 찾을 수 없습니다.\n"
                "facebookresearch/sam3 저장소를 설치했는지 확인하세요.\n"
                "예: cd sam3 && pip install -e ."
            ) from exc

        try:
            self.predictor = build_sam3_video_predictor(
                checkpoint_path=checkpoint,
                device=self.device,
            )
        except TypeError:
            try:
                self.predictor = build_sam3_video_predictor(
                    checkpoint=checkpoint,
                    device=self.device,
                )
            except TypeError:
                self.predictor = build_sam3_video_predictor(device=self.device)

        print("✓ SAM3 video tracking 모델 로드 완료")

    def _cleanup_temp_frames_dir(self):
        if self._temp_frames_dir and Path(self._temp_frames_dir).exists():
            shutil.rmtree(self._temp_frames_dir, ignore_errors=True)
        self._temp_frames_dir = None

    def _prepare_video_input(self, video_frames: Union[str, Path]):
        frame_dir = Path(video_frames)
        if not frame_dir.exists() or not frame_dir.is_dir():
            raise ValueError("유효한 프레임 디렉터리가 아닙니다.")

        image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        frame_files = sorted(
            [p for p in frame_dir.iterdir() if p.is_file() and p.suffix.lower() in image_exts],
            key=lambda p: natural_key(p.name),
        )
        if not frame_files:
            raise ValueError("프레임 디렉터리에 이미지 파일이 없습니다.")

        return str(frame_dir), frame_files

    def _build_numeric_frame_alias_dir(self, frame_files: List[Path]) -> str:
        self._cleanup_temp_frames_dir()
        temp_dir = Path(tempfile.mkdtemp(prefix="sam3_frame_alias_"))
        self._temp_frames_dir = str(temp_dir)

        for idx, src_path in enumerate(frame_files):
            dst_path = temp_dir / f"{idx:06d}.jpg"
            try:
                os.symlink(str(src_path.resolve()), str(dst_path))
                continue
            except OSError:
                pass
            try:
                os.link(str(src_path), str(dst_path))
                continue
            except OSError:
                pass
            shutil.copy2(str(src_path), str(dst_path))

        return str(temp_dir)

    def _init_predictor_state(self, predictor_input: Union[str, Path]):
        init_state_fn = getattr(self.predictor, "init_state", None)
        if init_state_fn is None:
            raise RuntimeError("SAM3 predictor에서 init_state 메서드를 찾을 수 없습니다.")

        kwargs = {
            "video_path": str(predictor_input),
            "async_loading_frames": self.DEFAULT_ASYNC_LOADING_FRAMES,
            "offload_video_to_cpu": self.DEFAULT_OFFLOAD_VIDEO_TO_CPU,
            "offload_state_to_cpu": self.DEFAULT_OFFLOAD_STATE_TO_CPU,
        }

        while kwargs:
            try:
                return init_state_fn(**kwargs)
            except TypeError as e:
                message = str(e)
                unsupported_key = None
                for key in list(kwargs.keys()):
                    if key in message and (
                        "unexpected keyword argument" in message
                        or "got an unexpected keyword" in message
                    ):
                        unsupported_key = key
                        break
                if unsupported_key is None:
                    raise
                kwargs.pop(unsupported_key, None)

        return init_state_fn(str(predictor_input))

    def _mask_from_predictor_output(self, output):
        if output is None:
            return None

        masks = None

        if isinstance(output, tuple):
            if len(output) >= 3:
                masks = output[2]
            elif len(output) >= 1:
                masks = output[-1]
        elif isinstance(output, dict):
            masks = output.get("masks") or output.get("mask_logits") or output.get("out_mask_logits")
        else:
            masks = output

        if masks is None:
            return None

        if hasattr(masks, "detach"):
            masks_np = masks.detach().cpu().numpy()
        else:
            masks_np = np.asarray(masks)

        if masks_np.size == 0:
            return None

        masks_np = np.squeeze(masks_np)

        if masks_np.ndim == 2:
            return (masks_np > 0).astype(np.uint8)

        if masks_np.ndim == 3:
            areas = masks_np.reshape(masks_np.shape[0], -1).sum(axis=1)
            best_idx = int(np.argmax(areas))
            return (masks_np[best_idx] > 0).astype(np.uint8)

        return None

    def _add_initial_prompt(
        self,
        start_frame_idx: int,
        initial_mask: Optional[np.ndarray] = None,
    ):
        if initial_mask is None:
            raise RuntimeError("SAM3 tracking 초기 마스크가 없습니다.")

        mask_u8 = (initial_mask > 0).astype(np.uint8)

        add_mask_fn = getattr(self.predictor, "add_new_mask", None)
        if add_mask_fn is not None:
            try:
                return add_mask_fn(
                    inference_state=self.inference_state,
                    frame_idx=start_frame_idx,
                    obj_id=1,
                    mask=mask_u8,
                )
            except TypeError:
                try:
                    return add_mask_fn(self.inference_state, start_frame_idx, 1, mask_u8)
                except TypeError:
                    pass

        add_prompt_fn = getattr(self.predictor, "add_new_points_or_box", None)
        if add_prompt_fn is not None:
            points, labels = self._get_prompt_from_mask(mask_u8 * 255)
            try:
                return add_prompt_fn(
                    inference_state=self.inference_state,
                    frame_idx=start_frame_idx,
                    obj_id=1,
                    points=points,
                    labels=labels,
                )
            except TypeError:
                return add_prompt_fn(self.inference_state, start_frame_idx, 1, points, labels)

        raise RuntimeError("SAM3 predictor에서 초기 prompt 입력 메서드를 찾을 수 없습니다.")

    def initialize_tracking(
        self,
        video_frames: Union[str, Path],
        initial_mask: Optional[np.ndarray],
        start_frame_idx: int = 0,
        shape_type: str = "polygon",
        prompt_points=None,
        prompt_labels=None,
        prompt_box=None,
    ):
        self.load_model()
        self._cleanup_temp_frames_dir()

        predictor_input, frame_files = self._prepare_video_input(video_frames)

        try:
            self.inference_state = self._init_predictor_state(predictor_input)
        except Exception as direct_error:
            alias_input = self._build_numeric_frame_alias_dir(frame_files)
            try:
                self.inference_state = self._init_predictor_state(alias_input)
            except Exception:
                raise direct_error

        self.shape_type = shape_type
        self.current_frame_idx = start_frame_idx
        self.is_tracking = True
        self.tracking_results = []
        self._propagate_iterator = None
        self._propagated_results_by_frame = {}

        output = self._add_initial_prompt(
            start_frame_idx=start_frame_idx,
            initial_mask=initial_mask,
        )

        mask = self._mask_from_predictor_output(output)
        if mask is not None:
            result = self._mask_to_result(start_frame_idx, mask)
            if result is not None:
                self.tracking_results.append(result)

        print(f"✓ SAM3 프레임 {start_frame_idx}에서 트랙킹 초기화 완료")

    def track_frame(self, frame_idx: int) -> Optional[TrackingResult]:
        if not self.is_tracking or self.predictor is None:
            return None

        if frame_idx in self._propagated_results_by_frame:
            return self._propagated_results_by_frame[frame_idx]

        try:
            propagate_fn = getattr(self.predictor, "propagate_in_video", None)
            if propagate_fn is not None:
                if self._propagate_iterator is None:
                    self._propagate_iterator = propagate_fn(
                        inference_state=self.inference_state
                    )

                for output in self._propagate_iterator:
                    out_frame_idx = frame_idx
                    if isinstance(output, tuple) and len(output) >= 1:
                        out_frame_idx = int(output[0])
                    elif isinstance(output, dict) and "frame_idx" in output:
                        out_frame_idx = int(output["frame_idx"])

                    mask = self._mask_from_predictor_output(output)
                    if mask is None:
                        continue

                    result = self._mask_to_result(out_frame_idx, mask)
                    if result is None:
                        continue

                    self._propagated_results_by_frame[out_frame_idx] = result
                    self.tracking_results.append(result)

                    if out_frame_idx >= frame_idx:
                        break

                return self._propagated_results_by_frame.get(frame_idx)

            track_fn = getattr(self.predictor, "track", None)
            if track_fn is not None:
                output = track_fn(
                    inference_state=self.inference_state,
                    obj_id=1,
                    frame_idx=frame_idx,
                )
                mask = self._mask_from_predictor_output(output)
                if mask is None:
                    return None

                result = self._mask_to_result(frame_idx, mask)
                if result is None:
                    return None

                self._propagated_results_by_frame[frame_idx] = result
                self.tracking_results.append(result)
                return result

            raise RuntimeError("SAM3 predictor에서 propagate_in_video/track 메서드를 찾을 수 없습니다.")

        except Exception as e:
            print(f"✗ SAM3 프레임 {frame_idx} 트랙킹 실패: {e}")
            return None

    def stop_tracking(self):
        self.is_tracking = False
        self.current_frame_idx = -1
        self._propagate_iterator = None
        self._propagated_results_by_frame.clear()
        self.tracking_results.clear()

        if self.predictor is not None and self.inference_state is not None:
            try:
                self.predictor.reset_state(self.inference_state)
            except Exception:
                pass

        self.inference_state = None
        self._cleanup_temp_frames_dir()

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        gc.collect()
        print("✓ SAM3 트랙킹 중지")

    def _get_prompt_from_mask(self, mask: np.ndarray):
        if mask.dtype != np.uint8:
            mask = (mask > 127).astype(np.uint8) * 255

        import cv2

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            h, w = mask.shape[:2]
            return np.array([[w / 2.0, h / 2.0]], dtype=np.float32), np.array([1], dtype=np.int32)

        contour = max(contours, key=cv2.contourArea)
        moments = cv2.moments(contour)

        if moments["m00"] != 0:
            cx = moments["m10"] / moments["m00"]
            cy = moments["m01"] / moments["m00"]
        else:
            x, y, w, h = cv2.boundingRect(contour)
            cx = x + w / 2.0
            cy = y + h / 2.0

        return np.array([[cx, cy]], dtype=np.float32), np.array([1], dtype=np.int32)

    def _mask_to_result(self, frame_idx: int, mask: np.ndarray) -> Optional[TrackingResult]:
        if mask is None or int(np.count_nonzero(mask)) == 0:
            return None

        if self.shape_type == "box":
            data = self._mask_to_box(mask)
            return TrackingResult(frame_idx=frame_idx, shape_type="box", data=data, confidence=1.0)

        points = self._mask_to_polygon(mask)
        if len(points) < 3:
            data = self._mask_to_box(mask)
            return TrackingResult(frame_idx=frame_idx, shape_type="box", data=data, confidence=1.0)

        return TrackingResult(frame_idx=frame_idx, shape_type="polygon", data=points, confidence=1.0)

    def _mask_to_box(self, mask: np.ndarray) -> BoxData:
        ys, xs = np.where(mask > 0)
        if len(xs) == 0 or len(ys) == 0:
            return (0.0, 0.0, 0.0, 0.0)

        x1 = float(xs.min())
        x2 = float(xs.max())
        y1 = float(ys.min())
        y2 = float(ys.max())

        return (x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1))

    def _mask_to_polygon(self, mask: np.ndarray) -> PolygonData:
        import cv2

        mask_u8 = (mask > 0).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []

        contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(contour) <= 1.0:
            return []

        epsilon = self.polygon_simplification * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        points = [(float(p[0][0]), float(p[0][1])) for p in approx]
        return points if len(points) >= 3 else []