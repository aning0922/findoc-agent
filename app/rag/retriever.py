import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

Embedder = Callable[[list[str]], list[list[float]]]


class IndexVersionUnverifiedError(RuntimeError):
    """Index provenance cannot establish the selected D6 revision."""


class RetrieverDataError(RuntimeError):
    """embedder 或 store 返回了不符合 Retriever 契约的数据。"""


@dataclass(frozen=True)
class TrustedContext:
    """服务端认证后产生的可信检索上下文"""

    workspace_id: str

    def __post_init__(self) -> None:
        """确保可信 workspace_id 是非空字符串"""
        if not isinstance(self.workspace_id, str):
            raise TypeError("workspace_id 必须是字符串")
        if not str.strip(self.workspace_id):
            raise ValueError("workspace_id 不能为空字符串")


@dataclass(frozen=True)
class SearchFilters:
    """服务端组装的业务过滤条件，不接受浏览器提交的任意过滤表达式。"""

    source_file: str | None = None
    document_id: str | None = None
    document_ids: tuple[str, ...] | None = None
    source_revisions: tuple[tuple[str, str], ...] | None = None

    def __post_init__(self) -> None:
        """确保 document_id 和 source_file 缺省或者为非空字符串"""

        if self.document_ids is not None:
            ids = self.document_ids
            if (type(ids) is not tuple or not ids
                    or any(type(d) is not str or not d.strip() for d in ids)
                    or len(set(ids)) != len(ids)):
                raise ValueError("document_ids must be a nonempty unique tuple")
            if self.document_id is not None or self.source_file is not None:
                raise ValueError("multi-document scope cannot mix legacy filters")
            object.__setattr__(self, "document_ids", tuple(sorted(ids)))
        if self.source_revisions is not None:
            revisions = self.source_revisions
            if (self.document_ids is None or type(revisions) is not tuple
                    or any(type(r) is not tuple or len(r) != 2
                           or any(type(v) is not str or not v.strip() for v in r)
                           for r in revisions)
                    or tuple(sorted(r[0] for r in revisions)) != self.document_ids):
                raise ValueError("revisions must match every selected document exactly")
            object.__setattr__(self, "source_revisions", tuple(sorted(revisions)))
        if self.document_id is not None:
            if not isinstance(self.document_id, str):
                raise TypeError("document_id 必须是字符串或 None")
            if not str.strip(self.document_id):
                raise ValueError("document_id 不能为空字符串")

        if self.source_file is not None:
            if not isinstance(self.source_file, str):
                raise TypeError("source_file 必须是字符串或 None")
            if not str.strip(self.source_file):
                raise ValueError("source_file 不能为空字符串")


def build_filter_expression(context: TrustedContext, filters: SearchFilters | None = None) -> str:
    """用可信的 workspace 和允许的过滤条件构造 store 过滤表达式"""
    clauses = [
        f"workspace_id == {json.dumps(context.workspace_id, ensure_ascii=False)}",
    ]
    if filters is not None and filters.document_id is not None:
        clauses.append(f"document_id == {json.dumps(filters.document_id, ensure_ascii=False)}")
    if filters is not None and filters.source_file is not None:
        clauses.append(f"source_file == {json.dumps(filters.source_file, ensure_ascii=False)}")

    if filters is not None and filters.document_ids is not None:
        # Equality/OR uses the same dynamic scalar fields as the existing single-document path.
        revisions = dict(filters.source_revisions or ())
        choices = []
        for document_id in filters.document_ids:
            clause = f"document_id == {json.dumps(document_id, ensure_ascii=False)}"
            if revisions:
                clause += f" and source_revision == {json.dumps(revisions[document_id])}"
            choices.append(f"({clause})")
        clauses.append("(" + " or ".join(choices) + ")")
    return " and ".join(clauses)


@dataclass(frozen=True)
class SearchHit:
    """Retriever 对上层返回的稳定单条检索结果。"""

    score: float
    chunk_id: str
    text: str
    page: int
    source_file: str
    type: Literal["paragraph", "table", "title"]
    section: str = ""
    table_md: str | None = None
    workspace_id: str | None = None
    """可选的实际命中身份；旧检索兼容缺省，Agent 结果验证要求存在并匹配。"""
    document_id: str | None = None
    """来自 store 实体的文档 ID，不从过滤条件或正文补造。"""
    source_revision: str | None = None


class SearchStore(Protocol):
    def search(
        self, query_vector: list[float], *, top_k: int, filter_expression: str
    ) -> list[Mapping[str, Any]]:
        """根据查询向量、数量和过滤表达式返回 store 原始命中"""
        ...


