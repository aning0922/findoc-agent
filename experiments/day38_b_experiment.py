import json
from pathlib import Path

from app.rag.parse.mineru_adapter import parse_mineru_output
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.rag.parse.models import DocChunk
import app.rag.chunk as chunk_module
from unittest.mock import patch
from statistics import median, quantiles

SOURCE_JSON = Path("experiments/day38_b_sample/boe_raw_782_787_content_list.json")
RESULTS_JSON = Path("experiments/day38_b_results.json")
BLIND_JSON = Path("experiments/day38_b_blind_sample.json")

CONFIGS = [
    ("S200", 200, 10),
    ("S400", 400, 10),
    ("S800", 800, 10),
    ("O60", 400, 60),
]


def build_experiment_splitter(size: int, overlap: int) -> RecursiveCharacterTextSplitter:
    """
    使用与生产代码相同的：
    - RecursiveCharacterTextSplitter
    - cl100k_base
    - CHINESE_SEPARATORS

    只让size和overlap来自参数。
    """
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=size,
        chunk_overlap=overlap,
        separators=chunk_module.CHINESE_SEPARATORS,
    )
    return splitter


def build_piece_groups(coarse_blocks: list[DocChunk], size: int, overlap: int) -> list[dict]:
    """
    将coarse_blocks分成piece_groups，每个元素是一个字典，包含：
    - raw_index
    - coarse_index
    - type
    - source_text
    - pieces
    - page
    - section
    - source_file
    - table_md
    """
    piece_groups = []
    splitter = build_experiment_splitter(size, overlap)
    for i, block in enumerate(coarse_blocks):
        index = i + 782
        if block.type == "title":
            continue
        if block.type == "table":
            pieces = [block.text]
        else:
            pieces = splitter.split_text(block.text)
        piece_groups.append(
            {
                "raw_index": index,
                "coarse_index": i,
                "type": block.type,
                "source_text": block.text,
                "pieces": pieces,
                "page": block.page,
                "section": block.section,
                "source_file": block.source_file,
                "table_md": block.table_md,
            }
        )
    return piece_groups


def flatten_piece_groups(piece_groups: list[dict]) -> list[dict]:
    """
    将piece_groups扁平化，得到一个列表，每个元素是一个字典，包含：
    - raw_index
    - coarse_index
    - piece_index
    - piece_text
    - type
    - page
    - section
    - source_file
    - table_md
    """
    flattened = []
    for group in piece_groups:
        for piece_index, piece in enumerate(group["pieces"]):
            flattened.append(
                {
                    "raw_index": group["raw_index"],
                    "coarse_index": group["coarse_index"],
                    "piece_index": piece_index,
                    "piece_text": piece,
                    "type": group["type"],
                    "page": group["page"],
                    "section": group["section"],
                    "source_file": group["source_file"],
                    "table_md": group["table_md"],
                }
            )
    return flattened


def assert_piece_alignment(piece_origins: list[dict], chunks: list[DocChunk]) -> None:
    assert len(piece_origins) == len(chunks)
    for piece_origin, chunk in zip(piece_origins, chunks):
        assert piece_origin["piece_text"] == chunk.text
        assert piece_origin["type"] == chunk.type
        assert piece_origin["page"] == chunk.page
        expected_section = piece_origin["section"] or "未分节"
        assert expected_section == chunk.section
        assert piece_origin["source_file"] == chunk.source_file
        assert piece_origin["table_md"] == chunk.table_md


def run_config(coarse_blocks: list[DocChunk], size: int, overlap: int) -> list[DocChunk]:
    """
    1. 创建本组splitter；
    2. 临时让chunk_module.recursive_chunk指向splitter.split_text；
    3. 调用生产chunk_module.chunk_docment(coarse_blocks)；
    4. 调用结束后恢复原函数；
    5. 返回精块。
    """
    splitter = build_experiment_splitter(size, overlap)
    with patch.object(chunk_module, "recursive_chunk", splitter.split_text):
        chunks = chunk_module.chunk_docment(coarse_blocks)
    return chunks


