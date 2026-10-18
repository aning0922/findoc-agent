import json
from pathlib import Path

import pytest
from pymilvus import MilvusClient

from app.rag.ingest import build_aligned_rows, replace_document_rows
from app.rag.store import count_rows, ensure_document_collection


def make_row(
    chunk_id: str,
    text: str,
    vector: list[float],
) -> dict[str, object]:
    # 返回包含chunk_id、text、vector及最小必要metadata的完整row
    return {
        "chunk_id": chunk_id,
        "text": text,
        "vector": vector,
    }


def document_ids(
    client: MilvusClient,
    collection_name: str,
    document_id: str,
) -> set[str]:
    # 按document_id查询，只返回chunk_id，然后组成集合
    document_filter = f"document_id == {json.dumps(document_id)}"

    rows = client.query(
        collection_name=collection_name,
        filter=document_filter,
        output_fields=["chunk_id"],
    )
    return {row["chunk_id"] for row in rows}


def test_document_replacement_lifecycle(tmp_path: Path) -> None:
    # 建立临时数据库和二维collection
    db_path = tmp_path / "day40_document_lifecycle.db"
    collection_name = "day40_document_lifecycle"
    client = MilvusClient(str(db_path))
    ensure_document_collection(client, collection_name, dim=2)
    try:
        d_b = [
            make_row("B1", "D-B1", [1.0, 0.0]),
        ]
        d_a = [
            make_row("A1", "D-A1", [1.0, 0.0]),
            make_row("A2", "D-A2", [0.0, 1.0]),
        ]
        # 摄取D-B
        replace_document_rows(client, collection_name, "D-B", d_b)

        assert document_ids(client, collection_name, "D-B") == {"B1"}
        assert count_rows(client, collection_name) == 1

        # 首次摄取D-A
        result = replace_document_rows(client, collection_name, "D-A", d_a)

        assert result.inserted == 2
        assert result.updated == 0
        assert result.skipped == 0
        assert result.final_ids == frozenset({"A1", "A2"})
        assert document_ids(client, collection_name, "D-A") == {"A1", "A2"}
        assert document_ids(client, collection_name, "D-B") == {"B1"}
        assert count_rows(client, collection_name) == 3

        # 重复摄取
        result = replace_document_rows(client, collection_name, "D-A", d_a)

        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)
        assert result.final_ids == frozenset({"A1", "A2"})
        assert document_ids(client, collection_name, "D-A") == {"A1", "A2"}
        assert document_ids(client, collection_name, "D-B") == {"B1"}
        assert count_rows(client, collection_name) == 3

        # 换序
        d_a_reordered = [
            make_row("A2", "D-A2", [0.0, 1.0]),
            make_row("A1", "D-A1", [1.0, 0.0]),
        ]
        result = replace_document_rows(
            client,
            collection_name,
            "D-A",
            d_a_reordered,
        )

        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)
        assert result.final_ids == frozenset({"A1", "A2"})
        assert document_ids(client, collection_name, "D-A") == {"A1", "A2"}
        assert document_ids(client, collection_name, "D-B") == {"B1"}
        assert count_rows(client, collection_name) == 3

        # 修改text
        d_a_modified = [
            make_row("A1", "D-A1", [1.0, 0.0]),
            make_row("A3", "D-A2-new", [0.0, 1.0]),
        ]
        result = replace_document_rows(client, collection_name, "D-A", d_a_modified)
        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)
        assert result.final_ids == frozenset({"A1", "A3"})
        assert document_ids(client, collection_name, "D-A") == {"A1", "A3"}
        assert document_ids(client, collection_name, "D-B") == {"B1"}
        assert count_rows(client, collection_name) == 3

        assert (
            client.get(
                collection_name=collection_name,
                ids=["A2"],
                output_fields=["chunk_id", "text"],
            )
            == []
        )

        search_results = client.search(
            collection_name=collection_name,
            data=[[0.0, 1.0]],
            limit=10,
            filter='document_id == "D-A"',
            output_fields=["chunk_id", "text"],
        )

        returned_entities = [hit["entity"] for hit in search_results[0]]
        assert returned_entities
        assert returned_entities[0]["chunk_id"] == "A3"
        assert returned_entities[0]["text"] == "D-A2-new"
        assert all(entity["chunk_id"] != "A2" for entity in returned_entities)
        assert all(entity["text"] != "D-A2" for entity in returned_entities)

        # 删除一个chunk
        remaining_rows = [
            make_row("A3", "D-A2-new", [0.0, 1.0]),
        ]
        result = replace_document_rows(
            client,
            collection_name,
            "D-A",
            remaining_rows,
        )

        assert (result.inserted, result.updated, result.skipped) == (1, 0, 0)
        assert result.final_ids == frozenset({"A3"})
        assert document_ids(client, collection_name, "D-A") == {"A3"}
        assert document_ids(client, collection_name, "D-B") == {"B1"}
        assert count_rows(client, collection_name) == 2
        assert (
            client.get(
                collection_name=collection_name,
                ids=["A1"],
                output_fields=["chunk_id"],
            )
            == []
        )

        # 删除整份D-A
        result = replace_document_rows(client, collection_name, "D-A", [])

        assert (result.inserted, result.updated, result.skipped) == (0, 0, 0)
        assert result.final_ids == frozenset()
        assert document_ids(client, collection_name, "D-A") == set()
        assert document_ids(client, collection_name, "D-B") == {"B1"}
        assert count_rows(client, collection_name) == 1
        assert (
            client.get(
                collection_name=collection_name,
                ids=["A3"],
                output_fields=["chunk_id"],
            )
            == []
        )
    finally:
        client.close()


