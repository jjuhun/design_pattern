from label.bounding_box import BoundingBox
from label.polygon import PolygonAnnotation


def propagate_selected_annotations_to_range(
    annotation_manager,
    source_frame_idx,
    selected_box_ids,
    selected_polygon_ids,
    start_frame_idx,
    end_frame_idx,
):
    if not selected_box_ids and not selected_polygon_ids:
        return 0, 0

    start_idx = min(start_frame_idx, end_frame_idx)
    end_idx = max(start_frame_idx, end_frame_idx)

    source_boxes = annotation_manager.get_bboxes(source_frame_idx)
    source_polygons = annotation_manager.get_polygons(source_frame_idx)

    source_box_map = {box.box_id: box for box in source_boxes}
    source_polygon_map = {polygon.polygon_id: polygon for polygon in source_polygons}

    selected_source_boxes = [source_box_map[box_id] for box_id in selected_box_ids if box_id in source_box_map]
    selected_source_polygons = [source_polygon_map[polygon_id] for polygon_id in selected_polygon_ids if polygon_id in source_polygon_map]

    created_box_count = 0
    created_polygon_count = 0

    for frame_idx in range(start_idx, end_idx + 1):
        if frame_idx == source_frame_idx:
            continue

        for src_box in selected_source_boxes:
            new_box = annotation_manager.create_bbox(
                src_box.x1,
                src_box.y1,
                src_box.x2,
                src_box.y2,
                src_box.class_id,
            )
            annotation_manager.add_bbox(frame_idx, new_box)
            created_box_count += 1

        for src_polygon in selected_source_polygons:
            new_polygon = annotation_manager.create_polygon(
                list(src_polygon.points),
                src_polygon.class_id,
            )
            annotation_manager.add_polygon(frame_idx, new_polygon)
            created_polygon_count += 1

    return created_box_count, created_polygon_count