def build_chunk_rows(
    config_name: str, size: int, overlap: int, chunks: list[DocChunk]
) -> list[dict]:
    if (config_name, size, overlap) not in CONFIGS:
        raise ValueError(f"Config not found for size={size} and overlap={overlap}")
    rows = []
    for index, chunk in enumerate(chunks):
        token_len = chunk_module.count_tokens(chunk.text)
        rows.append(
            {
                "config_name": config_name,
                "chunk_size": size,
                "overlap": overlap,
                "chunk_index": index,
                "type": chunk.type,
                "char_len": len(chunk.text),
                "token_len": token_len,
                "empty": not chunk.text.strip(),
                "over_limit": token_len > size,
                "page": chunk.page,
                "section": chunk.section,
                "source_file": chunk.source_file,
                "table_md_len": len(chunk.table_md or ""),
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "table_md": chunk.table_md,
            }
        )
    return rows


def describe_values(values: list[int]) -> dict:
    if not values:
        return {"count": 0, "p50": None, "p95": None, "max": None}
    if len(values) == 1:
        only_value = values[0]
        return {
            "count": 1,
            "p50": only_value,
            "p95": only_value,
            "max": only_value,
        }
    return {
        "count": len(values),
        "p50": median(values),
        "p95": quantiles(values, n=100, method="inclusive")[94],
        "max": max(values),
    }


def describe_rows(rows: list[dict]) -> dict:
    char_values = [row["char_len"] for row in rows]
    token_values = [row["token_len"] for row in rows]

    return {
        "chars": describe_values(char_values),
        "tokens": describe_values(token_values),
    }


def build_length_summary(rows: list[dict]) -> dict:
    """
    构建rows的摘要。
    """
    paragraph_rows = [row for row in rows if row["type"] == "paragraph"]

    return {
        "all": describe_rows(rows),
        "paragraphs": describe_rows(paragraph_rows),
    }


def measure_source_coverage(source_text: str, pieces: list[str]) -> dict:
    """
    测量source_text被pieces覆盖的程度。
    """
    count_list = []
    source_text_len = len(source_text)
    for i in range(source_text_len):
        count_list.append(0)
    search_start = 0
    start_and_end_list = []
    for piece in pieces:
        index = source_text.find(piece, search_start)
        if index == -1:
            raise ValueError(f"Piece {piece} not found in source text")

        next_index = source_text.find(piece, index + 1)
        if next_index != -1:
            raise ValueError("精块在同一粗正文中存在多个候选位置")

        end = index + len(piece)
        start_and_end_list.append((index, end))
        for i in range(index, end):
            count_list[i] += 1
        search_start = index + 1

    content_positions = [i for i, char in enumerate(source_text) if not char.isspace()]

    if not content_positions:
        raise ValueError("source_text没有非空白字符")

    covered_chars = sum(count_list[i] > 0 for i in content_positions)

    duplicate_chars = sum(max(count_list[i] - 1, 0) for i in content_positions)

    coverage_ratio = covered_chars / len(content_positions)

    return {
        "coverage_ratio": coverage_ratio,
        "duplicate_chars": duplicate_chars,
        "start_and_end_list": start_and_end_list,
        "source_nonspace_chars": len(content_positions),
        "covered_nonspace_chars": covered_chars,
    }


def build_coverage_summary(piece_groups: list[dict]) -> dict:
    """
    构建piece_groups的覆盖率摘要。
    """
    paragraph_list = []
    for group in piece_groups:
        if group["type"] == "paragraph":
            measurement = measure_source_coverage(group["source_text"], group["pieces"])
            paragraph_list.append(
                {
                    "raw_index": group["raw_index"],
                    "coarse_index": group["coarse_index"],
                    "source_nonspace_chars": measurement["source_nonspace_chars"],
                    "covered_nonspace_chars": measurement["covered_nonspace_chars"],
                    "coverage_ratio": measurement["coverage_ratio"],
                    "duplicate_chars": measurement["duplicate_chars"],
                    "start_and_end_list": measurement["start_and_end_list"],
                }
            )
    source_total = sum(paragraph["source_nonspace_chars"] for paragraph in paragraph_list)
    covered_total = sum(paragraph["covered_nonspace_chars"] for paragraph in paragraph_list)
    if source_total == 0:
        raise ValueError("没有可统计的正文字符")
    total_coverage_ratio = covered_total / source_total
    summary = {
        "source_nonspace_chars": source_total,
        "covered_nonspace_chars": covered_total,
        "coverage_ratio": total_coverage_ratio,
        "duplicate_chars": sum(paragraph["duplicate_chars"] for paragraph in paragraph_list),
        "paragraphs": paragraph_list,
    }
    return summary


