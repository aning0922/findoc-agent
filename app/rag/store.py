# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportUnnecessaryComparison=false
from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.rag.retriever import IndexVersionUnverifiedError, SearchFilters, TrustedContext

if TYPE_CHECKING:
    from app.rag.publications import IndexPublications

from pymilvus import MilvusClient, DataType

DIM = 1024


class MilvusSearchStore:
    """将 MilvusClient 适配为 Retriever 所需的 SearchStore 接口"""

    # Legacy runtime rows carry data_version, not D6 source_revision. Never infer provenance.
    supports_source_revisions = False

    def __init__(
        self, client: MilvusClient, collection_name: str, *, include_scope_metadata: bool = False,
        publications: "IndexPublications | None" = None
    ) -> None:
        """绑定既有客户端；runtime 显式请求实体身份，旧 collection 保留原字段集合。"""
        self._client = client
        self._collection_name = collection_name
        self._include_scope_metadata = include_scope_metadata
        self.publications = publications
        self.supports_source_revisions = publications is not None

    def validate_scope(self, context: TrustedContext, filters: SearchFilters | None) -> None:
        if filters is not None and filters.document_ids is not None:
            if self.publications is None or not filters.source_revisions:
                raise IndexVersionUnverifiedError("versioned_scope_required")
            for document, revision in filters.source_revisions:
                self.publications.assert_current(context.workspace_id, document, revision)

    def scoped_search(
        self, query_vector: list[float], *, query: str, context: TrustedContext,
        filters: SearchFilters | None, top_k: int, filter_expression: str,
    ) -> list[Mapping[str, Any]]:
        if filters is not None and filters.document_ids is not None:
            if self.publications is None or not filters.source_revisions:
                raise IndexVersionUnverifiedError("versioned_scope_required")
            return self.publications.search(query_vector, context, filters, top_k, query=query)
        if self.publications is not None and filters is not None and filters.document_id:
            # Preserve /chat's DTO while routing newly indexed documents to their active generation.
            from contextlib import closing
            with closing(self.publications.registry._connect()) as conn:
                rows = conn.execute(
                    "SELECT source_revision, state FROM index_publications "
                    "WHERE workspace_id=? AND document_id=?",
                    (context.workspace_id, filters.document_id),
                ).fetchall()
            if rows:
                active = [r[0] for r in rows if r[1] == 'active']
                if len(active) != 1:
                    raise IndexVersionUnverifiedError("index_publication_missing")
                return self.publications.search(query_vector, context, SearchFilters(
                    document_ids=(filters.document_id,),
                    source_revisions=((filters.document_id, active[0]),),
                ), top_k)
        return self.search(query_vector, top_k=top_k, filter_expression=filter_expression)

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filter_expression: str,
    ) -> list[Mapping[str, Any]]:
        """执行 Milvus 搜索 并把 distance/entity 转换成稳定的原始命中格式"""
        result = self._client.search(
            collection_name=self._collection_name,
            data=[query_vector],
            filter=filter_expression,
            limit=top_k,
            output_fields=[
                "text",
                "page",
                "section",
                "source_file",
                "chunk_id",
                "type",
                "table_md",
            ] + (["workspace_id", "document_id"] if self._include_scope_metadata else []),
        )
        return [
            {
                "score": float(hit["distance"]),
                **hit["entity"],
            }
            for hit in result[0]
        ]


def get_client(db_path: str = "./data/milvus.db") -> MilvusClient:
    """获取milvus客户端"""
    return MilvusClient(db_path)


def ensure_collection(client: MilvusClient, name: str, dim: int = DIM) -> None:
    """
    确保集合存在
    """
    if not client.has_collection(name):
        client.create_collection(collection_name=name, dimension=dim, metric_type="COSINE")


def ensure_document_collection(
    client: MilvusClient, name: str, dim: int = DIM, *, index_type: str | None = None,
) -> None:
    """
    创建以字符串 chunk_id 作为主键的集合
    """
    if not client.has_collection(name):
        if index_type is not None:
            schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
            schema.add_field(field_name="chunk_id", datatype=DataType.VARCHAR,
                             is_primary=True, max_length=128)
            schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dim)
            params = client.prepare_index_params()
            params.add_index(field_name="vector", index_type=index_type, metric_type="COSINE")
            client.create_collection(collection_name=name, schema=schema, index_params=params)
            return
        client.create_collection(
            collection_name=name,
            dimension=dim,
            primary_field_name="chunk_id",
            id_type="string",
            max_length=128,
            vector_field_name="vector",
            metric_type="COSINE",
        )


def insert_rows(client: MilvusClient, name: str, rows: list[dict[str, Any]]) -> int:
    """插入行"""
    client.insert(collection_name=name, data=rows)
    return len(rows)


def count_rows(client: MilvusClient, collection_name: str) -> int:
    """
    统计行数
    Args:
        client: Milvus客户端
        collection_name: 目标 collection 名称
    Returns:
        int: 行数
    """
    res = client.query(collection_name=collection_name, filter="", output_fields=["count(*)"])
    return int(res[0]["count(*)"])


def search(
    client: MilvusClient, name: str, query_vec: list[float], top_k: int = 5
) -> list[dict[str, Any]]:
    """
    搜索结果，返回距离和实体
    实体包含text, page, section, source_file, chunk_id, type, table_md
    这里的distance字段承载COSINE score，分数越大越相似。
    Args:
        client: Milvus客户端
        name: 集合名称
        query_vec: 查询向量
        top_k: 返回结果数量
    Returns:
        list[dict[str, Any]]: 搜索结果
            - distance: 距离
            - text: 文本
            - page: 页码
            - section: 章节
            - source_file: 源文件
            - chunk_id: 块ID
            - type: 类型
            - table_md: 表格元数据
    """
    res = client.search(
        collection_name=name,
        data=[query_vec],
        limit=top_k,
        output_fields=["text", "page", "section", "source_file", "chunk_id", "type", "table_md"],
    )
    return [{"distance": h["distance"], **h["entity"]} for h in res[0]]
