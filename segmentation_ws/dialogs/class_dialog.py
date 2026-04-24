from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QHBoxLayout,
    QPushButton,
    QLabel,
)


class ClassDialog(QDialog):
    def __init__(self, title="Class", class_id=None, name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(320, 140)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Class ID"))
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("Class ID")
        self.id_edit.setText("" if class_id is None else str(class_id))
        layout.addWidget(self.id_edit)

        layout.addWidget(QLabel("Class Name"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Class name")
        self.name_edit.setText(name)
        layout.addWidget(self.name_edit)

        button_row = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        button_row.addStretch()
        button_row.addWidget(self.ok_btn)
        button_row.addWidget(self.cancel_btn)
        layout.addLayout(button_row)

        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        self.name_edit.returnPressed.connect(self.accept)
        self.id_edit.setFocus()
        self.id_edit.selectAll()

    def get_name(self):
        return self.name_edit.text().strip()

    def get_class_id(self):
        text = self.id_edit.text().strip()
        if text == "":
            return None
        try:
            return int(text)
        except ValueError:
            return None