def build_basic_summary(rows: list[dict]) -> dict:
    table_rows = [
        {
            "chunk_index": row["chunk_index"],
            "char_len": row["char_len"],
            "token_len": row["token_len"],
            "table_md_len": row["table_md_len"],
            "over_limit": row["over_limit"],
        }
        for row in rows
        if row["type"] == "table"
    ]

    nonempty_chunk_ids = [row["chunk_id"] for row in rows if row["chunk_id"]]

    return {
        "chunk_count": len(rows),
        "type_counts": {
            "paragraph": sum(row["type"] == "paragraph" for row in rows),
            "table": sum(row["type"] == "table" for row in rows),
            "title": sum(row["type"] == "title" for row in rows),
        },
        "lengths": build_length_summary(rows),
        "empty_count": sum(row["empty"] for row in rows),
        "over_limit_count": sum(row["over_limit"] for row in rows),
        "over_limit_by_type": {
            "paragraph": sum(row["over_limit"] and row["type"] == "paragraph" for row in rows),
            "table": sum(row["over_limit"] and row["type"] == "table" for row in rows),
        },
        "metadata_values": {
            "pages": sorted({row["page"] for row in rows}),
            "sections": sorted({row["section"] for row in rows}),
            "source_files": sorted({row["source_file"] for row in rows}),
        },
        "table_rows": table_rows,
        "empty_chunk_id_count": sum(not row["chunk_id"] for row in rows),
        "unique_chunk_id_count": len(set(nonempty_chunk_ids)),
    }


def execute_config(
    config_name: str,
    size: int,
    overlap: int,
    coarse_blocks: list[DocChunk],
) -> dict:
    """
    执行一个配置，返回一个字典，包含：
    - config
    - summary
    - rows
    """
    piece_groups = build_piece_groups(coarse_blocks, size, overlap)
    piece_origins = flatten_piece_groups(piece_groups)

    chunks = run_config(coarse_blocks, size, overlap)

    assert_piece_alignment(piece_origins, chunks)

    rows = build_chunk_rows(
        config_name,
        size,
        overlap,
        chunks,
    )
    assert len(rows) == len(piece_origins)

    for row, origin in zip(rows, piece_origins):
        row["raw_index"] = origin["raw_index"]
        row["coarse_index"] = origin["coarse_index"]
        row["piece_index"] = origin["piece_index"]

    raw_indices = [origin["raw_index"] for origin in piece_origins]
    order_preserved = raw_indices == sorted(raw_indices)
    assert order_preserved
    basic_summary = build_basic_summary(rows)
    coverage_summary = build_coverage_summary(piece_groups)
    return {
        "config": {
            "name": config_name,
            "chunk_size": size,
            "overlap": overlap,
        },
        "summary": {
            **basic_summary,
            "coverage": coverage_summary,
            "alignment_ok": True,
            "order_preserved": order_preserved,
        },
        "rows": rows,
    }


def select_blind_rows(config_results: list[dict]) -> list[dict]:
    assert len(config_results) == 4

    selected: list[dict] = []

    for result in config_results:
        rows = result["rows"]

        table_rows = [row for row in rows if row["type"] == "table"]
        paragraph_rows = [row for row in rows if row["type"] == "paragraph"]

        # 固定样本中每组应有1个表格、至少3个正文块
        assert len(table_rows) == 1
        assert len(paragraph_rows) >= 3

        paragraph_indices = sorted(
            {
                0,
                len(paragraph_rows) // 2,
                len(paragraph_rows) - 1,
            }
        )
        assert len(paragraph_indices) == 3

        chosen_rows = [table_rows[0]]
        chosen_rows.extend(paragraph_rows[index] for index in paragraph_indices)

        # 使用副本，避免给完整实验结果中的row添加blind_index
        for row in chosen_rows:
            blind_row = dict(row)
            blind_row["blind_index"] = len(selected)
            selected.append(blind_row)

    # 4个配置，每组4块
    assert len(selected) == 16

    return selected


