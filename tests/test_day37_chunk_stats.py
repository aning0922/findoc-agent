import importlib
from app.rag.parse.models import DocChunk
import pytest
from typing import Literal


def test_try_chunk_reports_coarse_and_fine_counts_from_different_lists(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:

    coarse_blocks = []
    coarse_blocks.append(
        DocChunk(
            text="甲乙",
            type="paragraph",
            page=1,
            source_file="test.txt",
            section="",
            chunk_id="",
        )
    )
    coarse_blocks.append(
        DocChunk(
            text="丙丁",
            type="paragraph",
            page=1,
            source_file="test.txt",
            section="",
            chunk_id="",
        )
    )

    def parse_pdf(
        path: str, backend: Literal["fast", "mineru"] = "fast", mineru_out: str | None = None
    ) -> list[DocChunk]:

        return coarse_blocks

    def chunk_docment(input_blocks: list[DocChunk]) -> list[DocChunk]:
        assert input_blocks is coarse_blocks

        blocks: list[DocChunk] = []
        blocks.append(
            DocChunk(
                text="甲",
                type="paragraph",
                page=1,
                source_file="test.txt",
                section="",
                chunk_id="",
            )
        )
        blocks.append(
            DocChunk(
                text="乙",
                type="paragraph",
                page=1,
                source_file="test.txt",
                section="",
                chunk_id="",
            )
        )
        blocks.append(
            DocChunk(
                text="丙",
                type="paragraph",
                page=1,
                source_file="test.txt",
                section="",
                chunk_id="",
            )
        )
        blocks.append(
            DocChunk(
                text="丁",
                type="paragraph",
                page=1,
                source_file="test.txt",
                section="",
                chunk_id="",
            )
        )
        return blocks

    def save_chunks(chunks: list[DocChunk], path: str = "chunks.jsonl") -> None:
        pass

    monkeypatch.setattr("app.rag.parse.parse_pdf", parse_pdf)
    monkeypatch.setattr("app.rag.chunk.chunk_docment", chunk_docment)
    monkeypatch.setattr("app.rag.chunk.save_chunks", save_chunks)

    importlib.import_module("scripts.try_chunk")

    out, _ = capsys.readouterr()
    assert out.strip() == "粗块数: 2 + 精块数: 4"
