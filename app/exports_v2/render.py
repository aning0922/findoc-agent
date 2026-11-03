"""Local renderer CLI. User-authorized openpyxl/python-pptx; no network or models."""

import csv
import io
import json
from pathlib import Path
import re
import sys


def xlsx(data):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, key in [
        ("概览", "overview_matrix"),
        ("财务数据", "financial_matrix"),
        ("来源证据", "evidence_matrix"),
    ]:
        ws = wb.create_sheet(name)
        for row in data[key]:
            ws.append(
                [
                    re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", lambda m: "\\x%02x" % ord(m[0]), str(v))
                    for v in row
                ]
            )
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = Font(name="Microsoft YaHei", bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="17324D")
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.data_type = "s"
                cell.number_format = "@"
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.font = Font(name="Microsoft YaHei", size=11)
        for column in ws.columns:
            ws.column_dimensions[column[0].column_letter].width = (
                32 if name != "概览" else (28 if column[0].column == 1 else 95)
            )
        for r in range(2, ws.max_row + 1):
            ws.row_dimensions[r].height = 54
    stream = io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


def csv_bytes(data):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerows(
        data["financial_matrix"] if len(data["financial_matrix"]) > 1 else data["evidence_matrix"]
    )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


if __name__ == "__main__":
    data = json.loads(Path(sys.argv[2]).read_text())
    Path(sys.argv[3]).write_bytes({"xlsx": xlsx, "csv": csv_bytes}[sys.argv[1]](data))
