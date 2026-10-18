"""Explicit reindex of the isolated four-report acceptance runtime using the published API service."""

import asyncio
import json
import os
from pathlib import Path
import sys
import time
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from app.api.runtime_factory import create_runtime_app  # noqa: E402
from app.companies.sqlite_repository import SQLiteCompanyRepository  # noqa: E402
from app.rag.publications import IndexPublications  # noqa: E402

for k, v in dotenv_values(root.parent / "findoc-rag/.env").items():
    if v is not None:
        os.environ.setdefault(k, v)
index = json.loads((root / "product/validation/d16-real-index.json").read_text())
output = root / "product/validation/d16-flat-reindex.json"
report = dict(
    runtime_root=index["runtime_root"],
    reports=[],
    reason="AUTOINDEX HNSW missed a known higher-scoring row; ef probe did not change results",
)


async def main():
    app = create_runtime_app(Path(index["runtime_root"]))
    sources = app.state.source_service
    pub = IndexPublications(
        SQLiteCompanyRepository(Path(index["runtime_root"]) / "documents.db"),
        app.state.runtime_rag_resources.milvus_client,
    )
    try:
        for d in index["reports"]:
            t = time.monotonic()
            record = await sources.documents.get_document(d["document_id"])
            if record.status.value == 'failed':
                old = dict(source_revision=None)
                await sources.documents.retry_document(d["document_id"])
            else:
                old = await sources.source(d["document_id"])
                await sources.reindex(d["document_id"], old["attempt"])
            while True:
                current = await sources.documents.get_document(d["document_id"])
                if current.status.value == "failed":
                    raise RuntimeError(current.error_code)
                if current.status.value == "ready":
                    break
                await asyncio.sleep(1)
            src = await sources.source(d["document_id"])
            generation, manifest = await asyncio.to_thread(
                pub.verified, "demo", d["document_id"], src["source_revision"]
            )
            assert manifest["index_type"] == "FLAT"
            report["reports"].append(
                dict(
                    report_id=d["report_id"],
                    document_id=d["document_id"],
                    old_revision=old["source_revision"],
                    source=src,
                    generation=generation,
                    manifest=manifest,
                    seconds=time.monotonic() - t,
                )
            )
            output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
            print("rebuilt FLAT", d["report_id"], flush=True)
        report["status"] = "passed"
    finally:
        app.state.runtime_rag_resources.milvus_client.close()


try:
    asyncio.run(main())
except Exception as exc:
    report["status"] = "failed"
    report["safe_error_type"] = type(exc).__name__
finally:
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
sys.exit(0 if report["status"] == "passed" else 1)
