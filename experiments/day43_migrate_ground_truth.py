"""把冻结的 Day42 ground truth 迁移到 Day43 v2 chunk 身份。

职责：
1. 读取并验证冻结的12题 Day42题集。
2. 按 chunk_id 精确查询 legacy/v2 collection。
3. 验证13组 legacy/v2 chunk 承载同一份原文证据。
4. 只替换 relevant_chunk_ids 和 expected_metadata。
5. 原子写入并重新加载 eval/day43_questions_v2.jsonl。

限制：
不生成 embedding，不执行向量检索，不计算指标，不修改 collection，
不覆盖 eval/day42_questions.jsonl。
"""

import hashlib
import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, cast

from pymilvus import MilvusClient

from app.rag.store import get_client
from experiments.day43_config import (
    BUILD_ID,
    DEMO_WORKSPACE_ID,
    LEGACY_COLLECTION_NAME,
    MILVUS_DB_PATH,
    PROJECT_ROOT,
    V2_COLLECTION_NAME,
)


LEGACY_QUESTION_PATH = PROJECT_ROOT / "eval/day42_questions.jsonl"

V2_QUESTION_PATH = PROJECT_ROOT / "eval/day43_questions_v2.jsonl"

EXPECTED_QUESTION_COUNT = 12
EXPECTED_ANSWERABLE_COUNT = 10
EXPECTED_UNANSWERABLE_COUNT = 2
EXPECTED_RELEVANT_ID_COUNT = 13

SEMANTIC_QUESTION_FIELDS = (
    "case_id",
    "query",
    "category",
    "answerable",
    "source_file",
    "ground_truth",
)

COMMON_CHUNK_OUTPUT_FIELDS = [
    "chunk_id",
    "text",
    "page",
    "type",
    "source_file",
    "table_md",
    "section",
]

V2_IDENTITY_OUTPUT_FIELDS = [
    "workspace_id",
    "document_id",
    "data_version",
]

TABLE_HTML_MARKERS = (
    "<table",
    "<tr",
    "<td",
    "<th",
    "</table>",
    "</tr>",
    "</td>",
    "</th>",
)


LEGACY_TO_V2_CHUNK_ID: dict[str, str] = {
    # Q1：贵州茅台主要业务
    "19646258-7c45-4936-be5f-e9621715f24c": (
        "cfb9d3a9eb90f717fca61bc7f0d963bbb1327f9d389f37fb649eff3708fb93f0"
    ),
    # Q2：成都华微主要业务
    "a534a7fa-e40e-49d3-a029-5d882d82541e": (
        "91c0a24ba1c1761f42aa8a0cbd834240749a53554e7d5c6634b70417d549fa1d"
    ),
    # Q3：贵州茅台基本每股收益表
    "8a7a2aee-85c5-45cf-81ad-919610bbb154": (
        "3cb0f990b487c1b4fcbaf2fb430d1f5912e4af8eafdd59402f7ab1cdbd681a23"
    ),
    # Q4：京东方营业收入表
    "45986ebe-5115-430d-adc7-973e34bd6d17": (
        "8724f626cb8a0129f3158250929f967e002a4ce6a73879d6bce3f02482446b77"
    ),
    # Q6：成都华微经营活动现金流量净额变动原因
    "21121486-e64c-465d-9f42-3762ec682cbb": (
        "5e739485500376bf4ac2aae25b324859bd809dc78a61350e5cd5cb1d8113da9e"
    ),
    # Q7：京东方显示器件产品
    "1c2e77de-e97f-471c-ae8a-2bf56e9c22c0": (
        "77359bc700f95e9594c8ee4facbbb5060c86b52d23cbf9d95956bf69f2306ebf"
    ),
    # Q8：京东方显示器件收入占比表
    "332e59f2-efa5-4ed9-af37-79f1bf54f908": (
        "ade6f0673791178a6267bfe077f1e2f41c324b2d4b8a1eb2dc98f2453ec701f7"
    ),
    # Q9：贵州茅台五大核心竞争力
    "a06b431e-08c4-453f-96ee-7ebe96ef4ad1": (
        "11352699a389a7b3881ad631447123432dd4cb4f767705ffff4753642c999184"
    ),
    # Q10：成都华微现金管理最高额度正文
    "26633e24-a3ce-42e8-b0b6-a6b2c16bd707": (
        "49f7404915a07d00950862c641b9aeaf819709f197dd57a422f310ee3db522ca"
    ),
    # Q10：成都华微现金管理最高额度表格
    "58575d14-e232-4821-95bc-f0987d5f5d88": (
        "b9f974f614b16702de2def06cf3e4d50bb5731de907e33d69fa5d9fbb7c32978"
    ),
    # Q11：成都华微董事长，人员职务表
    "a97166cf-e693-456d-a908-a418f94dc9e1": (
        "33cc8277948f7c8f4b1439469f4901601944af35a0a1ae94e6a30e531fcd1f42"
    ),
    # Q11：成都华微董事长，人员经历表
    "6cb83d6c-2d18-4c8a-9e18-73ff971f36c3": (
        "83e3eaa099356fc8d260589d9d0342379fdd77183a7cb62536b59a88eefa86ca"
    ),
    # Q11：成都华微董事长，报表批准页正文
    "6cc698ea-7f5b-4b5c-8709-e07b2443c761": (
        "8730805774e4005c9dd2472e16e5cd59ab01a87dc3e2843936e69b9ba2143b3b"
    ),
}


