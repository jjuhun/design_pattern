# KITECH_Segmentation Segment Labeling UI

SAM2 기반 이미지/비디오 annotation 및 tracking 도구입니다.

## 주요 기능

- Image folder / Video open
- Box / Polygon / Keypoint annotation
- SAM2 single-frame interact
- SAM2 video tracking
- YOLO segmentation import/export
- Auto save
- Undo / Redo
- Timeline annotation management

## 실행 방법

```bash
conda env create -f environment.yaml
conda activate sam2_qt_env
python main.py
