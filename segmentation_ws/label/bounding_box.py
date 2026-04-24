from dataclasses import dataclass


@dataclass
class BoundingBox:
    box_id: int
    x1: int
    y1: int
    x2: int
    y2: int
    class_id: int

    def normalized(self):
        nx1 = min(self.x1, self.x2)
        ny1 = min(self.y1, self.y2)
        nx2 = max(self.x1, self.x2)
        ny2 = max(self.y1, self.y2)
        return BoundingBox(self.box_id, nx1, ny1, nx2, ny2, self.class_id)

    def to_xywh(self):
        box = self.normalized()
        return {
            "box_id": box.box_id,
            "x": box.x1,
            "y": box.y1,
            "w": box.x2 - box.x1,
            "h": box.y2 - box.y1,
            "class_id": box.class_id,
        }

    def is_valid(self, min_size=5):
        box = self.normalized()
        return (box.x2 - box.x1) >= min_size and (box.y2 - box.y1) >= min_size

    def contains_point(self, x, y):
        box = self.normalized()
        return box.x1 <= x <= box.x2 and box.y1 <= y <= box.y2