def main() -> None:
    content = SOURCE_JSON.read_text(encoding="utf-8")
    raw_data = json.loads(content)

    assert isinstance(raw_data, list)

    # 1. 校验确实取到6项
    assert len(raw_data) == 6

    # 2. 校验原始type顺序
    expected_types = ["text", "text", "text", "text", "table", "text"]
    assert [item["type"] for item in raw_data] == expected_types

    # 3. 表格可能没有text_level键，所以这里要使用.get()
    expected_levels = [2, 2, None, None, None, None]
    assert [item.get("text_level") for item in raw_data] == expected_levels

    # 4. 六项都来自page_idx=72
    assert all(item["page_idx"] == 72 for item in raw_data)

    # 5. 第5项，也就是sample[4]，必须是非空表格
    assert raw_data[4]["type"] == "table"
    assert raw_data[4].get("table_body", "").strip()

    # 6. 不允许过滤掉这个被识别成标题的复选框文本
    assert raw_data[0].get("text") == "十七、其他重大事项的说明"
    assert raw_data[1].get("text") == "适用 □不适用"

    coarse_blocks = parse_mineru_output(
        "experiments/day38_b_sample",
        "京东方A 2025年报.pdf",
    )
    assert len(coarse_blocks) == 6
    assert [block.type for block in coarse_blocks] == [
        "title",
        "title",
        "paragraph",
        "paragraph",
        "table",
        "paragraph",
    ]
    assert [block.section for block in coarse_blocks] == [
        "十七、其他重大事项的说明",
        "适用 □不适用",
        "适用 □不适用",
        "适用 □不适用",
        "适用 □不适用",
        "适用 □不适用",
    ]

    assert [block.text for block in coarse_blocks if block.type == "table"][0].startswith(
        "第73页表格\n"
    )

    assert coarse_blocks[4].table_md == raw_data[4]["table_body"]
    assert all(block.source_file == "京东方A 2025年报.pdf" for block in coarse_blocks)
    assert all(block.page == 73 for block in coarse_blocks)

    assert describe_values([])["p50"] is None
    assert describe_values([123])["p95"] == 123
    assert describe_values([100, 200, 300])["p50"] == 200

    overlap_case = measure_source_coverage(
        "ABCDEFGHIJ",
        ["ABCDEF", "EFGHIJ"],
    )
    assert overlap_case["coverage_ratio"] == 1.0
    assert overlap_case["duplicate_chars"] == 2
    assert overlap_case["start_and_end_list"] == [(0, 6), (4, 10)]

    space_case = measure_source_coverage(
        "AB CD",
        ["AB", "CD"],
    )
    assert space_case["coverage_ratio"] == 1.0
    assert space_case["duplicate_chars"] == 0

    config_results = [
        execute_config(
            config_name,
            size,
            overlap,
            coarse_blocks,
        )
        for config_name, size, overlap in CONFIGS
    ]

    blind_rows = select_blind_rows(config_results)

    artifact = {
        "experiment": {
            "production_head": "66592e4",
            "sample": "京东方A 2025年报 raw 782-787",
            "raw_start": 782,
            "raw_stop": 788,
            "raw_count": 6,
            "tokenizer": "cl100k_base",
            "percentile_method": "statistics.quantiles inclusive",
            "coverage_scope": "adapter粗正文到最终paragraph精块",
        },
        "configs": config_results,
    }

    RESULTS_JSON.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    BLIND_JSON.write_text(
        json.dumps(blind_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for result in config_results:
        config = result["config"]
        summary = result["summary"]
        paragraph_tokens = summary["lengths"]["paragraphs"]["tokens"]
        coverage = summary["coverage"]

        print(
            f"{config['name']} "
            f"size={config['chunk_size']} "
            f"overlap={config['overlap']} "
            f"chunks={summary['chunk_count']} "
            f"paragraph_tokens="
            f"{paragraph_tokens['p50']}/"
            f"{paragraph_tokens['p95']}/"
            f"{paragraph_tokens['max']} "
            f"coverage={coverage['coverage_ratio']:.4f} "
            f"duplicate_chars={coverage['duplicate_chars']} "
            f"empty={summary['empty_count']} "
            f"over_limit_p="
            f"{summary['over_limit_by_type']['paragraph']} "
            f"over_limit_t="
            f"{summary['over_limit_by_type']['table']}"
        )

    print(f"results={RESULTS_JSON}")
    print(f"blind_sample={BLIND_JSON} count={len(blind_rows)}")


if __name__ == "__main__":
    main()
