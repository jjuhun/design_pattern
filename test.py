import sys
import torch
import numpy as np
from PIL import Image
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtWidgets import QApplication
from transformers import Sam3Processor, Sam3Model


image_path = "/home/kitech/jjh/21-30JJH/26/20260311_173949_774508_p000000rs1.jpg"
text = "blue"

device = "cuda" if torch.cuda.is_available() else "cpu"

app = QApplication(sys.argv)

model = Sam3Model.from_pretrained("facebook/sam3").to(device)
processor = Sam3Processor.from_pretrained("facebook/sam3")


def run_sam3(pil_image, tag):
    inputs = processor(
        images=pil_image,
        text=text,
        return_tensors="pt"
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)

    results = processor.post_process_instance_segmentation(
        outputs,
        threshold=0.5,
        mask_threshold=0.5,
        target_sizes=inputs.get("original_sizes").tolist()
    )[0]

    print(f"\n[{tag}]")
    print("Found:", len(results["masks"]))
    print("boxes:", results["boxes"])
    print("scores:", results["scores"])
    print("masks shape:", results["masks"].shape if len(results["masks"]) > 0 else None)


# 1. PIL 직접 로드: 기준
pil_direct = Image.open(image_path).convert("RGB")
pil_direct.save("/tmp/sam3_direct_pil.png")
run_sam3(pil_direct, "PIL direct")


# 2. Qt QPixmap 로드 후 기존 방식처럼 RGBA로 가정해서 변환
pixmap = QPixmap(image_path)
qimage_old = pixmap.toImage()

w = qimage_old.width()
h = qimage_old.height()

ptr = qimage_old.bits()
ptr.setsize(qimage_old.byteCount())
arr_old = np.array(ptr).reshape(h, w, 4)

# 기존 코드에서 쓰던 방식
# 실제 QImage가 ARGB/BGRA면 이게 틀어질 수 있음
try:
    import cv2
    frame_old = cv2.cvtColor(arr_old, cv2.COLOR_RGBA2RGB)
except Exception:
    frame_old = arr_old[:, :, :3].copy()

pil_qt_old = Image.fromarray(frame_old.astype(np.uint8)).convert("RGB")
pil_qt_old.save("/tmp/sam3_qt_old_assumed_rgba.png")
run_sam3(pil_qt_old, "Qt old assumed RGBA")


# 3. Qt QImage를 RGBA8888로 강제 변환 후 RGB 추출
qimage_new = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)

w = qimage_new.width()
h = qimage_new.height()

ptr = qimage_new.bits()
ptr.setsize(qimage_new.byteCount())
arr_new = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))

frame_new = arr_new[:, :, :3].copy()
pil_qt_new = Image.fromarray(frame_new).convert("RGB")
pil_qt_new.save("/tmp/sam3_qt_new_rgba8888.png")
run_sam3(pil_qt_new, "Qt new RGBA8888")


print("\nSaved debug images:")
print("/tmp/sam3_direct_pil.png")
print("/tmp/sam3_qt_old_assumed_rgba.png")
print("/tmp/sam3_qt_new_rgba8888.png")