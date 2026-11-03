import asyncio
from contextlib import nullcontext
from copy import deepcopy
import json
import subprocess
from uuid import uuid4

import pytest
from app.exports_v2.projection import project, digest, matrix
from app.exports_v2.service import ExportService, ExportError
from tests.test_cplus_exports import BUNDLED


def fixture():
    points = [
        dict(
            company_id=company,
            metric_key="revenue",
            statement_kind="income_statement",
            time=dict(kind="duration", period_start="2025-01-01", period_end="2025-12-31"),
            raw_decimal=value,
            normalized_decimal=value,
            raw_unit="元",
            normalized_unit="CNY_YUAN",
            basis="PRC_GAAP",
            scope="consolidated",
            currency="CNY",
            report_year=2025,
            financial_review="unconfirmed",
            document_id="doc-" + company,
            source_revision="rev-" + company,
            evidence_refs=[
                dict(
                    document_id="doc-" + company,
                    source_revision="rev-" + company,
                    physical_page=88,
                    raw_label="营业收入",
                    raw_value=value,
                )
            ],
        )
        for company, value in (("a", "170447058533.57"), ("b", "458502366000.00"))
    ]
    payload = dict(
        schema_version="peer-comparison-v1",
        result_id="peer",
        candidate_view=True,
        comparisons=[dict(metric_key="revenue", state="candidate_observation", points=points)],
    )
    resolved = dict(
        snapshot=payload,
        display_status="current",
        selected_sources=[],
        display_companies={
            "a": dict(name="样本甲", security_code="000001", exchange="SZSE"),
            "b": dict(name="样本乙", security_code="000002", exchange="SZSE"),
        },
    )
    ref = dict(domain="peer_comparison_v1", id="peer", revision=1, payload_sha256=digest(payload))
    return resolved, ref


def test_display_labels_flat_period_and_chart_preserve_authority():
    resolved, ref = fixture()
    before = deepcopy(resolved["snapshot"])
    data = project(ref, resolved)
    row = data["financial"][0]
    assert (row["company_name"], row["company_code"], row["exchange"]) == (
        "样本甲",
        "000001",
        "SZSE",
    )
    assert (row["period_kind"], row["period_start"], row["period_end"], row["physical_page"]) == (
        "duration",
        "2025-01-01",
        "2025-12-31",
        88,
    )
    assert row["normalized_decimal"] == "170447058533.57" and row["authority"] == "unconfirmed"
    assert data["chart"]["kind"] == "bar" and len(data["chart"]["points"]) == 2
    assert data["evidence"][0]["report_year"] == 2025
    assert data["evidence"][0]["company_name"] == "样本甲"
    assert resolved["snapshot"] == before and digest(before) == ref["payload_sha256"]
    for key, value in [
        ("currency", "USD"),
        ("basis", "unknown"),
        ("time", dict(kind="instant", as_of_date="2025-12-31")),
    ]:
        changed = deepcopy(resolved)
        changed["snapshot"]["comparisons"][0]["points"][1][key] = value
        assert (
            project({**ref, "payload_sha256": digest(changed["snapshot"])}, changed)["chart"]
            is None
        )


def test_changed_registry_label_before_commit_leaves_unknown(tmp_path):
    resolved, ref = fixture()
    calls = []

    async def resolve(*args):
        calls.append(1)
        if len(calls) == 2:
            resolved["display_companies"]["a"]["name"] = "更名后"
        return resolved

    service = ExportService(
        tmp_path,
        resolver=resolve,
        identity_validator=lambda i: None,
        publication_guard=lambda *a: nullcontext(),
        before_commit_sync=lambda i: None,
        authorize_read=lambda *a: True,
        renderer_python=BUNDLED,
    )
    body = dict(
        operation_id=str(uuid4()),
        report_ref=ref,
        formats=["csv"],
        export_profile_version="research-v1",
    )
    with pytest.raises(ExportError, match="export_snapshot_or_status_changed"):
        asyncio.run(service.create(body, {"generation": 1}))
    assert service.operation(body["operation_id"], {"generation": 1})["state"] == "unknown"
    with service.tx() as db:
        assert db.execute("select count(*) from files").fetchone()[0] == 0


def test_native_business_chart_and_annual_explanation(tmp_path):
    resolved, ref = fixture()
    data = project(ref, resolved)
    data.update(
        overview_matrix=matrix(data["overview"], ["field", "value"]),
        financial_matrix=matrix(
            data["financial"], ["company_name", "metric_key", "normalized_decimal"]
        ),
        evidence_matrix=matrix(data["evidence"], ["text", "document_id", "physical_page"]),
    )
    source = tmp_path / "peer.json"
    source.write_text(json.dumps(data, ensure_ascii=False))
    from pathlib import Path

    renderer = Path(__file__).resolve().parents[1] / "app/exports_v2/render.py"
    subprocess.run(
        [BUNDLED, str(renderer), "pptx", str(source), str(tmp_path / "peer.pptx")], check=True
    )
    subprocess.run(
        [
            BUNDLED,
            "-c",
            "from pptx import Presentation;import sys;p=Presentation(sys.argv[1]);cs=[s.chart for sl in p.slides for s in sl.shapes if s.has_chart];assert len(cs)==1;assert list(cs[0].series[0].values)==[1704.4705853357,4585.02366];assert len(p.slides)==6",
            str(tmp_path / "peer.pptx"),
        ],
        check=True,
    )
    payload = dict(
        schema_version="annual-diff-v1",
        result_id="annual",
        left_source={"report_year": 2024},
        right_source={"report_year": 2025},
        topics=[
            dict(
                topic=t,
                program_label="comparison_required",
                explanation="已保存解释" + t,
                left={"evidence_refs": []},
                right={"evidence_refs": []},
            )
            for t in ("经营风险", "主要业务", "研发")
        ],
    )
    ref = dict(domain="annual_diff_v1", id="annual", revision=1, payload_sha256=digest(payload))
    data = project(ref, dict(snapshot=payload, display_status="stale"))
    source.write_text(json.dumps(data, ensure_ascii=False))
    subprocess.run(
        [BUNDLED, str(renderer), "pptx", str(source), str(tmp_path / "annual.pptx")], check=True
    )
    subprocess.run(
        [
            BUNDLED,
            "-c",
            "from pptx import Presentation;import sys;p=Presentation(sys.argv[1]);assert len(p.slides)==7;assert not any(s.has_chart for sl in p.slides for s in sl.shapes);text=' '.join(s.text for sl in p.slides for s in sl.shapes if s.has_text_frame);assert all('已保存解释'+t in text for t in ('经营风险','主要业务','研发'));assert '原快照未生成' not in text",
            str(tmp_path / "annual.pptx"),
        ],
        check=True,
    )


