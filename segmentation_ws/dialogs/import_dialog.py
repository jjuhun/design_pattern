from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QComboBox,
)


class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import")
        self.setModal(True)
        self.resize(560, 220)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Image source type
        type_label = QLabel("Image Source Type")
        layout.addWidget(type_label)

        type_row = QHBoxLayout()
        self.image_type_combo = QComboBox()
        self.image_type_combo.addItems(["MP4", "Frames Dir"])
        type_row.addWidget(self.image_type_combo)
        layout.addLayout(type_row)

        # Image source
        image_label = QLabel("Image Source (Required)")
        layout.addWidget(image_label)

        image_row = QHBoxLayout()
        self.image_path_edit = QLineEdit()
        self.image_path_edit.setPlaceholderText("Select mp4 file or frame directory")
        self.image_browse_btn = QPushButton("Browse")
        image_row.addWidget(self.image_path_edit)
        image_row.addWidget(self.image_browse_btn)
        layout.addLayout(image_row)

        # Label source
        label_label = QLabel("Label File (Optional)")
        layout.addWidget(label_label)

        label_row = QHBoxLayout()
        self.label_path_edit = QLineEdit()
        self.label_path_edit.setPlaceholderText("Select annotation json file")
        self.label_browse_btn = QPushButton("Browse")
        label_row.addWidget(self.label_path_edit)
        label_row.addWidget(self.label_browse_btn)
        layout.addLayout(label_row)

        # Buttons
        button_row = QHBoxLayout()
        self.ok_btn = QPushButton("OK")
        self.cancel_btn = QPushButton("Cancel")
        button_row.addStretch()
        button_row.addWidget(self.ok_btn)
        button_row.addWidget(self.cancel_btn)
        layout.addLayout(button_row)

        self.image_browse_btn.clicked.connect(self.browse_image_source)
        self.label_browse_btn.clicked.connect(self.browse_label_file)
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def browse_image_source(self):
        image_type = self.get_image_source_type()

        if image_type == "mp4":
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Video File",
                "",
                "Video Files (*.mp4 *.avi *.mov)"
            )
            if file_path:
                self.image_path_edit.setText(file_path)

        elif image_type == "dir":
            dir_path = QFileDialog.getExistingDirectory(
                self,
                "Select Frame Directory"
            )
            if dir_path:
                self.image_path_edit.setText(dir_path)

    def browse_label_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Label File",
            "",
            "JSON Files (*.json)"
        )
        if file_path:
            self.label_path_edit.setText(file_path)

    def get_image_source_type(self):
        text = self.image_type_combo.currentText().strip()
        if text == "MP4":
            return "mp4"
        return "dir"

    def get_image_path(self):
        return self.image_path_edit.text().strip()

    def get_label_path(self):
        return self.label_path_edit.text().strip()