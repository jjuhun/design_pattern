from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)


class LogPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.title_label = QLabel("Log")
        self.log_list = QListWidget()
        self.placeholder_text = "Logs will appear here"
        self.log_list.addItem(self.placeholder_text)

        layout.addWidget(self.title_label)
        layout.addWidget(self.log_list)

    def add_log(self, text: str):
        if self.log_list.count() == 1 and self.log_list.item(0).text() == self.placeholder_text:
            self.log_list.clear()
        self.log_list.addItem(text)
        self.log_list.scrollToBottom()

    def clear_logs(self):
        self.log_list.clear()
        self.log_list.addItem(self.placeholder_text)
