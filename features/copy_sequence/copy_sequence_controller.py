# 여기서부터 수정하고: 오른쪽 패널에서 실행하는 연속 복붙 기능을 별도 controller로 분리했다.
from copy import deepcopy
from typing import List

from PyQt5.QtWidgets import QInputDialog, QMessageBox


class CopySequenceControllerMixin:
    def on_copy_sequence_clicked(self):
        """오른쪽 패널의 연속 붙여넣기 버튼에서 호출되는 진입점."""
        self.paste_annotations_sequence()

    def paste_annotations_sequence(self):
        """내부 클립보드의 객체 표시 정보를 지정한 프레임 범위에 연속으로 붙여넣는다."""
        if self.current_index < 0 or self.source is None:
            QMessageBox.warning(self, "경고", "먼저 미디어를 열고 프레임을 선택하세요.")
            return
        if not self.annotation_clipboard:
            self.show_status_message("먼저 Ctrl+C로 복사할 객체를 선택하세요.")
            return

        total_frames = int(self.source.frame_count())
        if total_frames <= 0:
            QMessageBox.warning(self, "경고", "붙여넣을 프레임이 없습니다.")
            return

        start_frame = int(self.current_index)
        default_end_frame = min(start_frame + 10, total_frames - 1)
        if default_end_frame == start_frame and start_frame > 0:
            default_end_frame = max(start_frame - 10, 0)

        end_frame, ok = QInputDialog.getInt(
            self,
            "연속 붙여넣기",
            "종료 프레임:",
            default_end_frame,
            0,
            total_frames - 1,
            1,
        )
        if not ok:
            return
        end_frame = int(end_frame)
        # 여기서부터 수정하고: 연속 복붙 대상에 현재 프레임도 포함되게 했다.
        direction = 1 if end_frame > start_frame else -1
        target_frames = list(range(start_frame, end_frame + direction, direction))
        if not target_frames:
            self.show_status_message("연속 붙여넣기 범위가 없습니다.")
            return
        # 여기까지 수정했다: 연속 복붙 대상에 현재 프레임도 포함되게 했다.

        self.push_undo_state("연속 객체 붙여넣기")

        pasted_count = 0
        affected_current_ann_ids: List[int] = []
        for frame_idx in target_frames:
            frame_ann_ids: List[int] = []
            for copied in self.annotation_clipboard:
                label_id = copied.label_id if copied.label_id in self.labels_by_id else None
                payload = deepcopy(copied.data)
                ann, _created = self.store.upsert_annotation(
                    frame_idx,
                    copied.shape_type,
                    payload,
                    label_id,
                    track_id=copied.track_id,
                    hidden=False,
                )
                frame_ann_ids.append(ann.ann_id)
                pasted_count += 1

            if frame_idx == self.current_index:
                affected_current_ann_ids = frame_ann_ids

        if affected_current_ann_ids:
            self.refresh_annotations_for_current_frame(affected_current_ann_ids)
            self.canvas.set_selected_annotations(affected_current_ann_ids)
            self.sync_object_tree_selection(affected_current_ann_ids)
            self.sync_label_list_view(affected_current_ann_ids)
        else:
            self.refresh_annotations_for_current_frame(self.get_selected_annotation_ids())
        self.refresh_timeline_tree()

        direction_text = "정방향" if direction > 0 else "역순"
        self.show_status_message(
            f"연속 붙여넣기 완료: {len(target_frames)}개 프레임, {pasted_count}개 객체 ({direction_text})"
        )
# 여기까지 수정했다: 오른쪽 패널에서 실행하는 연속 복붙 기능을 별도 controller로 분리했다.
