from pathlib import Path
from typing import Any

from app.rag.store import (
    MilvusSearchStore,
    ensure_collection,
    get_client,
    insert_rows,
)


def test_milvus_search_store_applies_source_filter_and_maps_score(tmp_path: Path) -> None:
    """真实 Milvus 搜索必须应用 source_file 过滤并把 distance 映射成 score"""
    db_path = tmp_path / "day41_retriever.db"
    collection = "day41_source_filter"
    client = get_client(str(db_path))

    try:
        ensure_collection(client, collection, dim=2)
        rows: list[dict[str, Any]] = [
            {
                "id": 1,
                "vector": [1.0, 0.0],
                "chunk_id": "A-1",
                "text": "甲公司营业收入100亿元",
                "page": 1,
                "source_file": "a.pdf",
                "section": "财务数据",
                "type": "paragraph",
                "table_md": None,
            },
            {
                "id": 2,
                "vector": [0.8, 0.2],
                "chunk_id": "A-2",
                "text": "甲公司营业利润20亿元",
                "page": 2,
                "source_file": "a.pdf",
                "section": "财务数据",
                "type": "paragraph",
                "table_md": None,
            },
            {
                "id": 3,
                "vector": [1.0, 0.0],
                "chunk_id": "B-1",
                "text": "乙公司营业收入200亿元",
                "page": 1,
                "source_file": "b.pdf",
                "section": "财务数据",
                "type": "paragraph",
                "table_md": None,
            },
        ]
        insert_rows(client, collection, rows)

        store = MilvusSearchStore(client, collection)
        actual = store.search([1.0, 0.0], top_k=3, filter_expression='source_file == "a.pdf"')

        assert [hit["chunk_id"] for hit in actual] == ["A-1", "A-2"]
        assert all(hit["source_file"] == "a.pdf" for hit in actual)
        assert all(isinstance(hit["score"], float) for hit in actual)
        assert all("distance" not in hit for hit in actual)

    finally:
        client.close()