def test_document_replacement_converges_after_partial_insert_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    db_path = tmp_path / "day40_document_lifecycle.db"
    collection_name = "day40_document_lifecycle"
    client = MilvusClient(str(db_path))
    ensure_document_collection(client, collection_name, dim=2)
    original_insert = client.insert

    def insert_first_then_fail(
        *,
        collection_name: str,
        data: list[dict[str, object]],
    ) -> None:
        original_insert(
            collection_name=collection_name,
            data=[data[0]],
        )
        raise RuntimeError("simulated insert failure")

    try:
        d_b = [
            make_row("B1", "D-B1", [1.0, 0.0]),
        ]
        d_a = [
            make_row("A1", "D-A1", [1.0, 0.0]),
            make_row("A2", "D-A2", [0.0, 1.0]),
        ]
        replace_document_rows(client, collection_name, "D-B", d_b)
        replace_document_rows(client, collection_name, "D-A", d_a)

        d_a_modified = [
            make_row("A1", "D-A1", [1.0, 0.0]),
            make_row("A3", "D-A2-new", [0.0, 1.0]),
        ]

        with monkeypatch.context() as scoped:
            scoped.setattr(client, "insert", insert_first_then_fail)

            with pytest.raises(RuntimeError, match="simulated insert failure"):
                replace_document_rows(client, collection_name, "D-A", d_a_modified)
            assert document_ids(client, collection_name, "D-A") == {"A1"}
            assert document_ids(client, collection_name, "D-B") == {"B1"}
            assert count_rows(client, collection_name) == 2

            assert (
                client.get(
                    collection_name=collection_name,
                    ids=["A2"],
                    output_fields=["chunk_id"],
                )
                == []
            )

            assert (
                client.get(
                    collection_name=collection_name,
                    ids=["A3"],
                    output_fields=["chunk_id"],
                )
                == []
            )

        result = replace_document_rows(
            client,
            collection_name,
            "D-A",
            d_a_modified,
        )
        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)
        assert result.final_ids == frozenset({"A1", "A3"})
        assert document_ids(client, collection_name, "D-A") == {"A1", "A3"}
        assert document_ids(client, collection_name, "D-B") == {"B1"}
        assert count_rows(client, collection_name) == 3
        assert (
            client.get(
                collection_name=collection_name,
                ids=["A2"],
                output_fields=["chunk_id"],
            )
            == []
        )
    finally:
        client.close()


def test_gate_variant_document_replacement_with_unseen_ids(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "day40_gate_nova.db"
    collection_name = "day40_gate_nova"
    client = MilvusClient(str(db_path))
    ensure_document_collection(client, collection_name, dim=2)

    d_anchor = [
        make_row("K4", "增长", [1.0, 0.0]),
    ]
    d_nova = [
        make_row("N7", "海外收入增长", [1.0, 0.0]),
        make_row("N9", "存货周转放缓", [0.0, 1.0]),
    ]
    try:
        result = replace_document_rows(client, collection_name, "D-ANCHOR", d_anchor)
        assert (result.inserted, result.updated, result.skipped) == (1, 0, 0)
        assert result.final_ids == frozenset({"K4"})
        assert document_ids(client, collection_name, "D-ANCHOR") == {"K4"}
        assert document_ids(client, collection_name, "D-NOVA") == set()
        assert count_rows(client, collection_name) == 1

        result = replace_document_rows(client, collection_name, "D-NOVA", d_nova)
        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)
        assert result.final_ids == frozenset({"N7", "N9"})
        assert document_ids(client, collection_name, "D-ANCHOR") == {"K4"}
        assert document_ids(client, collection_name, "D-NOVA") == {"N7", "N9"}
        assert count_rows(client, collection_name) == 3

        result = replace_document_rows(
            client,
            collection_name,
            "D-NOVA",
            d_nova,
        )

        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)
        assert result.final_ids == frozenset({"N7", "N9"})
        assert document_ids(client, collection_name, "D-NOVA") == {"N7", "N9"}
        assert document_ids(client, collection_name, "D-ANCHOR") == {"K4"}
        assert count_rows(client, collection_name) == 3

        d_nova_reordered = [
            make_row("N9", "存货周转放缓", [0.0, 1.0]),
            make_row("N7", "海外收入增长", [1.0, 0.0]),
        ]
        result = replace_document_rows(client, collection_name, "D-NOVA", d_nova_reordered)
        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)
        assert result.final_ids == frozenset({"N7", "N9"})
        assert document_ids(client, collection_name, "D-ANCHOR") == {"K4"}
        assert document_ids(client, collection_name, "D-NOVA") == {"N9", "N7"}
        assert count_rows(client, collection_name) == 3

        d_nova_modified = [
            make_row("N7", "海外收入增长", [1.0, 0.0]),
            make_row("N12", "存货周转加快", [0.0, -1.0]),
        ]
        result = replace_document_rows(client, collection_name, "D-NOVA", d_nova_modified)
        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)

        assert (
            client.get(
                collection_name=collection_name,
                ids=["N9"],
                output_fields=["chunk_id"],
            )
            == []
        )
        assert document_ids(client, collection_name, "D-ANCHOR") == {"K4"}
        assert document_ids(client, collection_name, "D-NOVA") == {"N7", "N12"}
        assert count_rows(client, collection_name) == 3

        d_nova_remaining = [
            make_row("N12", "存货周转加快", [0.0, -1.0]),
        ]
        result = replace_document_rows(client, collection_name, "D-NOVA", d_nova_remaining)
        assert (result.inserted, result.updated, result.skipped) == (1, 0, 0)

        assert document_ids(client, collection_name, "D-ANCHOR") == {"K4"}
        assert document_ids(client, collection_name, "D-NOVA") == {"N12"}
        assert count_rows(client, collection_name) == 2

        assert (
            client.get(
                collection_name=collection_name,
                ids=["N7"],
                output_fields=["chunk_id"],
            )
            == []
        )

        final_rows = client.query(
            collection_name=collection_name,
            filter='document_id == "D-NOVA"',
            output_fields=["chunk_id", "text", "vector"],
        )

        assert len(final_rows) == 1
        assert final_rows[0]["chunk_id"] == "N12"
        assert final_rows[0]["text"] == "存货周转加快"
        assert final_rows[0]["vector"] == [0.0, -1.0]
    finally:
        client.close()


