"""Candidate grid from OCR line boxes. Coordinates/text are never corrected."""


def candidate_grid(lines):
    valid = []
    for index, line in enumerate(lines):
        box = line.get("bbox")
        if (
            not isinstance(box, list)
            or len(box) != 4
            or any(not isinstance(v, (int, float)) for v in box)
            or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)
            or not isinstance(line.get("text"), str)
            or not line["text"].strip()
        ):
            continue
        valid.append((index, line, (box[1] + box[3]) / 2))
    groups = []
    for item in sorted(valid, key=lambda x: x[2]):
        if not groups or abs(item[2] - groups[-1][0][2]) > 0.008:
            groups.append([item])
        else:
            groups[-1].append(item)
    rows = [sorted(group, key=lambda x: x[1]["bbox"][0]) for group in groups if len(group) >= 2]
    if len(rows) < 2:
        return []
    anchors = []
    for _, line, _ in sorted((item for row in rows for item in row), key=lambda x: x[1]["bbox"][0]):
        x = line["bbox"][0]
        if not anchors or x - anchors[-1] > 0.045:
            anchors.append(x)
    cells = []
    for row_number, row in enumerate(rows):
        for original_index, line, _ in row:
            column = min(range(len(anchors)), key=lambda c: abs(anchors[c] - line["bbox"][0]))
            cells.append(
                dict(
                    row=row_number,
                    column=column,
                    text=line["text"],
                    bbox=line["bbox"],
                    source_line_index=original_index,
                    confidence=line.get("confidence"),
                )
            )
    return [
        dict(
            table_id="ocr-layout-candidate",
            quality="needs_review",
            method="bbox_line_clustering",
            coordinate_system="normalized_top_left",
            row_count=len(rows),
            column_count=len(anchors),
            cells=cells,
            warning="整页版面聚类并非表格区域检测；合并单元格和换行可能错位，必须对照原图。",
        )
    ]
