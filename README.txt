Segment Labeling UI 구조
========================

이 프로젝트는 PyQt5 기반의 segmentation annotation 도구입니다.
현재 구조는 크게 세 영역으로 나뉩니다.

- main.py / main_window.py / canvas.py: 앱 실행과 UI 조립 뼈대
- features/: UI 기능별 controller와 기능별 엔진/소스/dialog
- core/: 여러 기능이 함께 쓰는 공통 데이터, dialog, 유틸


폴더 구조
---------

segment_labeling_UI/
├─ main.py
├─ main_window.py
├─ canvas.py
├─ requirement.txt
├─ README.txt
├─ weights/
│  └─ sam2.1_hiera_large.pt
├─ features/
│  ├─ mouse_event/
│  │  └─ controller.py
│  ├─ right_panel/
│  │  └─ controller.py
│  ├─ ai_interact/
│  │  ├─ controller.py
│  │  └─ engine.py
│  ├─ ai_tracking/
│  │  ├─ controller.py
│  │  ├─ engine.py
│  │  └─ dialogs.py
│  ├─ top_panel/
│  │  └─ controller.py
│  ├─ frame_panel/
│  │  ├─ controller.py
│  │  └─ sources.py
│  └─ shape_annotation/
│     └─ controller.py
└─ core/
   ├─ annotation/
   │  └─ models.py
   ├─ dialogs/
   │  └─ dialogs.py
   └─ common/
      ├─ constants.py
      └─ utils.py


1. 루트 파일
---------

main.py -> 프로그램을 처음 실행할 때 시작되는 파일입니다.
- QApplication 생성 전 Qt 실행 환경을 설정합니다.
- X11 display가 없을 때 offscreen backend를 설정합니다.
- MainWindow를 생성하고 앱 이벤트 루프를 시작합니다.

main_window.py -> 전체 창을 만들고 각 기능을 한곳에 연결하는 파일입니다.
- MainWindow 클래스의 조립용 뼈대입니다.
- 앱 전체 상태 변수, 주요 widget 인스턴스, timer, signal 연결, shortcut 연결을 초기화합니다.
- features 아래 controller mixin들을 상속해 기능을 조립합니다.
- closeEvent에서 timer와 frame source를 정리합니다.

canvas.py -> 이미지와 annotation이 보이는 가운데 작업 화면을 만드는 파일입니다.
- AnnotationCanvas 클래스의 조립용 뼈대입니다.
- canvas signal, scene/view 기본 설정, pixmap 표시, fit/resize, 기본 선택 상태를 관리합니다.
- mouse event 기능은 features/mouse_event/controller.py에서 mixin으로 받습니다.
- annotation shape rendering 관련 기능은 features/shape_annotation/controller.py의 ShapeCanvasMixin으로 받습니다.

requirement.txt -> 실행에 필요한 Python 패키지 목록입니다.
- 프로젝트 실행에 필요한 Python dependency 목록입니다.

weights/ -> AI 모델 파일을 넣어두는 폴더입니다.
- SAM checkpoint 파일을 보관합니다.
- 현재 AI interact/tracking이 찾는 주요 파일은 sam2.1_hiera_large.pt입니다.


2. features
--------

features/mouse_event/controller.py -> 이미지 위에서 클릭, 드래그, 선택, 점 편집을 처리합니다.
- MouseEventControllerMixin을 정의합니다.
- canvas 위의 wheel, double click, mouse press/move/release event를 처리합니다.
- annotation 선택, Ctrl 다중 선택, drag 이동, vertex 편집, polygon vertex 우클릭 메뉴를 담당합니다.
- annotation 데이터 저장 자체는 직접 하지 않고 signal을 emit합니다.

features/right_panel/controller.py -> 오른쪽 목록 패널에서 객체, 라벨, 타임라인을 보여주고 선택을 맞춥니다.
- RightPanelControllerMixin을 정의합니다.
- 오른쪽 패널의 Objects, Labels, Timeline, AI Tools 탭을 생성합니다.
- object tree, label list, timeline tree 갱신과 선택 동기화를 담당합니다.
- label 생성/수정/삭제, object label 변경, visibility toggle, timeline filter와 삭제를 처리합니다.
- 현재 프레임 annotation을 RenderAnnotation으로 변환해 canvas와 object panel에 전달합니다.

features/ai_interact/controller.py -> AI로 현재 프레임의 물체를 따는 버튼 흐름과 결과 확정을 처리합니다.
- AIInteractControllerMixin을 정의합니다.
- AI Tools의 single-frame interact 흐름을 담당합니다.
- Interact 시작, box/point prompt 처리, SAM 결과 preview, refine point 처리, 결과 confirm을 관리합니다.
- AI 작업 라벨 selector와 AI label 생성 버튼 callback을 처리합니다.
- 실제 SAM image segmentation 엔진은 같은 폴더의 engine.py를 사용합니다.

features/ai_interact/engine.py -> SAM 모델을 불러와 박스나 점 입력으로 마스크를 만드는 실제 AI 실행부입니다.
- SAMImageInteractEngine을 정의합니다.
- SAM2/SAM3 image predictor 로딩, checkpoint 경로 탐색, box prompt, point prompt, box+point prompt 실행을 담당합니다.
- mask를 polygon 또는 box 데이터로 변환합니다.

