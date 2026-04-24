from label.bounding_box import BoundingBox
from label.polygon import PolygonAnnotation


class AnnotationManager:
    def __init__(self):
        self.frame_annotations = {}
        self.next_box_id = 1
        self.next_polygon_id = 1
        self.selected_box_ids = set()
        self.selected_polygon_ids = set()

    def _ensure_frame(self, frame_idx):
        if frame_idx not in self.frame_annotations:
            self.frame_annotations[frame_idx] = {"boxes": [], "polygons": []}
        elif isinstance(self.frame_annotations[frame_idx], list):
            self.frame_annotations[frame_idx] = {
                "boxes": self.frame_annotations[frame_idx],
                "polygons": [],
            }
        return self.frame_annotations[frame_idx]

    def _ensure_frame_entry(self, frame_idx):
        entry = self.frame_annotations.get(frame_idx)

        if isinstance(entry, list):
            entry = {
                "boxes": entry,
                "polygons": [],
            }
            self.frame_annotations[frame_idx] = entry
            return entry

        if entry is None:
            entry = {
                "boxes": [],
                "polygons": [],
            }
            self.frame_annotations[frame_idx] = entry
            return entry

        if "boxes" not in entry:
            entry["boxes"] = []
        if "polygons" not in entry:
            entry["polygons"] = []

        return entry
    
    def clear(self):
        self.frame_annotations = {}
        self.next_box_id = 1
        self.next_polygon_id = 1
        self.selected_box_ids = set()
        self.selected_polygon_ids = set()

    def create_bbox(self, x1, y1, x2, y2, class_id):
        bbox = BoundingBox(
            box_id=self.next_box_id,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            class_id=class_id,
        )
        self.next_box_id += 1
        return bbox.normalized()

    def add_bbox(self, frame_idx, bbox):
        entry = self._ensure_frame_entry(frame_idx)
        entry["boxes"].append(bbox.normalized())

    def get_bboxes(self, frame_idx):
        entry = self._ensure_frame_entry(frame_idx)
        return entry["boxes"]

    def get_box_by_id(self, box_id):
        for frame_idx, frame_data in self.frame_annotations.items():
            for box in frame_data["boxes"]:
                if box.box_id == box_id:
                    return frame_idx, box
        return None, None

    def find_box_at_point(self, frame_idx, x, y):
        for box in reversed(self.get_bboxes(frame_idx)):
            if box.contains_point(x, y):
                return box
        return None

    def update_box_position(self, box_id, dx, dy, image_width=None, image_height=None):
        _, box = self.get_box_by_id(box_id)
        if box is None:
            return False

        new_x1 = box.x1 + dx
        new_y1 = box.y1 + dy
        new_x2 = box.x2 + dx
        new_y2 = box.y2 + dy

        if image_width is not None:
            box_w = new_x2 - new_x1
            if new_x1 < 0:
                new_x1 = 0
                new_x2 = box_w
            if new_x2 >= image_width:
                new_x2 = image_width - 1
                new_x1 = new_x2 - box_w

        if image_height is not None:
            box_h = new_y2 - new_y1
            if new_y1 < 0:
                new_y1 = 0
                new_y2 = box_h
            if new_y2 >= image_height:
                new_y2 = image_height - 1
                new_y1 = new_y2 - box_h

        box.x1 = int(new_x1)
        box.y1 = int(new_y1)
        box.x2 = int(new_x2)
        box.y2 = int(new_y2)

        normalized = box.normalized()
        box.x1, box.y1, box.x2, box.y2 = (
            normalized.x1, normalized.y1, normalized.x2, normalized.y2
        )
        return True

    def update_box_coordinates(self, box_id, x1, y1, x2, y2, image_width=None, image_height=None, min_size=5):
        _, box = self.get_box_by_id(box_id)
        if box is None:
            return False

        nx1 = int(x1)
        ny1 = int(y1)
        nx2 = int(x2)
        ny2 = int(y2)

        if image_width is not None:
            nx1 = max(0, min(nx1, image_width - 1))
            nx2 = max(0, min(nx2, image_width - 1))

        if image_height is not None:
            ny1 = max(0, min(ny1, image_height - 1))
            ny2 = max(0, min(ny2, image_height - 1))

        left = min(nx1, nx2)
        right = max(nx1, nx2)
        top = min(ny1, ny2)
        bottom = max(ny1, ny2)

        if (right - left) < min_size or (bottom - top) < min_size:
            return False

        box.x1 = left
        box.y1 = top
        box.x2 = right
        box.y2 = bottom
        return True

    def update_box_class(self, box_id, new_class_id):
        _, box = self.get_box_by_id(box_id)
        if box is None:
            return False
        box.class_id = new_class_id
        return True

    def remove_box_by_id(self, box_id):
        return self.remove_boxes_by_ids({box_id})

    def remove_boxes_by_ids(self, box_ids):
        box_ids = set(box_ids)
        removed_any = False
        for frame_data in self.frame_annotations.values():
            boxes = frame_data["boxes"]
            new_boxes = [b for b in boxes if b.box_id not in box_ids]
            if len(new_boxes) != len(boxes):
                frame_data["boxes"] = new_boxes
                removed_any = True
        self.selected_box_ids -= box_ids
        return removed_any

    def remove_boxes_by_class_id(self, class_id):
        removed_ids = []
        for frame_data in self.frame_annotations.values():
            remain = []
            for box in frame_data["boxes"]:
                if box.class_id == class_id:
                    removed_ids.append(box.box_id)
                else:
                    remain.append(box)
            frame_data["boxes"] = remain
        self.selected_box_ids -= set(removed_ids)

    def replace_class_id_in_boxes(self, old_class_id, new_class_id):
        for frame_data in self.frame_annotations.values():
            for box in frame_data["boxes"]:
                if box.class_id == old_class_id:
                    box.class_id = new_class_id

    def count_boxes_by_class_id(self, class_id):
        count = 0
        for frame_data in self.frame_annotations.values():
            for box in frame_data["boxes"]:
                if box.class_id == class_id:
                    count += 1
        return count

    def get_boxes_by_class_id(self, class_id):
        result = []
        for frame_idx, frame_data in self.frame_annotations.items():
            for box in frame_data["boxes"]:
                if box.class_id == class_id:
                    result.append({
                        "frame_idx": frame_idx,
                        "box_id": box.box_id,
                        "class_id": box.class_id,
                        "x1": box.x1,
                        "y1": box.y1,
                        "x2": box.x2,
                        "y2": box.y2,
                    })
        return result

    def create_polygon(self, points, class_id):
        polygon = PolygonAnnotation(
            polygon_id=self.next_polygon_id,
            points=[(int(x), int(y)) for x, y in points],
            class_id=class_id,
        )
        self.next_polygon_id += 1
        return polygon

    def add_polygon(self, frame_idx, polygon):
        entry = self._ensure_frame_entry(frame_idx)
        entry["polygons"].append(polygon)

    def get_polygons(self, frame_idx):
        entry = self._ensure_frame_entry(frame_idx)
        return entry["polygons"]

    def get_polygon_by_id(self, polygon_id):
        for frame_idx, frame_data in self.frame_annotations.items():
            for polygon in frame_data["polygons"]:
                if polygon.polygon_id == polygon_id:
                    return frame_idx, polygon
        return None, None

    def find_polygon_at_point(self, frame_idx, x, y):
        for polygon in reversed(self.get_polygons(frame_idx)):
            if polygon.contains_point(x, y):
                return polygon
        return None

    def update_polygon_point(self, polygon_id, point_idx, x, y, image_width=None, image_height=None):
        _, polygon = self.get_polygon_by_id(polygon_id)
        if polygon is None:
            return False
        return polygon.update_point(point_idx, x, y, image_width=image_width, image_height=image_height)

    def update_polygon_class(self, polygon_id, new_class_id):
        _, polygon = self.get_polygon_by_id(polygon_id)
        if polygon is None:
            return False
        polygon.class_id = new_class_id
        return True

    def move_polygon(self, polygon_id, dx, dy, image_width=None, image_height=None):
        _, polygon = self.get_polygon_by_id(polygon_id)
        if polygon is None:
            return False
        polygon.move(dx, dy, image_width=image_width, image_height=image_height)
        return True

    def remove_polygon_by_id(self, polygon_id):
        return self.remove_polygons_by_ids({polygon_id})

    def remove_polygons_by_ids(self, polygon_ids):
        polygon_ids = set(polygon_ids)
        removed_any = False
        for frame_data in self.frame_annotations.values():
            polygons = frame_data["polygons"]
            new_polygons = [p for p in polygons if p.polygon_id not in polygon_ids]
            if len(new_polygons) != len(polygons):
                frame_data["polygons"] = new_polygons
                removed_any = True
        self.selected_polygon_ids -= polygon_ids
        return removed_any

    def remove_polygons_by_class_id(self, class_id):
        removed_ids = []
        for frame_data in self.frame_annotations.values():
            remain = []
            for polygon in frame_data["polygons"]:
                if polygon.class_id == class_id:
                    removed_ids.append(polygon.polygon_id)
                else:
                    remain.append(polygon)
            frame_data["polygons"] = remain
        self.selected_polygon_ids -= set(removed_ids)

    def replace_class_id_in_polygons(self, old_class_id, new_class_id):
        for frame_data in self.frame_annotations.values():
            for polygon in frame_data["polygons"]:
                if polygon.class_id == old_class_id:
                    polygon.class_id = new_class_id

    def count_polygons_by_class_id(self, class_id):
        count = 0
        for frame_data in self.frame_annotations.values():
            for polygon in frame_data["polygons"]:
                if polygon.class_id == class_id:
                    count += 1
        return count

    def get_polygons_by_class_id(self, class_id):
        result = []
        for frame_idx, frame_data in self.frame_annotations.items():
            for polygon in frame_data["polygons"]:
                if polygon.class_id == class_id:
                    result.append({
                        "frame_idx": frame_idx,
                        "polygon_id": polygon.polygon_id,
                        "class_id": polygon.class_id,
                        "points": list(polygon.points),
                    })
        return result

    def set_selected_box(self, box_id):
        self.selected_box_ids = {box_id}
        self.selected_polygon_ids.clear()

    def add_selected_box(self, box_id):
        self.selected_box_ids.add(box_id)
        self.selected_polygon_ids.clear()

    def toggle_selected_box(self, box_id):
        if box_id in self.selected_box_ids:
            self.selected_box_ids.remove(box_id)
        else:
            self.selected_box_ids.add(box_id)
        self.selected_polygon_ids.clear()

    def clear_selected_boxes(self):
        self.selected_box_ids.clear()

    def get_selected_box_ids(self):
        return set(self.selected_box_ids)

    def set_selected_polygon(self, polygon_id):
        self.selected_polygon_ids = {polygon_id}
        self.selected_box_ids.clear()

    def add_selected_polygon(self, polygon_id):
        self.selected_polygon_ids.add(polygon_id)
        self.selected_box_ids.clear()

    def toggle_selected_polygon(self, polygon_id):
        if polygon_id in self.selected_polygon_ids:
            self.selected_polygon_ids.remove(polygon_id)
        else:
            self.selected_polygon_ids.add(polygon_id)
        self.selected_box_ids.clear()

    def clear_selected_polygons(self):
        self.selected_polygon_ids.clear()

    def get_selected_polygon_ids(self):
        return set(self.selected_polygon_ids)

    def clear_selected_annotations(self):
        self.selected_box_ids.clear()
        self.selected_polygon_ids.clear()

    def update_item_class(self, item_type, item_id, new_class_id):
        if item_type == "box":
            return self.update_box_class(item_id, new_class_id)
        if item_type == "polygon":
            return self.update_polygon_class(item_id, new_class_id)
        return False

    def get_item_by_id(self, item_type, item_id):
        if item_type == "box":
            frame_idx, item = self.get_box_by_id(item_id)
        elif item_type == "polygon":
            frame_idx, item = self.get_polygon_by_id(item_id)
        else:
            return None, None
        return frame_idx, item

    def get_items_by_class_id(self, class_id):
        result = []
        for item in self.get_boxes_by_class_id(class_id):
            result.append({
                "frame_idx": item["frame_idx"],
                "item_type": "box",
                "item_id": item["box_id"],
            })
        for item in self.get_polygons_by_class_id(class_id):
            result.append({
                "frame_idx": item["frame_idx"],
                "item_type": "polygon",
                "item_id": item["polygon_id"],
            })
        result.sort(key=lambda x: (x["frame_idx"], x["item_type"], x["item_id"]))
        return result

    def export_dict(self):
        result = {}
        for frame_idx, frame_data in self.frame_annotations.items():
            result[frame_idx] = {
                "boxes": [box.to_xywh() for box in frame_data["boxes"]],
                "polygons": [polygon.to_dict() for polygon in frame_data["polygons"]],
            }
        return result

    def load_annotations(self, annotations_dict, total_frames=None, valid_class_ids=None):
        self.frame_annotations = {}
        self.selected_box_ids = set()
        self.selected_polygon_ids = set()

        max_box_id = 0
        max_polygon_id = 0

        for frame_key, data in annotations_dict.items():
            try:
                frame_idx = int(frame_key)
            except ValueError:
                continue

            if total_frames is not None and (frame_idx < 0 or frame_idx >= total_frames):
                continue

            frame_data = self._ensure_frame(frame_idx)
            frame_data["boxes"] = []
            frame_data["polygons"] = []

            if isinstance(data, list):
                box_items = data
                polygon_items = []
            else:
                box_items = data.get("boxes", [])
                polygon_items = data.get("polygons", [])

            for item in box_items:
                class_id = item["class_id"]
                if valid_class_ids is not None and class_id not in valid_class_ids:
                    continue

                x1 = item["x"]
                y1 = item["y"]
                x2 = x1 + item["w"]
                y2 = y1 + item["h"]

                bbox = BoundingBox(
                    box_id=item["box_id"],
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    class_id=class_id,
                ).normalized()
                frame_data["boxes"].append(bbox)
                max_box_id = max(max_box_id, bbox.box_id)

            for item in polygon_items:
                class_id = item["class_id"]
                if valid_class_ids is not None and class_id not in valid_class_ids:
                    continue

                polygon = PolygonAnnotation(
                    polygon_id=item["polygon_id"],
                    points=[(int(x), int(y)) for x, y in item.get("points", [])],
                    class_id=class_id,
                )
                if not polygon.is_valid():
                    continue
                frame_data["polygons"].append(polygon)
                max_polygon_id = max(max_polygon_id, polygon.polygon_id)

        self.next_box_id = max_box_id + 1 if max_box_id > 0 else 1
        self.next_polygon_id = max_polygon_id + 1 if max_polygon_id > 0 else 1

    # ================================================================
    # 추가사항!!
    # ================================================================
    def export_state(self):
        return {
            "annotations": self.export_dict(),
            "next_box_id": self.next_box_id,
            "next_polygon_id": self.next_polygon_id,
            "selected_box_ids": list(self.selected_box_ids),
            "selected_polygon_ids": list(self.selected_polygon_ids),
        }

    def load_state(self, state, total_frames=None, valid_class_ids=None):
        self.load_annotations(
            annotations_dict=state.get("annotations", {}),
            total_frames=total_frames,
            valid_class_ids=valid_class_ids,
        )
        self.next_box_id = state.get("next_box_id", self.next_box_id)
        self.next_polygon_id = state.get("next_polygon_id", self.next_polygon_id)
        self.selected_box_ids = set(state.get("selected_box_ids", []))
        self.selected_polygon_ids = set(state.get("selected_polygon_ids", []))