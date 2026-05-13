# SAM3 단일 프레임 상호작용 엔진
# Interactor에서 sam3 선택 시 사용합니다.

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np


Point = Tuple[float, float]
BoxXYXY = Tuple[float, float, float, float]


class SAM3ImageInteractEngine:
    def __init__(
        self,
        model_path: str = "weights/sam3/sam3.pt",
        device: str = "cuda",
        polygon_simplification: float = 0.005,
        confidence_threshold: float = 0.5,
    ):
        if device != "cuda":
            raise ValueError("SAM3 interact는 현재 CUDA 전용으로 설정합니다. device='cuda'를 사용하세요.")

        self.model_path = str(model_path)
        self.device = device
        self.polygon_simplification = max(0.0, float(polygon_simplification))
        self.confidence_threshold = float(confidence_threshold)

        self.model = None
        self.processor = None

    def _validate_device(self):
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("SAM3 실행에는 torch가 필요합니다.") from exc

        if not torch.cuda.is_available():
            raise RuntimeError(
                "현재 CUDA GPU를 사용할 수 없습니다.\n"
                f"현재 실행 중인 Python: {sys.executable}\n"
                "nvidia-smi, NVIDIA 드라이버, CUDA PyTorch 설치 상태를 확인하세요."
            )

    def _resolve_model_path(self) -> str:
        path = Path(self.model_path)

        project_root = Path(__file__).resolve().parents[2]
        candidates = [
            path,
            Path.cwd() / path,
            project_root / path,
            project_root / "weights" / "sam3.pt",
            project_root / "weights" / "sam3" / "sam3.pt",
            project_root / "checkpoints" / "sam3.pt",
        ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        checked = "\n".join(f"- {p}" for p in candidates)
        raise FileNotFoundError(
            "SAM3 checkpoint 파일을 찾을 수 없습니다.\n"
            f"확인한 경로:\n{checked}"
        )

    def load_model(self):
        """
        facebookresearch/sam3.git 설치 기준으로 SAM3 이미지 모델을 로드합니다.

        필요 설치:
            git clone https://github.com/facebookresearch/sam3.git
            cd sam3
            pip install -e .
        """
        if self.model is not None and self.processor is not None:
            return

        self._validate_device()
        checkpoint_path = self._resolve_model_path()

        try:
            from sam3.model_builder import build_sam3_image_model
            from sam3.model.sam3_image_processor import Sam3Processor
        except ImportError as exc:
            raise ImportError(
                "SAM3 패키지를 찾을 수 없습니다.\n"
                "facebookresearch/sam3 저장소를 clone한 뒤 `pip install -e .`로 설치하세요."
            ) from exc

        try:
            self.model = build_sam3_image_model(
                checkpoint_path=checkpoint_path,
                device=self.device,
            )
        except TypeError:
            try:
                self.model = build_sam3_image_model(
                    checkpoint=checkpoint_path,
                    device=self.device,
                )
            except TypeError:
                self.model = build_sam3_image_model(
                    device=self.device,
                )

        self.processor = Sam3Processor(
            self.model,
            confidence_threshold=self.confidence_threshold,
        )

    def _frame_to_pil(self, frame):
        """
        기존 controller에서 넘기는 frame은 RGB numpy array입니다.
        SAM3 processor 입력용 PIL Image로 변환합니다.
        """
        from PIL import Image

        if isinstance(frame, Image.Image):
            return frame.convert("RGB")

        arr = np.asarray(frame)
        if arr.ndim != 3:
            raise ValueError("frame은 HxWxC 형태의 이미지여야 합니다.")

        if arr.shape[2] == 4:
            arr = arr[:, :, :3]

        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)

        return Image.fromarray(arr, mode="RGB")

    def _result_to_mask(self, result, image_size: Tuple[int, int]) -> Optional[np.ndarray]:
        """
        SAM3 결과에서 가장 점수가 높은 mask 하나를 np.uint8(H, W)로 반환합니다.
        """
        width, height = image_size

        if result is None:
            return None

        masks = None
        scores = None

        if isinstance(result, dict):
            masks = result.get("masks", None)
            scores = result.get("scores", None)
        else:
            masks = getattr(result, "masks", None)
            scores = getattr(result, "scores", None)

        if masks is None:
            return None

        masks_np = np.asarray(masks)

        if masks_np.size == 0:
            return None

        if masks_np.ndim == 2:
            mask = masks_np > 0
            return mask.astype(np.uint8)

        if masks_np.ndim > 3:
            masks_np = np.squeeze(masks_np)

        if masks_np.ndim == 2:
            return (masks_np > 0).astype(np.uint8)

        if masks_np.ndim != 3:
            return None

        best_idx = 0
        if scores is not None:
            scores_np = np.asarray(scores).reshape(-1)
            if scores_np.size > 0:
                best_idx = int(np.argmax(scores_np))

        best_idx = max(0, min(best_idx, masks_np.shape[0] - 1))
        mask = masks_np[best_idx] > 0

        if mask.shape[0] != height or mask.shape[1] != width:
            try:
                import cv2
                mask = cv2.resize(
                    mask.astype(np.uint8),
                    (width, height),
                    interpolation=cv2.INTER_NEAREST,
                ) > 0
            except ImportError:
                pass

        return mask.astype(np.uint8)

    def segment_with_text(self, frame, text_prompt: str) -> Optional[np.ndarray]:
        self.load_model()

        text_prompt = str(text_prompt or "").strip()
        if not text_prompt:
            raise ValueError("SAM3 text prompt가 비어 있습니다.")

        image = self._frame_to_pil(frame)

        result = self.processor.set_image(image)
        if result is not None:
            pass

        try:
            output = self.processor.set_text_prompt(text_prompt)
        except AttributeError:
            output = self.processor(text=text_prompt)

        return self._result_to_mask(output, image.size)

    def segment_with_box(self, frame, box: BoxXYXY) -> Optional[np.ndarray]:
        self.load_model()

        image = self._frame_to_pil(frame)
        x1, y1, x2, y2 = [float(v) for v in box]

        self.processor.set_image(image)

        try:
            output = self.processor.set_box_prompt(
                box=[x1, y1, x2, y2],
            )
        except AttributeError:
            try:
                output = self.processor.set_box_prompt(
                    boxes=[[x1, y1, x2, y2]],
                )
            except AttributeError as exc:
                raise RuntimeError(
                    "현재 설치된 SAM3 Processor에서 box prompt API를 찾을 수 없습니다."
                ) from exc

        return self._result_to_mask(output, image.size)

    def segment_with_points(self, frame, points, labels) -> Optional[np.ndarray]:
        self.load_model()

        image = self._frame_to_pil(frame)
        points_np = np.asarray(points, dtype=np.float32)
        labels_np = np.asarray(labels, dtype=np.int32)

        if points_np.size == 0:
            raise ValueError("SAM3 point prompt가 비어 있습니다.")

        self.processor.set_image(image)

        try:
            output = self.processor.set_point_prompt(
                points=points_np.tolist(),
                labels=labels_np.tolist(),
            )
        except AttributeError:
            try:
                output = self.processor.set_points_prompt(
                    points=points_np.tolist(),
                    labels=labels_np.tolist(),
                )
            except AttributeError as exc:
                raise RuntimeError(
                    "현재 설치된 SAM3 Processor에서 point prompt API를 찾을 수 없습니다."
                ) from exc

        return self._result_to_mask(output, image.size)

    def segment_with_box_and_points(self, frame, box: BoxXYXY, points, labels) -> Optional[np.ndarray]:
        """
        SAM2와 인터페이스를 맞추기 위한 함수입니다.
        SAM3 Processor가 box+point 동시 prompt를 직접 지원하지 않는 경우,
        box 결과를 우선 사용합니다.
        """
        try:
            return self.segment_with_box(frame, box)
        except Exception:
            return self.segment_with_points(frame, points, labels)