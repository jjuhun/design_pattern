# 프레임을 가져오는 방법을 하나의 인터페이스로 맞춰주는 파일입니다.
# 이미지 폴더와 비디오에서 추출한 캐시 프레임을 같은 방식으로 읽게 합니다.
from pathlib import Path
from PyQt5.QtGui import QPixmap

from core.common.utils import natural_key


class FrameSourceBase:
    def frame_count(self) -> int:
        """전체 프레임 개수를 반환한다."""
        raise NotImplementedError

    def frame_name(self, index: int) -> str:
        """지정한 프레임의 표시 이름을 반환한다."""
        raise NotImplementedError

    def display_name(self) -> str:
        """현재 미디어 소스의 표시 이름을 반환한다."""
        raise NotImplementedError

    def media_type(self) -> str:
        """미디어 소스 종류를 문자열로 반환한다."""
        raise NotImplementedError

    def fps(self) -> float:
        """재생에 사용할 초당 프레임 수를 반환한다."""
        return 5.0

    def get_pixmap(self, index: int):
        """지정한 프레임을 QPixmap으로 읽어온다."""
        raise NotImplementedError

    def frame_dir_path(self) -> str:
        """프레임 이미지들이 있는 디렉터리 경로를 반환한다."""
        raise NotImplementedError

    def close(self):
        """미디어 소스를 닫을 때 필요한 정리를 수행한다."""
        pass


class ImageFolderSource(FrameSourceBase):
    def __init__(self, folder_path: str, fps_value: float = 5.0):
        """이미지 폴더를 프레임 소스로 사용할 준비를 한다."""
        self.folder_path = Path(folder_path)
        self._fps = float(fps_value) if fps_value and fps_value > 0 else 5.0
        image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
        self.paths = [
            p for p in self.folder_path.iterdir()
            if p.is_file() and p.suffix.lower() in image_exts
        ]
        self.paths = sorted(self.paths, key=lambda p: natural_key(p.name))
        if not self.paths:
            raise ValueError("선택한 폴더에 이미지 파일이 없습니다.")

    def frame_count(self) -> int:
        """이미지 폴더 안의 프레임 개수를 반환한다."""
        return len(self.paths)

    def frame_name(self, index: int) -> str:
        """지정한 이미지 파일 이름을 반환한다."""
        return self.paths[index].name

    def display_name(self) -> str:
        """이미지 폴더 이름을 표시 이름으로 반환한다."""
        return self.folder_path.name

    def media_type(self) -> str:
        """이미지 폴더 소스임을 나타내는 값을 반환한다."""
        return "image_folder"

    def fps(self) -> float:
        """이미지 폴더 재생에 사용할 초당 프레임 수를 반환한다."""
        return self._fps

    def get_pixmap(self, index: int):
        """지정한 이미지 파일을 QPixmap으로 읽어온다."""
        if index < 0 or index >= len(self.paths):
            return QPixmap()
        return QPixmap(str(self.paths[index]))

    def frame_dir_path(self) -> str:
        """이미지 폴더 경로를 문자열로 반환한다."""
        return str(self.folder_path)


class CachedFrameSource(ImageFolderSource):
    def __init__(self, folder_path: str, source_name: str, fps_value: float):
        """비디오에서 추출된 캐시 프레임 폴더를 소스로 준비한다."""
        super().__init__(folder_path, fps_value=fps_value)
        self._source_name = source_name

    def display_name(self) -> str:
        """원본 비디오 파일 이름을 표시 이름으로 반환한다."""
        return self._source_name

    def media_type(self) -> str:
        """캐시 프레임 소스임을 나타내는 값을 반환한다."""
        return "cached_frame_dir"
