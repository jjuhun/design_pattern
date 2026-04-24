import cv2
import tempfile
import os
import shutil


class FrameManager:
    def __init__(self):
        self.frame_paths = []
        self.current_index = 0
        self.source_path = ""
        self.source_type = None   # "mp4" or "dir"
        self.temp_dir = None

    def clear(self):
        self.frame_paths = []
        self.current_index = 0
        self.source_path = ""
        self.source_type = None

        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir = None

    def load_directory(self, path):
        self.clear()

        valid_ext = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        files = [
            f for f in os.listdir(path)
            if os.path.splitext(f)[1].lower() in valid_ext
        ]
        files.sort()

        self.frame_paths = [os.path.join(path, f) for f in files]
        self.current_index = 0
        self.source_path = path
        self.source_type = "dir"

    def load_mp4(self, path):
        self.clear()

        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise RuntimeError("영상 열기 실패")

        self.temp_dir = tempfile.mkdtemp(prefix="frames_")
        self.frame_paths = []

        idx = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            save_path = os.path.join(self.temp_dir, f"frame_{idx:06d}.png")
            cv2.imwrite(save_path, frame)
            self.frame_paths.append(save_path)
            idx += 1

        cap.release()

        self.current_index = 0
        self.source_path = path
        self.source_type = "mp4"

    def has_frames(self):
        return len(self.frame_paths) > 0

    def get_total_frames(self):
        return len(self.frame_paths)

    def get_current_index(self):
        return self.current_index

    def get_current_frame_path(self):
        if not self.frame_paths:
            return None
        return self.frame_paths[self.current_index]

    def jump_to(self, index):
        if not self.frame_paths:
            return
        self.current_index = max(0, min(index, len(self.frame_paths) - 1))

    def move(self, delta):
        if not self.frame_paths:
            return
        self.jump_to(self.current_index + delta)