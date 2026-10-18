"""Open actual downloaded UTF-8 Markdown through a conventional renderer in Chromium."""

import json
from pathlib import Path
import subprocess
from markdown_it import MarkdownIt

root = Path(__file__).resolve().parent.parent
record = json.loads((root / "product/validation/d24-browser-record.json").read_text())
assert len(record["records"]) == 3 and all(r["exit_code"] == 0 for r in record["records"])
out = Path(record["artifacts"])
for index in range(4):
    for revision in (1, 2):
        md = (out / f"live-{index}-v{revision}.md").read_text()
        html = MarkdownIt("default", {"html": True}).render(md)
        (out / f"reader-{index}-v{revision}.html").write_text(
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>FinDoc Markdown 阅读验证</title><style>body{max-width:1100px;margin:32px auto;line-height:1.7;font-family:system-ui}table{border-collapse:collapse;font-size:14px}td,th{padding:8px;border:1px solid #ddd}pre{padding:12px;background:#f6f8fa;overflow:auto;white-space:pre}h1,h2{color:#163b66}</style>'
            + html
            + "</html>"
        )
subprocess.run(
    ["node", str(root / "frontend/scripts/inspect-d24-markdown.mjs"), str(out)],
    cwd=root / "frontend",
    check=True,
)
reader = json.loads((out / "markdown-reader-results.json").read_text())
(root / "product/validation/d24-markdown-reader.json").write_text(
    json.dumps(reader, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps(dict(artifact_dir=str(out), versions=8, actual_chromium=True)))