def test_legal_chunks_reach_milvus_with_identity_and_metadata_aligned(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "day40_chain.db"
    collection_name = "day40_chain"
    client = MilvusClient(str(db_path))
    ensure_document_collection(client, collection_name, dim=2)

    raw_chunks = [
        {
            "chunk_id": "I1",
            "text": "应收账款增加",
            "page": 4,
            "source_file": "chain.pdf",
            "section": "资产",
            "type": "paragraph",
            "table_md": "",
        },
        {
            "chunk_id": "I-WS",
            "text": "   \n",
            "page": 5,
            "source_file": "demo.pdf",
            "section": "",
            "type": "paragraph",
            "table_md": "",
        },
        {
            "chunk_id": "I3",
            "text": "经营现金流增长",
            "page": 6,
            "source_file": "chain.pdf",
            "section": "现金流",
            "type": "paragraph",
            "table_md": "",
        },
    ]

    def fake_embed(texts: list[str]) -> list[list[float]]:
        assert texts == ["应收账款增加", "经营现金流增长"]
        return [[1.0, 0.0], [0.0, 1.0]]

    try:
        aligned_rows = build_aligned_rows(raw_chunks, fake_embed)
        result = replace_document_rows(client, collection_name, "D-CHAIN", aligned_rows)

        assert all("vector" not in raw for raw in raw_chunks)

        assert (result.inserted, result.updated, result.skipped) == (2, 0, 0)
        assert result.final_ids == frozenset({"I1", "I3"})
        assert document_ids(client, collection_name, "D-CHAIN") == {"I1", "I3"}
        assert count_rows(client, collection_name) == 2

        stored_rows = client.query(
            collection_name=collection_name,
            filter='document_id == "D-CHAIN"',
            output_fields=[
                "chunk_id",
                "text",
                "page",
                "source_file",
                "section",
                "type",
                "table_md",
                "vector",
            ],
        )

        assert len(stored_rows) == 2

        stored_by_id = {row["chunk_id"]: row for row in stored_rows}
        assert set(stored_by_id) == {"I1", "I3"}

        raw_i1 = next(raw for raw in raw_chunks if raw["chunk_id"] == "I1")
        stored_i1 = stored_by_id["I1"]
        assert stored_i1["text"] == raw_i1["text"]
        assert stored_i1["page"] == raw_i1["page"]
        assert stored_i1["source_file"] == raw_i1["source_file"]
        assert stored_i1["section"] == raw_i1["section"]
        assert stored_i1["type"] == raw_i1["type"]
        assert stored_i1["table_md"] == raw_i1["table_md"]
        assert stored_i1["vector"] == [1.0, 0.0]

        raw_i3 = next(raw for raw in raw_chunks if raw["chunk_id"] == "I3")
        stored_i3 = stored_by_id["I3"]
        assert stored_i3["text"] == raw_i3["text"]
        assert stored_i3["page"] == raw_i3["page"]
        assert stored_i3["source_file"] == raw_i3["source_file"]
        assert stored_i3["section"] == raw_i3["section"]
        assert stored_i3["type"] == raw_i3["type"]
        assert stored_i3["table_md"] == raw_i3["table_md"]
        assert stored_i3["vector"] == [0.0, 1.0]
        assert (
            client.get(
                collection_name=collection_name,
                ids=["I-WS"],
                output_fields=["chunk_id"],
            )
            == []
        )
    finally:
        client.close()
