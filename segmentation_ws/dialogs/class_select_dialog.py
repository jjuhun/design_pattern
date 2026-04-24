from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox


class ClassSelectDialog(QDialog):
    def __init__(self, class_items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Class")
        self.setModal(True)
        self.resize(320, 110)

        layout = QVBoxLayout(self)

        self.combo = QComboBox()
        for item in class_items:
            text = f'[{item["class_id"]}] {item["name"]}'
            self.combo.addItem(text, item["class_id"])
        layout.addWidget(self.combo)

        button_row = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        button_row.addStretch()
        button_row.addWidget(self.ok_btn)
        button_row.addWidget(self.cancel_btn)
        layout.addLayout(button_row)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.combo.setFocus()

    def get_selected_class_id(self):
        return self.combo.currentData()

    def get_selected_class_text(self):
        return self.combo.currentText()
