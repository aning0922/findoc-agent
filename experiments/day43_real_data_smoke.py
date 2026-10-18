"""
职责：只读检查三份真实 MinerU content_list 是否满足 Day43 生产归一化合同。
输入：仓库内固定的三份源 PDF 和对应原始 content_list。
输出：每份文档的 smoke 质量报告。
失败：任何硬性不变量被破坏时，以非零状态结束。
限制：不写 JSONL、不生成 embedding、不访问 Milvus。
"""

import json
from pathlib import Path
from app.rag.parse.mineru_adapter import parse_mineru_output, PAGE_FURNITURE_TYPES
from app.rag.parse.models import DocChunk
from experiments.day43_config import REAL_DOCUMENTS


def load_raw_elements(content_list_file: Path) -> list[dict[str, object]]:
    """
    从 content_list.json 文件加载原始元素列表。
    Args:
        content_list_file: content_list.json 文件路径
    Returns:
        list[dict[str, object]]: 保持原始顺序的元素字典列表。
    Raises:
        FileNotFoundError: 输入文件不存在。
        ValueError: JSON 语法错误、顶层不是列表，或者某个元素不是字典。
    """
    content = content_list_file.read_text(encoding="utf-8")
    try:
        json_data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"文件 {content_list_file} 不是合法 JSON：{exc}") from exc
    if not isinstance(json_data, list):
        raise ValueError(f"文件 {content_list_file} 的 JSON 顶层不是 list")
    for index, raw in enumerate(json_data):
        if not isinstance(raw, dict):
            raise ValueError(f"文件 {content_list_file} 的第 {index} 个元素不是 dict")
    return json_data


def count_raw_types(elements: list[dict[str, object]], content_list_file: Path) -> dict[str, int]:
    """
    统计原始元素列表中各种类型的数量。
    Args:
        elements: 原始元素列表
        content_list_file: 当前元素列表所属的原始 JSON 路径，仅用于错误定位。
    Returns:
        dict[str, int]: 类型数量字典
    Raises:
        ValueError: 元素类型为 None、不是 str、为空字符串。
    """
    type_count: dict[str, int] = {}
    for index, element in enumerate(elements):
        element_type = element.get("type")
        if element_type is None:
            raise ValueError(f"文件 {content_list_file} 的第 {index} 个元素类型为 None")
        if not isinstance(element_type, str):
            raise ValueError(f"文件 {content_list_file} 的第 {index} 个元素类型不是 str")
        if element_type.strip() == "":
            raise ValueError(f"文件 {content_list_file} 的第 {index} 个元素类型为空字符串")
        type_count[element_type] = type_count.get(element_type, 0) + 1
    return type_count


def build_document_smoke_report(source_file: str, content_list_file: Path) -> dict[str, object]:
    """只读检查一份真实文档；输入是稳定源文件名和精确原始 JSON 路径；输出是单文档 smoke 报告；生产解析异常暂时直接向上抛出"""
    loaded_elements = load_raw_elements(content_list_file)
    raw_count_by_type = count_raw_types(loaded_elements, content_list_file)
    parsed_result = parse_mineru_output(str(content_list_file.parent), source_file)
    raw_table_count = raw_count_by_type.get("table", 0)
    output_table_count = len([chunk for chunk in parsed_result.chunks if chunk.type == "table"])
    raw_element_count = len(loaded_elements)
    failure_reasons: list[str] = []
    if (
        raw_element_count
        != parsed_result.stats.output_chunk_count + parsed_result.stats.skipped_element_count
    ):
        failure_reasons.append(
            f"元素总账不守恒：raw={raw_element_count}，"
            f"output={parsed_result.stats.output_chunk_count}，"
            f"skipped={parsed_result.stats.skipped_element_count}"
        )
    if len(parsed_result.chunks) != parsed_result.stats.output_chunk_count:
        failure_reasons.append(
            f"输出统计不一致：len(chunks)={len(parsed_result.chunks)}，"
            f"stats.output_chunk_count={parsed_result.stats.output_chunk_count}"
        )
    empty_table_shell_count = parsed_result.stats.skipped_count_by_reason.get(
        "empty_table_shell", 0
    )
    if raw_table_count != output_table_count + empty_table_shell_count:
        failure_reasons.append(
            f"表格总账不守恒：raw_table={raw_table_count}，"
            f"output_table={output_table_count}，"
            f"empty_table_shell={empty_table_shell_count}"
        )

    table_integrity_report = inspect_table_integrity(loaded_elements, parsed_result.chunks)
    degraded_table_text_count = table_integrity_report.get("degraded_table_text_count", 0)
    html_in_table_text_count = table_integrity_report.get("html_in_table_text_count", 0)
    missing_table_md_count = table_integrity_report.get("missing_table_md_count", 0)
    table_md_mismatch_count = table_integrity_report.get("table_md_mismatch_count", 0)
    if degraded_table_text_count > 0:
        failure_reasons.append(
            f"表格检索文本退化：{degraded_table_text_count} 个 table chunk 缺少可检索表体"
        )
    if html_in_table_text_count > 0:
        failure_reasons.append(
            f"表格检索文本退化：{html_in_table_text_count} 个 table chunk 包含 HTML 标签"
        )
    if missing_table_md_count > 0:
        failure_reasons.append(
            f"表格引用原文缺失：{missing_table_md_count} 个 table chunk 的 table_md 为空"
        )
    if table_md_mismatch_count > 0:
        failure_reasons.append(
            f"表格引用原文不一致：{table_md_mismatch_count} 个位置的 table_md 与原始 table_body 不一致"
        )

    section_integrity_report = inspect_section_integrity(loaded_elements, parsed_result.chunks)
    empty_section_count = section_integrity_report.get("empty_section_count", 0)
    nonempty_section_count = section_integrity_report.get("nonempty_section_count", 0)
    section_pollution_count = section_integrity_report.get("section_pollution_count", 0)
    if section_pollution_count > 0:
        failure_reasons.append(
            f"section 被页面杂物污染：{section_pollution_count} 个 chunk 的 section 包含 header/footer/page_number"
        )

    if empty_section_count + nonempty_section_count != len(parsed_result.chunks):
        failure_reasons.append(
            f"section 统计不守恒：empty={empty_section_count}，"
            f"nonempty={nonempty_section_count}，"
            f"chunks={len(parsed_result.chunks)}"
        )

    passed: bool = len(failure_reasons) == 0
    return {
        "source_file": source_file,
        "content_list_file": str(content_list_file),
        "raw_element_count": raw_element_count,
        "raw_count_by_type": raw_count_by_type,
        **parsed_result.stats.model_dump(),
        **table_integrity_report,
        **section_integrity_report,
        "raw_table_count": raw_table_count,
        "output_table_count": output_table_count,
        "passed": passed,
        "failure_reasons": failure_reasons,
    }


