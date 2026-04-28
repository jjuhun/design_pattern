# 객체 표시 정보와 라벨 데이터를 저장하는 구조를 모아둔 파일입니다.
# 화면에 그린 박스/폴리곤 정보는 AnnotationStore를 통해 프레임별로 관리됩니다.
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from copy import deepcopy

Point = Tuple[float, float]
BoxData = Tuple[float, float, float, float]
PolygonData = List[Point]
ShapeData = Union[BoxData, PolygonData]


@dataclass
class LabelDef:
    label_id: int
    class_name: str
    class_index: int
    color_hex: str


@dataclass
class Annotation:
    ann_id: int
    track_id: int
    frame_idx: int
    shape_type: str
    label_id: Optional[int]
    data: ShapeData
    hidden: bool = False


@dataclass
class RenderAnnotation:
    ann_id: int
    track_id: int
    shape_type: str
    data: ShapeData
    color_hex: str
    overlay_text: str
    object_list_text: str
    label_name: str
    label_id: Optional[int]
    hidden: bool = False


@dataclass
class ClipboardAnnotation:
    source_frame_idx: int
    track_id: int
    shape_type: str
    label_id: Optional[int]
    data: ShapeData


class AnnotationStore:
    def __init__(self):
        """프레임별 객체 표시 정보 저장소의 빈 상태를 만든다."""
        self._frames: Dict[int, Dict[int, Annotation]] = {}
        self._next_id = 1
        self._next_track_ids: Dict[Optional[int], int] = {}

    def clear(self):
        """저장된 모든 객체 표시 정보와 ID 상태를 초기화한다."""
        self._frames.clear()
        self._next_id = 1
        self._next_track_ids = {}

    def snapshot(self):
        """되돌리기/다시 실행에 사용할 현재 저장소 상태를 복사한다."""
        return {
            "frames": deepcopy(self._frames),
            "next_id": self._next_id,
            "next_track_ids": deepcopy(self._next_track_ids),
        }

    def restore(self, state):
        """복사해 둔 저장소 상태를 다시 적용한다."""
        self._frames = deepcopy(state.get("frames", {}))
        self._next_id = int(state.get("next_id", 1))
        next_track_ids = state.get("next_track_ids")
        if isinstance(next_track_ids, dict):
            self._next_track_ids = deepcopy(next_track_ids)
        else:
            legacy_next_track_id = int(state.get("next_track_id", 1))
            self._next_track_ids = {None: legacy_next_track_id}

    def _normalize_shape_data(self, shape_type: str, data: ShapeData) -> ShapeData:
        """박스 또는 폴리곤 좌표 데이터를 저장용 숫자 형태로 정리한다."""
        if shape_type == "box":
            x, y, w, h = data  # type: ignore[misc]
            return (float(x), float(y), float(w), float(h))
        if shape_type != "polygon":
            raise ValueError("지원하지 않는 shape_type입니다.")
        return [(float(x), float(y)) for x, y in data]  # type: ignore[list-item]

    def _allocate_track_id(self, label_id: Optional[int]) -> int:
        """라벨별로 다음 트랙 ID를 발급한다."""
        next_track_id = int(self._next_track_ids.get(label_id, 1))
        self._next_track_ids[label_id] = next_track_id + 1
        return next_track_id

    def _add(
        self,
        frame_idx: int,
        shape_type: str,
        data: ShapeData,
        label_id: Optional[int],
        track_id: Optional[int] = None,
        hidden: bool = False,
    ) -> Annotation:
        """새 객체 표시 정보를 만들고 지정한 프레임에 저장한다."""
        if track_id is None:
            track_id = self._allocate_track_id(label_id)
        ann = Annotation(
            ann_id=self._next_id,
            track_id=int(track_id),
            frame_idx=frame_idx,
            shape_type=shape_type,
            label_id=label_id,
            data=self._normalize_shape_data(shape_type, data),
            hidden=bool(hidden),
        )
        self._next_id += 1
        self._frames.setdefault(frame_idx, {})[ann.ann_id] = ann
        return ann

    def add_box(
        self,
        frame_idx: int,
        rect: BoxData,
        label_id: Optional[int],
        track_id: Optional[int] = None,
        hidden: bool = False,
    ) -> Annotation:
        """박스 객체 표시 정보를 프레임에 추가한다."""
        return self._add(frame_idx, "box", rect, label_id, track_id=track_id, hidden=hidden)

    def add_polygon(
        self,
        frame_idx: int,
        points: PolygonData,
        label_id: Optional[int],
        track_id: Optional[int] = None,
        hidden: bool = False,
    ) -> Annotation:
        """폴리곤 객체 표시 정보를 프레임에 추가한다."""
        return self._add(frame_idx, "polygon", points, label_id, track_id=track_id, hidden=hidden)

    def add_annotation(
        self,
        frame_idx: int,
        shape_type: str,
        data: ShapeData,
        label_id: Optional[int],
        track_id: Optional[int] = None,
        hidden: bool = False,
    ) -> Annotation:
        """도형 종류에 맞춰 객체 표시 정보를 추가한다."""
        if shape_type == "box":
            return self.add_box(frame_idx, data, label_id, track_id=track_id, hidden=hidden)  # type: ignore[arg-type]
        if shape_type == "polygon":
            return self.add_polygon(frame_idx, data, label_id, track_id=track_id, hidden=hidden)  # type: ignore[arg-type]
        raise ValueError("지원하지 않는 shape_type입니다.")

    def get_annotations(self, frame_idx: int, include_hidden: bool = True) -> List[Annotation]:
        """지정한 프레임의 객체 표시 정보 목록을 ID 순서로 반환한다."""
        anns = list(self._frames.get(frame_idx, {}).values())
        if not include_hidden:
            anns = [ann for ann in anns if not ann.hidden]
        return sorted(anns, key=lambda ann: ann.ann_id)

    def get_annotation(self, frame_idx: int, ann_id: int) -> Optional[Annotation]:
        """지정한 프레임에서 특정 객체 표시 정보를 찾는다."""
        return self._frames.get(frame_idx, {}).get(ann_id)

    def get_annotation_by_track_id(self, frame_idx: int, track_id: int, label_id: Optional[int] = None) -> Optional[Annotation]:
        """프레임과 트랙 ID로 객체 표시 정보를 찾는다."""
        for ann in self._frames.get(frame_idx, {}).values():
            if ann.track_id != track_id:
                continue
            if label_id is not None and ann.label_id != label_id:
                continue
            return ann
        return None

    def all_annotations(self) -> List[Annotation]:
        """모든 프레임의 객체 표시 정보를 프레임 순서대로 반환한다."""
        anns: List[Annotation] = []
        for frame in sorted(self._frames.keys()):
            anns.extend(sorted(self._frames[frame].values(), key=lambda ann: (ann.frame_idx, ann.ann_id)))
        return anns

    def update_annotation_label(self, frame_idx: int, ann_id: int, label_id: Optional[int]) -> bool:
        """객체 표시 정보의 라벨을 바꾸고 새 트랙 ID를 부여한다."""
        ann = self.get_annotation(frame_idx, ann_id)
        if ann is None:
            return False
        if ann.label_id != label_id:
            ann.label_id = label_id
            ann.track_id = self._allocate_track_id(label_id)
        return True

    def update_annotation_data(self, frame_idx: int, ann_id: int, data: ShapeData) -> bool:
        """객체 표시 정보의 도형 좌표를 갱신한다."""
        ann = self.get_annotation(frame_idx, ann_id)
        if ann is None:
            return False
        ann.data = self._normalize_shape_data(ann.shape_type, data)
        return True

    def update_annotation_visibility(self, frame_idx: int, ann_id: int, hidden: bool) -> bool:
        """객체 표시 정보의 숨김 상태를 갱신한다."""
        ann = self.get_annotation(frame_idx, ann_id)
        if ann is None:
            return False
        ann.hidden = bool(hidden)
        return True

    def upsert_annotation(
        self,
        frame_idx: int,
        shape_type: str,
        data: ShapeData,
        label_id: Optional[int],
        track_id: int,
        hidden: bool = False,
    ):
        """같은 트랙의 객체 표시 정보가 있으면 갱신하고 없으면 새로 추가한다."""
        ann = self.get_annotation_by_track_id(frame_idx, track_id, label_id=label_id)
        if ann is not None:
            ann.shape_type = shape_type
            ann.label_id = label_id
            ann.data = self._normalize_shape_data(shape_type, data)
            ann.hidden = bool(hidden)
            return ann, False
        return self._add(frame_idx, shape_type, data, label_id, track_id=track_id, hidden=hidden), True

    def clear_label_from_annotations(self, label_id: int):
        """삭제된 라벨을 사용하는 객체 표시 정보에서 라벨 연결을 제거한다."""
        for ann in self.all_annotations():
            if ann.label_id == label_id:
                ann.label_id = None

    def delete_annotation(self, frame_idx: int, ann_id: int) -> bool:
        """지정한 프레임의 객체 표시 정보를 삭제한다."""
        frame_map = self._frames.get(frame_idx)
        if frame_map is None or ann_id not in frame_map:
            return False
        del frame_map[ann_id]
        if not frame_map:
            del self._frames[frame_idx]
        return True
