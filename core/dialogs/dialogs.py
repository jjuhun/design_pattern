# 여러 기능에서 다시 쓸 수 있는 작은 대화창들을 모아둔 파일입니다.
# 현재는 라벨 이름과 클래스 번호를 입력하는 창을 담당합니다.
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)


class LabelEditDialog(QDialog):
    def __init__(self, parent=None, title="Label", class_name="", class_index=0):
        """라벨 이름과 클래스 번호를 입력하는 창을 만든다."""
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setText(class_name)
        form.addRow("클래스 이름", self.name_edit)

        self.index_spin = QSpinBox()
        self.index_spin.setMinimum(0)
        self.index_spin.setMaximum(999999)
        self.index_spin.setValue(class_index)
        form.addRow("클래스 번호", self.index_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        """사용자가 입력한 라벨 이름과 클래스 번호를 반환한다."""
        return self.name_edit.text().strip(), int(self.index_spin.value())
