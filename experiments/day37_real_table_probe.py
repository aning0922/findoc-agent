import json
from pathlib import Path
from itertools import islice
from day37_structure_lab import lab_doc_chunk_to_search_chunk, LabDocChunk


def fail_splitter(text: str) -> list[str]:
    raise AssertionError(f"table 不应调用 splitter: {text}")


def real_table_probe(path: Path) -> None:
    record: dict[str, object] = {}
    with path.open(encoding="utf-8") as file:
        line = next(islice(file, 1411, 1412))
        record = json.loads(line)

    chunks: list[LabDocChunk] = []
    chunks.append(
        LabDocChunk(
            text=str(record["section"]),
            type="title",
            title_level=1,
            page=int(str(record["page"])),
            source_file=str(record["source_file"]),
            table_md="",
            section="",
            chunk_id="",
        )
    )
    chunks.append(
        LabDocChunk(
            text=str(record["text"]),
            type=str(record["type"]),
            page=int(str(record["page"])),
            source_file=str(record["source_file"]),
            table_md=str(record["table_md"]),
            section="",
            chunk_id="",
            title_level=None,
        )
    )

    output_chunks = lab_doc_chunk_to_search_chunk(chunks, fail_splitter)
    if len(output_chunks) != 1:
        raise ValueError(f"expected 1 chunk, got {len(output_chunks)}")

    keyword = "账面价值"
    print(f"input_text_has_keyword: {keyword in str(record['text'])}")
    print(f"input_payload_has_keyword: {keyword in str(record['table_md'])}")
    print(f"output_text_has_keyword: {keyword in output_chunks[0].text}")
    print(f"payload_unchanged: {str(record['table_md']) == output_chunks[0].table_md}")
    index = output_chunks[0].text.find(keyword)
    if index == -1:
        raise ValueError("关键词未找到")
    else:
        start = max(0, index - 40)
        end = min(len(output_chunks[0].text), index + len(keyword) + 40)
        print(f"output_excerpt: {output_chunks[0].text[start:end]}")


if __name__ == "__main__":
    real_table_probe(Path("data/贵州茅台2025年报_chunks.jsonl"))
