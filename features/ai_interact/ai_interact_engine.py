# 한 프레임에서 SAM 모델을 실행하는 실제 AI 처리 파일입니다.
# 박스/점 입력 기준을 받아 마스크를 만들고 폴리곤 또는 박스 좌표로 바꿉니다.
"""
SAM2/SAM3 단일 프레임 상호작용(이미지 입력 기준) 엔진.
- 한 프레임 상호작용: 이미지 예측기를 사용한다.
- 연속 프레임 트랙킹: features/ai_tracking/engine.py의 비디오 예측기를 사용한다.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np

Point = Tuple[float, float]
BoxData = Tuple[float, float, float, float]
PolygonData = List[Point]


class SAMImageInteractEngine:
    SAM2_MODEL_SPECS = [
        {
            "name": "tiny",
            "configs": [
                "configs/sam2.1/sam2.1_hiera_t.yaml",
                "sam2.1_hiera_t.yaml",
                "sam2_hiera_t.yaml",
            ],
            "checkpoints": [
                "weights/sam2.1_hiera_tiny.pt",
                "checkpoints/sam2.1_hiera_tiny.pt",
                "weights/sam2_hiera_tiny.pt",
                "checkpoints/sam2_hiera_tiny.pt",
            ],
        },
        {
            "name": "large",
            "configs": [
                "configs/sam2.1/sam2.1_hiera_l.yaml",
                "sam2.1_hiera_l.yaml",
                "sam2_hiera_l.yaml",
            ],
            "checkpoints": [
                "weights/sam2.1_hiera_large.pt",
                "checkpoints/sam2.1_hiera_large.pt",
                "weights/sam2_hiera_large.pt",
                "checkpoints/sam2_hiera_large.pt",
            ],
        }
    ]

    SAM3_CONFIG_CANDIDATES = [
        "sam3_hiera_large.yaml",
        "sam3_hiera_l.yaml",
    ]
    SAM3_CHECKPOINT_CANDIDATES = [
        "weights/sam3_hiera_large.pt",
        "checkpoints/sam3_hiera_large.pt",
    ]

    def __init__(
        self,
        model_type: str = "sam2",
        device: str = "cuda",
        polygon_simplification: float = 0.005,
    ):
        """단일 프레임 SAM 상호작용 엔진의 모델 종류와 장치를 설정한다."""
        if device != "cuda":
            raise ValueError("SAM interact is configured as GPU-only. Use device='cuda'.")
        self.model_type = "sam2_tiny" if model_type == "sam2" else model_type
        self.device = device
        self.polygon_simplification = max(0.0, float(polygon_simplification))
        self.model_variant = None
        self.predictor = None

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

    def _resolve_existing_path(self, candidates: Union[str, List[str]]) -> str:
        """후보 경로 중 실제 존재하는 체크포인트 파일을 찾는다."""
        if isinstance(candidates, str):
            candidates = [candidates]

        expanded = []
        project_root = Path(__file__).resolve().parents[2]
        for item in candidates:
            expanded.extend([
                Path(item),
                Path(__file__).resolve().parent / item,
                project_root / item,
            ])

        for p in expanded:
            if p.exists():
                return str(p)

        checked = "\n".join(f"- {p}" for p in expanded)
        raise FileNotFoundError(
            "SAM checkpoint 파일을 찾을 수 없습니다.\n"
            f"찾은 경로:\n{checked}\n"
            "weights 또는 checkpoints 폴더에 모델 파일을 넣거나 checkpoint 경로를 수정하세요."
        )

    def _resolve_sam2_model_spec(self) -> Tuple[str, List[str], str]:
        """요청한 SAM2 variant의 checkpoint와 config 후보를 함께 고른다."""
        if self.model_type == "sam2_tiny":
            target_variant = "tiny"
        elif self.model_type == "sam2_large":
            target_variant = "large"
        else:
            raise ValueError(f"SAM2 variant를 알 수 없습니다: {self.model_type}")

        target_spec = None
        for spec in self.SAM2_MODEL_SPECS:
            if spec["name"] == target_variant:
                target_spec = spec
                break

        if target_spec is None:
            raise ValueError(f"SAM2 모델 사양을 찾을 수 없습니다: {target_variant}")

        try:
            checkpoint = self._resolve_existing_path(target_spec["checkpoints"])
        except FileNotFoundError as exc:
            expected = (
                "weights/sam2.1_hiera_tiny.pt"
                if target_variant == "tiny"
                else "weights/sam2.1_hiera_large.pt"
            )
            raise FileNotFoundError(
                f"SAM2.1 {target_variant} checkpoint 파일을 찾을 수 없습니다.\n"
                f"{expected} 위치에 파일을 넣어주세요."
            ) from exc

        return target_spec["name"], target_spec["configs"], checkpoint

    def _import_image_predictor_class(self):
        """설치된 sam2 패키지에서 사용할 수 있는 이미지 예측기 클래스를 찾는다."""
        candidates = [
            ("sam2.sam2_image_predictor", "SAM2ImagePredictor"),
            ("sam2.image_predictor", "SAM2ImagePredictor"),
            ("sam2.sam2_image_predictor", "SAMImagePredictor"),
            ("sam2.image_predictor", "SAMImagePredictor"),
        ]
        last_exc = None
        for module_name, class_name in candidates:
            try:
                module = __import__(module_name, fromlist=[class_name])
                cls = getattr(module, class_name)
                return cls
            except Exception as exc:
                last_exc = exc
                continue
        raise ImportError(
            "SAM2 image predictor를 찾을 수 없습니다. 설치된 sam2 패키지 버전을 확인하세요."
        ) from last_exc

    def _call_builder(self, builder, config_path: str, checkpoint_path: str):
        """빌더 함수 시그니처에 맞춰 모델 생성 함수를 호출한다."""
        sig = inspect.signature(builder)
        params = sig.parameters

        if "device" in params:
            return builder(config_path, checkpoint_path, device=self.device)

        # 일부 버전은 device 인자를 제공하지 않는다.
        return builder(config_path, checkpoint_path)

    def _build_model_with_candidates(self, builder, config_candidates: List[str], checkpoint: str):
        """여러 설정 후보 중 설치 환경에서 동작하는 설정으로 모델을 만든다."""
        last_cfg_err = None
        for cfg in config_candidates:
            try:
                return self._call_builder(builder, cfg, checkpoint)
            except Exception as exc:
                msg = str(exc)
                if "Cannot find primary config" in msg or "MissingConfigException" in type(exc).__name__:
                    last_cfg_err = exc
                    continue
                raise

        tried = "\n".join(f"- {c}" for c in config_candidates)
        raise RuntimeError(
            "SAM config 파일을 찾을 수 없습니다.\n"
            f"시도한 config:\n{tried}\n"
            "설치된 sam2 패키지의 config 경로와 checkpoint 종류가 맞는지 확인하세요."
        ) from last_cfg_err

    def load_model(self):
        """필요할 때 SAM 이미지 예측기 모델을 한 번만 로드한다."""
        if self.predictor is not None:
            return

        self._validate_device()

        try:
            from sam2 import build_sam as build_sam_module
        except Exception as exc:
            raise ImportError(
                "SAM2 라이브러리를 설치하거나, 설치된 버전에서 sam2.build_sam 모듈을 사용할 수 있는지 확인하세요.\n"
                "pip install git+https://github.com/facebookresearch/segment-anything-2.git\n"
                f"현재 실행 중인 Python: {sys.executable}"
            ) from exc

        ImagePredictorClass = self._import_image_predictor_class()

        if self.model_type in ("sam2_tiny", "sam2_large"):
            variant, config_candidates, checkpoint = self._resolve_sam2_model_spec()
            self.model_variant = variant
            builder = getattr(build_sam_module, "build_sam2", None)
            if builder is None:
                raise ImportError("설치된 sam2 패키지에서 build_sam2를 찾을 수 없습니다.")
            sam_model = self._build_model_with_candidates(builder, config_candidates, checkpoint)
            self.predictor = ImagePredictorClass(sam_model)
            return

        if self.model_type == "sam3":
            checkpoint = self._resolve_existing_path(self.SAM3_CHECKPOINT_CANDIDATES)
            # 전용 SAM3 빌더가 있으면 먼저 사용한다.
            builder = getattr(build_sam_module, "build_sam3", None)
            if builder is None:
                # 일부 패키지는 SAM3 설정에도 build_sam2를 재사용한다.
                builder = getattr(build_sam_module, "build_sam2", None)
            if builder is None:
                raise ImportError("설치된 sam2 패키지에서 SAM3용 빌더(build_sam3/build_sam2)를 찾을 수 없습니다.")
            sam_model = self._build_model_with_candidates(builder, self.SAM3_CONFIG_CANDIDATES, checkpoint)
            self.predictor = ImagePredictorClass(sam_model)
            return

        raise ValueError(f"Unknown model_type: {self.model_type}")

    def _parse_predict_output(self, predict_output):
        """예측기 출력에서 사용할 마스크 하나를 골라 이진 마스크로 바꾼다."""
        masks = None
        scores = None

        if isinstance(predict_output, tuple):
            if len(predict_output) >= 1:
                masks = predict_output[0]
            if len(predict_output) >= 2:
                scores = predict_output[1]
        else:
            masks = predict_output

        if masks is None:
            return None

        masks_np = np.asarray(masks)
        if masks_np.ndim == 2:
            mask = masks_np > 0
            return mask.astype(np.uint8)

        if masks_np.ndim >= 3:
            # 기대하는 형태는 [N, H, W]이다.
            cand = masks_np
            if cand.ndim > 3:
                cand = np.squeeze(cand)
            if cand.ndim == 2:
                return (cand > 0).astype(np.uint8)
            if cand.ndim != 3:
                return None

            best_idx = 0
            if scores is not None:
                scores_np = np.asarray(scores).reshape(-1)
                if scores_np.size > 0:
                    best_idx = int(np.argmax(scores_np))
            else:
                # 점수가 없으면 가장 넓은 마스크를 선택한다.
                areas = cand.reshape(cand.shape[0], -1).sum(axis=1)
                if areas.size > 0:
                    best_idx = int(np.argmax(areas))

            best_idx = max(0, min(best_idx, cand.shape[0] - 1))
            return (cand[best_idx] > 0).astype(np.uint8)

        return None

    def segment_with_box(self, frame_rgb: np.ndarray, box_xyxy: Tuple[float, float, float, float]) -> np.ndarray:
        """박스 입력 기준으로 현재 프레임을 분할한다."""
        self.load_model()
        self.predictor.set_image(frame_rgb)

        x1, y1, x2, y2 = box_xyxy
        box = np.array([[float(x1), float(y1), float(x2), float(y2)]], dtype=np.float32)
        try:
            output = self.predictor.predict(
                point_coords=None,
                point_labels=None,
                box=box,
                multimask_output=True,
            )
        except Exception:
            output = self.predictor.predict(
                point_coords=None,
                point_labels=None,
                box=box[0],
                multimask_output=True,
            )
        mask = self._parse_predict_output(output)
        if mask is None:
            raise RuntimeError("SAM image predictor가 유효한 마스크를 반환하지 않았습니다.")
        return mask

    def segment_with_points(self, frame_rgb: np.ndarray, points: np.ndarray, labels: np.ndarray) -> np.ndarray:
        """점 입력 기준으로 현재 프레임을 분할한다."""
        self.load_model()
        self.predictor.set_image(frame_rgb)

        pts = np.asarray(points, dtype=np.float32)
        lbs = np.asarray(labels, dtype=np.int32).reshape(-1)
        if pts.ndim != 2 or pts.shape[1] != 2:
            raise ValueError("points는 shape (N, 2) 이어야 합니다.")
        if lbs.size != pts.shape[0]:
            raise ValueError("labels 개수는 points 개수와 같아야 합니다.")

        output = self.predictor.predict(
            point_coords=pts,
            point_labels=lbs,
            box=None,
            multimask_output=True,
        )
        mask = self._parse_predict_output(output)
        if mask is None:
            raise RuntimeError("SAM image predictor가 유효한 마스크를 반환하지 않았습니다.")
        return mask

    def segment_with_box_and_points(
        self,
        frame_rgb: np.ndarray,
        box_xyxy: Tuple[float, float, float, float],
        points: np.ndarray,
        labels: np.ndarray,
    ) -> np.ndarray:
        """박스와 점 입력 기준을 함께 사용해 현재 프레임을 분할한다."""
        self.load_model()
        self.predictor.set_image(frame_rgb)

        pts = np.asarray(points, dtype=np.float32)
        lbs = np.asarray(labels, dtype=np.int32).reshape(-1)
        if pts.ndim != 2 or pts.shape[1] != 2:
            raise ValueError("points는 shape (N, 2) 이어야 합니다.")
        if lbs.size != pts.shape[0]:
            raise ValueError("labels 개수는 points 개수와 같아야 합니다.")

        x1, y1, x2, y2 = box_xyxy
        box = np.array([[float(x1), float(y1), float(x2), float(y2)]], dtype=np.float32)
        try:
            output = self.predictor.predict(
                point_coords=pts,
                point_labels=lbs,
                box=box,
                multimask_output=True,
            )
        except Exception:
            output = self.predictor.predict(
                point_coords=pts,
                point_labels=lbs,
                box=box[0],
                multimask_output=True,
            )

        mask = self._parse_predict_output(output)
        if mask is None:
            raise RuntimeError("SAM image predictor가 유효한 마스크를 반환하지 않았습니다.")
        return mask

    def mask_to_polygon(self, mask: np.ndarray) -> PolygonData:
        """이진 마스크에서 가장 큰 영역을 폴리곤 좌표로 변환한다."""
        import cv2

        m = (np.asarray(mask) > 0).astype(np.uint8) * 255
        contours, _ = cv2.findContours(m, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []

        largest = max(contours, key=cv2.contourArea)
        if self.polygon_simplification <= 0:
            simplified = largest
        else:
            epsilon = self.polygon_simplification * cv2.arcLength(largest, True)
            simplified = cv2.approxPolyDP(largest, epsilon, True)
        return [(float(pt[0][0]), float(pt[0][1])) for pt in simplified]

    @staticmethod
    def mask_to_box(mask: np.ndarray) -> BoxData:
        """이진 마스크 전체를 포함하는 박스 좌표를 계산한다."""
        import cv2

        m = (np.asarray(mask) > 0).astype(np.uint8)
        contours, _ = cv2.findContours(m, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return (0.0, 0.0, 0.0, 0.0)

        all_points = np.vstack(contours)
        x, y, w, h = cv2.boundingRect(all_points)
        return (float(x), float(y), float(w), float(h))
