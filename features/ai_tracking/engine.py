# 여러 프레임에 걸쳐 SAM 트랙킹을 실제로 실행하는 파일입니다.
# 초기 마스크를 기준으로 다음 프레임들의 결과를 계산합니다.
"""
SAM2/SAM3 기반 객체 트랙킹 엔진
"""

import gc
import numpy as np
import sys
import inspect
import os
import shutil
import tempfile

from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from pathlib import Path

Point = Tuple[float, float]
BoxData = Tuple[float, float, float, float]
PolygonData = List[Point]
ShapeData = Union[BoxData, PolygonData]


@dataclass
class TrackingResult:
    """트랙킹 결과 데이터"""
    frame_idx: int
    shape_type: str  # 가능한 값: "polygon" 또는 "bbox"
    data: ShapeData
    confidence: float = 1.0


class SAM2TrackingEngine:
    """SAM2/SAM3 트랙킹 엔진"""

    SAM2_CONFIG_CANDIDATES = [
        "configs/sam2.1/sam2.1_hiera_l.yaml",
        "sam2_hiera_l.yaml",
    ]
    SAM2_CHECKPOINT_CANDIDATES = [
        "weights/sam2.1_hiera_large.pt",
        "checkpoints/sam2.1_hiera_large.pt",
        "weights/sam2_hiera_large.pt",
        "checkpoints/sam2_hiera_large.pt",
    ]
    DEFAULT_OFFLOAD_VIDEO_TO_CPU = True
    DEFAULT_OFFLOAD_STATE_TO_CPU = True
    DEFAULT_ASYNC_LOADING_FRAMES = False
    
    def __init__(self, model_type: str = "sam2", device: str = "cuda"):
        """
        트랙킹 엔진의 모델 종류와 실행 장치를 설정한다.

        인자:
            model_type: "sam2" 또는 "sam3"
            device: "cuda" 또는 "cpu"
        """
        if device != "cuda":
            raise ValueError(
                "SAM interact/tracking is configured as GPU-only. "
                "Use device='cuda'."
            )
        self.model_type = model_type
        self.device = device
        self.predictor = None
        self.inference_state = None
        self._temp_frames_dir: Optional[str] = None
        self._propagate_iterator = None
        self._propagated_results_by_frame: Dict[int, TrackingResult] = {}
        self.current_frame_idx = -1
        self.is_tracking = False
        
        # 트랙킹된 결과 저장
        self.tracking_results: List[TrackingResult] = []

    def _validate_device(self):
        """CUDA GPU를 사용할 수 있는지 확인한다."""
        try:
            import torch
        except ImportError:
            raise RuntimeError("CUDA 사용 여부를 확인하려면 torch가 필요합니다.")

        if not torch.cuda.is_available():
            raise RuntimeError(
                "현재 CUDA GPU를 사용할 수 없습니다.\n"
                f"현재 실행 중인 Python: {sys.executable}\n"
                "nvidia-smi가 동작하는지, NVIDIA 드라이버가 설치/로드되어 있는지 확인하세요.\n"
                "이 앱의 SAM 기능은 GPU(CUDA) 전용으로 설정되어 있어 CPU 실행은 지원하지 않습니다."
            )

    def _resolve_checkpoint(self, checkpoints: Union[str, List[str]]) -> str:
        """체크포인트 경로를 현재 작업 폴더 또는 이 파일 기준으로 찾는다."""
        if isinstance(checkpoints, str):
            checkpoints = [checkpoints]

        candidates = []
        project_root = Path(__file__).resolve().parents[2]
        for checkpoint in checkpoints:
            candidates.extend([
                Path(checkpoint),
                Path(__file__).resolve().parent / checkpoint,
                project_root / checkpoint,
            ])

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        checked = "\n".join(f"- {candidate}" for candidate in candidates)
        raise FileNotFoundError(
            "SAM checkpoint 파일을 찾을 수 없습니다.\n"
            f"찾은 경로:\n{checked}\n"
            "weights 또는 checkpoints 폴더에 모델 파일을 넣거나 checkpoint 경로를 수정하세요."
        )

    def _build_video_predictor(self, builder, config_candidates: List[str], checkpoint: str):
        """설치된 SAM2 패키지 버전에 맞는 설정을 골라 예측기를 생성한다."""
        last_config_error = None
        for config in config_candidates:
            try:
                return builder(config, checkpoint, device=self.device)
            except Exception as e:
                message = str(e)
                if "Cannot find primary config" in message or "MissingConfigException" in type(e).__name__:
                    last_config_error = e
                    continue
                raise

        tried = "\n".join(f"- {config}" for config in config_candidates)
        raise RuntimeError(
            "SAM2 config 파일을 찾을 수 없습니다.\n"
            f"시도한 config:\n{tried}\n"
            "설치된 sam2 패키지의 configs 경로와 checkpoint 종류가 맞는지 확인하세요."
        ) from last_config_error

    def _mask_from_predictor_output(self, predictor_output):
        """비디오 예측기 출력에서 이진 마스크를 추출한다."""
        if predictor_output is None:
            return None

        out_mask_logits = predictor_output
        if isinstance(predictor_output, tuple):
            if len(predictor_output) >= 3:
                out_mask_logits = predictor_output[2]
            else:
                out_mask_logits = predictor_output[-1]

        if out_mask_logits is None:
            return None

        if hasattr(out_mask_logits, "__len__") and len(out_mask_logits) == 0:
            return None

        logits = out_mask_logits[0]
        if hasattr(logits, "detach"):
            mask = (logits > 0).detach().cpu().numpy()
        else:
            mask = np.asarray(logits) > 0

        mask = np.squeeze(mask).astype(np.uint8)
        return mask

    def _bbox_from_mask(self, mask: np.ndarray) -> Tuple[float, float, float, float]:
        """마스크가 차지하는 영역을 좌상단/우하단 박스 좌표로 계산한다."""
        ys, xs = np.where(mask > 0)
        if len(xs) == 0 or len(ys) == 0:
            return (0.0, 0.0, 0.0, 0.0)
        x1, x2 = xs.min(), xs.max()
        y1, y2 = ys.min(), ys.max()
        return (float(x1), float(y1), float(x2), float(y2))

    def _add_initial_prompt(
        self,
        start_frame_idx: int,
        initial_mask: Optional[np.ndarray] = None,
        prompt_points: Optional[np.ndarray] = None,
        prompt_labels: Optional[np.ndarray] = None,
        prompt_box: Optional[Tuple[float, float, float, float]] = None,
    ):
        """트랙킹 시작 프레임에 초기 마스크나 점/박스 입력 기준을 등록한다."""
        mask_u8 = None
        if initial_mask is not None:
            mask_u8 = (initial_mask > 0).astype(np.uint8)

        # 점/박스 입력 기준이 있으면 우선 사용한다.
        if prompt_points is not None or prompt_box is not None:
            add_points_or_box_fn = getattr(self.predictor, "add_new_points_or_box", None)
            if add_points_or_box_fn is not None:
                sig = inspect.signature(add_points_or_box_fn)
                params = sig.parameters
                kwargs = {
                    "inference_state": self.inference_state,
                    "frame_idx": start_frame_idx,
                    "obj_id": 1,
                }
                if prompt_points is not None and "points" in params:
                    kwargs["points"] = prompt_points
                if prompt_labels is not None and "labels" in params:
                    kwargs["labels"] = prompt_labels
                if prompt_box is not None and "box" in params:
                    kwargs["box"] = prompt_box
                return add_points_or_box_fn(**kwargs)

            # add_new_points_or_box를 사용할 수 없을 때는 마스크 입력으로 대체한다.
            if mask_u8 is None:
                if prompt_box is not None:
                    x1, y1, x2, y2 = [int(v) for v in prompt_box]
                    h = max(y2 + 1, 1)
                    w = max(x2 + 1, 1)
                    mask_u8 = np.zeros((h, w), dtype=np.uint8)
                    mask_u8[max(y1, 0):max(y2, 0), max(x1, 0):max(x2, 0)] = 1
                elif prompt_points is not None and len(prompt_points) > 0:
                    px, py = int(prompt_points[0][0]), int(prompt_points[0][1])
                    h = max(py + 16, 1)
                    w = max(px + 16, 1)
                    mask_u8 = np.zeros((h, w), dtype=np.uint8)
                    y1 = max(py - 12, 0)
                    y2 = min(py + 12, h - 1)
                    x1 = max(px - 12, 0)
                    x2 = min(px + 12, w - 1)
                    mask_u8[y1:y2 + 1, x1:x2 + 1] = 1

        if mask_u8 is None:
            raise RuntimeError("초기 프롬프트가 비어 있습니다.")

        add_new_mask_fn = getattr(self.predictor, "add_new_mask", None)
        if add_new_mask_fn is not None:
            sig = inspect.signature(add_new_mask_fn)
            params = sig.parameters
            kwargs = {
                "inference_state": self.inference_state,
                "frame_idx": start_frame_idx,
                "obj_id": 1,
            }

            if "mask" in params:
                kwargs["mask"] = mask_u8
                return add_new_mask_fn(**kwargs)

            if "points" in params and "labels" in params:
                points, labels = self._get_prompt_from_mask(mask_u8 * 255)
                kwargs["points"] = points
                kwargs["labels"] = labels
                return add_new_mask_fn(**kwargs)

            # 아주 오래되었거나 다른 형태의 버전에서는 위치 인자 호출을 시도한다.
            try:
                return add_new_mask_fn(self.inference_state, start_frame_idx, 1, mask_u8)
            except TypeError:
                pass

        add_points_or_box_fn = getattr(self.predictor, "add_new_points_or_box", None)
        if add_points_or_box_fn is not None:
            points, labels = self._get_prompt_from_mask(mask_u8 * 255)
            box = self._bbox_from_mask(mask_u8)
            sig = inspect.signature(add_points_or_box_fn)
            params = sig.parameters
            kwargs = {
                "inference_state": self.inference_state,
                "frame_idx": start_frame_idx,
                "obj_id": 1,
            }
            if "points" in params:
                kwargs["points"] = points
            if "labels" in params:
                kwargs["labels"] = labels
            if "box" in params:
                kwargs["box"] = box
            return add_points_or_box_fn(**kwargs)

        raise RuntimeError(
            "설치된 SAM 예측기에서 초기 프롬프트 함수(add_new_mask / add_new_points_or_box)를 찾을 수 없습니다."
        )

    def _cleanup_temp_frames_dir(self):
        """SAM 호환을 위해 만든 임시 프레임 폴더를 삭제한다."""
        if self._temp_frames_dir and Path(self._temp_frames_dir).exists():
            shutil.rmtree(self._temp_frames_dir, ignore_errors=True)
        self._temp_frames_dir = None

    def _build_numeric_frame_alias_dir(self, frame_files: List[Path]) -> str:
        """
        SAM2 일부 버전은 파일명 본문이 순수 숫자여야 하므로,
        frame_000123.jpg 같은 이름을 000123.jpg 별칭으로 매핑한다.
        이미지 재인코딩 없이 링크(또는 파일 복제 대체 처리)만 수행한다.
        """
        self._cleanup_temp_frames_dir()
        temp_dir = Path(tempfile.mkdtemp(prefix="sam2_frame_alias_"))
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

    def _prepare_video_input(self, video_frames: Union[str, Path]) -> Tuple[str, List[Path]]:
        """
        SAM2 비디오 예측기 init_state 입력을 준비한다.
        기본 입력은 디스크 기반 프레임 폴더 경로다.
        """
        if not isinstance(video_frames, (str, Path)):
            raise ValueError("video_frames는 프레임 디렉터리 경로(str/Path)여야 합니다.")
        frame_dir = Path(video_frames)
        if not frame_dir.exists() or not frame_dir.is_dir():
            raise ValueError("유효한 프레임 디렉터리가 아닙니다.")

        image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        frame_files = sorted(
            [p for p in frame_dir.iterdir() if p.is_file() and p.suffix.lower() in image_exts],
            key=lambda p: p.name,
        )
        if not frame_files:
            raise ValueError("프레임 디렉터리에 이미지 파일이 없습니다.")

        # 기본 경로는 항상 원본 프레임 디렉터리다.
        # 숫자 파일명 별칭은 init_state 직접 시도 실패 시 대체 처리로만 사용한다.
        return str(frame_dir), frame_files
    
    def load_model(self):
        """SAM2/SAM3 모델 로드 (첫 사용 시만)"""
        if self.predictor is not None:
            return
        
        try:
            from sam2.build_sam import build_sam2_video_predictor
        except ImportError as e:
            raise ImportError(
                "SAM2/SAM3 라이브러리를 설치하거나, 설치된 버전에서 sam2.build_sam 모듈을 사용할 수 있는지 확인하세요.\n"
                "pip install git+https://github.com/facebookresearch/segment-anything-2.git\n"
                f"현재 실행 중인 Python: {sys.executable}"
            ) from e

        if self.model_type == "sam2":
            self._validate_device()
            checkpoint = self._resolve_checkpoint(self.SAM2_CHECKPOINT_CANDIDATES)
            self.predictor = self._build_video_predictor(
                build_sam2_video_predictor,
                self.SAM2_CONFIG_CANDIDATES,
                checkpoint,
            )
        elif self.model_type == "sam3":
            try:
                from sam2.build_sam import build_sam3_video_predictor as sam3_builder
                sam3_configs = ["sam3_hiera_large.yaml", "sam3_hiera_l.yaml"]
            except ImportError:
                # 전용 SAM3 빌더가 없는 패키지는 SAM2 비디오 빌더를 대신 시도한다.
                try:
                    from sam2.build_sam import build_sam2_video_predictor as sam3_builder
                    sam3_configs = ["sam3_hiera_large.yaml", "sam3_hiera_l.yaml"]
                except ImportError as e:
                    raise ImportError(
                        "현재 설치된 sam2 패키지에서 SAM3 예측기를 찾을 수 없습니다.\n"
                        "SAM3를 사용하려면 지원되는 패키지를 설치하거나 SAM2를 선택하세요."
                    ) from e
            self._validate_device()
            checkpoint = self._resolve_checkpoint([
                "weights/sam3_hiera_large.pt",
                "checkpoints/sam3_hiera_large.pt",
            ])
            self.predictor = self._build_video_predictor(
                sam3_builder,
                sam3_configs,
                checkpoint,
            )
        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")

        print(f"✓ {self.model_type.upper()} 모델 로드 완료")
    
    def initialize_tracking(
        self,
        video_frames: Union[str, Path],
        initial_mask: Optional[np.ndarray],
        start_frame_idx: int = 0,
        shape_type: str = "polygon",
        prompt_points: Optional[np.ndarray] = None,
        prompt_labels: Optional[np.ndarray] = None,
        prompt_box: Optional[Tuple[float, float, float, float]] = None,
    ):
        """
        트랙킹 초기화
        
        인자:
            video_frames: 디스크 기반 프레임 폴더 경로
            initial_mask: 초기 마스크(uint8, 0-255), 점/박스 입력이 없을 때 사용
            start_frame_idx: 시작 프레임 인덱스
            shape_type: "polygon" 또는 "bbox"
        """
        self.load_model()
        self._cleanup_temp_frames_dir()

        predictor_input, frame_files = self._prepare_video_input(video_frames)
        try:
            self.inference_state = self._init_predictor_state(predictor_input)
        except Exception as direct_init_error:
            # 일부 SAM2 버전은 프레임 파일명 본문을 int()로 파싱한다.
            # 이 경우에만 숫자 별칭 디렉터리를 만들어 한 번 더 시도한다.
            if all(p.stem.isdigit() for p in frame_files):
                raise
            alias_input = self._build_numeric_frame_alias_dir(frame_files)
            try:
                self.inference_state = self._init_predictor_state(alias_input)
            except Exception:
                raise direct_init_error
        self.current_frame_idx = start_frame_idx
        self.is_tracking = True
        self.tracking_results = []
        self._propagate_iterator = None
        self._propagated_results_by_frame = {}
        self.shape_type = shape_type
        
        predictor_output = self._add_initial_prompt(
            start_frame_idx,
            initial_mask=initial_mask,
            prompt_points=prompt_points,
            prompt_labels=prompt_labels,
            prompt_box=prompt_box,
        )
        mask = self._mask_from_predictor_output(predictor_output)
        if mask is None:
            raise RuntimeError("초기 프롬프트 적용 후 마스크를 얻지 못했습니다.")
        result = self._mask_to_result(start_frame_idx, mask)
        self.tracking_results.append(result)
        
        print(f"✓ 프레임 {start_frame_idx}에서 트랙킹 초기화 완료")

    def _init_predictor_state(self, predictor_input: Union[str, Path]):
        """비디오 예측기의 추론 상태를 현재 패키지 버전에 맞춰 초기화한다."""
        init_state_fn = getattr(self.predictor, "init_state", None)
        if init_state_fn is None:
            raise RuntimeError("설치된 예측기에서 init_state 메서드를 찾을 수 없습니다.")

        # CPU 이전 옵션을 지원하는 버전에서는 키워드 인자로 명확히 전달한다.
        # 오래된 패키지에서 특정 키워드 인자를 지원하지 않으면 그 인자만 빼고 다시 시도한다.
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
                    if key in message and ("unexpected keyword argument" in message or "got an unexpected keyword" in message):
                        unsupported_key = key
                        break
                if unsupported_key is None:
                    raise
                kwargs.pop(unsupported_key, None)

        # 경로 위치 인자만 받는 예측기를 위한 마지막 호환 처리다.
        return init_state_fn(str(predictor_input))
    
    def track_frame(self, frame_idx: int) -> Optional[TrackingResult]:
        """
        다음 프레임 트랙킹
        
        인자:
            frame_idx: 트랙킹할 프레임 인덱스
            
        반환:
            TrackingResult 또는 실패 시 None
        """
        if not self.is_tracking or self.predictor is None:
            return None

        if frame_idx in self._propagated_results_by_frame:
            return self._propagated_results_by_frame[frame_idx]

        try:
            # 최신 SAM2 방식: propagate_in_video() 우선
            if hasattr(self.predictor, "propagate_in_video"):
                if self._propagate_iterator is None:
                    self._propagate_iterator = self.predictor.propagate_in_video(
                        inference_state=self.inference_state
                    )

                for propagate_output in self._propagate_iterator:
                    out_frame_idx = frame_idx
                    if isinstance(propagate_output, tuple) and len(propagate_output) >= 1:
                        out_frame_idx = int(propagate_output[0])

                    mask = self._mask_from_predictor_output(propagate_output)
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

            # 구버전 호환: track()
            if hasattr(self.predictor, "track"):
                video_predictor_output = self.predictor.track(
                    inference_state=self.inference_state,
                    obj_id=1,
                    frame_idx=frame_idx
                )
                mask = self._mask_from_predictor_output(video_predictor_output)
                if mask is None:
                    return None
                result = self._mask_to_result(frame_idx, mask)
                if result is None:
                    return None
                self._propagated_results_by_frame[frame_idx] = result
                self.tracking_results.append(result)
                return result

            raise RuntimeError("설치된 예측기에서 propagate_in_video/track 메서드를 찾을 수 없습니다.")
            
        except Exception as e:
            if "out of memory" in str(e).lower():
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
                raise RuntimeError(
                    "CUDA 메모리가 부족합니다. 트래킹 범위를 줄이거나(예: 100~200프레임 단위), "
                    "더 작은 모델을 사용하세요."
                ) from e
            print(f"✗ 프레임 {frame_idx} 트랙킹 실패: {e}")
            return None
    
    def stop_tracking(self):
        """트랙킹 중지 및 메모리 해제"""
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
        print("✓ 트랙킹 중지")
    
    def _get_prompt_from_mask(self, mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        마스크로부터 프롬프트 포인트 생성
        
        반환:
            (points, labels) - points는 (N, 2), labels는 (N,) 형태다.
        """
        # 마스크 정규화
        if mask.dtype != np.uint8:
            mask = (mask > 127).astype(np.uint8) * 255
        
        import cv2

        # 마스크 중심점 찾기
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            # 빈 마스크면 중앙점 반환
            h, w = mask.shape
            return np.array([[w // 2, h // 2]], dtype=np.float32), np.array([1], dtype=np.int32)
        
        # 가장 큰 외곽선의 중심점과 경계점을 선택한다.
        largest_contour = max(contours, key=cv2.contourArea)
        M = cv2.moments(largest_contour)
        
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            cx, cy = mask.shape[1] // 2, mask.shape[0] // 2
        
        # 중심점을 양수 프롬프트로 사용
        points = np.array([[cx, cy]], dtype=np.float32)
        labels = np.array([1], dtype=np.int32)  # 1은 양수 점을 뜻한다.
        
        return points, labels
    
    def _mask_to_result(self, frame_idx: int, mask: np.ndarray) -> Optional[TrackingResult]:
        """
        마스크를 객체 표시 데이터로 변환
        
        인자:
            frame_idx: 프레임 인덱스
            mask: 이진 마스크 (H, W)
            
        반환:
            TrackingResult
        """
        if self.shape_type == "polygon":
            polygon = self._mask_to_polygon(mask)
            if len(polygon) < 3:
                return None
            return TrackingResult(
                frame_idx=frame_idx,
                shape_type="polygon",
                data=polygon,
                confidence=1.0
            )
        else:  # 박스
            bbox = self._mask_to_bbox(mask)
            if bbox[2] <= 0 or bbox[3] <= 0:
                return None
            return TrackingResult(
                frame_idx=frame_idx,
                shape_type="bbox",
                data=bbox,
                confidence=1.0
            )
    
    def _mask_to_polygon(self, mask: np.ndarray) -> PolygonData:
        """
        마스크를 폴리곤 좌표로 변환
        
        인자:
            mask: 이진 마스크 (H, W)
            
        반환:
            (x, y) 좌표 목록
        """
        import cv2

        mask = (mask > 0).astype(np.uint8) * 255
        
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return []
        
        # 가장 큰 외곽선을 사용한다.
        largest_contour = max(contours, key=cv2.contourArea)
        
        # 외곽선 정밀도를 단순화한다.
        epsilon = 0.005 * cv2.arcLength(largest_contour, True)
        simplified = cv2.approxPolyDP(largest_contour, epsilon, True)
        
        # 좌표 변환: (x, y) 형식으로
        points = [(float(pt[0][0]), float(pt[0][1])) for pt in simplified]
        
        return points
    
    def _mask_to_bbox(self, mask: np.ndarray) -> BoxData:
        """
        마스크를 바운딩박스로 변환
        
        인자:
            mask: 이진 마스크 (H, W)
            
        반환:
            (x, y, w, h)
        """
        import cv2

        mask = (mask > 0).astype(np.uint8)
        
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            return (0.0, 0.0, 0.0, 0.0)
        
        # 모든 외곽선을 포함하는 바운딩박스를 만든다.
        all_points = np.vstack(contours)
        x, y, w, h = cv2.boundingRect(all_points)
        
        return (float(x), float(y), float(w), float(h))
    
    def get_results(self) -> List[TrackingResult]:
        """트랙킹 결과 반환"""
        return self.tracking_results
    
    def clear(self):
        """상태 초기화"""
        self.stop_tracking()
