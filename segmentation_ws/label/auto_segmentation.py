class AutoSegmentationEngine:
    def __init__(self):
        self.workspace_dir = "Auto_Segmentation"
        self.clear_session()

    def start_session(self, algorithm_name):
        self.algorithm_name = algorithm_name
        self.positive_points = []
        self.negative_points = []
        self.preview_points = []

    def set_algorithm(self, algorithm_name):
        self.algorithm_name = algorithm_name
        self.preview_points = self._build_preview_polygon()

    def get_algorithm(self):
        return self.algorithm_name

    def add_positive_point(self, x, y):
        self.positive_points.append((int(x), int(y)))
        self.preview_points = self._build_preview_polygon()
        return list(self.preview_points)

    def get_positive_points(self):
        return list(self.positive_points)

    def get_negative_points(self):
        return list(self.negative_points)

    def get_preview_polygon(self):
        return list(self.preview_points)

    def has_preview(self):
        return len(self.preview_points) >= 3

    def clear_session(self):
        self.algorithm_name = None
        self.positive_points = []
        self.negative_points = []
        self.preview_points = []

    def _build_preview_polygon(self):
        if not self.positive_points:
            return []

        if len(self.positive_points) == 1:
            x, y = self.positive_points[0]
            pad = 24
            return [
                (x - pad, y - pad),
                (x + pad, y - pad),
                (x + pad, y + pad),
                (x - pad, y + pad),
            ]

        xs = [p[0] for p in self.positive_points]
        ys = [p[1] for p in self.positive_points]

        pad = 20
        left = min(xs) - pad
        right = max(xs) + pad
        top = min(ys) - pad
        bottom = max(ys) + pad
        cx = (left + right) // 2
        cy = (top + bottom) // 2

        return [
            (left, cy),
            (left, top),
            (cx, top),
            (right, top),
            (right, cy),
            (right, bottom),
            (cx, bottom),
            (left, bottom),
        ]
