# SAM3 단일 프레임 상호작용 엔진입니다.
# HuggingFace Transformers 기반으로 SAM3를 로드하며, weights/*.pt 파일을 요구하지 않습니다.

from __future__ import annotations

import sys
from typing import List, Optional, Tuple

import numpy as np

Point = Tuple[float, float]
BoxData = Tuple[float, float, float, float]
PolygonData = List[Point]


class SAM3ImageInteractEngine:
    """
    HuggingFace Transformers 기반 SAM3 이미지 분할 엔진.

    - 최초 실행 시 HuggingFace cache로 모델을 다운로드한다.
    - 이후에는 ~/.cache/huggingface/hub 캐시를 재사용한다.
    - 프로젝트 weights/sam3_*.pt 파일은 사용하지 않는다.
    """

    MODEL_ID_CANDIDATES = (
        "facebook/sam3-hiera-large",
        "facebook/sam3",
    )

    _model = None
    _processor = None
    _model_id = None

    def __init__(self, device: str = "cuda", polygon_simplification: float = 0.005):
        if device != "cuda":
            raise ValueError("SAM3 interact is configured as GPU-only. Use device='cuda'.")
        self.device = device
        self.polygon_simplification = max(0.0, float(polygon_simplification))

    def _validate_device(self):
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("SAM3 실행에는 torch가 필요합니다.") from exc

        if not torch.cuda.is_available():
            raise RuntimeError(
                "현재 CUDA GPU를 사용할 수 없습니다.\n"
                f"현재 실행 중인 Python: {sys.executable}\n"
                "nvidia-smi, NVIDIA 드라이버, PyTorch CUDA 설치 상태를 확인하세요."
            )
        return torch

    def load_model(self):
        """SAM3 모델과 processor를 최초 1회만 로드한다."""
        if self.__class__._model is not None and self.__class__._processor is not None:
            return

        torch = self._validate_device()
        try:
            from transformers import Sam3Model, Sam3Processor
        except Exception as exc:
            raise ImportError(
                "SAM3 HuggingFace 실행에 필요한 transformers를 불러올 수 없습니다.\n"
                "pip install -U transformers huggingface_hub accelerate safetensors"
            ) from exc

        last_exc = None
        for model_id in self.MODEL_ID_CANDIDATES:
            try:
                processor = Sam3Processor.from_pretrained(model_id)
                model = Sam3Model.from_pretrained(model_id)
                model.to(self.device)
                model.eval()
                self.__class__._processor = processor
                self.__class__._model = model
                self.__class__._model_id = model_id
                return
            except Exception as exc:
                last_exc = exc
                continue

        raise RuntimeError(
            "SAM3 모델을 HuggingFace에서 불러오지 못했습니다.\n"
            "확인 항목:\n"
            "1) pip install -U transformers huggingface_hub accelerate safetensors\n"
            "2) hf auth login --force\n"
            "3) facebook/sam3 또는 facebook/sam3-hiera-large 접근 승인\n"
            "4) 최초 실행 시 인터넷 연결\n"
            f"마지막 오류: {last_exc}"
        )

    @property
    def model(self):
        self.load_model()
        return self.__class__._model

    @property
    def processor(self):
        self.load_model()
        return self.__class__._processor

    def _post_process(self, outputs, inputs, target_size: Tuple[int, int]):
        """Transformers processor의 SAM3 instance segmentation 결과를 표준 형태로 정리한다."""
        processor = self.processor
        h, w = target_size

        # Transformers 버전별 인자명이 달라질 수 있어 순차적으로 시도한다.
        attempts = [
            lambda: processor.post_process_instance_segmentation(
                outputs,
                threshold=0.5,
                mask_threshold=0.5,
                target_sizes=[(h, w)],
            ),
            lambda: processor.post_process_instance_segmentation(
                outputs,
                target_sizes=[(h, w)],
            ),
            lambda: processor.post_process_instance_segmentation(
                outputs,
                original_sizes=[(h, w)],
                reshaped_input_sizes=inputs.get("reshaped_input_sizes"),
            ),
        ]
        last_exc = None
        for fn in attempts:
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                continue
        raise RuntimeError(f"SAM3 post-process 실패: {last_exc}")

    def _extract_masks_scores(self, results) -> Tuple[np.ndarray, np.ndarray]:
        if results is None:
            return np.zeros((0, 1, 1), dtype=np.uint8), np.zeros((0,), dtype=np.float32)
        if isinstance(results, (list, tuple)):
            result = results[0] if results else {}
        else:
            result = results

        masks = result.get("masks") if isinstance(result, dict) else getattr(result, "masks", None)
        scores = None
        for key in ("scores", "score", "pred_scores"):
            if isinstance(result, dict) and key in result:
                scores = result[key]
                break
            if hasattr(result, key):
                scores = getattr(result, key)
                break

        if masks is None:
            return np.zeros((0, 1, 1), dtype=np.uint8), np.zeros((0,), dtype=np.float32)

        if hasattr(masks, "detach"):
            masks_np = masks.detach().cpu().numpy()
        else:
            masks_np = np.asarray(masks)
        masks_np = np.squeeze(masks_np)
        if masks_np.ndim == 2:
            masks_np = masks_np[None, :, :]
        if masks_np.ndim != 3:
            return np.zeros((0, 1, 1), dtype=np.uint8), np.zeros((0,), dtype=np.float32)
        masks_np = (masks_np > 0).astype(np.uint8)

        if scores is None:
            scores_np = masks_np.reshape(masks_np.shape[0], -1).sum(axis=1).astype(np.float32)
        elif hasattr(scores, "detach"):
            scores_np = scores.detach().cpu().numpy().reshape(-1).astype(np.float32)
        else:
            scores_np = np.asarray(scores).reshape(-1).astype(np.float32)
        if scores_np.size != masks_np.shape[0]:
            scores_np = masks_np.reshape(masks_np.shape[0], -1).sum(axis=1).astype(np.float32)
        return masks_np, scores_np

    def _run_sam3(self, frame_rgb: np.ndarray, text_prompt: str = "", box_xyxy: Optional[BoxData] = None):
        import torch
        from PIL import Image

        h, w = frame_rgb.shape[:2]
        image = Image.fromarray(np.asarray(frame_rgb, dtype=np.uint8), mode="RGB")
        text_prompt = str(text_prompt or "").strip()

        kwargs = {"images": image, "return_tensors": "pt"}
        if text_prompt:
            kwargs["text"] = text_prompt
        if box_xyxy is not None:
            x1, y1, x2, y2 = box_xyxy
            # processor 버전에 따라 input_boxes를 지원하지 않을 수 있다.
            kwargs["input_boxes"] = [[[float(x1), float(y1), float(x2), float(y2)]]]

        try:
            inputs = self.processor(**kwargs)
        except TypeError:
            # input_boxes 미지원 버전이면 text-only로 후보를 만들고 후단에서 box와 겹치는 마스크를 고른다.
            kwargs.pop("input_boxes", None)
            inputs = self.processor(**kwargs)

        inputs = {k: (v.to(self.device) if hasattr(v, "to") else v) for k, v in inputs.items()}
        with torch.inference_mode():
            try:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    outputs = self.model(**inputs)
            except Exception:
                outputs = self.model(**inputs)

        results = self._post_process(outputs, inputs, (h, w))
        return self._extract_masks_scores(results)

    def _select_best_mask(
        self,
        masks: np.ndarray,
        scores: np.ndarray,
        box_xyxy: Optional[BoxData] = None,
        points: Optional[np.ndarray] = None,
        labels: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        if masks.shape[0] == 0:
            raise RuntimeError("SAM3가 유효한 마스크를 반환하지 않았습니다. text prompt, bbox, 이미지 색상 변환을 확인하세요.")

        rank = scores.astype(np.float64).copy()

        if box_xyxy is not None:
            x1, y1, x2, y2 = [int(round(v)) for v in box_xyxy]
            h, w = masks.shape[1:]
            x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w))
            y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h))
            box_area = max(1, (x2 - x1) * (y2 - y1))
            overlaps = []
            for mask in masks:
                inter = int(mask[y1:y2, x1:x2].sum())
                area = max(1, int(mask.sum()))
                overlaps.append((inter / box_area) + (inter / area))
            rank += np.asarray(overlaps, dtype=np.float64) * 10.0

        if points is not None and labels is not None:
            pts = np.asarray(points, dtype=np.float32)
            lbs = np.asarray(labels, dtype=np.int32).reshape(-1)
            h, w = masks.shape[1:]
            point_scores = np.zeros((masks.shape[0],), dtype=np.float64)
            for px_py, label in zip(pts, lbs):
                px = max(0, min(int(round(float(px_py[0]))), w - 1))
                py = max(0, min(int(round(float(px_py[1]))), h - 1))
                inside = masks[:, py, px] > 0
                point_scores += np.where(inside, 5.0 if int(label) == 1 else -5.0, -2.0 if int(label) == 1 else 2.0)
            rank += point_scores

        best_idx = int(np.argmax(rank))
        mask = masks[best_idx].astype(np.uint8)
        if int(mask.sum()) == 0:
            raise RuntimeError("SAM3가 빈 마스크를 반환했습니다.")
        return mask

    def segment_with_text(self, frame_rgb: np.ndarray, text_prompt: str) -> np.ndarray:
        masks, scores = self._run_sam3(frame_rgb, text_prompt=text_prompt)
        return self._select_best_mask(masks, scores)

    def segment_with_text_and_box(self, frame_rgb: np.ndarray, text_prompt: str, box_xyxy: BoxData) -> np.ndarray:
        masks, scores = self._run_sam3(frame_rgb, text_prompt=text_prompt, box_xyxy=box_xyxy)
        return self._select_best_mask(masks, scores, box_xyxy=box_xyxy)

    def segment_with_text_and_points(self, frame_rgb: np.ndarray, text_prompt: str, points: np.ndarray, labels: np.ndarray) -> np.ndarray:
        if not text_prompt:
            raise RuntimeError("SAM3 point-only는 현재 HuggingFace image engine에서 직접 지원하지 않습니다. text prompt를 함께 입력하거나 SAM2를 사용하세요.")
        masks, scores = self._run_sam3(frame_rgb, text_prompt=text_prompt)
        return self._select_best_mask(masks, scores, points=points, labels=labels)

    def segment_with_text_box_and_points(
        self,
        frame_rgb: np.ndarray,
        text_prompt: str,
        box_xyxy: BoxData,
        points: np.ndarray,
        labels: np.ndarray,
    ) -> np.ndarray:
        masks, scores = self._run_sam3(frame_rgb, text_prompt=text_prompt, box_xyxy=box_xyxy)
        return self._select_best_mask(masks, scores, box_xyxy=box_xyxy, points=points, labels=labels)

    def mask_to_polygon(self, mask: np.ndarray) -> PolygonData:
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
        import cv2

        m = (np.asarray(mask) > 0).astype(np.uint8)
        contours, _ = cv2.findContours(m, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return (0.0, 0.0, 0.0, 0.0)
        all_points = np.vstack(contours)
        x, y, w, h = cv2.boundingRect(all_points)
        return (float(x), float(y), float(w), float(h))
