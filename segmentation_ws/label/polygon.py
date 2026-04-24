from dataclasses import dataclass


@dataclass
class PolygonAnnotation:
    polygon_id: int
    points: list
    class_id: int

    def normalized_points(self):
        return [(int(x), int(y)) for x, y in self.points]

    def is_valid(self, min_points=3):
        return len(self.points) >= min_points

    def contains_point(self, x, y):
        points = self.normalized_points()
        if len(points) < 3:
            return False

        inside = False
        n = len(points)
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            if ((y1 > y) != (y2 > y)):
                denom = (y2 - y1)
                if denom == 0:
                    continue
                x_intersect = (x2 - x1) * (y - y1) / denom + x1
                if x < x_intersect:
                    inside = not inside
        return inside

    def move(self, dx, dy, image_width=None, image_height=None):
        moved = [(x + dx, y + dy) for x, y in self.points]

        if image_width is not None and moved:
            min_x = min(x for x, _ in moved)
            max_x = max(x for x, _ in moved)
            shift_x = 0
            if min_x < 0:
                shift_x = -min_x
            elif max_x >= image_width:
                shift_x = (image_width - 1) - max_x
            moved = [(x + shift_x, y) for x, y in moved]

        if image_height is not None and moved:
            min_y = min(y for _, y in moved)
            max_y = max(y for _, y in moved)
            shift_y = 0
            if min_y < 0:
                shift_y = -min_y
            elif max_y >= image_height:
                shift_y = (image_height - 1) - max_y
            moved = [(x, y + shift_y) for x, y in moved]

        self.points = [(int(x), int(y)) for x, y in moved]
        return True

    def update_point(self, point_idx, x, y, image_width=None, image_height=None):
        if point_idx < 0 or point_idx >= len(self.points):
            return False

        nx = int(x)
        ny = int(y)

        if image_width is not None:
            nx = max(0, min(nx, image_width - 1))
        if image_height is not None:
            ny = max(0, min(ny, image_height - 1))

        self.points[point_idx] = (nx, ny)
        return True

    def to_dict(self):
        return {
            "polygon_id": self.polygon_id,
            "points": [[int(x), int(y)] for x, y in self.points],
            "class_id": self.class_id,
        }