# qt-material 테마 적용과 사용자 선택 저장을 담당한다.
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeSpec:
    key: str
    label: str
    material_theme: str


@dataclass(frozen=True)
class ThemeApplyResult:
    key: str
    label: str
    applied: bool
    error: str = ""


DEFAULT_THEME_KEY = "light"
THEMES = {
    "light": ThemeSpec("light", "라이트", "light_blue.xml"),
    "dark": ThemeSpec("dark", "다크", "dark_blue.xml"),
}

_SETTINGS_ORG = "KITECH"
_SETTINGS_APP = "SegmentLabelingUI"
_SETTINGS_THEME_KEY = "theme/key"
_THEME_RESOURCE_PARENT = str(Path(tempfile.gettempdir()) / "segtool_qt_material")

_LIGHT_GRAY_EXTRA = {
    "primaryColor": "#374047",
    "primaryLightColor": "#56616a",
    "primaryTextColor": "#ffffff",
}


_DARK_WHITE_EXTRA = {
    "primaryColor": "#ffffff",
    "primaryLightColor": "#ffffff",
    "primaryTextColor": "#263238",
}


def _theme_extra(theme_key: str):
    if theme_key == "dark":
        return dict(_DARK_WHITE_EXTRA)
    return dict(_LIGHT_GRAY_EXTRA)


_BUTTON_COLOR_PALETTES = {
    "light": {
        "border": "#374047",
        "text": "#374047",
        "background": "#e6e6e6",
        "pressed_background": "#374047",
        "pressed_text": "#e6e6e6",
        "flat_hover_background": "rgba(55, 64, 71, 0.2)",
        "flat_pressed_background": "rgba(55, 64, 71, 0.1)",
        "disabled_border": "rgba(255, 255, 255, 0.75)",
        "disabled_text": "rgba(255, 255, 255, 0.75)",
        "disabled_background": "transparent",
        "checked_disabled_text": "#f5f5f5",
        "checked_disabled_background": "#ffffff",
    },
    "dark": {
        "border": "#6f747c",
        "text": "#f1f3f4",
        "background": "#30363b",
        "pressed_background": "#5f6368",
        "pressed_text": "#f1f3f4",
        "flat_hover_background": "rgba(154, 160, 166, 0.2)",
        "flat_pressed_background": "rgba(154, 160, 166, 0.1)",
        "disabled_border": "rgba(220, 220, 220, 0.35)",
        "disabled_text": "rgba(220, 220, 220, 0.35)",
        "disabled_background": "transparent",
        "checked_disabled_text": "rgba(245, 245, 245, 0.65)",
        "checked_disabled_background": "rgba(220, 220, 220, 0.22)",
    },
}


_BUTTON_QSS_TEMPLATE = """
QPushButton,
QDialogButtonBox QPushButton {{
    text-transform: uppercase;
    margin: 0px;
    padding: 1px 16px;
    height: 32px;
    font-weight: bold;
    color: {text};
    background-color: {background};
    border: 2px solid {border};
    border-radius: 4px;
}}

QPushButton:checked,
QPushButton:pressed,
QDialogButtonBox QPushButton:pressed {{
    color: {pressed_text};
    background-color: {pressed_background};
    border-color: {pressed_background};
}}

QPushButton:flat,
QDialogButtonBox QPushButton:flat {{
    margin: 0px;
    color: {text};
    border: none;
    background-color: transparent;
}}

QPushButton:flat:hover,
QDialogButtonBox QPushButton:flat:hover {{
    background-color: {flat_hover_background};
}}

QPushButton:flat:pressed,
QPushButton:flat:checked,
QDialogButtonBox QPushButton:flat:pressed,
QDialogButtonBox QPushButton:flat:checked {{
    background-color: {flat_pressed_background};
}}

QPushButton:disabled,
QDialogButtonBox QPushButton:disabled {{
    color: {disabled_text};
    background-color: {disabled_background};
    border: 2px solid {disabled_border};
}}

QPushButton:flat:disabled,
QDialogButtonBox QPushButton:flat:disabled {{
    color: {disabled_text};
    background-color: {flat_pressed_background};
    border: none;
}}

QPushButton:checked:disabled,
QDialogButtonBox QPushButton:checked:disabled {{
    color: {checked_disabled_text};
    background-color: {checked_disabled_background};
    border-color: {checked_disabled_background};
}}
"""



def _dark_dialog_override_qss() -> str:
    asset_root = Path(__file__).resolve().parents[2] / "resources" / "ui"
    arrow_down = (asset_root / "arrow_down_white.svg").as_posix()
    arrow_up = (asset_root / "arrow_up_white.svg").as_posix()
    return f"""
QDialog QLineEdit,
QDialog QSpinBox,
QDialog QDoubleSpinBox,
QDialog QComboBox {{
    color: #ffffff;
    border-color: #ffffff;
    border-bottom: 2px solid #ffffff;
    selection-background-color: rgba(255, 255, 255, 45);
}}

QDialog QLineEdit:hover,
QDialog QSpinBox:hover,
QDialog QDoubleSpinBox:hover,
QDialog QComboBox:hover,
QDialog QLineEdit:focus,
QDialog QSpinBox:focus,
QDialog QDoubleSpinBox:focus,
QDialog QComboBox:focus {{
    color: #ffffff;
    border-color: #ffffff;
    border-bottom: 2px solid #ffffff;
}}

QDialog QComboBox::drop-down {{
    border: none;
    background: transparent;
    width: 26px;
}}
QDialog QComboBox::down-arrow {{
    image: url({arrow_down});
    width: 10px;
    height: 10px;
}}

QDialog QSpinBox::up-button,
QDialog QSpinBox::down-button,
QDialog QDoubleSpinBox::up-button,
QDialog QDoubleSpinBox::down-button {{
    border: none;
    background: transparent;
    width: 22px;
}}
QDialog QSpinBox::up-arrow,
QDialog QDoubleSpinBox::up-arrow {{
    image: url({arrow_up});
    width: 9px;
    height: 9px;
}}
QDialog QSpinBox::down-arrow,
QDialog QDoubleSpinBox::down-arrow {{
    image: url({arrow_down});
    width: 9px;
    height: 9px;
}}
"""