features/ai_tracking/controller.py -> AI tracking을 시작하고 멈추며 진행률과 결과 저장을 관리합니다.
- TrackingWorker와 AITrackingControllerMixin을 정의합니다.
- tracking 시작/중지, tracking UI 상태, progress bar, background QThread/worker 연결을 관리합니다.
- tracking 결과를 annotation store에 반영하고 현재 frame view를 갱신합니다.
- CUDA 확인과 annotation mask 변환 helper를 포함합니다.
- 실제 tracking 알고리즘은 같은 폴더의 engine.py를 사용합니다.

features/ai_tracking/engine.py -> 한 프레임의 annotation을 기준으로 다음 프레임들을 따라가는 실제 AI 실행부입니다.
- TrackingResult와 SAM2TrackingEngine을 정의합니다.
- SAM2 video predictor 로딩, 초기 prompt 등록, frame tracking, mask-to-polygon/box 변환을 담당합니다.
- tracking 결과 목록과 engine resource cleanup을 관리합니다.

features/ai_tracking/dialogs.py -> tracking을 시작할 때 모델과 종료 프레임을 고르는 창을 만듭니다.
- SelectSAMModelDialog와 TrackingRangeDialog를 정의합니다.
- tracking에 사용할 SAM 모델 선택 dialog와 tracking 종료 프레임 선택 dialog를 담당합니다.

features/top_panel/controller.py -> 맨 위 버튼줄과 저장, 내보내기, 되돌리기 같은 작업을 관리합니다.
- TopPanelControllerMixin을 정의합니다.
- 상단 toolbar를 생성합니다.
- Open Frames, Open Video, Export, Undo, Redo, media/frame/status label을 배치하고 기존 callback에 연결합니다.
- YOLO segment export, undo/redo stack, copy/paste, app state capture/restore를 담당합니다.

features/frame_panel/controller.py -> 이미지 폴더나 비디오를 열고 프레임 이동, 재생, 캐시 생성을 처리합니다.
- FramePanelControllerMixin을 정의합니다.
- 전체 중앙/하단 UI layout 조립, bottom frame transport panel, frame slider/spinbox를 관리합니다.
- image folder open, video open, video frame cache 생성/재사용, frame 이동, playback을 담당합니다.
- 비디오 frame cache는 프로젝트 루트의 .cache/frames 아래에 생성됩니다.

features/frame_panel/sources.py -> 폴더 이미지나 비디오에서 추출한 프레임을 같은 방식으로 읽게 해줍니다.
- FrameSourceBase, ImageFolderSource, CachedFrameSource를 정의합니다.
- image folder 또는 video cache folder에서 frame pixmap, frame name, fps, frame directory path를 제공합니다.

features/shape_annotation/controller.py -> Box와 Polygon을 만들고 화면에 그려지는 모양을 관리합니다.
- ShapeAnnotationControllerMixin과 ShapeCanvasMixin을 정의합니다.
- 왼쪽 Box/Polygon tool 버튼, tool mode 변경, canvas mode 변경 callback을 관리합니다.
- canvas의 annotationCreateRequested signal을 받아 box/polygon annotation을 실제 store에 저장합니다.
- annotation data update 요청, drawing cancel을 처리합니다.
- ShapeCanvasMixin은 annotation drawing/rendering, selection style, temporary box/polygon preview, AI preview 표시를 담당합니다.


3. core
----

core/annotation/models.py -> annotation, label, 복사한 객체 같은 데이터를 저장하는 구조를 정의합니다.
- annotation 관련 데이터 구조를 정의합니다.
- LabelDef, Annotation, RenderAnnotation, ClipboardAnnotation dataclass가 있습니다.
- AnnotationStore가 frame별 annotation 저장, 조회, 수정, 삭제, upsert, snapshot/restore를 담당합니다.

core/dialogs/dialogs.py -> 라벨 이름과 번호를 입력하거나 수정하는 작은 창을 만듭니다.
- LabelEditDialog를 정의합니다.
- label 이름과 class index를 입력/수정하는 공통 dialog입니다.

core/common/constants.py -> 여러 곳에서 같이 쓰는 고정값을 모아둡니다.
- LABEL_COLOR_PALETTE 등 공통 상수를 정의합니다.

core/common/utils.py -> 여러 곳에서 반복해서 쓰는 작은 helper 함수들을 모아둡니다.
- natural_key, clamp, box_to_polygon 같은 공통 helper 함수를 정의합니다.


4. 런타임 생성 폴더
---------------

.cache/
- 코드 파일이 아닙니다.
- 비디오를 열 때 frame_panel 기능이 비디오를 jpg frame으로 추출해 저장하는 cache입니다.
- 삭제해도 앱 코드는 망가지지 않지만, 같은 비디오를 다시 열 때 frame 추출을 다시 수행합니다.

__pycache__/
- Python이 실행/compile 중 자동 생성하는 bytecode cache입니다.
- 삭제해도 됩니다.


5. import 규칙
-----------

- main_window.py와 canvas.py는 features의 controller mixin을 import해서 조립합니다.
- features는 core를 import할 수 있습니다.
- features는 필요한 경우 같은 feature 안의 engine/dialog/source를 import합니다.
- core는 features를 import하지 않습니다.
- controller mixin은 MainWindow나 AnnotationCanvas를 직접 import하지 않고 self 기반으로 동작합니다.


6. 검증 명령
---------

문법 확인:

python3 -m py_compile main.py main_window.py canvas.py

전체 Python 파일 확인:

python3 -m py_compile $(find . -name "*.py")

앱 실행:

python3 main.py

주의:
- PyQt display 환경, CUDA, SAM checkpoint, GPU 상태에 따라 실행 중 환경 오류가 날 수 있습니다.
- SAM checkpoint는 weights/sam2.1_hiera_large.pt 위치를 기본으로 사용합니다.