def inspect_table_integrity(
    raw_elements: list[dict[str, object]], chunks: list[DocChunk]
) -> dict[str, int]:
    """只读检查输出表格的检索文本与引用原文，返回四种缺陷数量，不修改输入对象。"""
    tag_strs: list[str] = ["<table", "<tr", "<td", "<th", "</table>", "</tr>", "</td>", "</th>"]
    degraded_table_text_count: int = 0
    html_in_table_text_count: int = 0
    missing_table_md_count: int = 0
    table_md_mismatch_count: int = 0
    for chunk in chunks:
        if chunk.type != "table":
            continue

        texts: list[str] = chunk.text.strip().split("\n", 1)
        if len(texts) != 2 or not texts[1].strip():
            degraded_table_text_count += 1
        text_lower = chunk.text.lower()
        if any(tag in text_lower for tag in tag_strs):
            html_in_table_text_count += 1

        if not isinstance(chunk.table_md, str) or not chunk.table_md.strip():
            missing_table_md_count += 1

    raw_table_mds: list[str] = []
    chunk_table_mds: list[str | None] = []
    for raw in raw_elements:
        if raw.get("type") == "table":
            table_md = raw.get("table_body")
            if isinstance(table_md, str) and table_md.strip() != "":
                raw_table_mds.append(table_md)

    for chunk in chunks:
        if chunk.type == "table":
            table_md = chunk.table_md
            chunk_table_mds.append(table_md)

    for raw_table_md, chunk_table_md in zip(raw_table_mds, chunk_table_mds):
        if raw_table_md != chunk_table_md:
            table_md_mismatch_count += 1

    table_md_mismatch_count += abs(len(raw_table_mds) - len(chunk_table_mds))

    return {
        "degraded_table_text_count": degraded_table_text_count,
        "html_in_table_text_count": html_in_table_text_count,
        "missing_table_md_count": missing_table_md_count,
        "table_md_mismatch_count": table_md_mismatch_count,
    }


def inspect_section_integrity(
    raw_elements: list[dict[str, object]], chunks: list[DocChunk]
) -> dict[str, int]:
    """只读统计 chunk 的 section 使用情况，并检查页面杂物是否污染 section。"""
    page_furniture_texts: set[str] = set()

    for raw in raw_elements:
        raw_type = raw.get("type")
        raw_text = raw.get("text")
        if raw_type in PAGE_FURNITURE_TYPES and isinstance(raw_text, str) and raw_text.strip():
            page_furniture_texts.add(raw_text.strip())

    empty_section_count = 0
    nonempty_section_count = 0
    section_pollution_count = 0

    for chunk in chunks:
        section = chunk.section.strip()

        if not section:
            empty_section_count += 1
            continue

        nonempty_section_count += 1
        section_parts = {part.strip() for part in section.split("/") if part.strip()}

        if section_parts & page_furniture_texts:
            section_pollution_count += 1

    return {
        "empty_section_count": empty_section_count,
        "nonempty_section_count": nonempty_section_count,
        "section_pollution_count": section_pollution_count,
    }


def main() -> int:
    """生成三份真实文档的只读 smoke 报告，并返回整体检查退出码。"""
    reports: list[dict[str, object]] = []

    for document in REAL_DOCUMENTS:
        report = build_document_smoke_report(
            document["source_file"],
            document["content_list_file"],
        )
        reports.append(report)

    print(json.dumps(reports, ensure_ascii=False, indent=2))

    if all(report.get("passed") is True for report in reports):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
