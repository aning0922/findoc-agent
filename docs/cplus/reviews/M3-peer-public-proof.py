import asyncio, json, time
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from contextlib import nullcontext
from app.demo.seed import verify_seed, materialize
from app.financial_statements_v3 import StatementService
from app.peer_compare import PeerComparisonService
from app.retrieval_v2.models import TrustedIdentity
from tests.test_document_sources import Harness


async def main():
    seed = Path(
        "/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent/data/showcase-seed-v1"
    )
    _, digest = verify_seed(seed)
    with TemporaryDirectory(prefix="findoc-peer-real-") as tmp:
        root = Path(tmp) / "runtime"
        materialize(seed, root, digest)
        h = Harness(root)
        statements = StatementService(root, h.service)
        companies = [
            c.company_id for c in h.companies.list() if c.security_code in ("000651", "000333")
        ]
        selection = []
        inventory = []
        for d in h.docs.list_by_workspace("demo"):
            try:
                s = await h.service.source(d.document_id)
            except Exception:
                continue
            if s["company_id"] not in companies or s["report_year"] != 2025:
                continue
            collection = await statements.collect(str(uuid4()), d.document_id, s["source_revision"])
            cells = [
                c
                for c in collection["cells"]
                if c["extraction_status"] == "candidate"
                and c["time"].get("as_of_date") == "2025-12-31"
            ]
            inventory.append(
                dict(
                    company_id=s["company_id"],
                    document_id=d.document_id,
                    candidate_cells=len(cells),
                    metrics=sorted({c["metric_key"] for c in cells}),
                )
            )
            if cells:
                selection.append(
                    dict(collection_id=collection["id"], cell_ids=[c["cell_id"] for c in cells])
                )
        service = PeerComparisonService(
            root,
            statements=statements,
            identity_validator=lambda i: None,
            publication_guard=lambda i, f: nullcontext(),
            commit_check=lambda i, f: None,
        )
        identity = TrustedIdentity(
            workspace_id="demo",
            instance_id="proof",
            generation=1,
            principal_id="proof",
            expires_at=float(time.time() + 300),
        )
        result = (
            await service.compare(
                dict(
                    operation_id=str(uuid4()),
                    company_ids=companies,
                    collection_refs=selection,
                    candidate_view=True,
                ),
                identity,
            )
            if len(selection) == 2
            else None
        )
        proof = dict(
            tier="REAL_PDF_EXTRACTION_LOCAL_NO_LLM",
            seed_manifest_sha256=digest,
            inventory=inventory,
            comparison=[
                dict(
                    metric_key=g["metric_key"],
                    state=g["state"],
                    reason=g["reason"],
                    differences=g["differences"],
                )
                for g in result["result"]["comparisons"]
            ]
            if result
            else None,
            llm_calls=0,
            human_approvals=0,
            limitations=[
                "nullcontext guard does not verify integrated final fencing",
                "candidates are not confirmed financial facts",
            ],
        )
        verify_seed(seed, digest)
        Path("docs/cplus/reviews/M3-peer-public-proof.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2)
        )
        print(json.dumps(proof))


asyncio.run(main())
