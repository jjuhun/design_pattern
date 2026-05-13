# features/ai_interact/ai_interact_engine_sam3.py

from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor


class SAM3ImageInteractEngine:
    """
    Meta SAM3 Image Interact Engine

    동작 기준:
    1. text 없음 + point/box 있음
       -> point/box visual prompt 기준 segmentation

    2. text 있음 + point/box 있음
       -> point/box 결과 + text 결과를 함께 사용

    3. text만 있음
       -> text prompt만으로 segmentation

    주의:
    - Meta SAM3의 point/box API 함수명은 설치된 sam3 버전에 따라 다를 수 있음.
    - text prompt는 공식 예시 기준 set_text_prompt() 사용.
    """

    def __init__(
        self,
        model_path=None,
        device="cuda",
        polygon_simplification=0.005,
    ):
        self.model_path = str(model_path) if model_path is not None else None
        self.device = device if device == "cuda" and torch.cuda.is_available() else "cpu"
        self.polygon_simplification = float(polygon_simplification)

        self.model = self._build_model()
        if hasattr(self.model, "to"):
            self.model.to(self.device)
        if hasattr(self.model, "eval"):
            self.model.eval()

        self.processor = Sam3Processor(self.model)
        self.state = None
        self.current_image = None

    def _build_model(self):
        """
        Meta SAM3 모델 생성.

        build_sam3_image_model()이 checkpoint/model_path 인자를 받는 버전이면 사용하고,
        아니면 기본 호출로 fallback한다.
        """
        if self.model_path and Path(self.model_path).exists():
            for kwargs in (
                {"checkpoint_path": self.model_path},
                {"checkpoint": self.model_path},
                {"model_path": self.model_path},
            ):
                try:
                    return build_sam3_image_model(**kwargs)
                except TypeError:
                    continue

        return build_sam3_image_model()

    def set_image(self, image):
        """
        image:
            - numpy.ndarray
            - PIL.Image
            - image path str
        """
        pil_image = self._to_pil_image(image)
        self.current_image = pil_image
        self.state = self.processor.set_image(pil_image)
        return self.state

    def predict(
        self,
        image=None,
        points=None,
        labels=None,
        box=None,
        text_prompt=None,
    ):
        """
        통합 SAM3 실행 함수.

        points:
            [x, y] 또는 [[x, y], [x, y]]

        labels:
            [1] 또는 [1, 0]
            1 = positive, 0 = negative

        box:
            [x1, y1, x2, y2]

        text_prompt:
            "person", "car", "person with red cloth" 등
        """
        if image is not None:
            self.set_image(image)

        if self.state is None:
            raise RuntimeError("SAM3 image state is empty. set_image() 또는 image 입력이 필요합니다.")

        has_points = points is not None and len(np.asarray(points).reshape(-1)) >= 2
        has_box = box is not None
        has_text = text_prompt is not None and str(text_prompt).strip() != ""

        if not has_points and not has_box and not has_text:
            raise RuntimeError("SAM3 프롬프트가 없습니다. point, box, text 중 하나는 필요합니다.")

        outputs = []

        # 1. point/box visual prompt
        if has_points or has_box:
            visual_output = self._predict_visual_prompt(
                points=points if has_points else None,
                labels=labels,
                box=box if has_box else None,
            )
            if visual_output is not None:
                outputs.append(visual_output)

        # 2. text prompt
        if has_text:
            text_output = self._predict_text_prompt(str(text_prompt).strip())
            if text_output is not None:
                outputs.append(text_output)

        merged = self._merge_outputs(outputs)

        if merged is None or merged.get("masks") is None:
            return None

        return self._select_best_mask(merged)

    def segment_with_points(self, image, points, labels):
        return self.predict(
            image=image,
            points=points,
            labels=labels,
            box=None,
            text_prompt=None,
        )

    def segment_with_box(self, image, box):
        return self.predict(
            image=image,
            points=None,
            labels=None,
            box=box,
            text_prompt=None,
        )

    def segment_with_box_and_points(self, image, box, points, labels):
        return self.predict(
            image=image,
            points=points,
            labels=labels,
            box=box,
            text_prompt=None,
        )

    def segment_with_text(self, image, text_prompt):
        return self.predict(
            image=image,
            points=None,
            labels=None,
            box=None,
            text_prompt=text_prompt,
        )

    def segment_with_prompts(self, image, points=None, labels=None, box=None, text_prompt=None):
        return self.predict(
            image=image,
            points=points,
            labels=labels,
            box=box,
            text_prompt=text_prompt,
        )

    def _predict_text_prompt(self, text_prompt):
        """Meta SAM3 공식 예시 기준 text prompt."""
        output = self.processor.set_text_prompt(
            state=self.state,
            prompt=text_prompt,
        )
        return self._normalize_output(output)

    def _predict_visual_prompt(self, points=None, labels=None, box=None):
        """
        point/box visual prompt.

        Meta SAM3 설치 버전에 따라 함수명이 다를 수 있어 후보 메서드를 순서대로 탐색한다.
        실제 repo에서 함수명이 확인되면 이 부분을 고정 함수명으로 바꾸면 된다.
        """
        norm_points = None
        norm_labels = None
        norm_box = None

        if points is not None:
            norm_points = self._normalize_points(points)
            if labels is None:
                norm_labels = np.ones((len(norm_points),), dtype=np.int32)
            else:
                norm_labels = np.asarray(labels, dtype=np.int32).reshape(-1)

            if len(norm_labels) != len(norm_points):
                raise ValueError("points 개수와 labels 개수가 다릅니다.")

        if box is not None:
            norm_box = self._normalize_box(box)

        candidate_calls = []

        # 통합 visual prompt 계열
        candidate_calls.append(("set_visual_prompt", dict(points=norm_points, labels=norm_labels, box=norm_box)))
        candidate_calls.append(("set_visual_prompt", dict(points=norm_points, labels=norm_labels, boxes=norm_box)))

        # point + box 통합 계열
        candidate_calls.append(("set_point_box_prompt", dict(points=norm_points, labels=norm_labels, box=norm_box)))
        candidate_calls.append(("set_points_box_prompt", dict(points=norm_points, labels=norm_labels, boxes=norm_box)))

        # box만
        if norm_box is not None and norm_points is None:
            candidate_calls.append(("set_box_prompt", dict(box=norm_box)))
            candidate_calls.append(("set_box_prompt", dict(boxes=norm_box)))
            candidate_calls.append(("set_boxes_prompt", dict(boxes=norm_box)))

        # point만
        if norm_points is not None and norm_box is None:
            candidate_calls.append(("set_point_prompt", dict(points=norm_points, labels=norm_labels)))
            candidate_calls.append(("set_points_prompt", dict(points=norm_points, labels=norm_labels)))

        last_error = None

        for method_name, kwargs in candidate_calls:
            if not hasattr(self.processor, method_name):
                continue

            method = getattr(self.processor, method_name)
            clean_kwargs = {key: value for key, value in kwargs.items() if value is not None}

            try:
                output = method(state=self.state, **clean_kwargs)
                return self._normalize_output(output)
            except TypeError as ex:
                last_error = ex
                continue

        raise NotImplementedError(
            "현재 설치된 Meta SAM3 Processor에서 point/box visual prompt API를 찾지 못했습니다.\n"
            "아래 명령으로 실제 함수명을 확인하세요:\n"
            "grep -R \"def set_.*point\" sam3/\n"
            "grep -R \"def set_.*box\" sam3/\n"
            "grep -R \"def set_.*visual\" sam3/\n"
            f"마지막 오류: {last_error}"
        )

    def _normalize_output(self, output):
        """
        Meta SAM3 output을 dict 형태로 정리.
        예상 기본 형태:
            output['masks']
            output['boxes']
            output['scores']
        """
        if output is None:
            return None

        if isinstance(output, dict):
            return {
                "masks": self._to_numpy(output.get("masks")),
                "boxes": self._to_numpy(output.get("boxes")),
                "scores": self._to_numpy(output.get("scores")),
            }

        raise TypeError(f"지원하지 않는 SAM3 output 형식입니다: {type(output)}")

    def _merge_outputs(self, outputs):
        outputs = [out for out in outputs if out is not None]

        if not outputs:
            return None

        if len(outputs) == 1:
            return outputs[0]

        merged = {
            "masks": None,
            "boxes": None,
            "scores": None,
        }

        for key in merged.keys():
            values = []
            for out in outputs:
                value = out.get(key)
                if value is not None:
                    values.append(value)

            if values:
                try:
                    merged[key] = np.concatenate(values, axis=0)
                except Exception:
                    merged[key] = values[0]

        return merged

    def _select_best_mask(self, output):
        """
        controller는 mask 하나를 받아 mask_to_polygon()으로 넘기는 구조이므로
        여러 mask 중 score가 가장 높은 mask 하나를 반환한다.
        """
        masks = output.get("masks")
        scores = output.get("scores")

        if masks is None:
            return None

        masks = np.asarray(masks)

        if masks.ndim == 2:
            return masks.astype(bool)

        if masks.ndim == 3:
            if scores is not None:
                scores = np.asarray(scores).reshape(-1)
                if len(scores) == masks.shape[0]:
                    best_idx = int(np.argmax(scores))
                    return masks[best_idx].astype(bool)

            return masks[0].astype(bool)

        if masks.ndim == 4:
            # [N, 1, H, W] 또는 [1, N, H, W] 형태 대응
            masks = np.squeeze(masks)
            if masks.ndim == 2:
                return masks.astype(bool)
            if masks.ndim == 3:
                if scores is not None:
                    scores = np.asarray(scores).reshape(-1)
                    if len(scores) == masks.shape[0]:
                        return masks[int(np.argmax(scores))].astype(bool)
                return masks[0].astype(bool)

        return None

    def mask_to_polygon(self, mask):
        """binary mask -> polygon points"""
        if mask is None:
            return []

        mask = np.asarray(mask)

        if mask.dtype != np.uint8:
            mask = mask.astype(np.uint8)

        if mask.max() <= 1:
            mask = mask * 255

        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        if not contours:
            return []

        contour = max(contours, key=cv2.contourArea)
        epsilon = self.polygon_simplification * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        points = []
        for p in approx.reshape(-1, 2):
            points.append((float(p[0]), float(p[1])))

        return points

    def _normalize_points(self, points):
        arr = np.asarray(points, dtype=np.float32)

        if arr.ndim == 1:
            arr = arr.reshape(1, 2)

        if arr.shape[-1] != 2:
            raise ValueError(f"points 형식이 잘못되었습니다: {points}")

        return arr

    def _normalize_box(self, box):
        arr = np.asarray(box, dtype=np.float32).reshape(-1)

        if arr.size != 4:
            raise ValueError(f"box는 [x1, y1, x2, y2] 형식이어야 합니다: {box}")

        return arr.reshape(1, 4)

    def _to_pil_image(self, image):
        if isinstance(image, Image.Image):
            return image.convert("RGB")

        if isinstance(image, str):
            return Image.open(image).convert("RGB")

        if isinstance(image, np.ndarray):
            arr = image

            if arr.ndim == 2:
                return Image.fromarray(arr).convert("RGB")

            if arr.ndim == 3 and arr.shape[2] == 4:
                arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2RGB)

            return Image.fromarray(arr.astype(np.uint8)).convert("RGB")

        raise TypeError(f"지원하지 않는 image 형식입니다: {type(image)}")

    def _to_numpy(self, value):
        if value is None:
            return None

        if torch.is_tensor(value):
            return value.detach().cpu().numpy()

        return np.asarray(value)