# OS 기본 파일 선택기를 우선 사용하고, 실패하면 Qt 기본 다이얼로그로 돌아간다.
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt5.QtWidgets import QFileDialog, QWidget


def _can_use_zenity() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    return shutil.which("zenity") is not None


def _dialog_start_path(directory: str) -> str:
    if directory:
        path = Path(directory).expanduser()
    else:
        path = Path.cwd()

    if path.is_dir():
        return str(path) + os.sep
    return str(path)


def _run_zenity(args: List[str]) -> Optional[str]:
    if not _can_use_zenity():
        return None
    try:
        proc = subprocess.run(
            ["zenity", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if proc.returncode != 0:
        return ""
    return proc.stdout.splitlines()[0].strip() if proc.stdout else ""


def _qt_filters_to_zenity_filters(filter_text: str) -> List[str]:
    filters = []
    for raw_filter in filter_text.split(";;"):
        raw_filter = raw_filter.strip()
        if not raw_filter:
            continue

        match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", raw_filter)
        if match:
            label = match.group(1).strip() or "Files"
            patterns = match.group(2).strip() or "*"
        else:
            label = raw_filter
            patterns = "*"
        filters.append(f"{label} | {patterns}")

    return filters


def get_existing_directory(parent: QWidget, title: str, directory: str = "") -> str:
    selected = _run_zenity([
        "--file-selection",
        "--directory",
        f"--title={title}",
        f"--filename={_dialog_start_path(directory)}",
    ])
    if selected is not None:
        return selected
    return QFileDialog.getExistingDirectory(parent, title, directory)


def get_open_file_name(
    parent: QWidget,
    title: str,
    directory: str = "",
    filter_text: str = "",
) -> Tuple[str, str]:
    args = [
        "--file-selection",
        f"--title={title}",
        f"--filename={_dialog_start_path(directory)}",
    ]
    for zenity_filter in _qt_filters_to_zenity_filters(filter_text):
        args.append(f"--file-filter={zenity_filter}")
    if filter_text:
        args.append("--file-filter=All Files | *")

    selected = _run_zenity(args)
    if selected is not None:
        return selected, ""
    return QFileDialog.getOpenFileName(parent, title, directory, filter_text)