@dataclass(frozen=True)
class QuestionSetWriteResult:
    """记录 v2 问题集原子写入后的文件摘要。"""

    path: Path
    row_count: int
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class GroundTruthMigrationResult:
    """记录 Day42 ground truth 迁移到 v2 后的审计结果。"""

    legacy_question_path: Path
    v2_question_path: Path
    question_count: int
    answerable_count: int
    unanswerable_count: int
    relevant_id_count: int
    mapped_evidence_count: int
    v2_file_byte_size: int
    v2_file_sha256: str


def load_question_set(
    path: Path,
) -> list[dict[str, Any]]:
    """加载并验证冻结的12题检索问题集。

    Args:
        path: 一行一题的 UTF-8 JSONL 路径。

    Returns:
        保持原始行顺序的问题字典列表。

    Raises:
        FileNotFoundError: 题集文件不存在。
        ValueError: JSON、字段类型、答案标签或总账不符合冻结合同。

    Limitations:
        本函数只读题集文件，不访问 Milvus。
    """
    if not path.is_file():
        raise FileNotFoundError(f"问题集文件不存在：{path}")

    questions: list[dict[str, Any]] = []
    case_ids: set[str] = set()

    required_fields = {
        "case_id",
        "query",
        "category",
        "answerable",
        "relevant_chunk_ids",
        "source_file",
        "ground_truth",
        "expected_metadata",
    }

    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue

        try:
            raw_question = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} 第 {line_number} 行不是合法 JSON：{exc}") from exc

        if not isinstance(raw_question, dict):
            raise ValueError(f"{path} 第 {line_number} 行 JSON 顶层必须是字典")

        question: dict[str, Any] = raw_question

        missing_fields = sorted(required_fields - set(question))
        if missing_fields:
            raise ValueError(f"{path} 第 {line_number} 行缺少字段：{missing_fields}")

        case_id = question.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"{path} 第 {line_number} 行 case_id 必须是非空字符串")

        if case_id in case_ids:
            raise ValueError(f"{path} 中 case_id 重复：{case_id}")
        case_ids.add(case_id)

        for field_name in (
            "query",
            "category",
            "ground_truth",
        ):
            value = question.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{path} 第 {line_number} 行 {field_name} 必须是非空字符串")

        answerable = question.get("answerable")
        if not isinstance(answerable, bool):
            raise ValueError(f"{path} 第 {line_number} 行 answerable 必须是 bool")

        source_file = question.get("source_file")
        if source_file is not None and (
            not isinstance(source_file, str) or not source_file.strip()
        ):
            raise ValueError(f"{path} 第 {line_number} 行 source_file 必须是 None 或非空字符串")

        relevant_chunk_ids = question.get("relevant_chunk_ids")
        if not isinstance(relevant_chunk_ids, list):
            raise ValueError(f"{path} 第 {line_number} 行 relevant_chunk_ids 必须是列表")

        if not all(
            isinstance(chunk_id, str) and chunk_id.strip() for chunk_id in relevant_chunk_ids
        ):
            raise ValueError(f"{path} 第 {line_number} 行包含无效相关 chunk_id")

        if len(relevant_chunk_ids) != len(set(relevant_chunk_ids)):
            raise ValueError(f"{path} 第 {line_number} 行 relevant_chunk_ids 存在重复")

        expected_metadata = question.get("expected_metadata")
        if not isinstance(expected_metadata, dict):
            raise ValueError(f"{path} 第 {line_number} 行 expected_metadata 必须是字典")

        if answerable:
            if not relevant_chunk_ids:
                raise ValueError(
                    f"{path} 第 {line_number} 行可回答题 必须至少有一个 relevant_chunk_id"
                )

            if set(expected_metadata) != set(relevant_chunk_ids):
                raise ValueError(
                    f"{path} 第 {line_number} 行 "
                    "expected_metadata 键集合必须与 "
                    "relevant_chunk_ids 完全相同"
                )
        else:
            if relevant_chunk_ids:
                raise ValueError(f"{path} 第 {line_number} 行无答案题 不能包含 relevant_chunk_ids")

            if expected_metadata:
                raise ValueError(f"{path} 第 {line_number} 行无答案题 expected_metadata 必须为空")

        questions.append(question)

    question_count = len(questions)
    answerable_count = sum(question["answerable"] for question in questions)
    unanswerable_count = question_count - answerable_count
    relevant_id_count = sum(len(question["relevant_chunk_ids"]) for question in questions)

    if question_count != EXPECTED_QUESTION_COUNT:
        raise ValueError(
            f"{path} 题数错误：expected={EXPECTED_QUESTION_COUNT}, actual={question_count}"
        )

    if answerable_count != EXPECTED_ANSWERABLE_COUNT:
        raise ValueError(
            f"{path} 可回答题数错误："
            f"expected={EXPECTED_ANSWERABLE_COUNT}, "
            f"actual={answerable_count}"
        )

    if unanswerable_count != EXPECTED_UNANSWERABLE_COUNT:
        raise ValueError(
            f"{path} 无答案题数错误："
            f"expected={EXPECTED_UNANSWERABLE_COUNT}, "
            f"actual={unanswerable_count}"
        )

    if relevant_id_count != EXPECTED_RELEVANT_ID_COUNT:
        raise ValueError(
            f"{path} 相关 ID 总数错误："
            f"expected={EXPECTED_RELEVANT_ID_COUNT}, "
            f"actual={relevant_id_count}"
        )

    return questions


