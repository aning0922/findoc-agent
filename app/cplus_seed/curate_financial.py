"""Preset unconfirmed display series, never financial-service receipts or collections."""

import asyncio
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile

import pymupdf
from app.demo.seed import verify_seed, materialize, sha256
from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.companies.service import CompanyService
from app.documents.sqlite_repository import SQLiteDocumentRepository
from app.documents.local_object_store import LocalObjectStore
from app.documents.service import DocumentService
from app.documents.source_repository import SQLiteSourceRepository
from app.documents.source_service import DocumentSourceService
from app.financial_statements_v3.extraction import extract

PARENT_SHA = "287d939e8d72aba2092a4fae00f10ecab0711258a86f11f453dd760febe49459"
DISCLOSURES = {
    2024: "c7184706caf5f57c04a795990967cfc4f4253024e02f8bdaffe2b260df2c6006",
    2025: "7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c",
}
METRICS = (
    "revenue",
    "net_profit_parent",
    "operating_cash_flow",
    "total_assets",
    "total_liabilities",
)


def choose_current(cells, year):
    chosen = []
    missing = []
    for metric in METRICS:
        expected = (
            dict(kind="instant", as_of_date=f"{year}-12-31")
            if metric in ("total_assets", "total_liabilities")
            else dict(
                kind="duration",
                period_start=f"{year}-01-01",
                period_end=f"{year}-12-31",
                period_type="annual",
            )
        )
        matches = [c for c in cells if c["metric_key"] == metric and c["time"] == expected]
        reason = None
        if len(matches) != 1:
            reason = "missing_or_ambiguous_current_report_cell"
        elif matches[0]["extraction_status"] != "candidate":
            reason = "unsupported_current_report_cell"
        elif any(
            matches[0].get(k) != v
            for k, v in dict(
                basis="PRC_GAAP",
                scope="consolidated",
                currency="CNY",
                normalized_unit="CNY_YUAN",
                source_kind="fast_text",
                financial_review="unconfirmed",
            ).items()
        ):
            reason = "incomparable_or_not_unconfirmed_fast_candidate"
        elif not Decimal(matches[0]["normalized_decimal"]).is_finite():
            reason = "nonfinite_decimal"
        if reason:
            missing.append(dict(metric_key=metric, report_year=year, reason=reason))
        else:
            chosen.append(matches[0])
    return chosen, missing


async def observations(runtime, parent_sha):
    class Disabled:
        def dispatch(self, *args):
            raise RuntimeError("Read-only curation cannot dispatch")

    registry = SQLiteCompanyRepository(runtime / "documents.db")
    companies = CompanyService(registry, workspace_id="demo")
    objects = LocalObjectStore(runtime / "objects")
    documents = DocumentService(
        repository=SQLiteDocumentRepository(runtime / "documents.db"),
        object_store=objects,
        dispatcher=Disabled(),
        workspace_id="demo",
    )
    sources = DocumentSourceService(
        documents=documents,
        objects=objects,
        companies=companies,
        repository=SQLiteSourceRepository(registry),
    )
    grouped = {}
    missing = []
    proof = []
    for year, content_sha in DISCLOSURES.items():
        with closing(sqlite3.connect(runtime / "documents.db")) as db:
            rows = db.execute(
                "SELECT document_id FROM documents WHERE workspace_id='demo' AND content_sha256=? AND status='ready'",
                (content_sha,),
            ).fetchall()
        if len(rows) != 1:
            raise ValueError("explicit_disclosure_missing_or_ambiguous")
        document_id = rows[0][0]
        source = await sources.source(document_id)
        company = companies.get(source["company_id"])
        if (
            company.security_code,
            company.exchange,
            company.country,
            source["report_year"],
            source["basis"],
        ) != ("000651", "SZSE", "CN", year, "PRC_GAAP"):
            raise ValueError("unexpected_disclosure_identity")
        raw = await sources.file(document_id, source_revision=source["source_revision"])
        cells = extract(source, raw)
        selected, absent = choose_current(cells, year)
        missing.extend(absent)
        with pymupdf.open(stream=raw, filetype="pdf") as pdf:
            for cell in selected:
                if len(cell["evidence_refs"]) != 1:
                    raise ValueError("ambiguous_cell_evidence")
                ref = cell["evidence_refs"][0]
                page = pdf[ref["physical_page"] - 1]
                words = page.get_text("words")
                if not any(
                    w[4] == ref["raw_value"]
                    and all(abs(float(w[i]) - ref["bbox"][i]) < 0.1 for i in range(4))
                    for w in words
                ):
                    raise ValueError("exact_amount_or_bbox_unverified")
                normalized = "".join(page.get_text().split())
                if "人民币" + cell["raw_unit"] not in normalized:
                    raise ValueError("raw_unit_not_on_evidence_page")
                if ref["raw_value"].replace(",", "") != cell["raw_decimal"]:
                    raise ValueError("raw_decimal_changed")
                key = tuple(
                    [company.company_id, company.name, cell["metric_key"]]
                    + [cell[k] for k in ("basis", "scope", "currency", "normalized_unit")]
                )
                point = {
                    k: cell[k]
                    for k in (
                        "time",
                        "normalized_decimal",
                        "raw_decimal",
                        "raw_unit",
                        "document_id",
                        "source_revision",
                        "content_sha256",
                        "parser_version",
                    )
                }
                point.update(physical_page=ref["physical_page"], financial_review="unconfirmed")
                grouped.setdefault(key, []).append(point)
                proof.append(
                    dict(
                        metric_key=cell["metric_key"],
                        report_year=year,
                        physical_page=ref["physical_page"],
                        raw_label=ref["raw_label"],
                        raw_value=ref["raw_value"],
                        raw_unit=cell["raw_unit"],
                        bbox=ref["bbox"],
                        validation="actual_pdf_word_bbox_and_unit_exact",
                        financial_review="unconfirmed",
                    )
                )
    series = []
    for key, points in grouped.items():
        if len(points) > 2:
            raise ValueError("too_many_points")
        series.append(
            dict(
                zip(
                    (
                        "company_id",
                        "company_name",
                        "metric_key",
                        "basis",
                        "scope",
                        "currency",
                        "normalized_unit",
                    ),
                    key,
                ),
                points=sorted(points, key=lambda p: json.dumps(p["time"], sort_keys=True)),
            )
        )
    if len(series) > 5 or sum(len(s["points"]) for s in series) > 10:
        raise ValueError("curated_series_budget")
    return dict(
        schema_version="cplus-curated-financial-series-v1",
        data_origin="preset_candidate",
        financial_authority=False,
        human_approvals=0,
        parent_seed_manifest_sha256=parent_sha,
        series=series,
        missing=missing,
        limitations=[
            "预置候选未核准；不产生财务receipt或业务collection。",
            "固定两份报告仅选择本报告当年全年/年末唯一单元格；不自动选择latest或comparative。",
        ],
    ), proof


