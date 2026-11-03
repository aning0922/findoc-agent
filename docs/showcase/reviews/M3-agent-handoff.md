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

## Group 2 frozen UI wire (S02/A01/A02)

首组SHA `d9b913fa655abad5f7abd44b82c6b06743f01a0d` 已单独交割。第二组保持同branch接力，无旧业务文件修改。

IntentRequest追加可选 `requested_mode: quick|synthesis|deep`；旧body兼容。显式用户模式优先，否则只用用户文本的有限模式规则；LLM不允许升级mode。持久budget quick/synthesis/deep分别上限2/5/10。UI quick仍走旧接口，综合/深度需用户显式选择。

1. POST `/research/intent {operation_id,conversation_id,text,requested_mode?}` → 200 `intent-v2`，含intent_id/mode/goal/company_ids/periods/metric_keys/actions/clarifying_question/requires_confirmed_facts/source_turn_ids/proposal_origin/provider_error/scope。
2. POST `/synthesis/plans {operation_id,intent_id}` → 200 `research-plan-v2`，字段：`plan_id,revision,intent_id,conversation_id,goal,mode,company_ids,periods,metric_keys,roles,allowed_tools,limits,plan_origin,provider_error,requires_explicit_confirmation:true,plan_sha256,scope`。GET `/synthesis/plans/{plan_id}`读取原持久计划，零模型。scope公开仅scope_hash/runtime_instance_id/lease_generation/source_scope_sha/fact_selection_sha/memory_generation/allowed_tools；不返回raw私有票据或root路径。
3. POST `/synthesis/jobs` 或 `/deep-research/jobs`，body严格 `{operation_id,approved_plan_id,approved_plan_revision,approved_plan_sha256,confirmed:true}`，route须与计划mode一致。202 `{schema_version:"showcase-job-v2",job_id,mode,state:"queued",conversation_id,plan_id}`；后台执行，同plan最多1job，同operation复读不重启。
4. GET `/synthesis/jobs/{id}` 或 `/deep-research/jobs/{id}` → `showcase-job-v2`：`job_id,plan_id,conversation_id,mode,state,created_at,ended_at,error_code,scope,usage,steps,result`。state为queued/running/completed/partial/interrupted；result只在最终验证并COMMIT后非null。`steps:[{step_id,agent_id,state,tools:[name...]}]`，不发原始思维或未提交中间findings。`usage`为共享intent→plan→job的durable尝试/工具/预留token及unknown数，实际provider token为null（外部费用guard另记）。
5. GET 两个jobs集合均支持可选 `conversation_id=<UUID>` 并验证repository归属，返回 `{schema_version:"showcase-job-list-v2",items:[Job...]}`，当前route按synthesis/deep过滤，最多20条。
6. GET `/deep-research/jobs/{id}/events?after_seq=N`（synthesis同路径也支持）：JSON `{schema_version:"execution-events-v1",job_id,events:[execution-event-v1...],next_after_seq}`。Accept=text/event-stream时输出已有event的 `id: seq\ndata: JSON\n\n`；一次只读重放并关闭，前端可轮询/重连，绝不靠GET启动/继续模型。事件含job_id/event_seq/event_type/agent_id/label/state/public_summary/timestamp，phase/tool都来自实际执行持久记录。
7. 完成结果 `showcase-research-result-v2 {job_id,goal,mode,findings,scope_hash,agents:[{agent_id,state}],data_origin,limitations}`；finding维持kind/text/financial_refs/evidence_refs与四信任轴，不接受客户端findings/金额。

主控需注册native-operation POST：`/research/intent`、`/research/handoffs`、`/synthesis/plans`、`/synthesis/jobs`、`/deep-research/jobs`。不新增财务写Agent工具。factory创建service时新增可选 `execution_data_origin="fake"|"live"|"seed"`，默认fake；真正注入受控付费client并完成证据后由主控显式设live，不从浏览器选择。router提供shutdown close钩子；constructor每代一次，启动会把遗留queued/running job与running step收口interrupted，保留UNKNOWN尝试，不重跑。

## Group 2 mechanism and report reader

