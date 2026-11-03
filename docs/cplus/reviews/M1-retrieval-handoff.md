# M1 R01–R03 混合检索 / OCR 上下文交接

基线3c737327198a55b72d02490a981b5259cd164ffa；分支codex/cplus-hybrid-ocr。只新增retrieval_v2、独立tests和本公开证据。旧selected_scope/preparer/conversation/Agent/Findings/runtime/前端不改。无provider实例、未读.env/预算、未付费。PORTS实际位置为contracts/PORTS_V1.md。

## Root装配合同

`HybridRetrievalService(runtime_root, sources, parse_service, dense_search, embedder=None, embedding_model_version='unknown', memory=None, provider_once=None, identity_validator=None, publication_guard=None, parent_validator=None)`。

- root/sources/parse必须同一DB根。`dense_search(query:str, fast_refs:list[SourceRef], top_k:int)->list[SearchHit]` 可同步/异步，必须使用既有BGE/Milvus、frozen scope filters与publication索引资格；不传OCR到旧dense store。embedder/modelversion参数保留，M1当前不为OCR生成dense向量，OCR是明确FTS检索，不能宣称OCR dense完成。
- `TrustedIdentity(workspace_id,instance_id,generation,principal_id,expires_at:float)` 必须由root生成；浏览器不收这些字段。`identity_validator(identity)` 同步/异步，抛错/返回False拒绝。owner hash绑定全部identity字段，expires_at应使用固定lease expiry而非每请求滚动时间。不可缺省；未配置即403。
- **必需** `publication_guard(identity, fence_payload)` 同步contextmanager。root检查当前lease/instance/principal，取得来源documents/parse artifact/metadata、context、parent conversation及memory generation的真正读取栅栏，保持到内层cplus-research.db COMMIT完成。不能用普通提前GET代替。payload为context（含selected_sources、parent_conversation_id、memory_generation、context hash）或包含selected_sources的字典。源码有前后异步核验，但跨DB原子性必须由root提供；缺guard即503且操作保留unknown。模型调用前短暂进入guard确认，不跨模型调用持锁；最终再次进入guard。
- `parent_validator(conversation_id)` 同步/异步，必须从当前旧repository检查未删除和合法scope；未注入时带parent context拒绝。OCR-only不需旧conversation。`memory`当前复用ResearchMemoryService.tx/_generation/check_generation；没有memory则context generation为null。root guard须按此代际最终复验，不能回灌旧assistant全文。
- `provider_once(question:str,evidence:list[dict])->dict{text:str}` 同步/异步，root适配已有预算guard的generate_once，限制timeout/token/输入，文档文字作为不可信资料，禁止其授权工具/事实。单次answer最多调用一次；先持久unknown，不重放。返回解释保留ai_unreviewed/numeric unverified，无财务权威；不依赖模型自行给引用资格。没配置provider则provider_unconfigured；无足够候选直接insufficient_evidence。最多5条、fast每条最多1200字输入；OCR单行仍需root总输入预算限制。

`create_retrieval_router(service, identity_provider)` 提供API_V1的build/search/enrollment/context/answer POST及context/answer/operation GET。传入已验证身份provider；root唯一负责gateway白名单、read授权、超时与最终源栅栏。GET无模型和自动重建。POST统一返回 `{operation_id,state,result}` 回执，context/enrollment/answer对象在result内。异常安全码，unknown GET不执行任何工作；同UUID/body不同409。

## 数据与检索

SourceRef kind fast/ocr；fast必须workspace/company/document/source_revision/content_sha256/parser_version/report_year及attempt/report_type/basis/period_start/period_end完整当前身份，identity_status=fast_source_verified。OCR含指定artifact_id/artifact_sha256/config_hash/metadata_sha256/selected_pages和file_transcription_only；context使用POST enrollment返回的完整source_ref（含enrollment_id），不能自行伪造OCR enrollment。指定artifact读取不使用active/latest。仍保持legacy failed，不授READY/财务/企业经营核准身份。

EvidenceRef含source_ref/evidence_id/physical_page/text/line_index/bbox；fast匹配当前source record精确子串并拒绝旧unsupported-table page，OCR精确指定artifact页/行与bbox。CPlus不伪装旧evidence refs。独立cplus-research.db存不可变对象/operation及FTS manifests，查询从不建索引；未build明确degraded_not_built。build最多4源/6000段，查询各路最多20，最终5项，trigram参数化，短词无lexical时dense降级。

`search(refs,query,top_k=5)` 返回items，每项独立dense_cosine、lexical_rank、dense_rank、fusion_score（RRF k60）、rerank_score、retrieval_version和typed evidence_ref。query主题展开、叙述/数值密度与理财专项差异作轻量rerank，不全局屏蔽理财。`legacy_fast_adapter(refs,query,top_k=5)` 仅返回确有原始SearchHit且cosine>=0.55、fast可验证的hits，原score不改；lexical-only不进入旧路径。检索分不是人审precision或财务可信度。

## 验证 / 当前限制

3组必要测试：`pytest -q tests/test_cplus_retrieval.py tests/test_cplus_ocr_context.py` →3 passed（5既有Swig弃用warning）；包含FTS-only不伪cosine、原dense兼容门槛、OCR enrollment→context→单次fake answer重放不再调用、linked parent删除拒执行、provider timeout UNKNOWN不重放，legacy仍failed。Ruff通过。fixture guard是nullcontext，不证明root真实跨库fence已接线；实际模型由root后验。

公开脚本 `docs/cplus/evidence/M1-retrieval-real.py` 使用完整venv，HF/TRANSFORMERS_OFFLINE=1、PYTHONPATH=.，新临时物化root seed，真实BGE/Milvus/公开PDF及既有Vision artifact；辅助Harness只向临时副本增加synthetic辅助企业，不写seed。6题沿用M0-retrieval-before.json；首轮过严dense全文等值导致缺失，保留M1-retrieval-first-attempt.json，改精确子串后M1-retrieval-real.json记录最终页序和分数。风险题前两页38/39，已有68行OCR索引查询1hit，真实模型0/财务确认0；seed SHA保持efc10a4...。原M0六题与历史物理70页委托理财误引属于独立证据，不合并冒称本轮before命中。业务/现金流题仍有低cosine或lexical-only候选，不能宣称6题语义质量通过；后续人工相关性评测及拒答policy校准由root推进。

本模块尚未真实HTTP/UI接线、真实模型、最终并发source/memory/lease栅栏验收。OCR目前只有行级FTS；没有新OCR引擎调用、没有OCR dense，原图跳转与财务候选全部root接线。真实proof不含年报全文/原PDF/凭据/数据库。
