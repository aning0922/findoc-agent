"""Bounded real D27 run. Fresh business roots only; gold is assertion input only.

No acceptance, facts or historical business data are imported. Instrumentation
delegates once to production methods and saves failures before any assertions.
"""

import argparse
import asyncio
from dataclasses import asdict
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import subprocess
import sys
import threading
import tempfile
import time
import uuid
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reopen", type=Path)
    parser.add_argument("--questions", action="store_true")
    parser.add_argument("--business", action="store_true")
    parser.add_argument("--bench", action="store_true")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--warm-start", action="store_true")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime = args.reopen.resolve() if args.reopen else out / "runtime"
    assert runtime.is_relative_to(ROOT / "data/d27"), "D27 roots only"
    if args.business:
        assert args.reopen, "business requires this round offline D27 seed"
        target = Path(tempfile.mkdtemp(prefix="findoc-d11-d27-business-")).resolve()
        shutil.copytree(runtime, target, dirs_exist_ok=True)
        runtime = target
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[k] = "1"
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false",
        TIKTOKEN_CACHE_DIR=str(ROOT / "data/integration-tokenizer-cache"),
    )
    from dotenv import dotenv_values

    for k, v in dotenv_values(ROOT.parent / "findoc-rag/.env").items():
        if k.startswith("LLM_") and v:
            os.environ[k] = v
    os.environ["LLM_TIMEOUT_SECONDS"] = "90"
    assert all(os.environ.get(k) for k in ("LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"))
    proof = dict(
        schema="d27-real-v1",
        runtime_root=str(runtime),
        git_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        diff_sha256=hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT)
        ).hexdigest(),
        host=platform.platform(),
        machine=platform.machine(),
        python=sys.version,
        model=os.environ["LLM_MODEL"],
        bge="BAAI/bge-m3",
        dimensions=1024,
        budget=dict(
            question_attempts=18,
            maximum_question_provider_requests=16,
            sdk_retries=0,
            timeout_seconds=90,
            max_completion_tokens=4096,
            automatic_question_retries=0,
        ),
        human_semantic_review="pending",
        human_acceptances=0,
        reports=[],
        questions=[],
    )
    proof["code_manifest"] = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("app", "frontend/src")
        for p in (ROOT / folder).rglob("*")
        if p.is_file()
    }
    proof["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out / "preflight.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2))
    events, lock, label = [], threading.Lock(), {"value": "startup"}
    worker = threading.local()
    sampling_stop = threading.Event()

    def sample_resources():
        import psutil

        process = psutil.Process()
        while not sampling_stop.is_set():
            samples = []
            for child in [process, *process.children(recursive=True)]:
                try:
                    samples.append(
                        dict(
                            pid=child.pid,
                            rss_bytes=child.memory_info().rss,
                            cpu_seconds=sum(child.cpu_times()[:2]),
                        )
                    )
                except psutil.Error:
                    pass
            with (out / "resources.jsonl").open("a") as stream:
                stream.write(
                    json.dumps(
                        dict(monotonic=time.monotonic(), label=label["value"], processes=samples)
                    )
                    + "\n"
                )
            sampling_stop.wait(0.5)

    sampler = threading.Thread(target=sample_resources, daemon=True)
    sampler.start()

    def emit(event):
        with lock:
            events.append(event)
            with (out / "events.jsonl").open("a") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def observe(owner, name, kind, summarize=lambda r: {}):
        original = getattr(owner, name)

        @wraps(original)
        def call(*a, **kw):
            old_document = getattr(worker, "document", None)
            if kind == "document_process":
                worker.document = a[1]
            t, cpu = time.perf_counter(), time.process_time()
            event = dict(
                kind=kind,
                label=label["value"],
                started_monotonic=t,
                worker_document=getattr(worker, "document", None),
            )
            try:
                result = original(*a, **kw)
                event.update(summarize(result))
                return result
            except BaseException as exc:
                event["error_type"] = type(exc).__name__
                raise
            finally:
                event.update(
                    seconds=time.perf_counter() - t,
                    cpu_seconds=time.process_time() - cpu,
                    peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                )
                emit(event)
                if kind == "document_process":
                    worker.document = old_document

        setattr(owner, name, call)

    from openai.resources.chat.completions import Completions
    from app.api import runtime_factory as factory
    from app.rag.retriever import Retriever
    from app.rag.store import MilvusSearchStore
    from app.rag.publications import IndexPublications
    from app.documents.source_service import DocumentSourceService
    from app.documents import processor
    from app.agent.metric_extraction import metric_for

    # Count physical HTTP sends, separately from SDK logical calls. No URLs/headers stored.
    import httpx

    original_send = httpx.Client.send
    provider_host = urlparse(os.environ["LLM_BASE_URL"]).hostname

    def physical_send(self, request, *a, **kw):
        if request.url.host != provider_host:
            return original_send(self, request, *a, **kw)
        t = time.perf_counter()
        event = dict(kind="provider_http", label=label["value"], started_monotonic=t)
        try:
            response = original_send(self, request, *a, **kw)
            event["status"] = response.status_code
            return response
        except Exception as exc:
            event["error_type"] = type(exc).__name__
            raise
        finally:
            event["seconds"] = time.perf_counter() - t
            emit(event)

    httpx.Client.send = physical_send
    original_create = Completions.create
    provider_calls = 0

    def bounded_create(self, *a, **kw):
        nonlocal provider_calls
        provider_calls += 1
        if provider_calls > 16:
            raise RuntimeError("D27 physical model request budget exhausted")
        kw["max_tokens"] = 4096
        return original_create(self, *a, **kw)

    Completions.create = bounded_create
    observe(
        Completions,
        "create",
        "provider",
        lambda r: dict(
            request_id=r.id,
            model=r.model,
            usage=r.usage.model_dump() if r.usage else None,
            finish_reason=r.choices[0].finish_reason,
            raw_output=r.choices[0].message.content,
        ),
    )
    observe(factory, "_runtime_bge_embed", "bge", lambda r: dict(vectors=len(r)))
    observe(factory, "parse_fast_pdf_bytes", "parse", lambda r: dict(blocks=len(r)))
    observe(processor, "chunk_with_existing_strategy", "chunk", lambda r: dict(chunks=len(r)))
    observe(
        processor.DocumentProcessor,
        "process",
        "document_process",
        lambda r: dict(document_id=r.document_id, status=r.status.value),
    )
    observe(DocumentSourceService, "capture", "source_capture")
    observe(Retriever, "retrieve", "retrieve", lambda r: dict(hits=[asdict(h) for h in r]))
    observe(MilvusSearchStore, "search", "milvus_search", lambda r: dict(hits=len(r)))
    observe(IndexPublications, "search", "milvus_search", lambda r: dict(hits=len(r)))
    observe(IndexPublications, "_read_rows", "index_read_rows", lambda r: dict(rows=len(r)))
    observe(IndexPublications, "_verify_rows", "index_verify_rows")
    from pymilvus import MilvusClient

    observe(
        MilvusClient,
        "search",
        "milvus_physical_search",
        lambda r: dict(hit_counts=[len(h) for h in r]),
    )
    old_indexer = factory._build_runtime_indexer

    def indexer(*a, **kw):
        fn = old_indexer(*a, **kw)

        class Port:
            run = staticmethod(fn)

        observe(Port, "run", "index", lambda r: dict(final_ids=len(r.final_ids)))
        return Port.run

    factory._build_runtime_indexer = indexer
    started = time.perf_counter()
    app = factory.create_runtime_app(runtime)
    proof["startup_seconds"] = time.perf_counter() - started
    import psutil

    proof["process_start_to_ready_seconds"] = time.time() - psutil.Process().create_time()
    from app.rag.embed import _model

    proof["bge_devices"] = _model.target_devices
    from fastapi.testclient import TestClient
    from app.companies.models import CompanyCreate
    from app.documents.source_models import ReportUploadInput

    sources = json.loads((ROOT / "product/validation/sources.json").read_text())

    async def prepare():
        pending = []
        identities = {}
        for code, name in [("midea", "美的集团股份有限公司"), ("gree", "珠海格力电器股份有限公司")]:
            identities[code] = app.state.company_service.create(
                CompanyCreate(
                    name=name,
                    security_code="000333" if code == "midea" else "000651",
                    exchange="SZSE",
                )
            ).company_id
        for source in sources:
            label["value"] = source["id"]
            path = ROOT / source["path"]
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                with urlopen(source["url"], timeout=120) as response:
                    path.write_bytes(response.read())
            content = path.read_bytes()
            assert hashlib.sha256(content).hexdigest() == source["sha256"]
            code, year = source["id"].split("-")
            t = time.perf_counter()
            result = await app.state.source_service.upload(
                filename=source["id"] + ".pdf",
                content=content,
                payload=ReportUploadInput(
                    company_id=identities[code],
                    report_year=int(year),
                    report_type="annual",
                    basis="PRC_GAAP",
                    period_start=f"{year}-01-01",
                    period_end=f"{year}-12-31",
                    source_url=source["url"],
                ),
            )
            uploaded = time.perf_counter() - t
            doc = result["document_id"]
            if args.batch:
                pending.append((source, doc, t, uploaded))
                continue
            await finish(source, doc, t, uploaded)
        for source, doc, t, uploaded in pending:
            await finish(source, doc, t, uploaded)

    async def finish(source, doc, t, uploaded):
        while time.perf_counter() - t < 1800:
            record = await app.state.source_service.documents.get_document(doc)
            if record.status.value in ("ready", "failed"):
                break
            await asyncio.sleep(0.25)
        src = await app.state.source_service.source(doc)
        entry = dict(
            report_id=source["id"],
            document_id=doc,
            source=src,
            upload_started_monotonic=t,
            upload_seconds=uploaded,
            preparation_seconds=time.perf_counter() - t,
            status=record.status.value,
            error_code=record.error_code,
        )
        proof["reports"].append(entry)
        save()
        print(
            json.dumps(
                dict(
                    report=source["id"],
                    status=record.status.value,
                    seconds=entry["preparation_seconds"],
                )
            ),
            flush=True,
        )
        assert record.status.value == "ready", entry

    def save():
        proof["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        proof["process_cpu_seconds"] = time.process_time()
        proof["runtime_file_sizes"] = {
            str(p.relative_to(runtime)): p.stat().st_size for p in runtime.rglob("*") if p.is_file()
        }
        (out / "results.json").write_text(
            json.dumps(proof, ensure_ascii=False, indent=2, default=str) + "\n"
        )

    try:
        with TestClient(app) as client:
            if not args.reopen:
                preparation_start = time.perf_counter()
                asyncio.run(prepare())
                proof["preparation_wall_seconds"] = time.perf_counter() - preparation_start
                proof["batch_uploads"] = args.batch
            else:
                proof["reports"] = json.loads((args.reopen.parent / "results.json").read_text())[
                    "reports"
                ]
            mapping = {r["report_id"]: r for r in proof["reports"]}
            if args.bench:
                proof["retrieval_bench"] = []
                for size in (1, 4):
                    ids = [r["document_id"] for r in proof["reports"][:size]]
                    for sample in range(3):
                        label["value"] = f"retrieval-{size}-{sample}"
                        before, t = len(events), time.perf_counter()

                        async def search():
                            selection = await app.state.selection_preparer.prepare_many(
                                document_ids=ids, query="请摘录营业收入原值及原单位"
                            )
                            return await app.state.selected_scope_search.search(selection, top_k=12)

                        hits = asyncio.run(search())
                        proof["retrieval_bench"].append(
                            dict(
                                documents=size,
                                sample=sample,
                                seconds=time.perf_counter() - t,
                                hits=[asdict(h) for h in hits],
                                events=events[before:],
                            )
                        )
                        save()
            if args.questions:
                kit = json.loads((ROOT / "product/d26/AC30-10-QUESTIONS.json").read_text())
                for q in kit["questions"]:
                    label["value"] = q["id"]
                    before, t = len(events), time.perf_counter()
                    body = dict(
                        operation_id=str(uuid.uuid4()),
                        query=q["query"],
                        document_ids=[mapping[s]["document_id"] for s in q["selected_reports"]],
                    )
                    response = client.post("/research/runs", json=body)
                    result = response.json()
                    item = dict(
                        id=q["id"],
                        query=q["query"],
                        selected_reports=q["selected_reports"],
                        request=body,
                        http_status=response.status_code,
                        result=result,
                        seconds=time.perf_counter() - t,
                        human_semantic_review="pending",
                    )
                    current = events[before:]
                    item["calls"] = {
                        k: sum(e["kind"] == k for e in current)
                        for k in (
                            "retrieve",
                            "bge",
                            "milvus_search",
                            "milvus_physical_search",
                            "provider",
                            "provider_http",
                        )
                    }
                    item["hits"] = [
                        h for e in current if e["kind"] == "retrieve" for h in e.get("hits", [])
                    ]
                    item["sources"] = [mapping[s] for s in q["selected_reports"]]
                    item["expected"] = q["expected"]
                    item["engineering_pass"] = result.get("status") == q["expected"]
                    if "gold" in q:
                        gold = q["gold"]
                        r = mapping[q["selected_reports"][0]]
                        src, records = asyncio.run(
                            app.state.source_service.parsed_evidence(
                                r["document_id"],
                                company_id=r["source"]["company_id"],
                                source_revision=r["source"]["source_revision"],
                            )
                        )
                        tables = [
                            e
                            for e in records
                            if e["kind"] == "table"
                            and e["physical_page"] == gold["physical_page"]
                            and gold["raw_value"] in e["text"]
                        ]
                        checks = []
                        for table in tables:
                            structure = table["layout"]["table_structure"]
                            labels = [
                                c
                                for c in structure["cells"]
                                if metric_for(c["text"]) == gold["metric"]
                            ]
                            cells = [
                                c
                                for c in structure["cells"]
                                if c["actual_year"] == gold["period"]
                                and any(cell_label["row"] == c["row"] for cell_label in labels)
                            ]
                            checks.append(
                                dict(
                                    evidence_id=table["evidence_id"],
                                    structure=structure,
                                    aligned=any(c["text"] == gold["raw_value"] for c in cells),
                                )
                            )
                        citations = result.get("result", {}).get("citations", [])
                        content = result.get("result", {}).get("content", "")
                        item["gold"] = gold
                        item["table_checks"] = checks
                        item["gates"] = dict(
                            pdf_sha=src["content_sha256"]
                            == next(
                                s["sha256"] for s in sources if s["id"] == q["selected_reports"][0]
                            ),
                            table_structure=any(c["aligned"] for c in checks),
                            citation_identity=bool(citations)
                            and all(
                                c["document_id"] == r["document_id"]
                                and c["source_revision"] == src["source_revision"]
                                and c["content_sha256"] == src["content_sha256"]
                                for c in citations
                            ),
                            presentation=gold["raw_value"] in content
                            and str(gold["period"]) in content
                            and gold["raw_unit"] in content,
                            relevant_citation=any(
                                c["physical_page"] == gold["physical_page"]
                                and gold["raw_value"] in c["text"]
                                for c in citations
                            ),
                        )
                        item["engineering_pass"] &= all(item["gates"].values())
                    else:
                        raw = result.get("result", {})
                        item["engineering_pass"] &= (
                            raw.get("reason") == q["expected_reason"]
                            and not raw.get("content")
                            and not raw.get("citations")
                        )
                    proof["questions"].append(item)
                    save()
                    print(
                        json.dumps(
                            dict(
                                id=q["id"],
                                status=result.get("status"),
                                pass_=item["engineering_pass"],
                                calls=item["calls"],
                                seconds=item["seconds"],
                            )
                        ),
                        flush=True,
                    )
                    if result.get("run_id"):
                        assert (
                            client.get("/research/runs/by-operation/" + body["operation_id"]).json()
                            == result
                        )
                        assert client.post("/research/runs", json=body).json() == result
                        assert len(events) == before + len(current), (
                            "history/repeat caused execution"
                        )
            if args.business:
                from scripts.run_d27_business import run_business

                run_business(app, runtime, proof, events, label, save)
            save()
        if args.warm_start:
            label["value"] = "same-process-warm-start"
            started = time.perf_counter()
            warm_app = factory.create_runtime_app(runtime)
            proof["same_process_warm_factory_seconds"] = time.perf_counter() - started
            with TestClient(warm_app) as warm_client:
                started = time.perf_counter()
                response = warm_client.get("/health")
                proof["warm_health_status"] = response.status_code
                proof["warm_health_seconds"] = time.perf_counter() - started
            save()
    except BaseException as exc:
        proof["failure_type"] = type(exc).__name__
        save()
        raise
    finally:
        sampling_stop.set()
        sampler.join(timeout=2)
    print(
        json.dumps(
            dict(out=str(out), startup=proof["startup_seconds"], questions=len(proof["questions"]))
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