- Supervisor根据用户目标选择两种深度路线：Evidence+Finance，或Evidence+RiskOperations；综合single为generalist。真实native-function handler有各自prompt/tool allowlist/最多3轮结构化tool-call→真实handler→tool-result→draft；首个必需函数由SDK tool_choice约束，只有search_evidence/read_confirmed_facts/recall_notes三种本地只读能力。绝无native web/search server tools、递归委派、owner/fact签核或文件写工具。
- Provider/工具调用都先持久预留，失败UNKNOWN不退款/不重放；10次/12工具/并行2/执行≤240s且不超过可信lease expiry；6000 tokens/28000chars输入、单次max_tokens1024、总预留输入48000/输出12000。结果返回长度也检查。外部root成本guard仍负责跨generation 5元总额，本worker真实模型调用0。
- Quote verifier逐条查当前source/evidence/物理页/精确substring，unsupported表页拒绝；财务只读已有用户明确选取且与当前intent公司/指标/期间相符的local_operator，金额由程序渲染。模型不得自填financial_refs；模型数字解释持续numeric_claim_unverified。缺确认只保存unresolved，不制造可计算数据。Finance目前复用旧三指标，不把新资产/负债候选升级。
- 新Memory只用已完成公共recall_snapshot/check_generation/publication_guard。最终job结果事务包含在Memory guard内，COMMIT后才退出；另持source/conversation/preferences读fence到提交，核对Memory来源turn仍存在。Memory/来源变化中断或partial，无无锁发布。结果另存immutable sr_records并与job行交叉校验。
- `async service.verified_job(job_id, identity:RuntimeIdentity) -> dict`：只读，要求completed，重验当前可信身份、sources、quotes、financial资格/确定性文本、Memory generation/publication guard，零模型。返回 `job_id,workspace_id,state,company_name,period_label,data_origin,findings,limitations`。root再投影到S03 VerifiedJobSnapshot，financial_refs只由root投影为已验证ID list[str]，不改核心dict结构。
- S03参考文件在ce18路径读取时不存在，已直接 `git show a08fdc3:docs/showcase/reviews/S03-report-handoff.md` 和同提交models.py读取固定合同。S03 callback只有job_id时，主控必须绑定**当前请求的受信identity**调用上述reader；不从历史job.scope自造“当前权限”。reader验证截至读取，报告最终跨DB保存是否持同fence属于root/S03接线，未冒称该竞态已关闭。

## Group 2 actual checks

`python -m pytest tests/test_showcase_research.py tests/test_showcase_jobs.py -q`：6 PASS（首组3+第二组3代表性），约4.2s；Ruff新模块/两测试文件PASS，diff check PASS。

- 同一个2031经营风险问题，requested_mode=synthesis得到1个generalist、4次fake provider；deep得到Evidence+RiskOperations、7次fake provider、2实际工具调用、各自结构交接、>=3持久阶段、最后合并verifier与保存。数字是受控fixture实测，不是模型优劣结论。
- 财务目标实际走Evidence+Finance，缺确认返回unresolved，没有confirmed_financial或local_operator写入。只读job/history/events及报告reader不增加调用数；同operation不重跑，错误计划hash不执行任何子Agent。
- 并发抢最后1个尝试slot仅1方成功，UNKNOWN保留；Memory在merge期间改变使job=interrupted/result=null；instrumentation证明Memory guard在job数据库真正COMMIT结束后仍持有。该测试Memory为公共协议fake/SQLite，实际owner helper已独立完成，联合真实BGE与新Memory接线仍须root验证。
- 真实FastAPI HTTP(TestClient)走requested_mode覆盖、intent→plan→202job→GET完成→过滤列表→JSON事件/SSE；GET不增模型。不是Chromium UI验收。
- 数据为合成PDF、真实source SQLite/旧Task，embedding/index/LLM provider为fake；费用0，真人签核0。真实付费provider/官方PDF深度执行由root统一在5元总guard内另跑，本worker没有读取原.env或任何未知key。
- 保留5条PyMuPDF/Swig DeprecationWarning。第二组初Ruff仅unused Event import，已移除并复跑；未隐藏失败或警告。

已知限制：真实LLM/真实BGE+Memory/UI/S03最终报告发布/跨代真实双浏览器均未在此worker执行；classic需显式server local_identity，缺身份403；Demo必须child ASGI marker+可信headers，不接受浏览器伪造。Memory和source WAL不能证明锁时关闭。阶段SSE是持久快照重放+轮询而非无限连接。source缺匹配或模型违反结构可能partial/interrupted，不能把这类job当completed报告。provider实际token未知，保守预留数不是实际消耗。

回退按第二组/首组逆序revert；新job库随generation隔离，UNKNOWN/旧目录留作审计，不自动replay，不动旧Graph/content/schema。不创建新子代理，不push/main合并/部署。
