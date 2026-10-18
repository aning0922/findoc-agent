from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, cast

from dotenv import load_dotenv

from app.rag.evidence_gate import ConservativeScoreEvidenceGate
from app.rag.openai_compatible_llm import OpenAICompatibleLLMClient
from app.rag.retriever import (
    Retriever,
    SearchFilters,
    SearchHit,
    TrustedContext,
)
from app.rag.service import (
    RAGOutcome,
    RAGResult,
    RAGService,
    RefusalResult,
    SystemErrorResult,
    TRUSTED_RAG_PROMPT_VERSION,
)
from app.rag.store import MilvusSearchStore, count_rows, get_client
from experiments.day43_config import (
    BUILD_ID,
    DEMO_WORKSPACE_ID,
    EMBEDDING_MODEL_NAME,
    MANIFEST_PATH,
    METRIC_TYPE,
    MILVUS_DB_PATH,
    PROJECT_ROOT,
    REAL_DOCUMENTS,
    V2_COLLECTION_NAME,
)
from experiments.day43_manifest import load_v2_manifest
from experiments.day43_run_retrieval_comparison import validate_collection_metric
from scripts.evaluate_day42_retrieval import get_git_state, load_questions


TOP_K = 5
MIN_TOP_SCORE = 0.55
MAX_EVIDENCE_CHARS = 4000


class _RecordingRetriever(Retriever):
    """记录一次正式 Retriever 调用返回的原始 SearchHit。

    Args:
        delegate: 已配置完成的正式 Retriever。

    边界:
        本类只做透明转发和观测，不重排、过滤或修改命中结果；
        底层异常原样传播，失败时不保留上一道题的命中记录。
    """

    def __init__(self, delegate: Retriever) -> None:
        """保存底层 Retriever，并初始化为空的单题命中记录。"""
        self._delegate = delegate
        self.last_hits: list[SearchHit] | None = None

    def reset(self) -> None:
        """清空上一道题的命中记录，防止异常请求读取陈旧结果。"""
        self.last_hits = None

    def retrieve(
        self,
        query: str,
        *,
        context: TrustedContext,
        top_k: int = 5,
        filters: SearchFilters | None = None,
    ) -> list[SearchHit]:
        """透明执行一次检索并保存原始有序命中。

        Args:
            query: 当前用户问题。
            context: 服务端可信 workspace 上下文。
            top_k: 最多返回的证据数量。
            filters: 可选的 source_file 业务过滤条件。

        Returns:
            底层 Retriever 原样返回的有序 SearchHit 列表。

        Raises:
            底层 Retriever 的任何异常原样传播，由 RAGService 归类。
        """
        self.last_hits = None
        hits = self._delegate.retrieve(
            query,
            context=context,
            top_k=top_k,
            filters=filters,
        )
        self.last_hits = hits
        return hits


class _RecordingLLMClient:
    """记录一次正式 LLMClient 调用返回的原始模型正文。

    Args:
        delegate: 已配置完成的 OpenAI 兼容非流式客户端。

    边界:
        本类不解析、修复或改写模型输出；
        底层异常原样传播，失败时 raw_output 保持为 None。
    """

    def __init__(self, delegate: OpenAICompatibleLLMClient) -> None:
        """保存底层模型客户端，并初始化为空的单题输出记录。"""
        self._delegate = delegate
        self.raw_output: str | None = None

    def reset(self) -> None:
        """清空上一道题的原始模型输出。"""
        self.raw_output = None

    def generate(self, prompt: str) -> str:
        """透明执行一次非流式生成并记录未经修改的正文。

        Args:
            prompt: RAGService 构造完成的正式提示词。

        Returns:
            底层模型客户端原样返回的字符串。

        Raises:
            TimeoutError: 底层客户端规范化后的超时。
            其他异常: 供应商、网络、鉴权或额度异常原样传播。
        """
        self.raw_output = None
        raw_output = self._delegate.generate(prompt)
        self.raw_output = raw_output
        return raw_output


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """解析题集、输出文件和可重复 case ID 参数。

    Args:
        argv: 可注入的命令行参数；为 None 时读取当前进程参数。

    Returns:
        argparse 解析后的参数对象。

    Raises:
        SystemExit: 必填参数缺失或参数格式非法。
    """
    parser = argparse.ArgumentParser(description="运行可信 RAG 非流式 smoke 或正式 baseline。")
    parser.add_argument(
        "--questions",
        required=True,
        type=Path,
        help="版本化评测题集 JSONL 路径。",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="保存原始逐题结果的全新 JSON 路径。",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="只运行指定 case ID；可以重复提供，不提供时运行全部题目。",
    )
    return parser.parse_args(argv)


