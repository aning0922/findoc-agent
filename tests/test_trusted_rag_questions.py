import hashlib
import json
from typing import Any
from pathlib import Path

import pytest
from experiments.day43_config import PROJECT_ROOT
from scripts.evaluate_day42_retrieval import load_questions


LEGACY_QUESTION_PATH = PROJECT_ROOT / "eval/day43_questions_v2.jsonl"
TRUSTED_RAG_QUESTION_PATH = PROJECT_ROOT / "eval/trusted_rag_questions_v1.jsonl"
V2_CHUNK_DIR = PROJECT_ROOT / "data/day43_data_v2"
TRUSTED_RAG_BASELINE_CONFIG_PATH = PROJECT_ROOT / "eval/trusted_rag_baseline_config_v1.json"


@pytest.fixture
def local_data_dir() -> Path:
    """返回本地冻结数据目录；整个目录缺失时显示skip，内容错误不在此处跳过。"""
    if not V2_CHUNK_DIR.exists():
        pytest.skip(
            "缺少本地冻结数据 data/day43_data_v2；"
            "准备数据后运行 "
            "'uv run pytest tests/test_trusted_rag_questions.py "
            "-q -m local_data -rs'"
        )
    return V2_CHUNK_DIR


def test_trusted_rag_question_set_preserves_public_contract() -> None:
    """验证公开仓库内题集的冻结合同。

    输入：原12题、正式20题和已提交的baseline配置。
    输出：题数、schema、历史样本、核证字段与SHA-256均正确时通过。
    失败：题集内容、结构、数量或冻结身份发生漂移时失败。
    边界：不读取作者本地chunks，不证明证据内容仍存在于私有数据中。
    """
    legacy_questions = load_questions(LEGACY_QUESTION_PATH)
    formal_questions = load_questions(TRUSTED_RAG_QUESTION_PATH)

    # 第一层：正式题集必须保留原12题，不得借扩题修改历史冻结样本。
    assert formal_questions[:12] == legacy_questions

    # 第二层：冻结总题数、可回答/不可回答比例和稳定case ID。
    assert len(formal_questions) == 20
    assert sum(question["answerable"] is True for question in formal_questions) == 15
    assert sum(question["answerable"] is False for question in formal_questions) == 5

    case_ids = [question["case_id"] for question in formal_questions]
    assert case_ids == [f"Q{number}" for number in range(1, 21)]
    assert len(case_ids) == len(set(case_ids))

    questions_by_id = {question["case_id"]: question for question in formal_questions}

    # 第四层：Q13～Q17必须有答案要点和真实存在的冻结证据。
    for case_id in ("Q13", "Q14", "Q15", "Q16", "Q17"):
        question = questions_by_id[case_id]

        assert question["answerable"] is True

        answer_points = question.get("answer_points")
        assert isinstance(answer_points, list) and answer_points
        assert all(
            isinstance(answer_point, str) and answer_point.strip() for answer_point in answer_points
        )

        relevant_chunk_ids = question["relevant_chunk_ids"]
        expected_metadata = question["expected_metadata"]

        assert relevant_chunk_ids
        assert isinstance(expected_metadata, dict)
        assert set(relevant_chunk_ids) == set(expected_metadata)

    # 第五层：Q18～Q20必须是经过限定范围核证的不可回答题。
    for case_id in ("Q18", "Q19", "Q20"):
        question = questions_by_id[case_id]

        assert question["answerable"] is False
        assert question["answer_points"] == []
        assert question["relevant_chunk_ids"] == []
        assert question["expected_metadata"] == {}

        verification_scope = question.get("verification_scope")
        verification_basis = question.get("verification_basis")

        assert isinstance(verification_scope, str)
        assert verification_scope.strip()

        assert isinstance(verification_basis, str)
        assert verification_basis.strip()

    # baseline配置保存已经冻结的题集身份，不依赖作者本地chunks。
    baseline_config = json.loads(TRUSTED_RAG_BASELINE_CONFIG_PATH.read_text(encoding="utf-8"))
    expected_sha256 = baseline_config["question_set"]["sha256"]

    # 对题集原始字节计算SHA-256；内容发生任何变化时都必须失败。
    actual_sha256 = hashlib.sha256(TRUSTED_RAG_QUESTION_PATH.read_bytes()).hexdigest()

    assert actual_sha256 == expected_sha256


@pytest.mark.local_data
def test_trusted_rag_evidence_matches_local_chunks(
    local_data_dir: Path,
) -> None:
    """使用作者本地冻结chunks交叉核验证据ID与metadata。

    输入：存在的本地冻结数据目录。
    输出：无；全部证据对应时测试通过。
    失败：目录存在但为空、chunk损坏、证据缺失或metadata漂移时失败。
    边界：整个私有目录不存在时由fixture显示skip。
    """
    formal_questions = load_questions(TRUSTED_RAG_QUESTION_PATH)

    # 第三层：读取冻结v2数据，按chunk_id建立唯一证据索引。
    chunks_by_id: dict[str, dict[str, Any]] = {}

    chunk_paths = sorted(local_data_dir.glob("*_chunks.jsonl"))
    assert chunk_paths

    for chunk_path in chunk_paths:
        for line_number, line in enumerate(
            chunk_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue

            chunk = json.loads(line)
            assert isinstance(chunk, dict), f"{chunk_path} 第{line_number}行必须是JSON对象"

            chunk_id = chunk.get("chunk_id")
            assert isinstance(chunk_id, str) and chunk_id.strip(), (
                f"{chunk_path} 第{line_number}行缺少有效chunk_id"
            )
            assert chunk_id not in chunks_by_id, f"冻结v2数据存在重复chunk_id：{chunk_id}"

            chunks_by_id[chunk_id] = chunk

    questions_by_id = {question["case_id"]: question for question in formal_questions}

    # 第四层：Q13～Q17必须有答案要点和真实存在的冻结证据。
    for case_id in ("Q13", "Q14", "Q15", "Q16", "Q17"):
        question = questions_by_id[case_id]

        assert question["answerable"] is True

        answer_points = question.get("answer_points")
        assert isinstance(answer_points, list) and answer_points
        assert all(
            isinstance(answer_point, str) and answer_point.strip() for answer_point in answer_points
        )

        relevant_chunk_ids = question["relevant_chunk_ids"]
        expected_metadata = question["expected_metadata"]

        assert relevant_chunk_ids
        assert isinstance(expected_metadata, dict)
        assert set(relevant_chunk_ids) == set(expected_metadata)

        for chunk_id in relevant_chunk_ids:
            assert chunk_id in chunks_by_id, f"{case_id}相关证据不存在：{chunk_id}"

            actual_chunk = chunks_by_id[chunk_id]
            expected_chunk_metadata = expected_metadata[chunk_id]

            for field_name, expected_value in expected_chunk_metadata.items():
                assert actual_chunk.get(field_name) == expected_value, (
                    f"{case_id}证据{chunk_id}的{field_name}发生漂移："
                    f"expected={expected_value!r}, "
                    f"actual={actual_chunk.get(field_name)!r}"
                )
