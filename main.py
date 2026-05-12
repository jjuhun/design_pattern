# 앱을 실행하는 시작 파일입니다.
# Qt 실행 환경을 준비한 뒤 MainWindow를 띄웁니다.
import os
import subprocess
import sys

# PyTorch CUDA 메모리 단편화 완화(사용자가 별도로 지정한 경우는 존중).
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")


def _has_working_x11_display() -> bool:
    """현재 DISPLAY 값으로 실제 X11 화면에 연결할 수 있는지 확인한다."""
    display = os.environ.get("DISPLAY")
    if not display:
        return False

    # DISPLAY 값 예시: :0, :1, localhost:10.0
    if display.startswith(":"):
        display_num = display[1:].split(".", 1)[0]
        if display_num.isdigit():
            if not os.path.exists(f"/tmp/.X11-unix/X{display_num}"):
                return False
    # 오래된 DISPLAY 값 때문에 xcb가 비정상 종료되지 않도록 실제 연결 가능 여부를 확인한다.
    try:
        probe = subprocess.run(
            ["xdpyinfo", "-display", display],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=1,
        )
        return probe.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        # 확인 도구가 없으면 일반 데스크톱 환경에서 계속 실행되도록 기존 판단을 유지한다.
        return True


def _configure_qt_environment() -> None:
    """QApplication 생성 전에 Qt 플러그인 환경 변수를 안정적으로 설정한다."""
    # 사용할 수 있는 화면 서버가 없으면(예: SSH/CI) 화면 없는 백엔드를 강제로 사용한다.
    if not os.environ.get("WAYLAND_DISPLAY") and not _has_working_x11_display():
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    qt_plugin_dir = os.path.join(
        sys.prefix,
        "lib",
        f"python{sys.version_info.major}.{sys.version_info.minor}",
        "site-packages",
        "PyQt5",
        "Qt5",
        "plugins",
    )

    if os.path.isdir(qt_plugin_dir):
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = qt_plugin_dir
        os.environ["QT_PLUGIN_PATH"] = qt_plugin_dir


_configure_qt_environment()

from PyQt5.QtWidgets import QApplication

from core.common.theme import apply_saved_theme
from main_window import MainWindow

# cv2를 불러오며 Qt 환경 변수가 바뀔 수 있는 모듈 임포트 뒤에 다시 적용한다.
_configure_qt_environment()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_saved_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
