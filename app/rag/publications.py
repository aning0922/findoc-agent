"""Build immutable Milvus generations; only verified publications may be searched.

SQLite publication is the commit point. Crashes before it leave inaccessible collections.
Every query verifies all rows, then verifies hits and current SQLite state again. No
process-local cache can restore eligibility after a restart. Cleanup only drops revoked
or failed generations; building generations require explicit recovery on startup.
"""

from collections.abc import Mapping
from contextlib import closing
import hashlib
import json
import math
import struct
import uuid
from typing import Any

from pymilvus import MilvusClient

from app.companies.sqlite_repository import SQLiteCompanyRepository
from app.rag.ingest import ReplaceResult
from app.rag.retriever import IndexVersionUnverifiedError, SearchFilters, TrustedContext
from app.rag.store import ensure_document_collection

PAYLOAD_FIELDS = ('workspace_id', 'document_id', 'source_revision', 'content_sha256',
                  'attempt', 'parser_version', 'chunk_id', 'page', 'text', 'type',
                  'table_md', 'section', 'source_file', 'data_version')


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def row_digest(row: Mapping[str, Any]) -> str:
    payload = {k: row[k] for k in PAYLOAD_FIELDS}
    vector = row['vector']
    if not vector or not all(math.isfinite(v) for v in vector):
        raise IndexVersionUnverifiedError('invalid_vector')
    payload['vector_sha256'] = hashlib.sha256(
        struct.pack(f'<{len(vector)}f', *vector)
    ).hexdigest()
    return digest(payload)