def query_one_chunk(
    client: MilvusClient,
    collection_name: str,
    chunk_id: str,
    *,
    include_v2_identity: bool,
) -> dict[str, Any]:
    """按 chunk_id 从指定 collection 精确查询一条证据。

    Args:
        client: 已连接且 collection 已加载的 Milvus 客户端。
        collection_name: 要查询的 collection。
        chunk_id: 要精确查询的 chunk 主键。
        include_v2_identity: 是否同时读取 v2 身份字段。

    Returns:
        唯一匹配的 chunk 行。

    Raises:
        ValueError: collection 名或 chunk_id 无效，或者找不到记录。
        RuntimeError: 主键查询返回多行。

    Limitations:
        本函数执行主键 query，不执行向量 search。
    """
    if not isinstance(collection_name, str) or not collection_name.strip():
        raise ValueError("collection_name 必须是非空字符串")

    if not isinstance(chunk_id, str) or not chunk_id.strip():
        raise ValueError("chunk_id 必须是非空字符串")

    output_fields = list(COMMON_CHUNK_OUTPUT_FIELDS)

    if include_v2_identity:
        output_fields.extend(V2_IDENTITY_OUTPUT_FIELDS)

    chunk_id_literal = json.dumps(
        chunk_id,
        ensure_ascii=False,
    )

    # 第三方 Milvus query：按 chunk_id 主键精确读取证据，
    # 不使用向量相似度，不参与召回评测。
    raw_rows = client.query(
        collection_name=collection_name,
        filter=f"chunk_id == {chunk_id_literal}",
        output_fields=output_fields,
        limit=2,
    )
    rows = cast(list[dict[str, Any]], raw_rows)

    if not rows:
        raise ValueError(f"collection={collection_name} 中找不到 chunk_id={chunk_id}")

    if len(rows) != 1:
        raise RuntimeError(
            f"collection={collection_name} 按主键查询返回多行："
            f"chunk_id={chunk_id}, count={len(rows)}"
        )

    return rows[0]


