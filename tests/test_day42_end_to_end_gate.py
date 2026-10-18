import json
from pathlib import Path
from typing import Any

from pymilvus import MilvusClient

from app.rag.chunk import chunk_docment
from app.rag.evaluation import first_relevant_rank
from app.rag.ingest import build_aligned_rows, replace_document_rows
from app.rag.metrics import RankingCase, mean_hit_at_k, mean_reciprocal_rank
from app.rag.parse.mineru_adapter import parse_mineru_output
from app.rag.parse.models import DocChunk
from app.rag.retriever import (
    Retriever,
    SearchFilters,
    SearchHit,
    TrustedContext,
    build_filter_expression,
)
from app.rag.store import (
    MilvusSearchStore,
    count_rows,
    ensure_document_collection,
)


DIM = 5
COLLECTION_NAME = "day42_end_to_end_gate"
A_SOURCE_FILE = "gate/澄海精密2026简报.pdf"
A_SECTION = "澄海精密2026年运营简报/一、交付与质量"

# MinerU 输出的原始表体；用于验证 table_md 原样保存。
A_TABLE_BODY = (
    "<table>"
    "<tr><th>型号</th><th>低温循环次数</th><th>结论</th></tr>"
    "<tr><td>BJ-7</td><td>360次</td><td>通过</td></tr>"
    "<tr><td>BJ-9</td><td>240次</td><td>待复核</td></tr>"
    "</table>"
)

# 【建议】表格进入 embedding 前的可检索文本；不含 HTML 或 Markdown 装饰。
A_TABLE_SEARCH_TEXT = (
    "蓝晶模组低温验证表\n型号 | 低温循环次数 | 结论\nBJ-7 | 360次 | 通过\nBJ-9 | 240次 | 待复核"
)

# B 文档由 MinerU 输出的原始 HTML 表体。
B_TABLE_BODY = (
    "<table>"
    "<tr><th>型号</th><th>校准周期</th><th>状态</th></tr>"
    "<tr><td>YS-3</td><td>45天</td><td>正常</td></tr>"
    "</table>"
)

B_SOURCE_FILE = "gate/北辰精密2026简报.pdf"

A_DOCUMENT_ID = "WS-ALPHA:chenghai-2026"
B_DOCUMENT_ID = "WS-BETA:beichen-2026"

a_v1_elements: list[dict[str, Any]] = [
    {
        "type": "text",
        "text": "澄海精密2026年运营简报",
        "text_level": 1,
        "page_idx": 1,
    },
    {
        "type": "text",
        "text": "一、交付与质量",
        "text_level": 2,
        "page_idx": 1,
    },
    {
        "type": "text",
        "text": ("海岬一号产线位于宁波，负责蓝晶模组的试制。2026年第一季度计划交付120套。"),
        "text_level": None,
        "page_idx": 1,
    },
    {
        "type": "table",
        "table_caption": ["蓝晶模组低温验证表"],
        "table_body": A_TABLE_BODY,
        "page_idx": 1,
    },
]

a_v2_elements: list[dict[str, Any]] = [
    {
        "type": "text",
        "text": "澄海精密2026年运营简报",
        "text_level": 1,
        "page_idx": 1,
    },
    {
        "type": "text",
        "text": "一、交付与质量",
        "text_level": 2,
        "page_idx": 1,
    },
    {
        "type": "text",
        "text": ("海岬一号产线位于宁波，负责蓝晶模组的试制。2026年第一季度实际交付128套。"),
        "text_level": None,
        "page_idx": 1,
    },
    {
        "type": "table",
        "table_caption": ["蓝晶模组低温验证表"],
        "table_body": A_TABLE_BODY,
        "page_idx": 1,
    },
]


b_v1_elements: list[dict[str, Any]] = [
    {
        "type": "text",
        "text": "北辰精密2026年运营简报",
        "text_level": 1,
        "page_idx": 1,
    },
    {
        "type": "text",
        "text": "一、制造进展",
        "text_level": 2,
        "page_idx": 1,
    },
    {
        "type": "text",
        "text": ("霁光三号产线位于合肥，负责银杉组件的生产。2026年第一季度实际交付999套。"),
        "text_level": None,
        "page_idx": 1,
    },
    {
        "type": "table",
        "table_caption": ["银杉组件校准表"],
        "table_body": B_TABLE_BODY,
        "page_idx": 1,
    },
]


