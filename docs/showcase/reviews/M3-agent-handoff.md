# M3 Agent worker: implementation wire and evidence

2026-11-03；工作树 `/Users/aipuli/.codex/worktrees/4eab/findoc-agent`，分支 `codex/showcase-c01` 从集成 `c23c0a842ba6d62a9c24dc59ec05fbf45edec531` 建立，保留f01/l01。只新增app/showcase_research、对应tests、本交接；旧Graph/content/迁移/runtime/Conversations/gateway不改。已读root未commit的M3-agent.md、05/07/API_MINIMUM、ce18 M01-memory-handoff及实际旧依赖。以下接口先落盘，随后实现。

## Group 1: C01/C02/S01

- `ShowcaseResearchService(runtime_root, *, conversations, preparer, sources, search, facts, task_service, task_repository, llm_client=None, preferences=None, research_memory=None, local_identity=None)`，独立generation-local `showcase-research.db`。`create_showcase_research_router(service, *, identity_provider=None)`；主控唯一装配点。
- `RuntimeIdentity(instance_id, lease_generation, lease_expires_at, workspace_id, principal_id)`只由server provider返回。Demo provider要求ASGI `findoc_private_identity` marker与X-Findoc-Generation/Instance匹配，expiry从可信网关注入ISO头解析；没有marker时不信浏览器这些header。classic必须显式server local_identity，不自动猜身份。
- POST `/research/intent {operation_id,conversation_id,text}`：持久intent-v2 + intent_id，来源/企业来自conversation.selection和preparer.revalidate；最多8轮用户问题及结构焦点，不回灌旧assistant全文；已确认偏好从旧MemoryService.recall_context读取，独立研究笔记不作事实。模型结构提议经程序范围/年份/指标/actions/turn白名单二验；失败有限规则再澄清，不创建Task/事实。
- GET `/research/intents/{intent_id}`、GET `/research/operations/{operation_id}`、GET `/research/conversations/{conversation_id}/links`：只读持久结果，零模型。
- POST `/research/handoffs {operation_id,conversation_id,intent_id,confirmed:true}`：重建合法StartTaskV2，只支持同公司2期间或2公司同期间；每侧固定旧三指标，无已选事实时ID空并明确等真人核对。歧义来源版本拒绝，不选latest；单intent只建一个Task。UNKNOWN按旧TaskRepository.by_operation只读查证，不重跑start。不调用accept/save/resume。
- ResearchFindingV2使用kind/text/financial_refs/evidence_refs及四个信任轴；模型draft schema没有confirmed_financial分支。confirmed由真实admitted reference确定性渲染；引文必须原页精确归属；模型数字解释标numeric_claim_unverified，不能成为财务引用；unresolved_question含缺项/行动。

## Group 2: S02/A01/A02

- POST `/synthesis/plans {operation_id,intent_id}`：Supervisor提案经程序条件路由，保存plan_id/revision/scope_hash/plan_sha256/roles。计划不授权写财务。
- POST `/synthesis/jobs`、`/deep-research/jobs`：`{operation_id,approved_plan_id,approved_plan_revision,approved_plan_sha256,confirmed:true}`；scope/goal/工具/预算均从已存计划恢复，客户端不能提交authority。每plan最多一个job；GET job/history/events不调用provider。
- GET `/synthesis/jobs/{id}`、`/deep-research/jobs/{id}`，GET各自集合；GET `/deep-research/jobs/{id}/events?after_seq=`持久事件轮询，Accept SSE时只重放已存事件，不启动执行。
- 同一intent→plan→job共享预算账本：max10尝试/12工具/并行2，quick/synthesis可收紧至2/5；provider调用前原子预留+UNKNOWN，返回后记returned，异常UNKNOWN不退款不自动重放。input/output tokens和长度有限，真实SDK默认retry=0；job执行deadline=min(now+240s,lease expiry)，用户确认等待不自动启动模型。
- 深度条件选择Evidence+Finance（财务目标）或Evidence+RiskOperations（风险/经营目标）；每个handler独立prompt、工具白名单、结构化tool call/result与公开步骤。最多2子代理，无递归。真实模型可运行但本轮配置缺失；fake测试必须标明。
- 程序Verifier复核固定source/SHA/revision/页/精确excerpt，FinancialAnalysisService.admit_reference只读用户明确选择的local_operator，缺事实输出unresolved而不是金额。最终结构结果经verifier后入新表，旧ResearchRun不变。
- Memory最终公共协议使用 `await recall_snapshot(q, company_id=None)`、发模型前 `check_generation(gen)`、最终 `with publication_guard(gen,{memory_id:revision,...})`；job数据库COMMIT必须在guard内完成，退出后才释放SHARED锁。不读取Memory私有表/不重写owner栅栏；source/conversation/preference由本模块另做最终只读附加事务复核，WAL不支持则关闭。不是普通GET generation后写入。

主控接线需求：登记所有新mutation为native operation；header只能由gateway注入；router身份provider可用模块默认严格Demo provider，classic需显式local身份。旧provider缺少max_tokens参数，新SDK wrapper只注入max_tokens/timeout/retry=0，再复用现有generate_once/complete，不改旧文件。真实LLM配置未提供，不读未知key、不借Codex登录token、不产生外部模型费；当前仅授权离线fake，真实模型PASS必须另有明确执行证据。

## Group 1 implementation/checkpoint

已新增strict DTO、scope恢复/最终fence、独立操作+共享budget ledger、受限provider SDK代理、intent程序二验/规则澄清、独立Findings union/真实source verifier、显式旧Task handoff。新SDK代理只注入max_tokens=1024及超时，再复用既有generate_once/complete；主控可在更外层叠加共享费用guard，本worker不读取provider key、不发付费请求。

`python -m pytest tests/test_showcase_research.py -q`：3 PASS（约2.2s），包含15条固定意图题；fake provider仅证明JSON/范围/降级协议，不是语义模型质量验收。另测错误公司提议降级、精确原文+虚构引文拒绝、模型数字只能numeric_claim_unverified、UNKNOWN计费不退款/不重放、伪造身份header403、过期401、同op幂等/冲突。handoff真实调用PersistentTemplateService.start + TaskRepository，生成一个awaiting_human_confirmation旧Task，复读只查by_operation，不重复start、无人签/保存/resume。Source为合成PDF，embedding/index/chunk IDs为fake；真实LLM=0，真人财务签核=0。

`ruff check app/showcase_research tests/test_showcase_research.py` PASS。保留PyMuPDF/Swig 5条DeprecationWarning。首轮1FAIL/2PASS为“泛财务研究任务没有具体metric词时requires_confirmed_facts未置true”，已按财务任务语义修正规则并复跑；unused imports同步修正。未执行真实LLM、真实BGE/新Memory联调、UI、main/部署。Group2不依赖重新许可继续同owner实现，完成后独立SHA。