def validate_evidence_mapping(
    *,
    client: MilvusClient,
    legacy_questions: list[dict[str, Any]],
    id_mapping: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """验证13组 legacy/v2 chunk 承载同一份原文证据。

    Args:
        client: 已连接并加载两个 collection 的 Milvus 客户端。
        legacy_questions: 已通过题集合同检查的 Day42 问题。
        id_mapping: 冻结的 legacy ID 到 v2 ID 映射。

    Returns:
        以 v2 chunk_id 为键的已验证 v2 行。

    Raises:
        ValueError: 映射集合、身份、metadata 或证据原文不一致。
        RuntimeError: 主键查询或结果总账异常。

    Limitations:
        本函数只读两个 collection，不执行向量检索。
    """
    legacy_relevant_ids: list[str] = []

    for question in legacy_questions:
        relevant_ids = question.get("relevant_chunk_ids")
        if not isinstance(relevant_ids, list):
            raise ValueError(f"case_id={question.get('case_id')} 的 relevant_chunk_ids 必须是列表")

        legacy_relevant_ids.extend(cast(list[str], relevant_ids))

    if len(legacy_relevant_ids) != EXPECTED_RELEVANT_ID_COUNT:
        raise ValueError(
            "题集 legacy 相关 ID 数错误："
            f"expected={EXPECTED_RELEVANT_ID_COUNT}, "
            f"actual={len(legacy_relevant_ids)}"
        )

    if len(legacy_relevant_ids) != len(set(legacy_relevant_ids)):
        raise ValueError("题集中的 legacy relevant_chunk_ids 存在跨题重复")

    question_legacy_ids = set(legacy_relevant_ids)
    mapping_legacy_ids = set(id_mapping)

    if question_legacy_ids != mapping_legacy_ids:
        missing_mapping = sorted(question_legacy_ids - mapping_legacy_ids)
        unexpected_mapping = sorted(mapping_legacy_ids - question_legacy_ids)
        raise ValueError(
            "legacy 题集与映射表的 ID 集合不一致："
            f"missing_mapping={missing_mapping}, "
            f"unexpected_mapping={unexpected_mapping}"
        )

    v2_ids = list(id_mapping.values())

    if len(v2_ids) != len(set(v2_ids)):
        raise ValueError("多个 legacy ID 不能映射到同一个 v2 ID")

    if set(id_mapping) & set(v2_ids):
        raise ValueError("legacy ID 与 v2 ID 集合不应发生重叠")

    v2_rows_by_chunk_id: dict[
        str,
        dict[str, Any],
    ] = {}

    for legacy_id in legacy_relevant_ids:
        v2_id = id_mapping[legacy_id]

        legacy_row = query_one_chunk(
            client,
            LEGACY_COLLECTION_NAME,
            legacy_id,
            include_v2_identity=False,
        )
        v2_row = query_one_chunk(
            client,
            V2_COLLECTION_NAME,
            v2_id,
            include_v2_identity=True,
        )

        if v2_row.get("chunk_id") != v2_id:
            raise ValueError(
                f"v2 主键返回不一致：expected={v2_id}, actual={v2_row.get('chunk_id')}"
            )

        for field_name in (
            "source_file",
            "page",
            "type",
        ):
            legacy_value = legacy_row.get(field_name)
            v2_value = v2_row.get(field_name)

            if legacy_value != v2_value:
                raise ValueError(
                    "legacy/v2 metadata 不一致："
                    f"legacy_id={legacy_id}, "
                    f"v2_id={v2_id}, "
                    f"field={field_name}, "
                    f"legacy={legacy_value!r}, "
                    f"v2={v2_value!r}"
                )

        chunk_type = legacy_row.get("type")

        if chunk_type == "paragraph":
            legacy_text = legacy_row.get("text")
            v2_text = v2_row.get("text")

            if not isinstance(legacy_text, str) or not legacy_text.strip():
                raise ValueError(f"legacy paragraph text 无效：chunk_id={legacy_id}")

            if legacy_text != v2_text:
                raise ValueError(
                    f"legacy/v2 paragraph text 不一致：legacy_id={legacy_id}, v2_id={v2_id}"
                )

        elif chunk_type == "table":
            legacy_table_md = legacy_row.get("table_md")
            v2_table_md = v2_row.get("table_md")

            if not isinstance(legacy_table_md, str) or not legacy_table_md.strip():
                raise ValueError(f"legacy table_md 无效：chunk_id={legacy_id}")

            if legacy_table_md != v2_table_md:
                raise ValueError(f"legacy/v2 table_md 不一致：legacy_id={legacy_id}, v2_id={v2_id}")

            v2_text = v2_row.get("text")

            if not isinstance(v2_text, str):
                raise ValueError(f"v2 table text 必须是字符串：chunk_id={v2_id}")

            text_parts = v2_text.strip().split(
                "\n",
                1,
            )
            if len(text_parts) != 2 or not text_parts[1].strip():
                raise ValueError(f"v2 table text 缺少可检索表体：chunk_id={v2_id}")

            lowered_text = v2_text.lower()

            if any(marker in lowered_text for marker in TABLE_HTML_MARKERS):
                raise ValueError(f"v2 table text 包含 HTML：chunk_id={v2_id}")

        else:
            raise ValueError(f"相关证据类型不受支持：legacy_id={legacy_id}, type={chunk_type!r}")

        if v2_row.get("workspace_id") != DEMO_WORKSPACE_ID:
            raise ValueError(f"v2 workspace_id 错误：chunk_id={v2_id}")

        if v2_row.get("data_version") != BUILD_ID:
            raise ValueError(f"v2 data_version 错误：chunk_id={v2_id}")

        document_id = v2_row.get("document_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError(f"v2 document_id 无效：chunk_id={v2_id}")

        v2_rows_by_chunk_id[v2_id] = v2_row

    if len(v2_rows_by_chunk_id) != EXPECTED_RELEVANT_ID_COUNT:
        raise RuntimeError(
            "已验证 v2 证据数不守恒："
            f"expected={EXPECTED_RELEVANT_ID_COUNT}, "
            f"actual={len(v2_rows_by_chunk_id)}"
        )

    return v2_rows_by_chunk_id


def migrate_ground_truth(
    *,
    legacy_questions: list[dict[str, Any]],
    id_mapping: dict[str, str],
    v2_rows_by_chunk_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """生成使用 v2 chunk_id 的新题集，不修改 legacy 输入。

    Args:
        legacy_questions: 已验证的 Day42 问题列表。
        id_mapping: 冻结的 legacy ID 到 v2 ID 映射。
        v2_rows_by_chunk_id: 已通过证据等价检查的 v2 行索引。

    Returns:
        保持题目顺序和语义字段不变的 v2 问题列表。

    Raises:
        ValueError: 映射、metadata 或 v2 行不完整。
        RuntimeError: 迁移意外修改了 legacy 输入对象。

    Limitations:
        本函数是纯数据变换，不读取文件、不访问 Milvus。
    """
    original_questions = deepcopy(legacy_questions)
    migrated_questions: list[dict[str, Any]] = []

    for question in legacy_questions:
        new_question = deepcopy(question)

        answerable = question.get("answerable")
        old_relevant_ids = question.get("relevant_chunk_ids")
        old_expected_metadata = question.get("expected_metadata")

        if not isinstance(answerable, bool):
            raise ValueError(f"case_id={question.get('case_id')} answerable 必须是 bool")

        if not isinstance(old_relevant_ids, list):
            raise ValueError(f"case_id={question.get('case_id')} relevant_chunk_ids 必须是列表")

        if not isinstance(
            old_expected_metadata,
            dict,
        ):
            raise ValueError(f"case_id={question.get('case_id')} expected_metadata 必须是字典")

        if not answerable:
            if old_relevant_ids:
                raise ValueError(f"case_id={question.get('case_id')} 无答案题不能有相关 ID")

            if old_expected_metadata:
                raise ValueError(f"case_id={question.get('case_id')} 无答案题 metadata 必须为空")

            new_question["relevant_chunk_ids"] = []
            new_question["expected_metadata"] = {}
            migrated_questions.append(new_question)
            continue

        new_relevant_ids: list[str] = []
        new_expected_metadata: dict[
            str,
            dict[str, Any],
        ] = {}

        for old_id_value in old_relevant_ids:
            if not isinstance(
                old_id_value,
                str,
            ):
                raise ValueError("legacy relevant_chunk_id 必须是字符串")

            old_id = old_id_value

            if old_id not in id_mapping:
                raise ValueError(f"缺少 legacy ID 映射：{old_id}")

            new_id = id_mapping[old_id]

            if new_id not in v2_rows_by_chunk_id:
                raise ValueError(f"缺少已验证 v2 行：{new_id}")

            old_metadata_value = old_expected_metadata.get(old_id)
            if not isinstance(
                old_metadata_value,
                dict,
            ):
                raise ValueError(f"旧 expected_metadata 缺少：{old_id}")

            v2_row = v2_rows_by_chunk_id[new_id]
            new_metadata: dict[
                str,
                Any,
            ] = {}

            for field_name in old_metadata_value:
                if not isinstance(
                    field_name,
                    str,
                ):
                    raise ValueError("expected_metadata 字段名 必须是字符串")

                if field_name not in v2_row:
                    raise ValueError(
                        f"v2 row 缺少 metadata 字段：chunk_id={new_id}, field={field_name}"
                    )

                new_metadata[field_name] = v2_row[field_name]

            new_relevant_ids.append(new_id)
            new_expected_metadata[new_id] = new_metadata

        new_question["relevant_chunk_ids"] = new_relevant_ids
        new_question["expected_metadata"] = new_expected_metadata

        for field_name in SEMANTIC_QUESTION_FIELDS:
            if new_question.get(field_name) != question.get(field_name):
                raise RuntimeError(
                    "ground truth 迁移改变了题目语义字段："
                    f"case_id={question.get('case_id')}, "
                    f"field={field_name}"
                )

        migrated_questions.append(new_question)

    if legacy_questions != original_questions:
        raise RuntimeError("ground truth 迁移修改了 legacy 输入对象")

    return migrated_questions


def write_question_set(
    path: Path,
    questions: list[dict[str, Any]],
) -> QuestionSetWriteResult:
    """确定性、原子地写入一行一题的 UTF-8 JSONL。

    Args:
        path: v2 问题集输出路径。
        questions: 已完成身份迁移的问题列表。

    Returns:
        最终文件的行数、字节数和 SHA-256。

    Raises:
        RuntimeError: 输出路径指向 legacy 题集。
        TypeError: 问题对象不能序列化为 JSON。
        OSError: 目录创建、写入、同步或替换失败。

    Failure behavior:
        序列化或写入失败时保留已有目标文件。
    """
    if path.resolve() == LEGACY_QUESTION_PATH.resolve():
        raise RuntimeError("v2 题集不能覆盖 legacy 题集")

    serialized_lines = [
        json.dumps(
            question,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        for question in questions
    ]

    payload = ("\n".join(serialized_lines) + "\n").encode("utf-8")

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

            temporary_file.write(payload)
            temporary_file.flush()

            # Python 标准库 fsync：
            # 要求操作系统同步当前临时文件内容。
            os.fsync(temporary_file.fileno())

        temporary_path.replace(path)

    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return QuestionSetWriteResult(
        path=path,
        row_count=len(questions),
        byte_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def migrate_day43_ground_truth() -> GroundTruthMigrationResult:
    """执行真实 Day42→Day43 v2 ground truth 迁移。

    Returns:
        题数、证据映射数和 v2 题集文件摘要。

    Raises:
        RuntimeError: 路径隔离、证据映射、回读或 legacy 保留失败。
        题集、Milvus 和文件异常直接向上抛出。
    """
    if LEGACY_QUESTION_PATH.resolve() == V2_QUESTION_PATH.resolve():
        raise RuntimeError("v2 题集路径不能与 legacy 相同")

    legacy_bytes_before = LEGACY_QUESTION_PATH.read_bytes()

    legacy_questions = load_question_set(LEGACY_QUESTION_PATH)

    client = get_client(str(MILVUS_DB_PATH))

    try:
        if not client.has_collection(LEGACY_COLLECTION_NAME):
            raise RuntimeError(f"legacy collection 不存在：{LEGACY_COLLECTION_NAME}")

        if not client.has_collection(V2_COLLECTION_NAME):
            raise RuntimeError(f"v2 collection 不存在：{V2_COLLECTION_NAME}")

        # 第三方 Milvus load_collection：
        # 把已持久化 collection 恢复为可查询状态，
        # 不新增、删除或覆盖数据。
        client.load_collection(LEGACY_COLLECTION_NAME)
        client.load_collection(V2_COLLECTION_NAME)

        v2_rows_by_chunk_id = validate_evidence_mapping(
            client=client,
            legacy_questions=legacy_questions,
            id_mapping=LEGACY_TO_V2_CHUNK_ID,
        )

    finally:
        client.close()

    migrated_questions = migrate_ground_truth(
        legacy_questions=legacy_questions,
        id_mapping=LEGACY_TO_V2_CHUNK_ID,
        v2_rows_by_chunk_id=(v2_rows_by_chunk_id),
    )

    write_result = write_question_set(
        V2_QUESTION_PATH,
        migrated_questions,
    )

    reloaded_questions = load_question_set(V2_QUESTION_PATH)

    if reloaded_questions != migrated_questions:
        raise RuntimeError("重新加载的 v2 题集与写入前对象不一致")

    legacy_bytes_after = LEGACY_QUESTION_PATH.read_bytes()

    if legacy_bytes_after != legacy_bytes_before:
        raise RuntimeError("ground truth 迁移修改了 legacy 题集")

    answerable_count = sum(question["answerable"] for question in reloaded_questions)
    relevant_id_count = sum(len(question["relevant_chunk_ids"]) for question in reloaded_questions)

    return GroundTruthMigrationResult(
        legacy_question_path=(LEGACY_QUESTION_PATH),
        v2_question_path=V2_QUESTION_PATH,
        question_count=len(reloaded_questions),
        answerable_count=answerable_count,
        unanswerable_count=(len(reloaded_questions) - answerable_count),
        relevant_id_count=(relevant_id_count),
        mapped_evidence_count=len(v2_rows_by_chunk_id),
        v2_file_byte_size=(write_result.byte_size),
        v2_file_sha256=(write_result.sha256),
    )


def main() -> int:
    """运行真实 ground truth 迁移并打印审计摘要。"""
    result = migrate_day43_ground_truth()

    print(
        json.dumps(
            asdict(result),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
