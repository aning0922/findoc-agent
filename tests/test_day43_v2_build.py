from copy import deepcopy
import hashlib
import json
from pathlib import Path
from collections.abc import Mapping
from typing import Any
from pymilvus import MilvusClient
import pytest

from app.rag.ingest import build_versioned_export_rows, load_versioned_jsonl, write_versioned_jsonl
from app.rag.parse.models import DocChunk
from app.rag.store import count_rows, ensure_document_collection
from app.rag.retriever import (
    Retriever,
    SearchFilters,
    TrustedContext,
    build_filter_expression,
)
from experiments.day43_compare_retrieval import (
    LegacyComparisonStore,
    adapt_filter_for_legacy,
    evaluate_question_set_with_retriever,
    evaluate_question_with_retriever,
)
from experiments.day43_config import RealDocumentConfig

from experiments.day43_build_v2 import DocumentJsonlBuildResult, build_document_jsonl
from experiments.day43_load_v2_collection import (
    DocumentCollectionLoadResult,
    V2CollectionBuildResult,
    load_document_into_collection,
    validate_v2_collection_contract,
)

from experiments.day43_manifest import (
    build_v2_manifest,
    load_v2_manifest,
    write_v2_manifest,
)
from experiments.day43_migrate_ground_truth import migrate_ground_truth


def test_build_versioned_export_rows_adds_identity_without_vector() -> None:
    """验证导出阶段从外部注入可信身份，不修改 DocChunk，也不提前生成 vector。"""
    chunk: DocChunk = DocChunk(
        text="主营业务收入构成\n业务 | 收入占比\n显示器件 | 81.34%",
        page=19,
        type="table",
        source_file="data/京东方A 2025年报.pdf",
        table_md="原始 HTML",
        section="第三节 管理层讨论与分析",
        chunk_id="stable-table-id",
    )
    original_chunk = chunk.model_dump()
    rows = build_versioned_export_rows(
        [chunk],
        workspace_id="demo-financial-reports",
        document_id="demo-financial-reports:boe-a-2025-annual-report",
        data_version="day43_data_v2",
    )
    assert len(rows) == 1
    assert rows[0]["text"] == "主营业务收入构成\n业务 | 收入占比\n显示器件 | 81.34%"
    assert rows[0]["page"] == 19
    assert rows[0]["type"] == "table"
    assert rows[0]["source_file"] == "data/京东方A 2025年报.pdf"
    assert rows[0]["table_md"] == "原始 HTML"
    assert rows[0]["section"] == "第三节 管理层讨论与分析"
    assert rows[0]["chunk_id"] == "stable-table-id"
    assert rows[0]["workspace_id"] == "demo-financial-reports"
    assert rows[0]["document_id"] == "demo-financial-reports:boe-a-2025-annual-report"
    assert rows[0]["data_version"] == "day43_data_v2"
    assert chunk.model_dump() == original_chunk
    assert "vector" not in rows[0]


def test_build_versioned_export_rows_rejects_empty_chunk_id() -> None:
    """验证导出阶段拒绝空 chunk_id。"""
    chunk: DocChunk = DocChunk(
        text="主营业务收入构成\n业务 | 收入占比\n显示器件 | 81.34%",
        page=19,
        type="table",
        source_file="data/京东方A 2025年报.pdf",
        table_md="原始 HTML",
        section="第三节 管理层讨论与分析",
        chunk_id="",
    )
    with pytest.raises(ValueError) as exc_info:
        build_versioned_export_rows(
            [chunk],
            workspace_id="demo-financial-reports",
            document_id="demo-financial-reports:boe-a-2025-annual-report",
            data_version="day43_data_v2",
        )
    message = str(exc_info.value)
    assert "chunks[0]" in message
    assert "chunk_id" in message


def test_build_versioned_export_rows_rejects_duplicate_chunk_id() -> None:
    """验证同一文档内重复 chunk_id 在导出 JSONL 前被拒绝，并能定位第二个重复块。"""
    chunks: list[DocChunk] = []
    chunks.append(
        DocChunk(
            text="主营业务收入构成\n业务 | 收入占比\n显示器件 | 81.34%",
            page=19,
            type="table",
            source_file="data/京东方A 2025年报.pdf",
            table_md="原始 HTML",
            section="第三节 管理层讨论与分析",
            chunk_id="stable-table-id",
        )
    )
    chunks.append(
        DocChunk(
            text="另一条内容不同但错误复用了相同 ID 的表格",
            page=19,
            type="table",
            source_file="data/京东方A 2025年报.pdf",
            table_md="原始 HTML",
            section="第三节 管理层讨论与分析",
            chunk_id="stable-table-id",
        )
    )
    with pytest.raises(ValueError) as exc_info:
        build_versioned_export_rows(
            chunks,
            workspace_id="demo-financial-reports",
            document_id="demo-financial-reports:boe-a-2025-annual-report",
            data_version="day43_data_v2",
        )
    message = str(exc_info.value)
    assert "chunks[1]" in message
    assert "chunk_id" in message
    assert "重复" in message


def test_write_versioned_jsonl_writes_deterministic_one_line_records(tmp_path: Path) -> None:
    """验证相同 rows 生成相同字节的一行式 UTF-8 JSONL，并返回准确摘要。"""
    out_path = tmp_path / "first.jsonl"
    second_path = tmp_path / "second.jsonl"

    rows = [
        {
            "text": "有效中文正文",
            "page": 1,
            "table_md": None,
            "chunk_id": "chunk-1",
        },
        {
            "text": "业务 | 收入占比\n显示器件 | 81.34%",
            "page": 19,
            "table_md": "<table><tr><td>显示器件</td></tr></table>",
            "chunk_id": "chunk-2",
        },
    ]
    result = write_versioned_jsonl(out_path, rows)
    result2 = write_versioned_jsonl(second_path, rows)
    assert out_path.read_text(encoding="utf-8") == second_path.read_text(encoding="utf-8")
    assert result.sha256 == result2.sha256
    assert result.row_count == 2
    assert result.byte_size == len(out_path.read_bytes())
    assert result.sha256 == hashlib.sha256(out_path.read_bytes()).hexdigest()
    assert len(out_path.read_text(encoding="utf-8").splitlines()) == 2
    loaded_rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines()]
    assert loaded_rows == rows
    assert "有效中文正文" in out_path.read_text(encoding="utf-8")


def test_write_versioned_jsonl_preserves_existing_file_when_serialization_fails(
    tmp_path: Path,
) -> None:
    """验证写入失败时保留原文件内容，不创建临时文件。"""
    out_path = tmp_path / "document.jsonl"
    original_bytes = b'{"status":"original-complete"}\n'
    out_path.write_bytes(original_bytes)
    rows = [
        {"text": "第一条合法数据", "chunk_id": "chunk-1"},
        {"text": object(), "chunk_id": "chunk-2"},
    ]

    with pytest.raises(TypeError):
        write_versioned_jsonl(out_path, rows)
    assert out_path.read_bytes() == original_bytes
    assert list(tmp_path.glob(".document.jsonl.*.tmp")) == []