def _resolve_path(path: Path) -> Path:
    """将 CLI 相对路径解析为基于项目根目录的绝对路径。

    Args:
        path: CLI 提供的绝对或相对路径。

    Returns:
        规范化后的绝对路径。

    边界:
        本函数不检查路径是否存在，也不创建文件。
    """
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


def _calculate_sha256(path: Path) -> str:
    """计算文件的 SHA-256，用于冻结题集和 manifest 身份。

    Args:
        path: 已存在的普通文件。

    Returns:
        文件内容的十六进制 SHA-256。

    Raises:
        OSError: 文件不可读取。
    """
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _select_questions(
    questions: list[dict[str, Any]],
    requested_case_ids: list[str] | None,
) -> list[dict[str, Any]]:
    """按 CLI case ID 选择题目，并保持用户给出的顺序。

    Args:
        questions: 已通过现有 load_questions 合同校验的完整题集。
        requested_case_ids: CLI 指定的 case ID；None 表示选择全部。

    Returns:
        保持题集顺序或 CLI 指定顺序的题目列表。

    Raises:
        ValueError: case ID 重复，或者请求了题集中不存在的 case ID。
    """
    if requested_case_ids is None:
        return questions

    if len(requested_case_ids) != len(set(requested_case_ids)):
        raise ValueError("--case-id 不能重复")

    questions_by_id = {cast(str, question["case_id"]): question for question in questions}

    missing_case_ids = [case_id for case_id in requested_case_ids if case_id not in questions_by_id]
    if missing_case_ids:
        raise ValueError("题集中不存在以下 case ID：" + ", ".join(missing_case_ids))

    return [questions_by_id[case_id] for case_id in requested_case_ids]


def _serialize_hits(
    hits: list[SearchHit] | None,
) -> list[dict[str, Any]]:
    """将 Retriever 原始命中转换为可审计 JSON 数据。

    Args:
        hits: 本题成功返回的命中列表；检索异常时为 None。

    Returns:
        包含完整文本、score 和服务端元数据的有序列表。
    """
    if hits is None:
        return []

    return [
        {
            "rank": rank,
            "chunk_id": hit.chunk_id,
            "score": hit.score,
            "text": hit.text,
            "source_file": hit.source_file,
            "page": hit.page,
            "type": hit.type,
            "section": hit.section,
        }
        for rank, hit in enumerate(hits, start=1)
    ]


def _serialize_outcome(outcome: RAGOutcome) -> dict[str, Any]:
    """将唯一领域终态转换为互斥的评测记录字段。

    Args:
        outcome: RAGService 返回的成功、拒答或系统失败终态。

    Returns:
        固定包含 terminal_state、refusal_reason、answer、citations、
        error_type、safe_message 和 raw_error 的字典。

    边界:
        RAGResult 才能发布 answer 和 citations；
        RefusalResult 只能记录拒答原因；
        SystemErrorResult 只能记录错误字段，不能伪装成拒答。
    """
    if isinstance(outcome, RAGResult):
        return {
            "terminal_state": "answered",
            "refusal_reason": None,
            "answer": outcome.content,
            "citations": [
                {
                    "number": citation.number,
                    "source_file": citation.source_file,
                    "page": citation.page,
                    "chunk_id": citation.chunk_id,
                }
                for citation in outcome.citations
            ],
            "error_type": None,
            "safe_message": None,
            "raw_error": None,
        }
    elif isinstance(outcome, RefusalResult):
        return {
            "terminal_state": "refusal",
            "refusal_reason": outcome.reason.value,
            "answer": None,
            "citations": [],
            "error_type": None,
            "safe_message": None,
            "raw_error": None,
        }
    elif isinstance(outcome, SystemErrorResult):
        return {
            "terminal_state": "system_error",
            "refusal_reason": None,
            "answer": None,
            "citations": [],
            "error_type": outcome.error_type.value,
            "safe_message": outcome.message,
            "raw_error": outcome.raw_error,
        }

    raise TypeError(f"未知 RAGOutcome 类型：{type(outcome).__name__}")


