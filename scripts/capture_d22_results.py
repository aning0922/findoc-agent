"""Capture validated API payloads/screenshots as QA files, never user report history."""

import hashlib
import json
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from app.reports.contracts import ReportDraft  # noqa: E402

path = root / "product/validation/d22-real-reports.json"
proof = json.loads(path.read_text())
runtime = Path(proof["runtime_root"])
previews = root / "product/validation/d22-previews"
previews.mkdir(exist_ok=True)
screens = root / "product/validation/d22-screenshots"
screens.mkdir(exist_ok=True)
browser = json.loads((root / "product/validation/d22-browser-record.json").read_text())
artifacts = Path(browser["artifacts"])
for name, case in zip(
    ["midea-2024-2025", "gree-2024-2025", "midea-gree-2024", "midea-gree-2025"],
    proof["cases"],
    strict=True,
):
    draft = ReportDraft.model_validate_json(
        (runtime / "drafts" / f"{case['task_id']}.json").read_text()
    )
    target = previews / (name + ".json")
    target.write_text(draft.model_dump_json() + "\n")
    case["preview_file"] = str(target.relative_to(root))
    case["preview_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    widths = (
        [1440, 1024]
        if name == "midea-2024-2025"
        else [1440, 1280]
        if name == "midea-gree-2025"
        else [1440]
    )
    for width in widths:
        shutil.copy2(artifacts / f"{case['task_id']}-{width}.png", screens / f"{name}-{width}.png")
proof["validation_captures_only"] = True
proof["formal_report_storage_implemented"] = False
path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
(root / "product/validation/report-draft-v1.schema.json").write_text(
    json.dumps(ReportDraft.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
)
print("Four complete payloads validate; six new D22 screenshots captured.")