def build_curated_seed(parent, destination, bundle):
    parent, target, bundle = Path(parent), Path(destination), Path(bundle)
    if target.exists() or target.is_symlink() or bundle.exists() or bundle.is_symlink():
        raise FileExistsError("new_seed_and_bundle_only")
    if (
        any(p.is_symlink() for p in [*target.parents, *bundle.parents])
        or target.resolve().is_relative_to(parent.resolve())
        or bundle.resolve().is_relative_to(parent.resolve())
    ):
        raise ValueError("unsafe_destination")
    manifest, parent_sha = verify_seed(parent, PARENT_SHA)
    with tempfile.TemporaryDirectory(prefix="findoc-curated-candidates-") as temp:
        runtime = Path(temp) / "read-copy"
        materialize(parent, runtime, parent_sha)
        data, proof = asyncio.run(observations(runtime, parent_sha))
        frozen = Path(temp) / "frozen"
        shutil.copytree(parent, frozen)
        frozen.chmod(0o700)
        name = "cplus-financial-candidates.json"
        (frozen / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        (frozen / name).chmod(0o400)
        updated = {
            **manifest,
            "seed_version": "showcase-cplus-seed-v3",
            "files": manifest["files"] + [dict(path=name, sha256=sha256(frozen / name))],
        }
        (frozen / "manifest.json").chmod(0o600)
        (frozen / "manifest.json").write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
        )
        (frozen / "manifest.json").chmod(0o400)
        frozen.chmod(0o500)
        _, new_sha = verify_seed(frozen)
        for entry in manifest["files"]:
            if sha256(parent / entry["path"]) != sha256(frozen / entry["path"]):
                raise ValueError("parent_file_changed")
        shutil.copytree(frozen, target)
    verify_seed(target, new_sha)
    verify_seed(parent, parent_sha)
    with bundle.open("xb") as stream:
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            archive.add(target, arcname="showcase-cplus-seed-v3")
    bundle_files = verify_bundle(bundle, updated, new_sha)
    return dict(
        seed_root=str(target),
        manifest_sha256=new_sha,
        bundle_sha256=sha256(bundle),
        bundle_files_verified=bundle_files,
        parent_manifest_sha256=parent_sha,
        parent_files_unchanged=len(manifest["files"]),
        series=len(data["series"]),
        points=sum(len(s["points"]) for s in data["series"]),
        missing=data["missing"],
        validation=proof,
        new_model_calls=0,
        human_approvals=0,
    )


def verify_bundle(bundle, manifest, manifest_sha):
    """Hash every archived file without extracting or mutating a seed."""
    prefix = "showcase-cplus-seed-v3/"
    expected = {prefix + e["path"]: e["sha256"] for e in manifest["files"]}
    expected[prefix + "manifest.json"] = manifest_sha
    seen = set()
    with tarfile.open(bundle) as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise ValueError("unexpected_or_duplicate_bundle_member")
            digest = hashlib.sha256()
            with archive.extractfile(member) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected[member.name]:
                raise ValueError("bundle_file_checksum_failed")
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("bundle_files_missing")
    return len(seen)