def write_content_list(
    root: Path,
    directory_name: str,
    elements: list[dict[str, Any]],
) -> Path:
    """把手造的 raw elements 写成临时 MinerU content-list 文件。

    每个 document 或 document version 使用独立目录，避免
    parse_mineru_output 在同一目录中找到多个 *_content_list.json。

    Args:
        root: pytest 提供的临时根目录，一般传入 tmp_path。
        directory_name: 当前 document/version 的目录名，例如 a_v1。
        elements: 手造的 MinerU raw elements。

    Returns:
        content-list 文件所在目录，用作 parse_mineru_output 的 out_dir。
    """
    content_dir = root / directory_name
    content_dir.mkdir(parents=True)

    content_file = content_dir / f"{directory_name}_content_list.json"
    content_file.write_text(
        json.dumps(elements, ensure_ascii=False),
        encoding="utf-8",
    )

    return content_dir


def deterministic_embed(texts: list[str]) -> list[list[float]]:
    """根据五个固定关键词为每条文本生成确定性的五维向量"""
    markers = (
        "海岬一号",
        "BJ-7",
        "实际交付",
        "霁光三号",
        "YS-3",
    )
    return [[1.0 if marker in text else 0.0 for marker in markers] for text in texts]


def prepare_rows(
    content_dir: Path,
    *,
    source_file: str,
    workspace_id: str,
) -> tuple[list[DocChunk], list[DocChunk], list[dict[str, Any]]]:
    """
    执行 adapter、chunk、可信 metadata 注入和向量对齐，返回 chunks 与 rows

    Args:
        content_dir: MinerU 输入的 content-list 文件所在目录。
        source_file: 源文件路径。
        workspace_id: 服务端附加的可信 workspace。

    Returns:
        tuple[list[DocChunk], list[DocChunk], list[dict[str, Any]]]: 块、分块和行列表。
    """
    # 1. parse_mineru_output
    blocks = parse_mineru_output(str(content_dir), source_file).chunks
    # 2. chunk_docment
    chunks = chunk_docment(blocks)
    # 3. model_dump，并由服务端添加 workspace_id
    raw_chunks: list[dict[str, Any]] = [
        {
            **chunk.model_dump(),
            "workspace_id": workspace_id,
        }
        for chunk in chunks
    ]
    # 4. build_aligned_rows
    rows: list[dict[str, Any]] = build_aligned_rows(raw_chunks, deterministic_embed)
    # 5. 返回 chunks 和 rows
    return blocks, chunks, rows


def document_ids(
    client: MilvusClient,
    document_id: str,
) -> set[str]:
    """查询指定 document 当前在 Milvus 中实际存在的 chunk ID 集合"""
    return {
        row["chunk_id"]
        for row in client.query(
            COLLECTION_NAME,
            filter=f"document_id == {json.dumps(document_id)}",
            output_fields=["chunk_id"],
        )
    }


def retrieved_ids(hits: list[SearchHit]) -> list[str]:
    """按检索排名顺序提取 SearchHit 中的 chunk ID"""
    return [hit.chunk_id for hit in hits]


def assert_rows_aligned(
    chunks: list[DocChunk],
    rows: list[dict[str, Any]],
    *,
    expected_workspace_id: str,
) -> None:
    """断言 chunk、embedding text、vector 和 row 数量及位置严格对齐

    Args:
        chunks: chunk 状态机输出的合法 chunks。
        rows: build_aligned_rows 生成的待写入 Milvus 的 rows。
        expected_workspace_id: 服务端附加的可信 workspace。
    """
    embedding_texts = [chunk.text for chunk in chunks]
    expected_vectors = deterministic_embed(embedding_texts)
    row_vectors = [row["vector"] for row in rows]

    # 四组对象必须具有相同数量。
    assert len(chunks) == len(embedding_texts) == len(expected_vectors) == len(rows)

    # 每条向量必须符合临时 collection 的维度契约。
    assert all(len(vector) == DIM for vector in expected_vectors)
    assert all(len(vector) == DIM for vector in row_vectors)

    # Rows 中保存的向量及顺序必须与预期完全一致。
    assert row_vectors == expected_vectors

    for index, (chunk, row) in enumerate(zip(chunks, rows, strict=True)):
        assert row["chunk_id"] == chunk.chunk_id, index
        assert row["text"] == chunk.text, index
        assert row["page"] == chunk.page, index
        assert row["section"] == chunk.section, index
        assert row["source_file"] == chunk.source_file, index
        assert row["type"] == chunk.type, index
        assert row["table_md"] == chunk.table_md, index
        assert row["workspace_id"] == expected_workspace_id, index
        assert row["vector"] == expected_vectors[index], index