class Retriever:
    def __init__(self, embedder: Embedder, store: SearchStore) -> None:
        """注入查询向量生成器和向量检索存储"""
        self._embedder = embedder
        self._store = store

    def retrieve(
        self,
        query: str,
        *,
        context: TrustedContext,
        top_k: int = 5,
        filters: SearchFilters | None = None,
    ) -> list[SearchHit]:
        """使用可信的上下文和业务过滤条件执行一次向量检索"""
        normalized_query = self._validate_input(query, top_k)
        if not isinstance(context, TrustedContext):
            raise TypeError("context 必须是 TrustedContext 实例")
        if filters is not None and not isinstance(filters, SearchFilters):
            raise TypeError("filters 必须是 SearchFilters 实例或 None")
        filter_expression = build_filter_expression(context, filters)
        if filters is not None and filters.source_revisions is not None:
            if getattr(self._store, "supports_source_revisions", False) is not True:
                raise IndexVersionUnverifiedError("index_source_revision_unverified")
        validate_scope = getattr(type(self._store), "validate_scope", None)
        if callable(validate_scope):
            validate_scope(self._store, context, filters)
        query_vectors = self._embedder([normalized_query])
        if len(query_vectors) != 1 or not query_vectors[0]:
            raise RetrieverDataError("embedder 必须为单个 query 返回恰好一个非空向量")
        query_vector = query_vectors[0]
        scoped_search = getattr(type(self._store), "scoped_search", None)
        if callable(scoped_search):
            raw_hits = scoped_search(self._store, query_vector, query=normalized_query, context=context, filters=filters,
                                     top_k=top_k, filter_expression=filter_expression)
        else:
            raw_hits = self._store.search(
                query_vector, top_k=top_k, filter_expression=filter_expression
            )
        hits = [self._to_search_hit(hit) for hit in raw_hits]
        for hit in hits:
            # Older single-document stores may omit identity, but contradictory identity is rejected.
            if hit.workspace_id is not None and hit.workspace_id != context.workspace_id:
                raise RetrieverDataError("store hit workspace outside selected scope")
            if filters is not None:
                if (filters.document_id is not None and hit.document_id is not None
                        and hit.document_id != filters.document_id):
                    raise RetrieverDataError("store hit document outside selected scope")
                if filters.document_ids is not None:
                    if (hit.workspace_id != context.workspace_id
                            or hit.document_id not in filters.document_ids):
                        raise RetrieverDataError("store hit missing or outside selected identity")
                    if filters.source_revisions is not None:
                        if hit.source_revision != dict(filters.source_revisions)[hit.document_id]:
                            raise IndexVersionUnverifiedError("index_source_revision_mismatch")
        return hits

    @staticmethod
    def _to_search_hit(raw_hit: Mapping[str, Any]) -> SearchHit:
        """校验一条 store 原始结果，并转换为稳定的 SearchHit DTO。"""
        required_fields = (
            "score",
            "chunk_id",
            "text",
            "page",
            "source_file",
            "type",
        )
        missing_fields = [field_name for field_name in required_fields if field_name not in raw_hit]
        if missing_fields:
            raise RetrieverDataError(f"store hit 缺少关键字段： {','.join(missing_fields)}")

        score = raw_hit["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise RetrieverDataError("store hit 的 score 必须是浮点数或整数")

        page = raw_hit["page"]
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise RetrieverDataError("store hit 的 page 必须是大于等于 1 的整数")

        if not isinstance(raw_hit["chunk_id"], str) or not str.strip(raw_hit["chunk_id"]):
            raise RetrieverDataError("store hit 的 chunk_id 必须是非空字符串")
        if not isinstance(raw_hit["text"], str) or not str.strip(raw_hit["text"]):
            raise RetrieverDataError("store hit 的 text 必须是非空字符串")
        if not isinstance(raw_hit["source_file"], str) or not str.strip(raw_hit["source_file"]):
            raise RetrieverDataError("store hit 的 source_file 必须是非空字符串")

        hit_type = raw_hit["type"]
        if not isinstance(hit_type, str) or hit_type not in (
            "paragraph",
            "table",
            "title",
        ):
            raise RetrieverDataError("store hit 的 type 必须是 'paragraph', 'table' 或 'title'")

        validated_type = cast(
            Literal["paragraph", "table", "title"],
            hit_type,
        )
        section = raw_hit.get("section", "")
        if not isinstance(section, str):
            raise RetrieverDataError("store hit 的 section 必须是字符串")

        table_md = raw_hit.get("table_md")
        if table_md is not None and not isinstance(table_md, str):
            raise RetrieverDataError("store hit 的 table_md 必须是字符串或 None")
        workspace_id = raw_hit.get("workspace_id")
        document_id = raw_hit.get("document_id")
        source_revision = raw_hit.get("source_revision")
        for identity in (workspace_id, document_id, source_revision):
            if identity is not None and (not isinstance(identity, str) or not identity.strip()):
                raise RetrieverDataError("store hit 的范围身份必须是非空字符串或 None")
        return SearchHit(
            score=float(score),
            chunk_id=raw_hit["chunk_id"],
            text=raw_hit["text"],
            page=int(page),
            source_file=raw_hit["source_file"],
            type=validated_type,
            section=section,
            table_md=table_md,
            workspace_id=workspace_id,
            document_id=document_id,
            source_revision=source_revision,
        )

    @staticmethod
    def _validate_input(query: str, top_k: int) -> str:
        """校验 query 和 top_k，并返回去除首尾空白的查询文本"""
        if not isinstance(query, str):
            raise TypeError("query 必须是字符串")
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query 不能为空")

        if not isinstance(top_k, int) or isinstance(top_k, bool):
            raise TypeError("top_k 必须是整数")
        if top_k < 1:
            raise ValueError("top_k 必须大于等于 1")
        return normalized_query