def _frame_navigation_override_qss(theme_key: str) -> str:
    asset_root = Path(__file__).resolve().parents[2] / "resources" / "ui"
    if theme_key == "dark":
        accent = "#ffffff"
        track = "#202428"
        disabled_track = "rgba(255, 255, 255, 45)"
        disabled_handle = "rgba(255, 255, 255, 95)"
        selection = "rgba(255, 255, 255, 45)"
        icon_suffix = "white"
    else:
        accent = "#374047"
        track = "#d5d8da"
        disabled_track = "rgba(55, 64, 71, 45)"
        disabled_handle = "rgba(55, 64, 71, 95)"
        selection = "rgba(55, 64, 71, 45)"
        icon_suffix = "gray"

    arrow_down = (asset_root / f"arrow_down_{icon_suffix}.svg").as_posix()
    arrow_up = (asset_root / f"arrow_up_{icon_suffix}.svg").as_posix()
    return f"""
QSlider#frameSlider::groove:horizontal {{
    height: 4px;
    background: {track};
    border-radius: 2px;
    margin: 0px;
}}
QSlider#frameSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}
QSlider#frameSlider::add-page:horizontal {{
    background: {track};
    border-radius: 2px;
}}
QSlider#frameSlider::handle:horizontal {{
    image: none;
    background: {accent};
    border: 1px solid {accent};
    width: 12px;
    height: 12px;
    margin: -5px 0px;
    border-radius: 6px;
}}
QSlider#frameSlider::handle:horizontal:hover,
QSlider#frameSlider::handle:horizontal:pressed {{
    image: none;
    background: {accent};
    border-color: {accent};
}}
QSlider#frameSlider::groove:horizontal:disabled,
QSlider#frameSlider::add-page:horizontal:disabled,
QSlider#frameSlider::sub-page:horizontal:disabled {{
    background: {disabled_track};
}}
QSlider#frameSlider::handle:horizontal:disabled {{
    image: none;
    background: {disabled_handle};
    border-color: {disabled_handle};
}}

QSpinBox#frameSpin {{
    color: {accent};
    border-color: {accent};
    border-bottom: 2px solid {accent};
    selection-background-color: {selection};
}}
QSpinBox#frameSpin:hover,
QSpinBox#frameSpin:focus {{
    color: {accent};
    border-color: {accent};
    border-bottom: 2px solid {accent};
}}
QSpinBox#frameSpin::up-button,
QSpinBox#frameSpin::down-button {{
    border: none;
    background: transparent;
    width: 22px;
}}
QSpinBox#frameSpin::up-arrow {{
    image: url({arrow_up});
    width: 9px;
    height: 9px;
}}
QSpinBox#frameSpin::down-arrow {{
    image: url({arrow_down});
    width: 9px;
    height: 9px;
}}
"""

def _button_override_qss(theme_key: str) -> str:
    colors = _BUTTON_COLOR_PALETTES.get(theme_key, _BUTTON_COLOR_PALETTES[DEFAULT_THEME_KEY])
    return _BUTTON_QSS_TEMPLATE.format(**colors)


def _apply_theme_overrides(app: QApplication, theme_key: str) -> None:
    override_qss = _button_override_qss(theme_key)
    override_qss += "\n" + _frame_navigation_override_qss(theme_key)
    if theme_key == "dark":
        override_qss += "\n" + _dark_dialog_override_qss()
    app.setStyleSheet(app.styleSheet() + "\n" + override_qss)



def theme_options() -> Iterable[ThemeSpec]:
    return THEMES.values()


def normalize_theme_key(theme_key: Optional[str]) -> str:
    key = str(theme_key or DEFAULT_THEME_KEY).strip().lower()
    return key if key in THEMES else DEFAULT_THEME_KEY


def load_theme_key() -> str:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    return normalize_theme_key(settings.value(_SETTINGS_THEME_KEY, DEFAULT_THEME_KEY))


def save_theme_key(theme_key: str) -> None:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue(_SETTINGS_THEME_KEY, normalize_theme_key(theme_key))


def apply_theme(
    app: Optional[QApplication] = None,
    theme_key: Optional[str] = None,
    persist: bool = False,
) -> ThemeApplyResult:
    key = normalize_theme_key(theme_key)
    spec = THEMES[key]
    app = app or QApplication.instance()
    if app is None:
        return ThemeApplyResult(key, spec.label, False, "QApplication 인스턴스가 없습니다.")

    try:
        from qt_material import apply_stylesheet
    except ImportError as exc:
        return ThemeApplyResult(key, spec.label, False, f"qt-material 패키지를 불러올 수 없습니다: {exc}")

    try:
        apply_stylesheet(app, theme=spec.material_theme, parent=_THEME_RESOURCE_PARENT, extra=_theme_extra(key))
        _apply_theme_overrides(app, key)
    except Exception as exc:
        return ThemeApplyResult(key, spec.label, False, f"테마 적용 중 오류가 발생했습니다: {exc}")

    if persist:
        save_theme_key(key)
    return ThemeApplyResult(key, spec.label, True)


def apply_saved_theme(app: Optional[QApplication] = None) -> ThemeApplyResult:
    return apply_theme(app, load_theme_key(), persist=False)
