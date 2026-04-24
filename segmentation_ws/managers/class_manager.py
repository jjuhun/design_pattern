class ClassManager:
    CLASS_COLORS = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFE66D",
        "#A29BFE", "#FDCB6E", "#00CEC9", "#E17055", "#74B9FF",
        "#55EFC4", "#FD79A8"
    ]

    def __init__(self):
        self.classes = []
        self.selected_class_id = None
        self.color_index = 0
        self.next_class_id = 0

    def has_class_name(self, name):
        return any(item["name"] == name for item in self.classes)

    def has_class_id(self, class_id):
        return any(item["class_id"] == class_id for item in self.classes)

    def add_class(self, name):
        name = name.strip()
        if not name:
            return False, None, "Class name is empty."

        if self.has_class_name(name):
            return False, None, "Class already exists."

        color = self.CLASS_COLORS[self.color_index % len(self.CLASS_COLORS)]
        self.color_index += 1

        class_id = self.next_class_id
        self.next_class_id += 1

        self.classes.append({
            "class_id": class_id,
            "name": name,
            "color": color,
        })
        return True, class_id, None

    def edit_class(self, old_class_id, new_class_id, new_name):
        new_name = new_name.strip()
        if new_class_id is None:
            return False, "Class ID is invalid."
        if not new_name:
            return False, "New class name is empty."

        existing_id = self.get_class_id_by_name(new_name)
        if existing_id is not None and existing_id != old_class_id:
            return False, "Class name already exists."

        if self.has_class_id(new_class_id) and new_class_id != old_class_id:
            return False, "Class ID already exists."

        for item in self.classes:
            if item["class_id"] == old_class_id:
                item["class_id"] = new_class_id
                item["name"] = new_name

                if self.selected_class_id == old_class_id:
                    self.selected_class_id = new_class_id

                if new_class_id >= self.next_class_id:
                    self.next_class_id = new_class_id + 1

                self.classes.sort(key=lambda x: x["class_id"])
                return True, None

        return False, "Class not found."

    def remove_class(self, class_id):
        before = len(self.classes)
        self.classes = [item for item in self.classes if item["class_id"] != class_id]

        if len(self.classes) == before:
            return False, "Class not found."

        if self.selected_class_id == class_id:
            self.selected_class_id = None

        return True, None

    def select_class(self, class_id):
        if self.has_class_id(class_id):
            self.selected_class_id = class_id
            return True
        return False

    def clear_selected_class(self):
        self.selected_class_id = None

    def get_class_color(self, class_id):
        for item in self.classes:
            if item["class_id"] == class_id:
                return item["color"]
        return "#FF0000"

    def get_class_name(self, class_id):
        for item in self.classes:
            if item["class_id"] == class_id:
                return item["name"]
        return f"Unknown({class_id})"

    def get_class_id_by_name(self, name):
        for item in self.classes:
            if item["name"] == name:
                return item["class_id"]
        return None

    def get_classes(self):
        return self.classes

    def get_selected_class_id(self):
        return self.selected_class_id

    def get_selected_name(self):
        if self.selected_class_id is None:
            return "None"
        return self.get_class_name(self.selected_class_id)

    def get_selected_class_display(self):
        if self.selected_class_id is None:
            return "None"
        return f"[{self.selected_class_id}] {self.get_class_name(self.selected_class_id)}"

    def clear(self):
        self.classes = []
        self.selected_class_id = None
        self.color_index = 0
        self.next_class_id = 0

    def load_classes(self, class_list):
        self.clear()

        max_class_id = -1

        for item in class_list:
            class_id = item["class_id"]
            name = item["name"]
            color = item.get("color", self.CLASS_COLORS[self.color_index % len(self.CLASS_COLORS)])

            self.classes.append({
                "class_id": class_id,
                "name": name,
                "color": color,
            })

            if class_id > max_class_id:
                max_class_id = class_id

        self.classes.sort(key=lambda x: x["class_id"])
        self.next_class_id = max_class_id + 1 if max_class_id >= 0 else 0

    # ================================================================
    # 추가사항!!
    # ================================================================
    def export_state(self):
        return {
            "classes": [dict(item) for item in self.classes],
            "selected_class_id": self.selected_class_id,
            "color_index": self.color_index,
            "next_class_id": self.next_class_id,
        }

    def load_state(self, state):
        self.classes = [dict(item) for item in state.get("classes", [])]
        self.selected_class_id = state.get("selected_class_id")
        self.color_index = state.get("color_index", 0)
        self.next_class_id = state.get("next_class_id", 0)
        self.classes.sort(key=lambda x: x["class_id"])