def _evaluate_case(
    question: dict[str, Any],
    *,
    service: RAGService,
    recording_retriever: _RecordingRetriever,
    recording_llm: _RecordingLLMClient,
    context: TrustedContext,
) -> dict[str, Any]:
    """通过正式 RAGService 运行一道题并记录完整原始结果。

    Args:
        question: 已通过题集合同校验的一道题。
        service: 已注入正式 Retriever、gate 和 LLMClient 的 RAGService。
        recording_retriever: 只负责保存本题检索命中的透明记录器。
        recording_llm: 只负责保存本题模型原始输出的透明记录器。
        context: 冻结的可信 workspace 上下文。

    Returns:
        包含预期标签、领域终态、检索结果、模型原始输出和延迟的记录。

    边界:
        本函数不捕获并伪造初始化失败；
        请求级错误应由 RAGService 转换成 SystemErrorResult。
    """
    recording_retriever.reset()
    recording_llm.reset()

    query = cast(str, question["query"])
    source_file = cast(str | None, question.get("source_file"))

    filters = SearchFilters(source_file=source_file)

    started = perf_counter()
    outcome = service.answer(
        query,
        context=context,
        top_k=TOP_K,
        filters=filters,
    )
    latency_ms = (perf_counter() - started) * 1000

    result = {
        "case_id": question["case_id"],
        "query": query,
        "category": question["category"],
        "expected_answerable": question["answerable"],
        "source_file_filter": source_file,
        "retrieved_hits": _serialize_hits(recording_retriever.last_hits),
        "raw_model_output": recording_llm.raw_output,
        "latency_ms": latency_ms,
    }
    result.update(_serialize_outcome(outcome))
    return result


def _build_summary(
    results: list[dict[str, Any]],
) -> dict[str, int]:
    """根据预期可答性和真实领域终态生成最小 baseline 汇总。

    Args:
        results: 完整逐题原始结果。

    Returns:
        可回答成功/误拒、不可回答正确拒答/漏拒、system error
        和成功答案引用校验通过数量。

    边界:
        system_error 单独统计，不计入正确拒答或误拒。
    """
    answerable_answered = 0
    answerable_refused = 0
    unanswerable_refused = 0
    unanswerable_answered = 0
    system_error_count = 0

    for result in results:
        answerable = cast(bool, result["expected_answerable"])
        terminal_state = cast(str, result["terminal_state"])

        if terminal_state == "system_error":
            system_error_count += 1
        elif answerable and terminal_state == "answered":
            answerable_answered += 1
        elif answerable and terminal_state == "refusal":
            answerable_refused += 1
        elif not answerable and terminal_state == "refusal":
            unanswerable_refused += 1
        elif not answerable and terminal_state == "answered":
            unanswerable_answered += 1
        else:
            raise ValueError(
                f"未知评测组合：answerable={answerable}, terminal_state={terminal_state}"
            )

    return {
        "answerable_total": sum(result["expected_answerable"] is True for result in results),
        "answerable_answered": answerable_answered,
        "answerable_refused": answerable_refused,
        "unanswerable_total": sum(result["expected_answerable"] is False for result in results),
        "unanswerable_correctly_refused": unanswerable_refused,
        "unanswerable_answered": unanswerable_answered,
        "system_error_count": system_error_count,
        # RAGResult 只有在引用校验通过后才能形成。
        "answered_with_validated_citations": (answerable_answered + unanswerable_answered),
    }


