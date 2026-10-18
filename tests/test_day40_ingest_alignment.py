from typing import Any

import pytest

from app.rag.ingest import build_aligned_rows


@pytest.mark.parametrize("empty_text", ["", "   \n"])
def test_rows_keep_vectors_bound_to_the_same_legal_chunks(empty_text: str) -> None:

    def fake_embed(texts: list[str]) -> list[list[float]]:
        assert texts == ["营收增长", "库存下降"]
        vector_by_text = {
            "营收增长": [1.0, 0.0],
            "库存下降": [0.0, 1.0],
        }
        return [vector_by_text[text] for text in texts]

    raw_chunks = [
        {
            "chunk_id": "A",
            "text": "营收增长",
            "page": 1,
            "source_file": "demo.pdf",
            "section": "",
            "type": "paragraph",
            "table_md": "",
        },
        {
            "chunk_id": "E",
            "text": empty_text,
            "page": 2,
            "source_file": "demo.pdf",
            "section": "",
            "type": "paragraph",
            "table_md": "",
        },
        {
            "chunk_id": "C",
            "text": "库存下降",
            "page": 3,
            "source_file": "demo.pdf",
            "section": "",
            "type": "paragraph",
            "table_md": "",
        },
    ]
    rows = build_aligned_rows(raw_chunks, fake_embed)

    assert [row["chunk_id"] for row in rows] == ["A", "C"]
    assert rows[0]["vector"] == [1.0, 0.0]
    assert rows[1]["vector"] == [0.0, 1.0]

    assert rows[1]["text"] == "库存下降"
    assert rows[1]["page"] == 3
    assert rows[1]["source_file"] == "demo.pdf"
    assert rows[1]["section"] == ""
    assert rows[1]["type"] == "paragraph"
    assert rows[1]["table_md"] == ""


def test_short_vector_result_does_not_silently_build_partial_rows() -> None:
    def fake_short_embed(texts: list[str]) -> list[list[float]]:
        assert texts == ["营收增长", "库存下降"]
        return [[1.0, 0.0]]

    raw_chunks = [
        {
            "chunk_id": "A",
            "text": "营收增长",
            "page": 1,
            "source_file": "demo.pdf",
            "section": "",
            "type": "paragraph",
            "table_md": "",
        },
        {
            "chunk_id": "C",
            "text": "库存下降",
            "page": 3,
            "source_file": "demo.pdf",
            "section": "",
            "type": "paragraph",
            "table_md": "",
        },
    ]

    with pytest.raises(ValueError, match="vectors 长度与 legal_chunks 长度不一致"):
        build_aligned_rows(raw_chunks, fake_short_embed)


@pytest.mark.parametrize(
    ("invalid_chunk", "error_pattern"),
    [
        ({"chunk_id": "N", "text": None}, "text"),
        ({"chunk_id": "M"}, "text"),
        ({"chunk_id": "I", "text": 123}, "text"),
        ({"text": "正常内容"}, "chunk_id"),
    ],
)
def test_invalid_chunk_fails_before_embedding(
    invalid_chunk: dict[str, Any],
    error_pattern: str,
) -> None:
    def must_not_embed(texts: list[str]) -> list[list[float]]:
        raise AssertionError(f"embedder不应被调用：{texts}")

    with pytest.raises(ValueError, match=error_pattern):
        build_aligned_rows([invalid_chunk], must_not_embed)


def test_gate_variant_rejects_short_vector_list_before_row_assembly() -> None:
    raw_chunks = [
        {
            "chunk_id": "G1",
            "text": "供应商欠款增加",
            "page": 2,
            "source_file": "gate.pdf",
        },
        {
            "chunk_id": "G-WS",
            "text": "  \t\n",
            "page": 2,
            "source_file": "gate.pdf",
        },
        {
            "chunk_id": "G3",
            "text": "经营现金流改善",
            "page": 3,
            "source_file": "gate.pdf",
        },
    ]

    def fake_embedder(texts: list[str]) -> list[list[float]]:
        assert texts == ["供应商欠款增加", "经营现金流改善"]
        return [[0.6, 0.8]]

    with pytest.raises(ValueError, match="vectors 长度与 legal_chunks 长度不一致"):
        build_aligned_rows(raw_chunks, fake_embedder)
