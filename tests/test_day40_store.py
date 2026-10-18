from pathlib import Path
from typing import Any

from app.rag.store import get_client, ensure_collection, insert_rows, search


def test_search_cosine_score_is_larger_when_more_similar(tmp_path: Path) -> None:
    db_path = tmp_path / "day40_store.db"
    collection = "day40_cosine_direction"

    client = get_client(str(db_path))
    try:
        ensure_collection(client, collection, dim=2)
        rows: list[dict[str, Any]] = [
            {
                "id": 101,
                "document_id": "D-ACME",
                "chunk_id": "C-REV",
                "text": "甲公司营收增长",
                "page": 7,
                "source_file": "acme.pdf",
                "section": "经营情况",
                "type": "paragraph",
                "table_md": "",
                "vector": [1.0, 0.0],
            },
            {
                "id": 102,
                "document_id": "D-ACME",
                "chunk_id": "C-MIX",
                "text": "甲公司营收与利润均增长",
                "page": 8,
                "source_file": "acme.pdf",
                "section": "经营情况",
                "type": "paragraph",
                "table_md": "",
                "vector": [1.0, 1.0],
            },
            {
                "id": 103,
                "document_id": "D-OCEAN",
                "chunk_id": "C-DOLPHIN",
                "text": "海豚通过回声定位",
                "page": 2,
                "source_file": "ocean.pdf",
                "section": "海洋生物",
                "type": "paragraph",
                "table_md": "",
                "vector": [-1.0, 0.0],
            },
        ]
        inserted = insert_rows(client, collection, rows)
        assert inserted == 3

        hits = search(client, collection, query_vec=[1.0, 0.0], top_k=3)

        assert [hit["chunk_id"] for hit in hits] == ["C-REV", "C-MIX", "C-DOLPHIN"]

        score = [hit["distance"] for hit in hits]

        assert score[0] > score[1] > score[2]

        assert hits[0]["text"] == "甲公司营收增长"
        assert hits[0]["page"] == 7
        assert hits[0]["source_file"] == "acme.pdf"
        assert hits[0]["section"] == "经营情况"
        assert hits[0]["type"] == "paragraph"
        assert hits[0]["table_md"] == ""
    finally:
        client.close()