def _write_json_atomically(
    path: Path,
    payload: dict[str, Any],
) -> None:
    """将报告写入全新文件，失败时不留下半成品。

    Args:
        path: 必须尚不存在的最终输出路径。
        payload: 可序列化且不允许包含 NaN 的完整报告。

    Raises:
        FileExistsError: 最终输出文件已经存在。
        TypeError/ValueError: 报告无法序列化为标准 JSON。
        OSError: 创建、写入或替换文件失败。
    """
    if path.exists():
        raise FileExistsError(f"拒绝覆盖已有评测结果：{path}")

    path.parent.mkdir(parents=True, exist_ok=True)

    serialized = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            temporary_path = Path(temporary_file.name)

        temporary_path.replace(path)
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    """校验冻结环境，通过正式 RAGService 运行题集并保存原始报告。

    Args:
        argv: 可选命令行参数，便于离线测试；None 表示使用进程参数。

    Returns:
        0 表示报告成功写入。

    Raises:
        输入、配置、manifest、collection 或输出文件合同失败时停止运行；
        不将实验环境初始化失败伪装成某道题的正常拒答。
    """
    args = _parse_args(argv)

    question_path = _resolve_path(args.questions)
    output_path = _resolve_path(args.output)

    if not question_path.is_file():
        raise FileNotFoundError(f"题集文件不存在：{question_path}")
    if output_path.exists():
        raise FileExistsError(f"拒绝覆盖已有评测结果：{output_path}")

    questions = load_questions(question_path)
    selected_questions = _select_questions(
        questions,
        cast(list[str] | None, args.case_ids),
    )

    # 只在真实 CLI 执行阶段显式加载，不在模块 import 阶段加载。
    load_dotenv(PROJECT_ROOT / ".env")

    # 这里只读取安全配置；绝对不要读取后写出 LLM_API_KEY。
    llm_model = os.environ["LLM_MODEL"]
    llm_base_url = os.environ["LLM_BASE_URL"]
    llm_timeout_seconds = float(os.environ["LLM_TIMEOUT_SECONDS"])

    expected_document_ids = {document["document_id"] for document in REAL_DOCUMENTS}

    manifest = load_v2_manifest(
        MANIFEST_PATH,
        project_root=PROJECT_ROOT,
        expected_build_id=BUILD_ID,
        expected_workspace_id=DEMO_WORKSPACE_ID,
        expected_collection_name=V2_COLLECTION_NAME,
        expected_document_ids=expected_document_ids,
    )

    manifest_collection = manifest.get("collection")
    if not isinstance(manifest_collection, dict):
        raise RuntimeError("已验证 manifest 缺少 collection 字典")

    expected_row_count = manifest_collection.get("actual_row_count")
    if (
        isinstance(expected_row_count, bool)
        or not isinstance(expected_row_count, int)
        or expected_row_count < 1
    ):
        raise RuntimeError("manifest.collection.actual_row_count 必须是正整数")

    # Client 构造本身不发送模型请求。
    real_llm = OpenAICompatibleLLMClient.from_env()
    recording_llm = _RecordingLLMClient(real_llm)

    # 延迟导入：直到参数、题集、输出路径、环境配置和 manifest
    # 都已经通过检查后，才加载冻结的 embedding 模型。
    from app.rag.embed import embed

    client = get_client(str(MILVUS_DB_PATH))
    try:
        if not client.has_collection(V2_COLLECTION_NAME):
            raise RuntimeError(f"冻结 collection 不存在：{V2_COLLECTION_NAME}")

        client.load_collection(V2_COLLECTION_NAME)

        actual_row_count = count_rows(
            client,
            V2_COLLECTION_NAME,
        )
        if actual_row_count != expected_row_count:
            raise RuntimeError(
                "collection 行数与 manifest 不一致："
                f"expected={expected_row_count}, "
                f"actual={actual_row_count}"
            )

        validate_collection_metric(
            client,
            V2_COLLECTION_NAME,
            expected_metric_type=METRIC_TYPE,
        )

        store = MilvusSearchStore(
            client,
            V2_COLLECTION_NAME,
        )
        formal_retriever = Retriever(embed, store)
        recording_retriever = _RecordingRetriever(formal_retriever)

        evidence_gate = ConservativeScoreEvidenceGate(min_top_score=MIN_TOP_SCORE)

        service = RAGService(
            retriever=recording_retriever,
            llm_client=recording_llm,
            evidence_gate=evidence_gate,
            max_evidence_chars=MAX_EVIDENCE_CHARS,
        )

        context = TrustedContext(workspace_id=DEMO_WORKSPACE_ID)

        started_at = datetime.now(UTC).isoformat()
        results = [
            _evaluate_case(
                question,
                service=service,
                recording_retriever=recording_retriever,
                recording_llm=recording_llm,
                context=context,
            )
            for question in selected_questions
        ]

        git_state = get_git_state()

        report: dict[str, Any] = {
            "started_at": started_at,
            "questions": {
                "path": str(question_path.relative_to(PROJECT_ROOT)),
                "sha256": _calculate_sha256(question_path),
                "selected_case_ids": [question["case_id"] for question in selected_questions],
            },
            "data": {
                "build_id": BUILD_ID,
                "manifest_path": str(MANIFEST_PATH.relative_to(PROJECT_ROOT)),
                "manifest_sha256": _calculate_sha256(MANIFEST_PATH),
                "collection_name": V2_COLLECTION_NAME,
                "collection_row_count": actual_row_count,
                "embedding_model": EMBEDDING_MODEL_NAME,
            },
            "rag_config": {
                "llm_model": llm_model,
                "llm_base_url": llm_base_url,
                "llm_timeout_seconds": llm_timeout_seconds,
                "top_k": TOP_K,
                "evidence_gate": {
                    "type": ("ConservativeScoreEvidenceGate"),
                    "min_top_score": MIN_TOP_SCORE,
                    "assumption": (
                        "只作为生成前最低相似度资格判断；"
                        "高相似度不代表证据足以回答，"
                        "仍由模型协议执行第二层判断。"
                    ),
                },
                "max_evidence_chars": (MAX_EVIDENCE_CHARS),
                "prompt_version": (TRUSTED_RAG_PROMPT_VERSION),
            },
            "code": git_state,
            "summary": _build_summary(results),
            "results": results,
        }

        _write_json_atomically(output_path, report)
    finally:
        client.close()

    print(f"评测结果已保存：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
