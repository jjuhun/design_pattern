# 여러 파일에서 반복해서 쓰는 작은 보조 함수를 모아둔 파일입니다.
# 정렬, 값 제한, 박스 좌표를 폴리곤 좌표로 바꾸는 기능이 있습니다.
import re


def natural_key(text: str):
    """숫자가 섞인 문자열을 사람이 보는 순서대로 정렬할 키로 바꾼다."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def clamp(value, lo, hi):
    """값이 지정한 최솟값과 최댓값 사이에 머물도록 제한한다."""
    return max(lo, min(hi, value))
def box_to_polygon(box):
    """박스 좌표를 네 꼭짓점 폴리곤 좌표로 변환한다."""
    x1, y1, x2, y2 = box
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
