# KITECH_Segmentation

SAM2 기반 이미지/비디오 Annotation 및 Tracking 도구입니다.

---

# 주요 기능

- Image Folder / Video Open
- Box / Polygon / Keypoint Annotation
- SAM2 Single-frame Interact
- SAM2 Video Tracking
- AI Refine Prompt
- YOLO Segmentation Import / Export
- Auto Save
- Undo / Redo
- Timeline Annotation Management

---

# 실행 환경

- Ubuntu 22.04
- Python 3.10
- PyQt5
- CUDA GPU 권장

---

# 실행 방법

## 1. Conda 환경 생성

```bash
conda env create -f environment.yaml
```

## 2. 환경 활성화

```bash
conda activate sam2_qt_env
```

## 3. 프로그램 실행

```bash
python main.py
```

---

# AI 모델 설치

---

# SAM2 설치 방법

## 1. SAM2 Clone 및 설치

```bash
git clone https://github.com/facebookresearch/sam2.git
cd sam2
pip install -e .
```

## 2. Checkpoint 다운로드

```bash
cd checkpoints
./download_ckpts.sh
```

## 3. Checkpoint 파일 복사

다운로드된 `.pt` 파일을 프로젝트의 `weights/` 폴더에 복사하세요.

```text
KITECH_Segmentation/
├── weights/
│   ├── sam2.1_hiera_tiny.pt
│   └── sam2.1_hiera_large.pt
```

예시:

```bash
cp sam2/checkpoints/*.pt ~/jjh_ws/weights/
```

---

# SAM3 설치 방법

## 1. SAM3 Clone 및 설치

```bash
git clone <SAM3_REPOSITORY_URL>
cd sam3
pip install -e .
```

## 2. SAM3 Checkpoint 다운로드

SAM3 모델 가중치를 다운로드합니다.

## 3. Checkpoint 파일 복사

다운로드한 checkpoint 파일을 프로젝트의 `weights/` 폴더에 복사하세요.

예시:

```text
KITECH_Segmentation/
├── weights/
│   ├── sam3.pt
│   ├── sam2.1_hiera_tiny.pt
│   └── sam2.1_hiera_large.pt
```

---

# 지원 AI 모델

- SAM2.1 Tiny
- SAM2.1 Large
- SAM3

# 프로젝트 구조

```text
KITECH_Segmentation/
├── core/
│   ├── annotation/
│   ├── common/
│   └── dialogs/
│
├── features/
│   ├── ai_interact/
│   ├── ai_tracking/
│   ├── copy_sequence/
│   ├── frame_panel/
│   ├── mouse_event/
│   ├── right_panel/
│   ├── shape_annotation/
│   └── top_panel/
│
├── weights/
├── canvas.py
├── main.py
├── main_window.py
├── environment.yaml
├── requirement.txt
└── README.md
```

---

# 지원 Annotation 타입

- Box
- Polygon
- Keypoint

---

# AI 기능

## SAM2 Single-frame Interact

- Bounding Box Prompt
- Point Prompt
- Refine Prompt

## SAM2 Video Tracking

- Box Tracking
- Polygon Tracking
- Keypoint Tracking
- Forward / Backward Tracking

---

# Dataset 기능

## Export

YOLO Segmentation 형식으로 Export 가능합니다.

```text
result/
├── data.yaml
├── train.txt
└── labels/
    └── train/
        ├── frame_000000.txt
        └── ...
```

## Import

YOLO Segmentation Export 결과를 다시 Import 가능합니다.

---

# 기타 기능

- Auto Save
- Undo / Redo
- Timeline Annotation Viewer
- Label Management
- Multi-object Selection
- Polygon Vertex Editing

---

# 주의사항

- SAM2 Checkpoint 파일은 GitHub에 포함되지 않습니다.
- `weights/` 폴더에 직접 배치해야 합니다.
- CUDA GPU 환경을 권장합니다.