def test_build_document_jsonl_runs_parse_chunk_identity_and_atomic_write(tmp_path: Path) -> None:
    """验证单文档按 parse→chunk→身份注入→原子 JSONL 的生产顺序完成构建。"""
    input_dir = tmp_path / "mineru_input"
    output_dir = tmp_path / "day43_data_v2"

    input_dir.mkdir()

    content_file = input_dir / "mini_content_list.json"
    output_jsonl = output_dir / "京东方A 2025年报_chunks.jsonl"

    raw_table_body = (
        "<table>"
        "<tr><th>业务</th><th>占比</th></tr>"
        "<tr><td>显示器件</td><td>81.34%</td></tr>"
        "</table>"
    )
    raw_elements = [
        {
            "type": "text",
            "text": "经营情况",
            "text_level": 1,
            "page_idx": 1,
        },
        {
            "type": "text",
            "text": "营业收入同比增长。",
            "page_idx": 1,
        },
        {
            "type": "table",
            "table_caption": ["收入构成"],
            "table_body": raw_table_body,
            "page_idx": 1,
        },
    ]

    content_file.write_text(
        json.dumps(raw_elements, ensure_ascii=False),
        encoding="utf-8",
    )
    assert content_file.is_file()
    assert not output_dir.exists()
    assert not output_jsonl.exists()

    result = build_document_jsonl(
        source_file="data/京东方A 2025年报.pdf",
        document_id="demo-financial-reports:boe-a-2025-annual-report",
        content_list_file=content_file,
        output_jsonl=output_jsonl,
        workspace_id="demo-financial-reports",
        data_version="day43_data_v2",
    )
    assert output_dir.is_dir()
    assert output_jsonl.is_file()

    assert result.source_file == "data/京东方A 2025年报.pdf"
    assert result.document_id == ("demo-financial-reports:boe-a-2025-annual-report")
    assert result.content_list_file == content_file
    assert result.output_jsonl == output_jsonl
    assert result.parsed_block_count == 3
    assert result.final_chunk_count == 2
    assert result.skipped_element_count == 0
    assert result.byte_size == len(output_jsonl.read_bytes())
    assert result.sha256 == hashlib.sha256(output_jsonl.read_bytes()).hexdigest()
    jsonl_lines = [
        line for line in output_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(jsonl_lines) == 2
    rows = [json.loads(line) for line in jsonl_lines]
    paragraph_row = next(row for row in rows if row["type"] == "paragraph")
    table_row = next(row for row in rows if row["type"] == "table")
    chunk_ids = [row["chunk_id"] for row in rows]

    assert all(isinstance(chunk_id, str) and chunk_id.strip() for chunk_id in chunk_ids)
    assert len(chunk_ids) == len(set(chunk_ids))
    assert all(row["workspace_id"] == "demo-financial-reports" for row in rows)
    assert all(
        row["document_id"] == "demo-financial-reports:boe-a-2025-annual-report" for row in rows
    )
    assert all(row["data_version"] == "day43_data_v2" for row in rows)
    assert all(row["source_file"] == "data/京东方A 2025年报.pdf" for row in rows)
    assert all(row["page"] == 2 for row in rows)
    assert all(row["section"] == "经营情况" for row in rows)
    assert all("vector" not in row for row in rows)
    assert paragraph_row["text"] == "营业收入同比增长。"
    assert paragraph_row["table_md"] is None
    assert table_row["text"] == ("收入构成\n业务 | 占比\n显示器件 | 81.34%")
    assert "<table" not in table_row["text"].lower()
    assert "<tr" not in table_row["text"].lower()
    assert "<td" not in table_row["text"].lower()
    assert "<th" not in table_row["text"].lower()
    assert table_row["table_md"] == raw_table_body


def test_load_versioned_jsonl_validates_and_returns_published_rows(tmp_path: Path) -> None:
    """验证已发布的合法 v2 JSONL 能按原顺序读取，且内容和身份保持不变。"""
    chunks = [
        DocChunk(
            text="营业收入同比增长。",
            page=2,
            type="paragraph",
            source_file="data/京东方A 2025年报.pdf",
            table_md=None,
            section="经营情况",
            chunk_id="paragraph-id",
        ),
        DocChunk(
            text="收入构成\n业务 | 占比\n显示器件 | 81.34%",
            page=2,
            type="table",
            source_file="data/京东方A 2025年报.pdf",
            table_md=(
                "<table>"
                "<tr><th>业务</th><th>占比</th></tr>"
                "<tr><td>显示器件</td><td>81.34%</td></tr>"
                "</table>"
            ),
            section="经营情况",
            chunk_id="table-id",
        ),
    ]
    export_rows = build_versioned_export_rows(
        chunks,
        workspace_id="demo-financial-reports",
        document_id="demo-financial-reports:boe-a-2025-annual-report",
        data_version="day43_data_v2",
    )
    output_path = tmp_path / "boe_chunks.jsonl"

    write_versioned_jsonl(
        output_path,
        export_rows,
    )

    loaded_rows = load_versioned_jsonl(
        output_path,
        expected_workspace_id="demo-financial-reports",
        expected_document_id="demo-financial-reports:boe-a-2025-annual-report",
        expected_source_file="data/京东方A 2025年报.pdf",
        expected_data_version="day43_data_v2",
    )
    assert loaded_rows == export_rows
    assert len(loaded_rows) == 2
    assert [row["type"] for row in loaded_rows] == ["paragraph", "table"]
    assert all("vector" not in row for row in loaded_rows)
    table_row = loaded_rows[1]

    assert "显示器件" in table_row["text"]
    assert "81.34%" in table_row["text"]
    assert "<table" not in table_row["text"].lower()
    assert table_row["table_md"] == chunks[1].table_md


def test_load_versioned_jsonl_rejects_document_identity_mismatch_with_line_number(
    tmp_path: Path,
) -> None:
    """验证 document_id 与可信配置不一致时，在向量化前按文件和行号定位失败。"""
    wrong_row = {
        "text": "营业收入同比增长。",
        "page": 2,
        "type": "paragraph",
        "source_file": "data/京东方A 2025年报.pdf",
        "table_md": None,
        "section": "经营情况",
        "chunk_id": "paragraph-id",
        "workspace_id": "demo-financial-reports",
        "document_id": "demo-financial-reports:wrong-document",
        "data_version": "day43_data_v2",
    }

    output_path = tmp_path / "wrong_identity.jsonl"

    write_versioned_jsonl(
        output_path,
        [wrong_row],
    )
    with pytest.raises(ValueError) as exc_info:
        load_versioned_jsonl(
            output_path,
            expected_workspace_id="demo-financial-reports",
            expected_document_id=("demo-financial-reports:boe-a-2025-annual-report"),
            expected_source_file="data/京东方A 2025年报.pdf",
            expected_data_version="day43_data_v2",
        )
    message = str(exc_info.value)
    assert str(output_path) in message
    assert "第 1 行" in message
    assert "document_id" in message
    assert "wrong-document" in message
    assert "boe-a-2025-annual-report" in message


def fake_embed(texts: list[str]) -> list[list[float]]:
    """根据文本是否包含表格关键词生成确定性的五维测试向量。"""
    return [
        [
            float("显示器件" in text),
            float("营业收入" in text),
            0.0,
            0.0,
            1.0,
        ]
        for text in texts
    ]


def test_load_document_into_collection_embeds_and_replaces_validated_rows(tmp_path: Path) -> None:
    """验证已通过 Gate 的 JSONL rows 能保持向量、身份和 chunk_id 对齐后按文档写库。"""
    db_path = tmp_path / "day43_v2_collection_test.db"
    collection_name = "day43_v2_collection_test"
    client = MilvusClient(str(db_path))
    try:
        ensure_document_collection(client, collection_name, dim=5)
        assert client.has_collection(collection_name)
        assert count_rows(client, collection_name) == 0

        document_config = RealDocumentConfig(
            source_file="data/京东方A 2025年报.pdf",
            document_id=("demo-financial-reports:boe-a-2025-annual-report"),
            content_list_file=tmp_path / "unused_content_list.json",
            output_jsonl=tmp_path / "boe_chunks.jsonl",
        )
        chunks = [
            DocChunk(
                text="营业收入同比增长。",
                page=2,
                type="paragraph",
                source_file=document_config["source_file"],
                table_md=None,
                section="经营情况",
                chunk_id="paragraph-id",
            ),
            DocChunk(
                text=("收入构成\n业务 | 占比\n显示器件 | 81.34%"),
                page=2,
                type="table",
                source_file=document_config["source_file"],
                table_md=(
                    "<table>"
                    "<tr><th>业务</th><th>占比</th></tr>"
                    "<tr><td>显示器件</td><td>81.34%</td></tr>"
                    "</table>"
                ),
                section="经营情况",
                chunk_id="table-id",
            ),
        ]
        jsonl_rows = build_versioned_export_rows(
            chunks,
            workspace_id="demo-financial-reports",
            document_id=document_config["document_id"],
            data_version="day43_data_v2",
        )
        assert all("vector" not in row for row in jsonl_rows)

        result = load_document_into_collection(
            client=client,
            collection_name=collection_name,
            document_config=document_config,
            jsonl_rows=jsonl_rows,
            embedder=fake_embed,
            expected_vector_dim=5,
        )
        assert result.source_file == document_config["source_file"]
        assert result.document_id == document_config["document_id"]
        assert result.jsonl_path == document_config["output_jsonl"]
        assert result.jsonl_row_count == 2
        assert result.embedded_row_count == 2
        assert result.final_document_row_count == 2
        document_filter = "document_id == " + json.dumps(
            document_config["document_id"],
            ensure_ascii=False,
        )

        stored_rows = client.query(
            collection_name=collection_name,
            filter=document_filter,
            output_fields=[
                "chunk_id",
                "text",
                "page",
                "type",
                "source_file",
                "table_md",
                "section",
                "workspace_id",
                "document_id",
                "data_version",
            ],
        )

        assert {row["chunk_id"] for row in stored_rows} == {
            "paragraph-id",
            "table-id",
        }

        stored_by_id = {row["chunk_id"]: row for row in stored_rows}
        assert all(row["workspace_id"] == "demo-financial-reports" for row in stored_rows)

        assert all(row["document_id"] == document_config["document_id"] for row in stored_rows)

        assert all(row["source_file"] == document_config["source_file"] for row in stored_rows)

        assert all(row["data_version"] == "day43_data_v2" for row in stored_rows)

        stored_paragraph = stored_by_id["paragraph-id"]

        assert stored_paragraph["text"] == "营业收入同比增长。"
        assert stored_paragraph["type"] == "paragraph"
        assert stored_paragraph["table_md"] is None
        assert stored_paragraph["page"] == 2
        assert stored_paragraph["section"] == "经营情况"

        stored_table = stored_by_id["table-id"]

        assert "显示器件" in stored_table["text"]
        assert "81.34%" in stored_table["text"]
        assert stored_table["type"] == "table"
        assert stored_table["table_md"] == chunks[1].table_md
        assert stored_table["page"] == 2
        assert stored_table["section"] == "经营情况"

        assert count_rows(client, collection_name) == 2
    finally:
        client.close()


def test_load_document_into_collection_preserves_other_document(tmp_path: Path) -> None:
    """验证第二份文档按自身 document_id 统计和替换，同时第一份文档保持完整。"""
    db_path = tmp_path / "day43_multi_document_test.db"
    collection_name = "day43_multi_document_test"

    document_a = RealDocumentConfig(
        source_file="data/京东方A 2025年报.pdf",
        document_id=("demo-financial-reports:boe-a-2025-annual-report"),
        content_list_file=tmp_path / "unused_boe_content_list.json",
        output_jsonl=tmp_path / "boe_chunks.jsonl",
    )

    chunks_a = [
        DocChunk(
            text="京东方营业收入同比增长。",
            page=2,
            type="paragraph",
            source_file=document_a["source_file"],
            table_md=None,
            section="经营情况",
            chunk_id="boe-paragraph-1",
        ),
        DocChunk(
            text="京东方显示器件业务保持增长。",
            page=3,
            type="paragraph",
            source_file=document_a["source_file"],
            table_md=None,
            section="经营情况",
            chunk_id="boe-paragraph-2",
        ),
    ]

    rows_a = build_versioned_export_rows(
        chunks_a,
        workspace_id="demo-financial-reports",
        document_id=document_a["document_id"],
        data_version="day43_data_v2",
    )

    rows_a = build_versioned_export_rows(
        chunks_a,
        workspace_id="demo-financial-reports",
        document_id=document_a["document_id"],
        data_version="day43_data_v2",
    )

    document_b = RealDocumentConfig(
        source_file="data/贵州茅台2025年报.pdf",
        document_id=("demo-financial-reports:kweichow-moutai-2025-annual-report"),
        content_list_file=tmp_path / "unused_moutai_content_list.json",
        output_jsonl=tmp_path / "moutai_chunks.jsonl",
    )

    chunks_b = [
        DocChunk(
            text="贵州茅台主要从事茅台酒及系列酒的生产与销售。",
            page=8,
            type="paragraph",
            source_file=document_b["source_file"],
            table_md=None,
            section="公司业务概要",
            chunk_id="moutai-paragraph-1",
        ),
    ]

    rows_b = build_versioned_export_rows(
        chunks_b,
        workspace_id="demo-financial-reports",
        document_id=document_b["document_id"],
        data_version="day43_data_v2",
    )

    client = MilvusClient(str(db_path))

    try:
        ensure_document_collection(client, collection_name, dim=5)
        result_a = load_document_into_collection(
            client=client,
            collection_name=collection_name,
            document_config=document_a,
            jsonl_rows=rows_a,
            embedder=fake_embed,
            expected_vector_dim=5,
        )
        assert result_a.jsonl_row_count == 2
        assert result_a.embedded_row_count == 2
        assert result_a.final_document_row_count == 2
        assert count_rows(client, collection_name) == 2

        expected_a_ids = {
            "boe-paragraph-1",
            "boe-paragraph-2",
        }

        result_b = load_document_into_collection(
            client=client,
            collection_name=collection_name,
            document_config=document_b,
            jsonl_rows=rows_b,
            embedder=fake_embed,
            expected_vector_dim=5,
        )

        assert result_b.jsonl_row_count == 1
        assert result_b.embedded_row_count == 1
        assert result_b.final_document_row_count == 1

        assert count_rows(client, collection_name) == 3

        filter_a = "document_id == " + json.dumps(
            document_a["document_id"],
            ensure_ascii=False,
        )

        stored_a = client.query(
            collection_name=collection_name,
            filter=filter_a,
            output_fields=[
                "chunk_id",
                "text",
                "document_id",
                "source_file",
                "workspace_id",
            ],
        )

        assert len(stored_a) == 2
        assert {row["chunk_id"] for row in stored_a} == expected_a_ids
        assert all(row["document_id"] == document_a["document_id"] for row in stored_a)
        assert all(row["source_file"] == document_a["source_file"] for row in stored_a)

        filter_b = "document_id == " + json.dumps(
            document_b["document_id"],
            ensure_ascii=False,
        )

        stored_b = client.query(
            collection_name=collection_name,
            filter=filter_b,
            output_fields=[
                "chunk_id",
                "text",
                "document_id",
                "source_file",
                "workspace_id",
            ],
        )

        assert len(stored_b) == 1
        assert {row["chunk_id"] for row in stored_b} == {
            "moutai-paragraph-1",
        }
        assert stored_b[0]["document_id"] == document_b["document_id"]
        assert stored_b[0]["source_file"] == document_b["source_file"]

        assert expected_a_ids.isdisjoint({row["chunk_id"] for row in stored_b})

    finally:
        client.close()


def test_validate_v2_collection_contract_accepts_document_collection(
    tmp_path: Path,
) -> None:
    """验证标准 document collection 满足字符串主键、向量维度、动态字段和 COSINE 合同。"""

    client = MilvusClient(str(tmp_path / "day43_collection_contract.db"))
    collection_name = "day43_collection_contract"

    try:
        ensure_document_collection(
            client,
            collection_name,
            dim=5,
        )

        validate_v2_collection_contract(
            client,
            collection_name,
            expected_vector_dim=5,
            expected_metric_type="COSINE",
        )
    finally:
        client.close()


def test_build_v2_manifest_joins_document_results_and_preserves_audit_facts() -> None:
    """验证 manifest 按稳定文档身份关联 JSONL 与 collection 构建结果，并保留文件指纹、实际行数、legacy 保护结果和质量统计"""
    jsonl_results = [
        DocumentJsonlBuildResult(
            source_file="data/成都华微电子2025年报.pdf",
            document_id=("demo-financial-reports:chengdu-huawei-2025-annual-report"),
            content_list_file=Path(
                "mineru_out/成都华微电子2025年报/auto/成都华微电子2025年报_content_list.json"
            ),
            output_jsonl=Path("data/day43_data_v2/成都华微电子2025年报_chunks.jsonl"),
            parsed_block_count=3268,
            final_chunk_count=2436,
            skipped_element_count=520,
            byte_size=1962561,
            sha256=("1f2ebfb4618c6daeab37bbe77526684f3004f94445f09a90e92a3ec4b6da6c19"),
        ),
        DocumentJsonlBuildResult(
            source_file="data/贵州茅台2025年报.pdf",
            document_id=("demo-financial-reports:kweichow-moutai-2025-annual-report"),
            content_list_file=Path(
                "mineru_out/贵州茅台2025年报/auto/贵州茅台2025年报_content_list.json"
            ),
            output_jsonl=Path("data/day43_data_v2/贵州茅台2025年报_chunks.jsonl"),
            parsed_block_count=2057,
            final_chunk_count=1504,
            skipped_element_count=329,
            byte_size=1477317,
            sha256=("530660e3246ff01d36cd1e38fd5ac398da9951451e15bec91282014760669014"),
        ),
    ]

    collection_result = V2CollectionBuildResult(
        collection_name="findoc_day43_v2",
        embedding_model="BAAI/bge-m3",
        vector_dim=1024,
        metric_type="COSINE",
        expected_total_row_count=3940,
        actual_collection_row_count=3940,
        global_chunk_id_count=3940,
        legacy_row_count_before=7451,
        legacy_row_count_after=7451,
        document_results=(
            DocumentCollectionLoadResult(
                source_file="data/贵州茅台2025年报.pdf",
                document_id=("demo-financial-reports:kweichow-moutai-2025-annual-report"),
                jsonl_path=Path("data/day43_data_v2/贵州茅台2025年报_chunks.jsonl"),
                jsonl_row_count=1504,
                embedded_row_count=1504,
                final_document_row_count=1504,
            ),
            DocumentCollectionLoadResult(
                source_file="data/成都华微电子2025年报.pdf",
                document_id=("demo-financial-reports:chengdu-huawei-2025-annual-report"),
                jsonl_path=Path("data/day43_data_v2/成都华微电子2025年报_chunks.jsonl"),
                jsonl_row_count=2436,
                embedded_row_count=2436,
                final_document_row_count=2436,
            ),
        ),
    )

    smoke_reports: list[dict[str, object]] = [
        {
            "source_file": "data/成都华微电子2025年报.pdf",
            "passed": True,
            "degraded_table_text_count": 0,
            "html_in_table_text_count": 0,
            "missing_table_md_count": 0,
            "table_md_mismatch_count": 0,
            "section_pollution_count": 0,
        },
        {
            "source_file": "data/贵州茅台2025年报.pdf",
            "passed": True,
            "degraded_table_text_count": 0,
            "html_in_table_text_count": 0,
            "missing_table_md_count": 0,
            "table_md_mismatch_count": 0,
            "section_pollution_count": 0,
        },
    ]

    manifest = build_v2_manifest(
        jsonl_results=jsonl_results,
        collection_result=collection_result,
        smoke_reports=smoke_reports,
        build_id="day43_data_v2",
        workspace_id="demo-financial-reports",
        database_path=Path("data/milvus.db"),
        legacy_collection_name="findoc",
    )

    assert manifest["manifest_schema_version"] == "1.0"
    assert manifest["build_id"] == "day43_data_v2"
    assert manifest["workspace_id"] == "demo-financial-reports"

    assert manifest["embedding"] == {
        "model_name": "BAAI/bge-m3",
        "vector_dim": 1024,
    }

    assert manifest["retrieval_contract"] == {
        "metric_type": "COSINE",
    }

    assert manifest["collection"] == {
        "database_path": "data/milvus.db",
        "collection_name": "findoc_day43_v2",
        "expected_row_count": 3940,
        "actual_row_count": 3940,
    }

    assert manifest["legacy_preservation"] == {
        "collection_name": "findoc",
        "row_count_before": 7451,
        "row_count_after": 7451,
        "preserved": True,
    }

    assert len(manifest["documents"]) == 2

    documents_by_id = {document["document_id"]: document for document in manifest["documents"]}

    chengdu = documents_by_id["demo-financial-reports:chengdu-huawei-2025-annual-report"]
    assert chengdu == {
        "source_file": "data/成都华微电子2025年报.pdf",
        "content_list_file": (
            "mineru_out/成都华微电子2025年报/auto/成都华微电子2025年报_content_list.json"
        ),
        "output_jsonl": ("data/day43_data_v2/成都华微电子2025年报_chunks.jsonl"),
        "document_id": ("demo-financial-reports:chengdu-huawei-2025-annual-report"),
        "jsonl_row_count": 2436,
        "embedded_row_count": 2436,
        "final_document_row_count": 2436,
        "jsonl_byte_size": 1962561,
        "jsonl_sha256": ("1f2ebfb4618c6daeab37bbe77526684f3004f94445f09a90e92a3ec4b6da6c19"),
    }

    moutai = documents_by_id["demo-financial-reports:kweichow-moutai-2025-annual-report"]
    assert moutai["source_file"] == "data/贵州茅台2025年报.pdf"
    assert moutai["jsonl_row_count"] == 1504
    assert moutai["embedded_row_count"] == 1504
    assert moutai["final_document_row_count"] == 1504
    assert moutai["jsonl_byte_size"] == 1477317
    assert moutai["jsonl_sha256"] == (
        "530660e3246ff01d36cd1e38fd5ac398da9951451e15bec91282014760669014"
    )

    assert manifest["quality_checks"] == {
        "global_chunk_ids_unique": True,
        "document_ids_unique": True,
        "degraded_table_text_count": 0,
        "html_in_table_text_count": 0,
        "missing_table_md_count": 0,
        "table_md_mismatch_count": 0,
        "section_pollution_count": 0,
    }


def test_write_v2_manifest_writes_deterministic_atomic_json(
    tmp_path: Path,
) -> None:
    """验证相同 manifest 生成相同 UTF-8 JSON 字节、摘要和完整文件。"""
    first_path = tmp_path / "first" / "manifest.json"
    second_path = tmp_path / "second" / "manifest.json"

    manifest = {
        "manifest_schema_version": "1.0",
        "build_id": "day43_data_v2",
        "workspace_id": "demo-financial-reports",
        "collection": {
            "collection_name": "findoc_day43_v2",
            "expected_row_count": 5269,
            "actual_row_count": 5269,
        },
        "documents": [
            {
                "source_file": "data/贵州茅台2025年报.pdf",
                "document_id": ("demo-financial-reports:kweichow-moutai-2025-annual-report"),
                "jsonl_row_count": 1504,
            }
        ],
    }

    first_result = write_v2_manifest(
        first_path,
        manifest,
    )
    second_result = write_v2_manifest(
        second_path,
        manifest,
    )

    first_bytes = first_path.read_bytes()
    second_bytes = second_path.read_bytes()

    assert first_path.is_file()
    assert second_path.is_file()
    assert first_bytes == second_bytes

    assert first_result.path == first_path
    assert second_result.path == second_path
    assert first_result.byte_size == len(first_bytes)
    assert second_result.byte_size == len(second_bytes)
    assert first_result.sha256 == hashlib.sha256(first_bytes).hexdigest()
    assert second_result.sha256 == hashlib.sha256(second_bytes).hexdigest()
    assert first_result.sha256 == second_result.sha256

    assert json.loads(first_path.read_text(encoding="utf-8")) == manifest
    assert "贵州茅台2025年报.pdf" in first_path.read_text(encoding="utf-8")
    assert first_bytes.endswith(b"\n")
    assert list(first_path.parent.glob(".manifest.json.*.tmp")) == []
    assert list(second_path.parent.glob(".manifest.json.*.tmp")) == []


def test_write_v2_manifest_preserves_existing_file_when_serialization_fails(
    tmp_path: Path,
) -> None:
    """验证新 manifest 无法序列化时保留原文件，并且不残留临时文件。"""
    manifest_path = tmp_path / "manifest.json"
    original_bytes = b'{"status":"previous-complete-manifest"}\n'
    manifest_path.write_bytes(original_bytes)

    invalid_manifest = {
        "manifest_schema_version": "1.0",
        "build_id": "day43_data_v2",
        "invalid_value": object(),
    }

    with pytest.raises(TypeError):
        write_v2_manifest(
            manifest_path,
            invalid_manifest,
        )

    assert manifest_path.read_bytes() == original_bytes
    assert list(tmp_path.glob(".manifest.json.*.tmp")) == []


def test_load_v2_manifest_recomputes_jsonl_integrity_and_returns_manifest(tmp_path: Path) -> None:
    """验证重新加载 manifest 时会复查当前 JSONL 的身份、行数、字节数和 SHA-256。"""
    document_id = "demo-financial-reports:boe-a-2025-annual-report"
    source_file = "data/京东方A 2025年报.pdf"

    jsonl_path = tmp_path / "data/day43_data_v2" / "京东方A 2025年报_chunks.jsonl"

    manifest_path = tmp_path / "data/day43_data_v2" / "manifest.json"

    rows = [
        {
            "text": "营业收入同比增长。",
            "page": 2,
            "type": "paragraph",
            "source_file": source_file,
            "table_md": None,
            "section": "经营情况",
            "chunk_id": "stable-paragraph-id",
            "workspace_id": "demo-financial-reports",
            "document_id": document_id,
            "data_version": "day43_data_v2",
        }
    ]

    jsonl_write_result = write_versioned_jsonl(
        jsonl_path,
        rows,
    )

    manifest = {
        "manifest_schema_version": "1.0",
        "build_id": "day43_data_v2",
        "workspace_id": "demo-financial-reports",
        "embedding": {
            "model_name": "BAAI/bge-m3",
            "vector_dim": 1024,
        },
        "retrieval_contract": {
            "metric_type": "COSINE",
        },
        "collection": {
            "database_path": "data/milvus.db",
            "collection_name": "findoc_day43_v2",
            "expected_row_count": 1,
            "actual_row_count": 1,
        },
        "legacy_preservation": {
            "collection_name": "findoc",
            "row_count_before": 7451,
            "row_count_after": 7451,
            "preserved": True,
        },
        "documents": [
            {
                "source_file": source_file,
                "content_list_file": (
                    "mineru_out/京东方A 2025年报/auto/京东方A 2025年报_content_list.json"
                ),
                "output_jsonl": ("data/day43_data_v2/京东方A 2025年报_chunks.jsonl"),
                "document_id": document_id,
                "jsonl_row_count": 1,
                "embedded_row_count": 1,
                "final_document_row_count": 1,
                "jsonl_byte_size": jsonl_write_result.byte_size,
                "jsonl_sha256": jsonl_write_result.sha256,
            }
        ],
        "quality_checks": {
            "global_chunk_ids_unique": True,
            "document_ids_unique": True,
            "degraded_table_text_count": 0,
            "html_in_table_text_count": 0,
            "missing_table_md_count": 0,
            "table_md_mismatch_count": 0,
            "section_pollution_count": 0,
        },
    }

    write_v2_manifest(
        manifest_path,
        manifest,
    )

    loaded_manifest = load_v2_manifest(
        manifest_path,
        project_root=tmp_path,
        expected_build_id="day43_data_v2",
        expected_workspace_id="demo-financial-reports",
        expected_collection_name="findoc_day43_v2",
        expected_document_ids={document_id},
    )
    assert loaded_manifest == manifest
    assert loaded_manifest["build_id"] == "day43_data_v2"
    assert loaded_manifest["workspace_id"] == ("demo-financial-reports")
    assert loaded_manifest["collection"]["collection_name"] == ("findoc_day43_v2")
    assert loaded_manifest["documents"][0]["document_id"] == (document_id)
    assert loaded_manifest["documents"][0]["jsonl_row_count"] == 1


def prepare_test_manifest(
    tmp_path: Path,
) -> tuple[Path, Path, str, dict[str, object]]:
    """创建一份合法的最小 v2 JSONL 和对应 manifest，供 loader 测试复用。"""
    manifest_path = tmp_path / "data/day43_data_v2" / "manifest.json"
    jsonl_path = tmp_path / "data/day43_data_v2" / "京东方A 2025年报_chunks.jsonl"
    document_id = "demo-financial-reports:boe-a-2025-annual-report"
    source_file = "data/京东方A 2025年报.pdf"
    rows = [
        {
            "text": "营业收入同比增长。",
            "page": 2,
            "type": "paragraph",
            "source_file": source_file,
            "table_md": None,
            "section": "经营情况",
            "chunk_id": "stable-paragraph-id",
            "workspace_id": "demo-financial-reports",
            "document_id": document_id,
            "data_version": "day43_data_v2",
        }
    ]

    jsonl_write_result = write_versioned_jsonl(
        jsonl_path,
        rows,
    )
    manifest = {
        "manifest_schema_version": "1.0",
        "build_id": "day43_data_v2",
        "workspace_id": "demo-financial-reports",
        "embedding": {
            "model_name": "BAAI/bge-m3",
            "vector_dim": 1024,
        },
        "retrieval_contract": {
            "metric_type": "COSINE",
        },
        "collection": {
            "database_path": "data/milvus.db",
            "collection_name": "findoc_day43_v2",
            "expected_row_count": 1,
            "actual_row_count": 1,
        },
        "legacy_preservation": {
            "collection_name": "findoc",
            "row_count_before": 7451,
            "row_count_after": 7451,
            "preserved": True,
        },
        "documents": [
            {
                "source_file": source_file,
                "content_list_file": (
                    "mineru_out/京东方A 2025年报/auto/京东方A 2025年报_content_list.json"
                ),
                "output_jsonl": ("data/day43_data_v2/京东方A 2025年报_chunks.jsonl"),
                "document_id": document_id,
                "jsonl_row_count": 1,
                "embedded_row_count": 1,
                "final_document_row_count": 1,
                "jsonl_byte_size": jsonl_write_result.byte_size,
                "jsonl_sha256": jsonl_write_result.sha256,
            }
        ],
        "quality_checks": {
            "global_chunk_ids_unique": True,
            "document_ids_unique": True,
            "degraded_table_text_count": 0,
            "html_in_table_text_count": 0,
            "missing_table_md_count": 0,
            "table_md_mismatch_count": 0,
            "section_pollution_count": 0,
        },
    }

    write_v2_manifest(
        manifest_path,
        manifest,
    )
    return (
        manifest_path,
        jsonl_path,
        document_id,
        manifest,
    )


def test_load_v2_manifest_rejects_jsonl_sha256_mismatch(
    tmp_path: Path,
) -> None:
    """验证 JSONL 内容被等长替换后，即使身份和行数不变也会因 SHA-256 不一致被拒绝。"""
    manifest_path, jsonl_path, document_id, _ = prepare_test_manifest(tmp_path)

    changed_rows = [
        {
            "text": "营业收入同比下降。",
            "page": 2,
            "type": "paragraph",
            "source_file": "data/京东方A 2025年报.pdf",
            "table_md": None,
            "section": "经营情况",
            "chunk_id": "stable-paragraph-id",
            "workspace_id": "demo-financial-reports",
            "document_id": document_id,
            "data_version": "day43_data_v2",
        }
    ]

    write_versioned_jsonl(
        jsonl_path,
        changed_rows,
    )

    with pytest.raises(ValueError) as exc_info:
        load_v2_manifest(
            manifest_path,
            project_root=tmp_path,
            expected_build_id="day43_data_v2",
            expected_workspace_id="demo-financial-reports",
            expected_collection_name="findoc_day43_v2",
            expected_document_ids={document_id},
        )

    message = str(exc_info.value)

    assert document_id in message
    assert str(jsonl_path) in message
    assert "SHA-256" in message


def test_migrate_ground_truth_replaces_ids_without_mutating_question_semantics() -> None:
    """验证多证据题按原顺序迁移 ID，无答案题保持为空，且不修改 legacy 输入。"""
    legacy_questions = [
        {
            "case_id": "Q10",
            "query": "最高额度是多少？",
            "category": "cross_company_confusable",
            "answerable": True,
            "relevant_chunk_ids": [
                "old-paragraph",
                "old-table",
            ],
            "source_file": None,
            "ground_truth": "最高额度为50,000万元。",
            "expected_metadata": {
                "old-paragraph": {
                    "source_file": "data/a.pdf",
                    "page": 83,
                    "type": "paragraph",
                },
                "old-table": {
                    "source_file": "data/a.pdf",
                    "page": 83,
                    "type": "table",
                },
            },
        },
        {
            "case_id": "Q5",
            "query": "不存在的数据？",
            "category": "unanswerable",
            "answerable": False,
            "relevant_chunk_ids": [],
            "source_file": None,
            "ground_truth": "没有证据。",
            "expected_metadata": {},
        },
    ]

    original_questions = deepcopy(legacy_questions)

    id_mapping = {
        "old-paragraph": "new-paragraph",
        "old-table": "new-table",
    }

    v2_rows_by_chunk_id = {
        "new-paragraph": {
            "chunk_id": "new-paragraph",
            "source_file": "data/a.pdf",
            "page": 83,
            "type": "paragraph",
            "section": "其他说明",
        },
        "new-table": {
            "chunk_id": "new-table",
            "source_file": "data/a.pdf",
            "page": 83,
            "type": "table",
            "section": "现金管理",
        },
    }

    migrated = migrate_ground_truth(
        legacy_questions=legacy_questions,
        id_mapping=id_mapping,
        v2_rows_by_chunk_id=v2_rows_by_chunk_id,
    )

    assert legacy_questions == original_questions

    assert migrated[0]["relevant_chunk_ids"] == [
        "new-paragraph",
        "new-table",
    ]

    assert migrated[0]["expected_metadata"] == {
        "new-paragraph": {
            "source_file": "data/a.pdf",
            "page": 83,
            "type": "paragraph",
        },
        "new-table": {
            "source_file": "data/a.pdf",
            "page": 83,
            "type": "table",
        },
    }

    for field_name in (
        "case_id",
        "query",
        "category",
        "answerable",
        "source_file",
        "ground_truth",
    ):
        assert migrated[0][field_name] == legacy_questions[0][field_name]

    assert migrated[1] == legacy_questions[1]


def test_legacy_filter_adapter_removes_only_expected_workspace_clause() -> None:
    """验证 legacy 兼容只移除与预期完全一致的 workspace 条件。"""
    expected_workspace_id = "demo-financial-reports"

    valid_filter_expression = build_filter_expression(
        TrustedContext(expected_workspace_id),
    )

    adapted_filter = adapt_filter_for_legacy(
        valid_filter_expression,
        expected_workspace_id=expected_workspace_id,
    )

    assert adapted_filter == ""

    wrong_workspace_expression = build_filter_expression(
        TrustedContext("wrong-workspace"),
    )

    with pytest.raises(ValueError, match="workspace_id"):
        adapt_filter_for_legacy(
            wrong_workspace_expression,
            expected_workspace_id=expected_workspace_id,
        )


def test_legacy_filter_adapter_preserves_source_file_clause() -> None:
    """验证移除 workspace 条件后完整保留 source_file 条件，并拒绝未知条件。"""
    workspace_id = "demo-financial-reports"
    source_file = "data/贵州茅台2025年报.pdf"

    filter_expression = build_filter_expression(
        TrustedContext(workspace_id),
        SearchFilters(source_file=source_file),
    )

    adapted_filter = adapt_filter_for_legacy(
        filter_expression,
        expected_workspace_id=workspace_id,
    )

    assert adapted_filter == (f"source_file == {json.dumps(source_file, ensure_ascii=False)}")

    workspace_clause = f"workspace_id == {json.dumps(workspace_id, ensure_ascii=False)}"
    unknown_filter_expression = (
        f"{workspace_clause} and document_id == {json.dumps('unexpected', ensure_ascii=False)}"
    )

    with pytest.raises(ValueError, match="只允许保留 source_file"):
        adapt_filter_for_legacy(
            unknown_filter_expression,
            expected_workspace_id=workspace_id,
        )


def test_legacy_comparison_store_adapts_filter_without_changing_search_inputs() -> None:
    """验证 legacy store 只转换过滤表达式，不改变向量、top_k 和命中结果。"""

    class RecordingSearchStore:
        """记录兼容层转发参数的测试存储，不执行真实向量检索。"""

        def __init__(self, returned_hits: list[Mapping[str, Any]]) -> None:
            """保存预设命中，并初始化尚未收到调用的记录字段。"""
            self.returned_hits = returned_hits
            self.received_query_vector: list[float] | None = None
            self.received_top_k: int | None = None
            self.received_filter_expression: str | None = None

        def search(
            self,
            query_vector: list[float],
            *,
            top_k: int,
            filter_expression: str,
        ) -> list[Mapping[str, Any]]:
            """记录调用参数并返回预设命中，模拟真实 SearchStore。"""
            self.received_query_vector = query_vector
            self.received_top_k = top_k
            self.received_filter_expression = filter_expression
            return self.returned_hits

    workspace_id = "demo-financial-reports"
    source_file = "data/贵州茅台2025年报.pdf"
    query_vector = [0.1, 0.2, 0.3]

    returned_hits: list[Mapping[str, Any]] = [
        {
            "score": 0.88,
            "chunk_id": "legacy-id",
            "text": "贵州茅台主要业务包括茅台酒及系列酒。",
            "page": 8,
            "source_file": source_file,
            "type": "paragraph",
            "section": "主要业务",
            "table_md": None,
        }
    ]

    delegate = RecordingSearchStore(returned_hits)

    store = LegacyComparisonStore(
        delegate,
        expected_workspace_id=workspace_id,
    )

    filter_expression = build_filter_expression(
        TrustedContext(workspace_id),
        SearchFilters(source_file=source_file),
    )

    actual_hits = store.search(
        query_vector,
        top_k=5,
        filter_expression=filter_expression,
    )

    assert delegate.received_query_vector is query_vector
    assert delegate.received_query_vector == [0.1, 0.2, 0.3]
    assert delegate.received_top_k == 5
    assert delegate.received_filter_expression == (
        f"source_file == {json.dumps(source_file, ensure_ascii=False)}"
    )

    assert actual_hits is returned_hits
    assert actual_hits == returned_hits


def test_evaluate_question_with_retriever_preserves_ranking_and_metadata_contract() -> None:
    """验证统一 Retriever 单题评测保留排名、过滤、元数据和指标样本合同。"""

    class RecordingSearchStore:
        """记录 Retriever 传入的检索参数并返回预设命中的测试存储。"""

        def __init__(self, returned_hits: list[Mapping[str, Any]]) -> None:
            """保存预设命中，并初始化尚未收到调用的记录字段。"""
            self.returned_hits = returned_hits
            self.received_query_vector: list[float] | None = None
            self.received_top_k: int | None = None
            self.received_filter_expression: str | None = None

        def search(
            self,
            query_vector: list[float],
            *,
            top_k: int,
            filter_expression: str,
        ) -> list[Mapping[str, Any]]:
            """记录调用参数并返回预设命中，模拟真实 SearchStore。"""
            self.received_query_vector = query_vector
            self.received_top_k = top_k
            self.received_filter_expression = filter_expression
            return self.returned_hits

    received_embed_texts: list[list[str]] = []

    def deterministic_embed(texts: list[str]) -> list[list[float]]:
        """记录待向量化文本，并返回固定的测试查询向量。"""
        received_embed_texts.append(texts)
        return [[0.1, 0.2, 0.3]]

    workspace_id = "demo-financial-reports"
    source_file = "data/贵州茅台2025年报.pdf"

    returned_hits: list[Mapping[str, Any]] = [
        {
            "score": 0.91,
            "chunk_id": "unrelated-id",
            "text": "不相关内容",
            "page": 7,
            "source_file": source_file,
            "type": "paragraph",
            "section": "公司简介",
            "table_md": None,
        },
        {
            "score": 0.88,
            "chunk_id": "relevant-v2-id",
            "text": "公司主要业务是茅台酒及系列酒的生产与销售。",
            "page": 8,
            "source_file": source_file,
            "type": "paragraph",
            "section": "主要业务",
            "table_md": None,
        },
    ]

    question: dict[str, Any] = {
        "case_id": "Q-test",
        "query": "贵州茅台的主要业务是什么？",
        "category": "ordinary_text",
        "answerable": True,
        "relevant_chunk_ids": ["relevant-v2-id"],
        "source_file": source_file,
        "ground_truth": "主要业务是茅台酒及系列酒的生产与销售。",
        "expected_metadata": {
            "relevant-v2-id": {
                "source_file": source_file,
                "page": 8,
                "type": "paragraph",
            }
        },
    }

    store = RecordingSearchStore(returned_hits)
    retriever = Retriever(
        deterministic_embed,
        store,
    )

    result, metric_case = evaluate_question_with_retriever(
        question,
        retriever=retriever,
        context=TrustedContext(workspace_id),
        top_k=5,
    )

    assert received_embed_texts == [["贵州茅台的主要业务是什么？"]]
    assert store.received_query_vector == [0.1, 0.2, 0.3]
    assert store.received_top_k == 5
    assert store.received_filter_expression == build_filter_expression(
        TrustedContext(workspace_id),
        SearchFilters(source_file=source_file),
    )

    assert result["case_id"] == "Q-test"
    assert result["query"] == "贵州茅台的主要业务是什么？"
    assert result["category"] == "ordinary_text"
    assert result["answerable"] is True
    assert result["source_file_filter"] == source_file
    assert result["status"] == "normal"
    assert result["relevant_rank"] == 2
    assert result["latency_ms"] >= 0
    assert result["error"] is None

    assert [hit["chunk_id"] for hit in result["hits"]] == [
        "unrelated-id",
        "relevant-v2-id",
    ]
    assert [hit["rank"] for hit in result["hits"]] == [1, 2]

    metadata_check = result["metadata_check"]

    assert metadata_check["filter_ok"] is True
    assert metadata_check["relevant_metadata_status"] == "passed"
    assert metadata_check["relevant_hit_checks"] == [
        {
            "chunk_id": "relevant-v2-id",
            "ok": True,
            "mismatches": {},
        }
    ]

    assert metric_case == (
        ("unrelated-id", "relevant-v2-id"),
        frozenset({"relevant-v2-id"}),
    )


def test_evaluate_question_set_with_retriever_excludes_warmup_and_unanswerable_metrics() -> None:
    """验证整套评测排除 warm-up 延迟，并且无答案题不进入排名指标。"""

    class QuestionAwareSearchStore:
        """根据测试查询向量返回不同命中，并记录总调用次数。"""

        def __init__(self) -> None:
            """初始化检索调用计数。"""
            self.call_count = 0

        def search(
            self,
            query_vector: list[float],
            *,
            top_k: int,
            filter_expression: str,
        ) -> list[Mapping[str, Any]]:
            """根据查询向量返回可回答题或无答案题的预设命中。"""
            self.call_count += 1

            assert top_k == 5
            assert filter_expression == ('workspace_id == "demo-financial-reports"')

            if query_vector == [1.0, 0.0]:
                return [
                    {
                        "score": 0.95,
                        "chunk_id": "relevant-id",
                        "text": "公司主营业务为集成电路设计、测试与销售。",
                        "page": 10,
                        "source_file": "data/成都华微电子2025年报.pdf",
                        "type": "paragraph",
                        "section": "主要业务",
                        "table_md": None,
                    }
                ]

            if query_vector == [0.0, 1.0]:
                return [
                    {
                        "score": 0.60,
                        "chunk_id": "ordinary-unrelated-id",
                        "text": "这是普通但与问题无关的年报内容。",
                        "page": 20,
                        "source_file": "data/成都华微电子2025年报.pdf",
                        "type": "paragraph",
                        "section": "经营情况",
                        "table_md": None,
                    }
                ]

            raise AssertionError(f"测试收到未知查询向量：{query_vector}")

    embed_calls: list[list[str]] = []

    def deterministic_embed(texts: list[str]) -> list[list[float]]:
        """根据测试问题返回固定向量，并记录 embedding 调用。"""
        embed_calls.append(texts)

        if texts == ["成都华微主要从事哪些业务？"]:
            return [[1.0, 0.0]]

        if texts == ["成都华微是否披露了量子芯片收入？"]:
            return [[0.0, 1.0]]

        raise AssertionError(f"测试收到未知 embedding 文本：{texts}")

    questions: list[dict[str, Any]] = [
        {
            "case_id": "Q-answerable",
            "query": "成都华微主要从事哪些业务？",
            "category": "ordinary_text",
            "answerable": True,
            "relevant_chunk_ids": ["relevant-id"],
            "source_file": None,
            "ground_truth": "公司主营业务为集成电路设计、测试与销售。",
            "expected_metadata": {
                "relevant-id": {
                    "source_file": "data/成都华微电子2025年报.pdf",
                    "page": 10,
                    "type": "paragraph",
                }
            },
        },
        {
            "case_id": "Q-unanswerable",
            "query": "成都华微是否披露了量子芯片收入？",
            "category": "no_answer",
            "answerable": False,
            "relevant_chunk_ids": [],
            "source_file": None,
            "ground_truth": "年报未披露该信息。",
            "expected_metadata": {},
        },
    ]

    store = QuestionAwareSearchStore()
    retriever = Retriever(
        deterministic_embed,
        store,
    )

    report = evaluate_question_set_with_retriever(
        questions,
        retriever=retriever,
        context=TrustedContext("demo-financial-reports"),
        top_k=5,
    )

    assert store.call_count == 3
    assert embed_calls == [
        ["成都华微主要从事哪些业务？"],
        ["成都华微主要从事哪些业务？"],
        ["成都华微是否披露了量子芯片收入？"],
    ]

    assert report["warmup_ms"] >= 0

    assert report["metrics"]["question_count"] == 2
    assert report["metrics"]["answerable_count"] == 1
    assert report["metrics"]["hit_at_1"] == 1.0
    assert report["metrics"]["hit_at_5"] == 1.0
    assert report["metrics"]["mrr"] == 1.0

    assert report["metrics"]["latency_sample_count"] == 2
    assert report["metrics"]["exploratory_p50_ms"] is not None
    assert report["metrics"]["exploratory_p95_ms"] is not None

    assert len(report["results"]) == 2

    answerable_result = report["results"][0]
    assert answerable_result["case_id"] == "Q-answerable"
    assert answerable_result["status"] == "normal"
    assert answerable_result["relevant_rank"] == 1

    unanswerable_result = report["results"][1]
    assert unanswerable_result["case_id"] == "Q-unanswerable"
    assert unanswerable_result["status"] == "normal"
    assert unanswerable_result["relevant_rank"] is None
    assert unanswerable_result["metadata_check"]["relevant_metadata_status"] == "not_applicable"