class IndexPublications:
    def __init__(self, registry: SQLiteCompanyRepository, client: MilvusClient) -> None:
        self.registry = registry
        self.client = client

    @staticmethod
    def _current(conn: Any, manifest: dict[str, Any], *, building: bool = False) -> None:
        row = conn.execute(
            'SELECT d.status, d.attempt, d.content_sha256, s.parser_version, s.physical_pages, '
            's.invalidated_at FROM documents d JOIN document_sources s '
            'ON d.document_id=s.document_id AND d.workspace_id=s.workspace_id '
            'AND d.attempt=s.attempt AND d.content_sha256=s.content_sha256 '
            'WHERE d.workspace_id=? AND d.document_id=? AND s.source_revision=?',
            (manifest['workspace_id'], manifest['document_id'], manifest['source_revision'])
        ).fetchone()
        if (row is None or row['invalidated_at'] is not None
                or row['status'] not in (('indexing',) if building else ('ready',))
                or any(row[k] != manifest[k] for k in
                       ('attempt', 'content_sha256', 'parser_version', 'physical_pages'))):
            raise IndexVersionUnverifiedError('index_source_not_current')

    def _read_rows(
        self, generation: str, ids: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        self.client.load_collection(collection_name=generation)
        count = self.client.query(collection_name=generation, filter='',
                                  output_fields=['count(*)'])[0]['count(*)']
        if ids is None:
            # Diagnostic callers only; publication verification supplies the full manifest IDs.
            if count > 16000:
                raise IndexVersionUnverifiedError('manifest_ids_required')
            return list(self.client.query(collection_name=generation, filter='',
                         output_fields=[*PAYLOAD_FIELDS, 'vector'], limit=max(1, count)))
        if count != len(ids):
            raise IndexVersionUnverifiedError('index_row_count_mismatch')
        rows: list[dict[str, Any]] = []
        for start in range(0, len(ids), 128):
            rows.extend(self.client.get(collection_name=generation, ids=list(ids[start:start+128]),
                                        output_fields=[*PAYLOAD_FIELDS, 'vector']))
        return rows

    def _verify_rows(self, generation: str, manifest: dict[str, Any]) -> None:
        if manifest.get('index_type') is not None:
            actual_index = self.client.describe_index(generation, 'vector')
            if actual_index['index_type'] != manifest['index_type']:
                raise IndexVersionUnverifiedError('index_profile_changed')
        rows = self._read_rows(generation, tuple(manifest['rows']))
        actual = {r['chunk_id']: row_digest(r) for r in rows}
        if len(actual) != len(rows) or actual != manifest['rows']:
            raise IndexVersionUnverifiedError('index_manifest_mismatch')

    def publish(self, document_id: str, rows: list[dict[str, Any]]) -> ReplaceResult:
        if not rows:
            raise IndexVersionUnverifiedError('empty_index')
        first = rows[0]
        identity = {k: first[k] for k in ('workspace_id', 'document_id', 'source_revision',
                                        'content_sha256', 'attempt', 'parser_version')}
        if identity['document_id'] != document_id:
            raise IndexVersionUnverifiedError('index_identity_mismatch')
        with closing(self.registry._connect()) as conn:
            source = conn.execute('SELECT physical_pages FROM document_sources '
                                  'WHERE source_revision=?', (identity['source_revision'],)).fetchone()
        if source is None:
            raise IndexVersionUnverifiedError('source_snapshot_missing')
        manifest = dict(identity, physical_pages=source[0], rows={}, index_type='FLAT')
        for row in rows:
            if (any(row[k] != v for k, v in identity.items())
                    or type(row['page']) is not int or not 1 <= row['page'] <= source[0]
                    or not row['text'].strip() or not row['chunk_id'].strip()
                    or (row['type'] == 'table' and not row['table_md'])):
                raise IndexVersionUnverifiedError('index_row_invalid')
            manifest['rows'][row['chunk_id']] = row_digest(row)
        if len(manifest['rows']) != len(rows):
            raise IndexVersionUnverifiedError('duplicate_chunk')
        generation = 'fd16_' + uuid.uuid4().hex
        with closing(self.registry._connect()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            self._current(conn, manifest, building=True)
            conn.execute('INSERT INTO index_publications VALUES (?,?,?,?,?,?,?)',
                         (generation, identity['workspace_id'], document_id,
                          identity['source_revision'], canonical(manifest), digest(manifest), 'building'))
        try:
            ensure_document_collection(self.client, generation, dim=len(first['vector']), index_type='FLAT')
            for offset in range(0, len(rows), 128):
                self.client.insert(collection_name=generation, data=rows[offset:offset + 128])
            self.client.flush(collection_name=generation)
            self._verify_rows(generation, manifest)
            with closing(self.registry._connect()) as conn, conn:
                conn.execute('BEGIN IMMEDIATE')
                self._current(conn, manifest, building=True)
                conn.execute("UPDATE index_publications SET state='complete' WHERE generation=? "
                             "AND state='building'", (generation,))
            # A distinct commit records complete-but-unpublished versions after a crash.
            with closing(self.registry._connect()) as conn, conn:
                conn.execute('BEGIN IMMEDIATE')
                self._current(conn, manifest, building=True)
                conn.execute("UPDATE index_publications SET state='revoked' "
                             "WHERE workspace_id=? AND document_id=? AND state='active'",
                             (identity['workspace_id'], document_id))
                changed = conn.execute("UPDATE index_publications SET state='active' "
                                       "WHERE generation=? AND state='complete'", (generation,))
                if changed.rowcount != 1:
                    raise IndexVersionUnverifiedError('publication_lost')
        except Exception:
            with closing(self.registry._connect()) as conn, conn:
                conn.execute("UPDATE index_publications SET state='failed' WHERE generation=?",
                             (generation,))
            raise
        return ReplaceResult(len(rows), 0, 0, frozenset(manifest['rows']))

    def _current_manifest(self, workspace: str, document: str, revision: str) -> tuple[str, dict[str, Any]]:
        with closing(self.registry._connect()) as conn, conn:
            conn.execute('BEGIN')
            row = conn.execute("SELECT * FROM index_publications WHERE workspace_id=? "
                               "AND document_id=? AND source_revision=? AND state='active'",
                               (workspace, document, revision)).fetchone()
            if row is None:
                raise IndexVersionUnverifiedError('index_publication_missing')
            manifest = json.loads(row['manifest_json'])
            if (digest(manifest) != row['manifest_sha256']
                    or any(manifest[k] != row[k] for k in
                           ('workspace_id', 'document_id', 'source_revision'))):
                raise IndexVersionUnverifiedError('index_manifest_corrupt')
            self._current(conn, manifest)
        return row['generation'], manifest

    def assert_current(self, workspace: str, document: str, revision: str) -> None:
        """Cheap admission before query embedding; not an index integrity receipt.

        Full rows are still read and verified immediately before native search
        and again after it. No eligibility or integrity result is cached.
        """
        generation, _ = self._current_manifest(workspace, document, revision)
        if not self.client.has_collection(generation):
            raise IndexVersionUnverifiedError('index_publication_missing')

    def verified(self, workspace: str, document: str, revision: str) -> tuple[str, dict[str, Any]]:
        generation, manifest = self._current_manifest(workspace, document, revision)
        self._verify_rows(generation, manifest)
        return generation, manifest

    def search(self, vector: list[float], context: TrustedContext, filters: SearchFilters,
               top_k: int, *, query: str = "") -> list[Mapping[str, Any]]:
        if not filters.source_revisions:
            raise IndexVersionUnverifiedError('versioned_scope_required')
        verified = [self.verified(context.workspace_id, d, r)
                    for d, r in filters.source_revisions]
        hits: list[Mapping[str, Any]] = []
        for generation, manifest in verified:
            # Exact section/field anchors restrict this same versioned Milvus query.
            # Text narrows relevance only; it can never create workspace/source authority.
            anchor = ''
            if query == '主要会计数据和财务指标':
                anchor = 'text like "%主要会计数据和财务指标%"'
            elif query == '公司简介 股票简称 股票代码 公司中文名称':
                anchor = '(text like "%股票简称%" or text like "%股票代码%")'
            result = self.client.search(collection_name=generation, data=[vector], limit=top_k,
                                        filter=anchor, output_fields=[*PAYLOAD_FIELDS, 'vector'])
            for hit in result[0]:
                entity = hit['entity']
                if manifest['rows'].get(entity.get('chunk_id')) != row_digest(entity):
                    raise IndexVersionUnverifiedError('index_hit_mismatch')
                hits.append(dict(entity, score=float(hit['distance'])))
        # Whole set is checked again, even if no hit was returned for one selected document.
        for (generation, _), (doc, rev) in zip(verified, filters.source_revisions, strict=True):
            if self.verified(context.workspace_id, doc, rev)[0] != generation:
                raise IndexVersionUnverifiedError('index_publication_changed')
        with closing(self.registry._connect()) as conn, conn:
            conn.execute('BEGIN')
            for generation, manifest in verified:
                self._current(conn, manifest)
                state = conn.execute('SELECT state FROM index_publications WHERE generation=?',
                                     (generation,)).fetchone()
                if state is None or state[0] != 'active':
                    raise IndexVersionUnverifiedError('index_publication_changed')
        ranked = sorted(hits, key=lambda h: float(h['score']), reverse=True)
        if len(filters.source_revisions) == 1:
            return ranked[:top_k]
        # Reserve ranked evidence from every selected report before filling further slots.
        # This keeps a nearly identical newer report from starving the older report's evidence.
        groups = [[h for h in ranked if h['document_id'] == doc]
                  for doc, _ in filters.source_revisions]
        balanced: list[Mapping[str, Any]] = []
        for rank in range(top_k):
            for group in groups:
                if rank < len(group) and len(balanced) < top_k:
                    balanced.append(group[rank])
        return sorted(balanced, key=lambda h: float(h['score']), reverse=True)

    def recover(self) -> None:
        """Explicit single-process startup recovery, before dispatcher/search admission.

        Interrupted builds never become ready automatically; explicit document retry is required.
        Active ready generations survive only after full verification. Failed cleanup is retryable.
        """
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("UPDATE index_publications SET state='failed' "
                         "WHERE state IN ('building','complete')")
            entries = conn.execute("SELECT * FROM index_publications WHERE state='active'").fetchall()
        for entry in entries:
            try:
                self.verified(entry['workspace_id'], entry['document_id'], entry['source_revision'])
            except Exception:
                with closing(self.registry._connect()) as conn, conn:
                    conn.execute("UPDATE index_publications SET state='revoked' WHERE generation=?",
                                 (entry['generation'],))
        with closing(self.registry._connect()) as conn, conn:
            conn.execute("UPDATE documents SET failed_stage=status, status='failed', "
                         "error_code='INDEX_BUILD_INTERRUPTED', "
                         "safe_error_message='索引构建中断，请显式重试' "
                         "WHERE status IN ('queued','parsing','indexing')")
        self.cleanup()

    def cleanup(self) -> None:
        with closing(self.registry._connect()) as conn:
            entries = conn.execute("SELECT generation FROM index_publications "
                                   "WHERE state IN ('failed','revoked')").fetchall()
        for entry in entries:
            if self.client.has_collection(entry[0]):
                self.client.drop_collection(entry[0])