def test_day42_unknown_end_to_end_gate(tmp_path: Path) -> None:
    """验证陌生输入从 adapter 到检索评测的完整职责链"""
    # Arrange：分别写 A V1、A V2、B 的 content-list 文件
    a_v1_dir = write_content_list(tmp_path, "a_v1", a_v1_elements)
    a_v2_dir = write_content_list(tmp_path, "a_v2", a_v2_elements)
    b_dir = write_content_list(tmp_path, "b", b_v1_elements)

    client = MilvusClient(str(tmp_path / "day42_gate.db"))
    ensure_document_collection(
        client,
        COLLECTION_NAME,
        dim=DIM,
    )

    try:
        # 1. adapter → chunk
        a_v1_blocks, a_v1_chunks, a_v1_rows = prepare_rows(
            a_v1_dir, source_file=A_SOURCE_FILE, workspace_id="WS-ALPHA"
        )
        assert [block.type for block in a_v1_blocks] == ["title", "title", "paragraph", "table"]
        assert [block.page for block in a_v1_blocks] == [2, 2, 2, 2]
        assert a_v1_blocks[0].section == "澄海精密2026年运营简报"
        assert a_v1_blocks[1].section == A_SECTION
        assert a_v1_blocks[2].section == A_SECTION
        assert a_v1_blocks[3].section == A_SECTION
        assert all(block.source_file == A_SOURCE_FILE for block in a_v1_blocks)
        adapter_table = a_v1_blocks[3]
        assert adapter_table.text == A_TABLE_SEARCH_TEXT
        assert adapter_table.table_md == A_TABLE_BODY
        assert "BJ-7" in adapter_table.text
        assert "360次" in adapter_table.text

        assert [chunk.type for chunk in a_v1_chunks] == ["paragraph", "table"]
        assert len(a_v1_chunks) == 2
        paragraph_chunk = a_v1_chunks[0]
        table_chunk = a_v1_chunks[1]

        assert paragraph_chunk.page == 2
        assert paragraph_chunk.section == A_SECTION
        assert paragraph_chunk.source_file == A_SOURCE_FILE

        assert table_chunk.page == 2
        assert table_chunk.section == A_SECTION
        assert table_chunk.source_file == A_SOURCE_FILE
        assert table_chunk.text == A_TABLE_SEARCH_TEXT
        assert table_chunk.table_md == A_TABLE_BODY

        assert paragraph_chunk.chunk_id
        assert table_chunk.chunk_id
        assert paragraph_chunk.chunk_id != table_chunk.chunk_id

        # 2. chunk → vector → rows
        assert_rows_aligned(a_v1_chunks, a_v1_rows, expected_workspace_id="WS-ALPHA")

        table_row = a_v1_rows[1]
        assert table_row["type"] == "table"

        assert "蓝晶模组低温验证表" in table_row["text"]
        assert "BJ-7" in table_row["text"]
        assert "360次" in table_row["text"]

        assert table_row["table_md"] == A_TABLE_BODY

        # 3. 首次摄取 B 和 A V1

        # 分别生成 B 和 A V1 的完整待写入 rows。
        _, b_chunks, b_rows = prepare_rows(
            b_dir,
            source_file=B_SOURCE_FILE,
            workspace_id="WS-BETA",
        )
        assert_rows_aligned(
            b_chunks,
            b_rows,
            expected_workspace_id="WS-BETA",
        )

        # 在写库前保存根据源输入生成的预期 ID 集合。
        expected_a_v1_ids = {chunk.chunk_id for chunk in a_v1_chunks}
        expected_b_ids = {chunk.chunk_id for chunk in b_chunks}

        # 先写入独立的 B，再写入 A V1。
        b_result = replace_document_rows(
            client,
            COLLECTION_NAME,
            B_DOCUMENT_ID,
            b_rows,
        )
        a_v1_result = replace_document_rows(
            client,
            COLLECTION_NAME,
            A_DOCUMENT_ID,
            a_v1_rows,
        )

        # ReplaceResult 的最终 ID 集合必须等于输入产生的预期集合。
        assert b_result.final_ids == frozenset(expected_b_ids)
        assert a_v1_result.final_ids == frozenset(expected_a_v1_ids)

        # 从数据库重新查询实际 document 状态。
        a_v1_ids = document_ids(client, A_DOCUMENT_ID)
        b_ids = document_ids(client, B_DOCUMENT_ID)
        total_rows = count_rows(client, COLLECTION_NAME)

        assert a_v1_ids == expected_a_v1_ids
        assert b_ids == expected_b_ids
        assert total_rows == len(a_v1_rows) + len(b_rows)

        # 4. A V1 原样重跑

        # 必须重新从同一份原始输入执行完整链路，不能直接复用第一次的 rows。
        _, regenerated_a_v1_chunks, regenerated_a_v1_rows = prepare_rows(
            a_v1_dir,
            source_file=A_SOURCE_FILE,
            workspace_id="WS-ALPHA",
        )
        assert_rows_aligned(
            regenerated_a_v1_chunks,
            regenerated_a_v1_rows,
            expected_workspace_id="WS-ALPHA",
        )

        # 相同版本重新生成时，stable ID 集合必须不变。
        regenerated_a_v1_ids = {chunk.chunk_id for chunk in regenerated_a_v1_chunks}
        assert regenerated_a_v1_ids == a_v1_ids

        # 使用同一个 document_id 执行完整替换。
        rerun_result = replace_document_rows(
            client,
            COLLECTION_NAME,
            A_DOCUMENT_ID,
            regenerated_a_v1_rows,
        )

        # 替换后的最终 ID、数据库状态和第一次摄取完全一致。
        assert rerun_result.final_ids == frozenset(a_v1_ids)
        assert document_ids(client, A_DOCUMENT_ID) == a_v1_ids

        # 相同版本重跑不能增加重复行，也不能改变另一个 document。
        assert count_rows(client, COLLECTION_NAME) == total_rows
        assert document_ids(client, B_DOCUMENT_ID) == b_ids

        # 5. A 更新为 V2

        # 从 A V2 的原始输入重新执行 adapter、chunk、embedding 和 rows 对齐。
        _, a_v2_chunks, a_v2_rows = prepare_rows(
            a_v2_dir,
            source_file=A_SOURCE_FILE,
            workspace_id="WS-ALPHA",
        )
        assert_rows_aligned(
            a_v2_chunks,
            a_v2_rows,
            expected_workspace_id="WS-ALPHA",
        )

        # 根据 type 找到新旧正文和表格，不依赖列表的固定位置。
        old_paragraph_chunk = next(chunk for chunk in a_v1_chunks if chunk.type == "paragraph")
        old_table_chunk = next(chunk for chunk in a_v1_chunks if chunk.type == "table")
        new_paragraph_chunk = next(chunk for chunk in a_v2_chunks if chunk.type == "paragraph")
        new_table_chunk = next(chunk for chunk in a_v2_chunks if chunk.type == "table")

        # 先根据输入验证 stable ID 的变化规律。
        assert old_paragraph_chunk.text != new_paragraph_chunk.text
        assert old_paragraph_chunk.chunk_id != new_paragraph_chunk.chunk_id

        assert old_table_chunk.text == new_table_chunk.text
        assert old_table_chunk.table_md == new_table_chunk.table_md
        assert old_table_chunk.chunk_id == new_table_chunk.chunk_id

        # 保存 V2 根据源输入生成的预期最终 ID 集合。
        expected_a_v2_ids = {chunk.chunk_id for chunk in a_v2_chunks}

        # 使用与 V1 相同的 document_id 完成 document 替换。
        a_v2_result = replace_document_rows(
            client,
            COLLECTION_NAME,
            A_DOCUMENT_ID,
            a_v2_rows,
        )

        # ReplaceResult 与 Milvus 实际状态必须都等于 V2 的预期 ID 集合。
        assert a_v2_result.final_ids == frozenset(expected_a_v2_ids)
        assert document_ids(client, A_DOCUMENT_ID) == expected_a_v2_ids

        # V1 的旧正文 ID 必须彻底消失，不能成为 ghost row。
        old_paragraph_rows = client.get(
            collection_name=COLLECTION_NAME,
            ids=[old_paragraph_chunk.chunk_id],
            output_fields=["chunk_id", "text"],
        )
        assert old_paragraph_rows == []

        # V2 的新正文和未变化的表格必须存在。
        new_document_rows = client.query(
            collection_name=COLLECTION_NAME,
            filter=f"document_id == {json.dumps(A_DOCUMENT_ID)}",
            output_fields=[
                "chunk_id",
                "text",
                "page",
                "section",
                "source_file",
                "type",
                "table_md",
                "workspace_id",
            ],
        )

        stored_a_v2_by_id = {row["chunk_id"]: row for row in new_document_rows}

        assert set(stored_a_v2_by_id) == expected_a_v2_ids
        assert len(new_document_rows) == 2

        # 数据库必须保存更新后的正文，而不是旧版本正文。
        stored_new_paragraph = stored_a_v2_by_id[new_paragraph_chunk.chunk_id]
        assert "实际交付128套" in stored_new_paragraph["text"]
        assert "计划交付120套" not in stored_new_paragraph["text"]
        assert stored_new_paragraph["workspace_id"] == "WS-ALPHA"

        # 未修改的表格仍使用原 ID，并保留检索文本与引用 payload。
        stored_table = stored_a_v2_by_id[new_table_chunk.chunk_id]
        assert stored_table["type"] == "table"
        assert "BJ-7" in stored_table["text"]
        assert stored_table["table_md"] == A_TABLE_BODY

        # 更新一个 document 不能改变另一个 document。
        assert document_ids(client, B_DOCUMENT_ID) == b_ids

        # A 仍是两行、B 仍是两行，因此 collection 总行数不变。
        assert count_rows(client, COLLECTION_NAME) == total_rows

        # 构造真实临时 Milvus store。
        store = MilvusSearchStore(
            client,
            COLLECTION_NAME,
        )

        # 注入确定性 query embedder 和真实临时 Milvus store。
        retriever = Retriever(
            embedder=deterministic_embed,
            store=store,
        )

        # 6. G1：普通正文
        # 根据手造源数据提前建立 G1 ground truth。
        g1_relevant_ids = {
            new_paragraph_chunk.chunk_id,
        }

        # 不提供业务 filter 时，Retriever 仍必须应用可信 workspace。
        g1_hits = retriever.retrieve(
            "海岬一号产线位于哪里，负责什么模组？",
            context=TrustedContext(workspace_id="WS-ALPHA"),
            top_k=3,
        )

        assert g1_hits
        assert all(isinstance(hit, SearchHit) for hit in g1_hits)

        g1_retrieved_ids = retrieved_ids(g1_hits)
        g1_rank = first_relevant_rank(
            g1_retrieved_ids,
            g1_relevant_ids,
        )

        # 相关正文应排名第一。
        assert g1_rank == 1
        assert g1_hits[0].chunk_id == new_paragraph_chunk.chunk_id

        # 可信 workspace 必须排除 WS-BETA 的数据。
        assert set(g1_retrieved_ids).isdisjoint(b_ids)
        assert set(g1_retrieved_ids).issubset(expected_a_v2_ids)

        # 检查 SearchHit 的身份与引用 metadata。
        g1_first_hit = g1_hits[0]

        assert g1_first_hit.text == new_paragraph_chunk.text
        assert g1_first_hit.page == 2
        assert g1_first_hit.source_file == A_SOURCE_FILE
        assert g1_first_hit.type == "paragraph"
        assert g1_first_hit.section == A_SECTION
        assert g1_first_hit.table_md is None

        # 命中的必须是 V2 正文，不能残留 V1 内容。
        assert "海岬一号产线位于宁波" in g1_first_hit.text
        assert "蓝晶模组" in g1_first_hit.text
        assert "实际交付128套" in g1_first_hit.text
        assert "计划交付120套" not in g1_first_hit.text

        # 7. G2：表格 + source_file filter

        # 相关 ID 来自手造源数据，而不是检索结果。
        g2_relevant_ids = {
            new_table_chunk.chunk_id,
        }

        g2_hits = retriever.retrieve(
            "BJ-7完成了多少次低温循环，验证结论是什么？",
            context=TrustedContext(workspace_id="WS-ALPHA"),
            filters=SearchFilters(
                source_file=A_SOURCE_FILE,
            ),
            top_k=3,
        )

        assert g2_hits
        assert all(isinstance(hit, SearchHit) for hit in g2_hits)

        g2_retrieved_ids = retrieved_ids(g2_hits)
        g2_rank = first_relevant_rank(
            g2_retrieved_ids,
            g2_relevant_ids,
        )

        # 确定性关键词向量下，BJ-7 表格应排名第一。
        assert g2_rank == 1
        assert g2_hits[0].chunk_id == new_table_chunk.chunk_id

        # workspace 和 source_file 必须同时限制结果范围。
        assert all(hit.source_file == A_SOURCE_FILE for hit in g2_hits)
        assert set(g2_retrieved_ids).isdisjoint(b_ids)
        assert set(g2_retrieved_ids).issubset(expected_a_v2_ids)

        # SearchHit 必须保留检索、身份和引用字段。
        g2_first_hit = g2_hits[0]

        assert g2_first_hit.type == "table"
        assert g2_first_hit.page == 2
        assert g2_first_hit.source_file == A_SOURCE_FILE
        assert g2_first_hit.section == A_SECTION

        # 检索文本必须包含表名和表体语义。
        assert "蓝晶模组低温验证表" in g2_first_hit.text
        assert "BJ-7" in g2_first_hit.text
        assert "360次" in g2_first_hit.text
        assert "通过" in g2_first_hit.text

        # 命中后必须能取回完整引用 payload。
        assert g2_first_hit.table_md == A_TABLE_BODY

        # 8. G3：用户尝试提交 workspace_id

        # 模拟来自用户的不可信请求。用户故意提交 WS-BETA，
        # 但它不能覆盖服务端认证得到的可信 workspace。
        request_payload: dict[str, Any] = {
            "query": "澄海精密第一季度实际交付多少套？",
            "workspace_id": "WS-BETA",
            "source_file": A_SOURCE_FILE,
            "top_k": 3,
        }

        # Ground truth 必须在执行检索前根据手造源数据建立。
        # G3 的答案存在于更新后的 A V2 正文。
        g3_relevant_ids = {
            new_paragraph_chunk.chunk_id,
        }

        # TrustedContext 只能由服务端认证结果构造，
        # 不能使用 request_payload 中用户提交的 workspace_id。
        trusted_context = TrustedContext(
            workspace_id="WS-ALPHA",
        )

        # 验证当前测试确实构造了用户 workspace 与可信 workspace 冲突的场景。
        assert request_payload["workspace_id"] == "WS-BETA"
        assert request_payload["workspace_id"] != trusted_context.workspace_id

        # 对允许进入 Retriever 的用户字段进行类型检查和类型收窄。
        g3_query = request_payload["query"]
        g3_source_file = request_payload["source_file"]
        g3_top_k = request_payload["top_k"]

        assert isinstance(g3_query, str)
        assert isinstance(g3_source_file, str)
        assert isinstance(g3_top_k, int)
        assert not isinstance(g3_top_k, bool)

        # 用户只允许提供 source_file 业务过滤条件。
        # request_payload 中的 workspace_id 不进入 SearchFilters。
        allowed_filters = SearchFilters(
            source_file=g3_source_file,
        )

        # 显式检查最终过滤表达式：
        # 可信 workspace 与允许的 source_file 必须使用 and 组合。
        g3_filter_expression = build_filter_expression(
            trusted_context,
            allowed_filters,
        )

        assert g3_filter_expression == (
            'workspace_id == "WS-ALPHA" and source_file == "gate/澄海精密2026简报.pdf"'
        )

        # 用户提交的 WS-BETA 不能出现在最终可信过滤表达式中。
        assert "WS-BETA" not in g3_filter_expression

        # 只使用服务端可信上下文和允许的 source_file filter 执行检索。
        # 不使用 request_payload["workspace_id"] 构造 TrustedContext。
        g3_hits = retriever.retrieve(
            g3_query,
            context=trusted_context,
            filters=allowed_filters,
            top_k=g3_top_k,
        )

        # 当前可信过滤范围内存在 A V2，因此应当返回结果。
        assert g3_hits

        # Retriever 应返回稳定的 SearchHit DTO。
        assert all(isinstance(hit, SearchHit) for hit in g3_hits)

        # 按真实返回顺序提取 chunk ID。
        g3_retrieved_ids = retrieved_ids(g3_hits)

        # 所有返回结果必须属于 WS-ALPHA 中更新后的 A V2。
        assert set(g3_retrieved_ids).issubset(expected_a_v2_ids)

        # 用户提交 WS-BETA 不能导致任何 B chunk 被返回。
        assert set(g3_retrieved_ids).isdisjoint(b_ids)

        # 用户允许的 source_file 业务过滤条件也必须生效。
        assert all(hit.source_file == A_SOURCE_FILE for hit in g3_hits)

        # 根据检索前建立的 ground truth 计算第一条相关结果的 rank。
        g3_rank = first_relevant_rank(
            g3_retrieved_ids,
            g3_relevant_ids,
        )

        # 查询包含“实际交付”，相关的 A V2 正文应排在第一位。
        assert g3_rank == 1
        assert g3_hits[0].chunk_id == new_paragraph_chunk.chunk_id

        # 检查第一条 SearchHit 的身份、来源和引用 metadata。
        g3_first_hit = g3_hits[0]

        assert g3_first_hit.chunk_id == new_paragraph_chunk.chunk_id
        assert g3_first_hit.text == new_paragraph_chunk.text
        assert g3_first_hit.type == "paragraph"
        assert g3_first_hit.page == 2
        assert g3_first_hit.source_file == A_SOURCE_FILE
        assert g3_first_hit.section == A_SECTION
        assert g3_first_hit.table_md is None

        # 必须返回 A V2 更新后的内容。
        assert "实际交付128套" in g3_first_hit.text

        # A V1 的旧内容已经被 document 替换删除。
        assert "计划交付120套" not in g3_first_hit.text

        # WS-BETA 的内容不能越过可信 workspace 边界。
        assert "实际交付999套" not in g3_first_hit.text
        assert "霁光三号" not in g3_first_hit.text

        # 9. metrics

        # 三条查询都在各自的可信检索范围内有明确相关 chunk，
        # 因此全部作为可回答题进入 Hit@K 和 MRR 的分母。
        gate_cases: list[RankingCase] = [
            (
                g1_retrieved_ids,
                g1_relevant_ids,
            ),
            (
                g2_retrieved_ids,
                g2_relevant_ids,
            ),
            (
                g3_retrieved_ids,
                g3_relevant_ids,
            ),
        ]

        # 再次确认进入指标分母的题数和相关性标注完整。
        assert len(gate_cases) == 3
        assert all(relevant_ids for _, relevant_ids in gate_cases)

        # 复用项目已有指标函数，不在 Gate 中重新实现计算公式。
        gate_hit_at_1 = mean_hit_at_k(
            gate_cases,
            k=1,
        )
        gate_hit_at_3 = mean_hit_at_k(
            gate_cases,
            k=3,
        )
        gate_mrr = mean_reciprocal_rank(
            gate_cases,
        )

        # 三条查询的相关 chunk 都应位于第一名。
        assert [g1_rank, g2_rank, g3_rank] == [1, 1, 1]

        # 确定性 Gate 的三个相关结果都在 rank 1，
        # 因此三个汇总指标都应达到 1.0。
        assert gate_hit_at_1 == 1.0
        assert gate_hit_at_3 == 1.0
        assert gate_mrr == 1.0

    finally:
        client.drop_collection(COLLECTION_NAME)