@pytest.mark.parametrize("domain", ["checkup_v1", "template_run_v1"])
def test_checkup_rules_and_saved_findings_present_without_financial_invention(tmp_path, domain):
    from pathlib import Path

    payload = dict(
        schema_version="checkup-v1",
        id="checkup",
        candidate_view=True,
        rules=[
            dict(rule_id=k, observation=v, status="candidate_observation", reason=None, unit=u)
            for k, v, u in [
                ("income_profit_divergence", "direction_diverges", "DIRECTION"),
                ("cash_profit_divergence", None, "DIRECTION"),
                ("debt_asset_change", "0.178119", "PERCENTAGE_POINTS"),
            ]
        ],
        findings=[dict(kind="model_interpretation", text="保存时的待审解释，不产生新结论。")],
    )
    if domain == "template_run_v1":
        payload["schema_version"] = "template-run-v1"
        payload["run_id"] = payload.pop("id")
        payload["checkup_rules"] = payload.pop("rules")
    ref = dict(domain=domain, id="checkup", revision=1, payload_sha256=digest(payload))
    data = project(ref, dict(snapshot=payload, display_status="stale"))
    assert data["chart"] is None
    assert len([e for e in data["evidence"] if e.get("kind") == "saved_checkup_rule"]) == 3
    assert "保存时的待审解释" in next(
        r["value"] for r in data["overview"] if r["field"] == "interpretation"
    )
    source = tmp_path / "checkup.json"
    source.write_text(json.dumps(data, ensure_ascii=False))
    renderer = Path(__file__).resolve().parents[1] / "app/exports_v2/render.py"
    subprocess.run(
        [BUNDLED, str(renderer), "pptx", str(source), str(tmp_path / "checkup.pptx")], check=True
    )
    subprocess.run(
        [
            BUNDLED,
            "-c",
            "from pptx import Presentation;import sys;p=Presentation(sys.argv[1]);text=' '.join(s.text for sl in p.slides for s in sl.shapes if s.has_text_frame);assert all(v in text for v in ('收入与利润方向','现金流与利润方向','资产负债率变化','0.178119','数据不足','保存时的待审解释','stale'));assert not any(s.has_chart for sl in p.slides for s in sl.shapes)",
            str(tmp_path / "checkup.pptx"),
        ],
        check=True,
    )


def test_year_trend_does_not_mix_quarter_and_full_year():
    resolved, _ = fixture()
    points = deepcopy(resolved["snapshot"]["comparisons"][0]["points"])
    points[1]["company_id"] = "a"
    points[1]["time"] = dict(kind="duration", period_start="2024-01-01", period_end="2024-12-31")
    payload = dict(schema_version="showcase-report-v2", report_id="trend", revision=1, cells=points)
    ref = dict(domain="showcase_report_v2", id="trend", revision=1, payload_sha256=digest(payload))
    resolved["snapshot"] = payload
    assert project(ref, resolved)["chart"]["kind"] == "line"
    points[1]["time"]["period_end"] = "2024-03-31"
    assert project({**ref, "payload_sha256": digest(payload)}, resolved)["chart"] is None


@pytest.mark.parametrize(
    "domain,schema,id_key",
    [
        ("chart_report_v1", "chart-report-v1", "report_id"),
        ("template_run_v1", "template-run-v1", "run_id"),
    ],
)
def test_chart_and_template_domain_contract(domain, schema, id_key):
    resolved, _ = fixture()
    points = deepcopy(resolved["snapshot"]["comparisons"][0]["points"])
    points[1]["company_id"] = "a"
    points[1]["time"] = dict(kind="duration", period_start="2024-01-01", period_end="2024-12-31")
    payload = dict(
        schema_version=schema,
        financial_points=points,
        selected_sources=[],
        checkup_rules=[
            dict(rule_id="cash_profit_divergence", observation=None, status="insufficient")
        ],
        findings=[],
        interpretation="已保存待审解释",
        **{id_key: "new-domain"},
    )
    resolved["snapshot"] = payload
    ref = dict(domain=domain, id="new-domain", revision=1, payload_sha256=digest(payload))
    result = project(ref, resolved)
    assert len(result["financial"]) == 2 and result["chart"]["kind"] == "line"
    assert any(e.get("kind") == "saved_checkup_rule" for e in result["evidence"])
    assert (
        next(r["value"] for r in result["overview"] if r["field"] == "interpretation")
        == "已保存待审解释"
    )
    with pytest.raises(ValueError, match="resolved_revision_mismatch"):
        project({**ref, "revision": 2}, resolved)
    with pytest.raises(ValueError, match="resolved_domain_or_id_mismatch"):
        project({**ref, "id": "other"}, resolved)
