# 프레임을 열고 이동하는 기능을 관리하는 파일입니다.
# 이미지 폴더/비디오 열기, 비디오 프레임 캐시, 하단 이동 버튼과 재생을 담당합니다.
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget

from core.common.utils import clamp
from features.frame_panel.sources import CachedFrameSource, FrameSourceBase, ImageFolderSource


class FramePanelControllerMixin:
    def build_ui(self):
        """중앙 작업 화면, 좌우 패널, 하단 프레임 이동 패널을 조립한다."""
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)
        left_panel = self.build_left_toolbar()
        right_panel = self.build_right_panel()

        splitter.addWidget(left_panel)
        splitter.addWidget(self.canvas)
        splitter.addWidget(right_panel)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([120, 1160, 420])
        root_layout.addWidget(splitter, 1)

        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(6)

        self.first_button = QPushButton("|<<")
        self.first_button.clicked.connect(self.first_frame)
        bottom_layout.addWidget(self.first_button)

        self.back10_button = QPushButton("<<")
        self.back10_button.clicked.connect(lambda: self.jump_frames(-10))
        bottom_layout.addWidget(self.back10_button)

        self.prev_button = QPushButton("<")
        self.prev_button.clicked.connect(self.prev_frame)
        bottom_layout.addWidget(self.prev_button)

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_playback)
        bottom_layout.addWidget(self.play_button)

        self.next_button = QPushButton(">")
        self.next_button.clicked.connect(self.next_frame)
        bottom_layout.addWidget(self.next_button)

        self.forward10_button = QPushButton(">>")
        self.forward10_button.clicked.connect(lambda: self.jump_frames(10))
        bottom_layout.addWidget(self.forward10_button)

        self.last_button = QPushButton(">>|")
        self.last_button.clicked.connect(self.last_frame)
        bottom_layout.addWidget(self.last_button)

        bottom_layout.addWidget(self.frame_slider, 1)
        bottom_layout.addWidget(self.frame_spin)
        bottom_layout.addWidget(self.total_frames_label)
        root_layout.addLayout(bottom_layout)

    def close_current_source(self):
        """현재 열린 프레임 소스를 닫고 트랙킹 중이면 중지를 요청한다."""
        if self.is_tracking:
            self.on_stop_tracking()
        if self.source is not None:
            self.source.close()
            self.source = None

    def _refresh_transport_enabled(self, enabled: bool):
        """하단 프레임 이동 버튼들의 활성화 상태를 한 번에 바꾼다."""
        for btn in [
            self.first_button, self.back10_button, self.prev_button,
            self.play_button, self.next_button, self.forward10_button, self.last_button,
        ]:
            if btn is not None:
                btn.setEnabled(enabled)

    def load_source(self, source: FrameSourceBase):
        """새 프레임 소스를 열고 화면과 상태를 첫 프레임 기준으로 초기화한다."""
        if self.timer.isActive():
            self.timer.stop()
        self.close_current_source()
        self.store.clear()
        self.clear_undo_history()
        self.annotation_clipboard = []
        self.current_index = 0
        self.source = source
        total = self.source.frame_count()
        self.frame_slider.setEnabled(True)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(max(0, total - 1))
        self.frame_spin.setEnabled(True)
        self.frame_spin.setMinimum(0)
        self.frame_spin.setMaximum(max(0, total - 1))
        self.total_frames_label.setText(f"/ {total}")
        self._refresh_transport_enabled(total > 0)
        self.play_button.setText("Play")
        self._set_tracking_button_states(False)
        self._set_tracking_status("준비 중")
        self._reset_tracking_progress_ui()
        
        self.refresh_timeline_tree()
        self.update_frame_view()

    def open_frames_folder(self):
        """사용자가 선택한 이미지 폴더를 프레임 소스로 연다."""
        folder = QFileDialog.getExistingDirectory(self, "프레임 폴더 선택")
        if not folder:
            return
        try:
            self.load_source(ImageFolderSource(folder))
        except Exception as e:
            QMessageBox.warning(self, "경고", str(e))

    def _video_frame_cache_root(self) -> Path:
        """비디오에서 추출한 프레임 캐시를 저장할 루트 폴더를 반환한다."""
        return Path(__file__).resolve().parents[2] / ".cache" / "frames"

    def _video_source_signature(self, video_path: Path) -> Dict[str, object]:
        """비디오 캐시 재사용 판단에 필요한 파일 정보를 만든다."""
        stat = video_path.stat()
        return {
            "source_path": str(video_path.resolve()),
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
        }

    def _video_cache_dir_for(self, video_path: Path) -> Path:
        """비디오 파일마다 겹치지 않는 캐시 폴더 경로를 만든다."""
        safe_stem = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in video_path.stem).strip("_")
        safe_stem = safe_stem or "video"
        digest = hashlib.sha1(str(video_path.resolve()).encode("utf-8")).hexdigest()[:10]
        return self._video_frame_cache_root() / f"{safe_stem}_{digest}"

    def _is_reusable_video_cache(self, cache_dir: Path, expected_signature: Dict[str, object]) -> Optional[Dict[str, object]]:
        """기존 비디오 프레임 캐시를 다시 쓸 수 있는지 검사한다."""
        meta_path = cache_dir / "cache_meta.json"
        if not cache_dir.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if meta.get("source") != expected_signature:
            return None

        frame_count = int(meta.get("frame_count", 0))
        if frame_count <= 0:
            return None
        first_frame = cache_dir / "frame_000000.jpg"
        last_frame = cache_dir / f"frame_{frame_count - 1:06d}.jpg"
        if not first_frame.exists() or not last_frame.exists():
            return None
        return meta

    def _extract_video_frames_to_cache(self, video_path: str) -> Tuple[Path, float, int, bool]:
        """비디오를 프레임 이미지로 추출하거나 기존 캐시를 재사용한다."""
        import cv2

        source_path = Path(video_path).resolve()
        if not source_path.exists():
            raise RuntimeError("비디오 파일을 찾을 수 없습니다.")

        source_signature = self._video_source_signature(source_path)
        cache_dir = self._video_cache_dir_for(source_path)
        cache_dir.parent.mkdir(parents=True, exist_ok=True)

        cached_meta = self._is_reusable_video_cache(cache_dir, source_signature)
        if cached_meta is not None:
            return cache_dir, float(cached_meta.get("fps", 30.0)), int(cached_meta.get("frame_count", 0)), True

        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
        cache_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(str(source_path))
        if not cap.isOpened():
            raise RuntimeError("비디오 파일을 열 수 없습니다.")

        fps = cap.get(cv2.CAP_PROP_FPS)
        fps = float(fps) if fps and fps > 0 else 30.0
        frame_idx = 0

        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                out_path = cache_dir / f"frame_{frame_idx:06d}.jpg"
                if not cv2.imwrite(str(out_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95]):
                    raise RuntimeError(f"프레임 저장 실패: {out_path}")
                frame_idx += 1
        finally:
            cap.release()

        if frame_idx == 0:
            shutil.rmtree(cache_dir, ignore_errors=True)
            raise RuntimeError("비디오에서 프레임을 추출하지 못했습니다.")

        meta = {
            "source": source_signature,
            "frame_count": frame_idx,
            "fps": fps,
            "pattern": "frame_%06d.jpg",
        }
        (cache_dir / "cache_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return cache_dir, fps, frame_idx, False

    def open_video_file(self):
        """사용자가 선택한 비디오 파일을 프레임 캐시로 변환해 연다."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "비디오 파일 선택",
            "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v)"
        )
        if not file_path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage("비디오 프레임 캐시 준비 중...")
        try:
            cache_dir, fps, frame_count, reused = self._extract_video_frames_to_cache(file_path)
            self.load_source(CachedFrameSource(str(cache_dir), source_name=Path(file_path).name, fps_value=fps))
            if reused:
                self.show_status_message(f"비디오 캐시 재사용 완료 ({frame_count} 프레임)")
            else:
                self.show_status_message(f"비디오 캐시 생성 완료 ({frame_count} 프레임)")
        except Exception as e:
            QMessageBox.warning(self, "경고", str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def update_frame_view(self, refresh_timeline: bool = True):
        """현재 프레임 이미지를 표시하고 관련 목록과 이동 UI를 갱신한다."""
        if self.source is None or self.current_index < 0:
            return
        pixmap = self.source.get_pixmap(self.current_index)
        self.canvas.set_pixmap(pixmap)
        total = self.source.frame_count()

        self.media_label.setText(self.source.display_name())
        self.frame_name_label.setText(self.source.frame_name(self.current_index))

        self.frame_slider.blockSignals(True)
        self.frame_slider.setValue(self.current_index)
        self.frame_slider.blockSignals(False)

        self.frame_spin.blockSignals(True)
        self.frame_spin.setValue(self.current_index)
        self.frame_spin.blockSignals(False)

        idx = self.current_index
        self.first_button.setEnabled(idx > 0)
        self.back10_button.setEnabled(idx > 0)
        self.prev_button.setEnabled(idx > 0)
        self.play_button.setEnabled(total > 1)
        self.next_button.setEnabled(idx < total - 1)
        self.forward10_button.setEnabled(idx < total - 1)
        self.last_button.setEnabled(idx < total - 1)

        # 프레임 이동만으로는 타임라인 목록 자체가 바뀌지 않으므로,
        # 재생성하지 않아 다중 선택 상태를 유지한다.
        self.refresh_annotations_for_current_frame(self.get_selected_annotation_ids(), refresh_timeline=False)

    def go_to_frame(self, index):
        """슬라이더나 숫자 입력에서 요청한 프레임으로 이동한다."""
        if self.source is None:
            return
        total = self.source.frame_count()
        self.current_index = clamp(int(index), 0, total - 1)
        self.update_frame_view()

    def go_to_frame_index(self, frame_idx):
        """타임라인에서 호출되는 프레임 이동 함수"""
        if self.source is None:
            return
        total = self.source.frame_count()
        if 0 <= frame_idx < total:
            self.current_index = frame_idx
            self.update_frame_view()

    def first_frame(self):
        """첫 번째 프레임으로 이동한다."""
        if self.source is None:
            return
        self.current_index = 0
        self.update_frame_view()

    def last_frame(self):
        """마지막 프레임으로 이동한다."""
        if self.source is None:
            return
        self.current_index = self.source.frame_count() - 1
        self.update_frame_view()

    def jump_frames(self, delta):
        """현재 위치에서 지정한 수만큼 앞뒤로 프레임을 이동한다."""
        if self.source is None:
            return
        total = self.source.frame_count()
        self.current_index = clamp(self.current_index + delta, 0, total - 1)
        self.update_frame_view()

    def prev_frame(self):
        """이전 프레임으로 한 칸 이동한다."""
        self.jump_frames(-1)

    def next_frame(self):
        """다음 프레임으로 한 칸 이동하고 끝에서는 재생을 멈춘다."""
        if self.source is None:
            return
        if self.current_index < self.source.frame_count() - 1:
            self.current_index += 1
            self.update_frame_view()
        elif self.timer.isActive():
            self.timer.stop()
            self.play_button.setText("Play")

    def toggle_playback(self):
        """프레임 자동 재생을 시작하거나 일시정지한다."""
        if self.source is None:
            return
        if self.is_tracking:
            self.show_status_message("트랙킹 중에는 재생을 사용할 수 없습니다.")
            return
        if self.timer.isActive():
            self.timer.stop()
            self.play_button.setText("Play")
            return
        fps = max(1.0, float(self.source.fps()))
        interval_ms = max(1, int(1000.0 / fps))
        self.timer.start(interval_ms)
        self.play_button.setText("Pause")

    def advance_playback(self):
        """재생 타이머가 울릴 때 다음 프레임으로 이동한다."""
        if self.source is None:
            return
        if self.is_tracking:
            self.timer.stop()
            self.play_button.setText("Play")
            return
        if self.current_index >= self.source.frame_count() - 1:
            self.timer.stop()
            self.play_button.setText("Play")
            return
        self.current_index += 1
        self.update_frame_view()

    # ---------- SAM2/SAM3 트랙킹 관련 메서드 ----------
