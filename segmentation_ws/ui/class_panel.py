from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)


class ClassPanel(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Class View", parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 18, 8, 8)
        layout.setSpacing(8)

        self.class_table = QTableWidget(0, 4)
        self.class_table.setHorizontalHeaderLabels(["Color", "Class ID", "Class Name", "Count"])
        self.class_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.class_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.class_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.class_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.class_table.verticalHeader().setVisible(False)
        self.class_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.class_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.class_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.class_table.setFixedHeight(100)  # 🔥 원하는 높이로 고정
        layout.addWidget(self.class_table)

        input_row = QHBoxLayout()
        self.class_name_edit = QLineEdit()
        self.class_name_edit.setPlaceholderText("Class name")
        self.add_class_btn = QPushButton("Add")
        input_row.addWidget(self.class_name_edit)
        input_row.addWidget(self.add_class_btn)
        layout.addLayout(input_row)

        manage_row = QHBoxLayout()
        self.edit_class_btn = QPushButton("Edit")
        self.remove_class_btn = QPushButton("Remove")
        manage_row.addWidget(self.edit_class_btn)
        manage_row.addWidget(self.remove_class_btn)
        layout.addLayout(manage_row)

        layout.addWidget(QLabel("Objects of selected class"))

        self.object_list = QListWidget()
        self.object_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.object_list.setFixedHeight(100) 
        layout.addWidget(self.object_list)
