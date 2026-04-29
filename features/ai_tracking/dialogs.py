# AI 트랙킹을 시작할 때 필요한 선택 창들을 모아둔 파일입니다.
# 사용할 SAM 모델과 트랙킹 종료 프레임을 고르게 합니다.
"""
트랙킹 관련 다이얼로그
"""

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QPushButton,
    QDialogButtonBox,
    QFormLayout,
)
from PyQt5.QtCore import Qt


class SelectSAMModelDialog(QDialog):
    """SAM 모델 선택 다이얼로그"""
    
    def __init__(self, parent=None):
        """사용자가 트랙킹에 사용할 SAM 모델을 고르는 창을 만든다."""
        super().__init__(parent)
        self.setWindowTitle("SAM 모델 선택")
        self.setModal(True)
        self.selected_model = "sam2"  # 기본값
        
        layout = QVBoxLayout(self)
        
        # 모델 선택 라디오 버튼
        model_group = QButtonGroup(self)
        
        layout.addWidget(QLabel("트랙킹에 사용할 SAM 모델을 선택하세요:"))
        
        radio_sam2 = QRadioButton("SAM2 (추천: 빠르고 안정적)")
        radio_sam3 = QRadioButton("SAM3 (더 정확함)")
        
        radio_sam2.setChecked(True)
        
        model_group.addButton(radio_sam2, 0)
        model_group.addButton(radio_sam3, 1)
        
        layout.addWidget(radio_sam2)
        layout.addWidget(radio_sam3)
        
        layout.addStretch()
        
        # 버튼
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.model_group = model_group
    
    def get_selected_model(self) -> str:
        """선택된 모델 반환"""
        if self.model_group.checkedId() == 1:
            return "sam3"
        return "sam2"


class TrackingRangeDialog(QDialog):
    """트랙킹 범위 설정 다이얼로그"""
    
    def __init__(self, parent=None, start_frame: int = 0, max_frame: int = 100):
        """트랙킹 시작 프레임과 종료 프레임을 보여주는 범위 선택 창을 만든다."""
        super().__init__(parent)
        self.setWindowTitle("트랙킹 범위 설정")
        self.setModal(True)
        self.start_frame = start_frame
        self.end_frame = start_frame
        
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        # 시작 프레임 (읽기 전용)
        start_label = QLabel(str(start_frame))
        form_layout.addRow("시작 프레임:", start_label)
        
        # 여기서부터 수정하고: 종료 프레임을 시작 프레임 앞/뒤 모두 선택할 수 있게 했다.
        # 종료 프레임
        self.end_spin = QSpinBox()
        self.end_spin.setMinimum(0)
        self.end_spin.setMaximum(max_frame - 1)
        default_end_frame = min(start_frame + 10, max_frame - 1)
        if default_end_frame == start_frame and start_frame > 0:
            default_end_frame = max(start_frame - 10, 0)
        self.end_spin.setValue(default_end_frame)
        form_layout.addRow("종료 프레임:", self.end_spin)
        # 여기까지 수정했다: 종료 프레임을 시작 프레임 앞/뒤 모두 선택할 수 있게 했다.
        
        layout.addLayout(form_layout)
        
        info_label = QLabel(f"총 프레임 수: {max_frame}")
        layout.addWidget(info_label)
        # 여기서부터 수정하고: 종료 프레임이 작으면 역순 트랙킹이 된다는 안내를 추가했다.
        direction_info_label = QLabel("종료 프레임이 시작 프레임보다 작으면 역순으로 트랙킹합니다.")
        direction_info_label.setWordWrap(True)
        layout.addWidget(direction_info_label)
        # 여기까지 수정했다: 종료 프레임이 작으면 역순 트랙킹이 된다는 안내를 추가했다.
        
        layout.addStretch()
        
        # 버튼
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_end_frame(self) -> int:
        """종료 프레임 반환"""
        return self.end_spin.value()
