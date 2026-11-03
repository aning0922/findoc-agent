# M3 Agent 最小实施接力（主控，2026-11-03）

先读原工作包05/07和API_MINIMUM，再看真实代码。新增 app/showcase_research 或 app/synthesis/deep_research 命名空间均可，但不改旧 ResearchRun content、旧Graph协议、旧迁移/财务签核。主控拥有runtime/Conversations/AppShell/gateway热点。

## 真实可复用依赖

- ConversationRepository.selection(cid,text) 给服务端冻结范围，旧ConversationService.create只核验来源不发模型；detail/turn/user_text/history由repository读，不信前端自报workspace/doc/fact scope。
- DocumentTaskPreparer.prepare_many/revalidate：1–4份READY+封面company/year/type matches_cover，完整固定来源身份。OCR新产物manual_check不能偷走旧入口；当前先对真实文本PDF研究。
- SelectedScopeSearch.search(selection,top_k=5) 是真实BGE/Milvus，SearchHit有实际workspace/document/source_revision/chunk/page/text。table_context有unsupported页保护。新的引用verifier要再用sources.parsed_evidence/page_context查原文归属与精确excerpt，不能把仅有ID当证据。
- 旧FinancialAnalysisService与RevenueConfirmationService.admit_reference/query/read只能读取用户明确选择的local_operator事实；无已核准事实输出unresolved，不得创建receipt或自动选latest。Multi-Agent工具没有owner-authorize/confirm/save/resume。
- llm_client.generate_once/complete 明确关闭SDK重试；所有真实provider调用必须先原子持久预留，预算含intent/supervisor/子代理/整理，不对UNKNOWN退款或重放。
- PersistentTemplateService.start(StartTaskV2) 为旧财务研究创建入口；可以构造合法TemplateRequest后明确用户确认创建关联Task，绝不调用resume/ACCEPT/SAVE。TaskRepository.by_operation可只读恢复。
- ResearchMemoryService独立模块正在完成，先以协议注入，禁止用旧枚举MemoryService冒充语义召回。只把有效笔记快照送模型；不回灌可能含已删笔记的旧assistant全文。最终提交需持有独立memory_generation read fence至job commit（默认rollback journal，WAL不支持则拒绝）。

## C01/C02/S01先交割

- POST `/research/intent {operation_id,conversation_id,text}` 返回持久intent-v2/intent_id。输入最多8轮用户问题及已确认偏好，LLM结构化提议后程序检查公司/年度/指标/turn来自冻结范围；失败有限规则再澄清。不是模型写权限。10–20固定复杂题，假/真实provider分开。
- POST `/research/handoffs {operation_id,conversation_id,intent_id,confirmed:true}` 严格恢复已有两种模板可支持的公司/期间。客户端不传金额/fact authority。创建Task只一次；未知结果按原operation GET读回，不自动另建，返回task链接/缺少核对动作。原Conversation不需改存储schema，可通过v2关联表GET发现。
- Findings v2 是kind/text/financial_refs/evidence_refs标准discriminated union，信任轴data_origin/source_status/transcription_review_status/interpretation_review_status分开。confirmed_financial只由服务器已有admitted facts确定性渲染；sourced_excerpt为真实原文；model_interpretation持续AI待审，数字不经确定性来源不能当已核准（拒绝或明确numeric_claim_unverified）；unresolved_question说明缺口。旧ResearchRun不变。

## S02/A01/A02有限真实执行

可新增 `/synthesis/plans` 为拟议/可确认计划，冻结scope hash与revision；POST `/synthesis/jobs` 与 `/deep-research/jobs` 只接受已确认plan ID/revision/hash+operation，客户端不能改source scope/工具/预算。GET job/history/events绝不启动/续跑模型。

- 简单快速路仍走旧真实工具；综合模式共享新只读工具和verifier；深度模式Supervisor根据目标条件实际选择至少2不同子Agent。Evidence只做证据，Finance只读已核准与缺口，Risk/Operations做披露风险。不是每次跑同样角色标签；子Agent有独立prompt/tool allowlist、结构化输入输出和真实模型调用/交接轨迹，不递归委派。至少一固定案例证明动态选择角色。
- 单job最多10 provider尝试/12工具/并行2/deadline≤240秒或lease余时，服务端上限可收紧；tokens/输入输出大小受控。先持久预留再call，UNKNOWN不重试；进程重启running收口interrupted而非重跑。当前尚无有效LLM配置，真实provider验证待部署者给配置，离线研发继续但不声称模型已跑。
- 原始工具结果/quote由程序verifier按固定源再读、查SHA/revision/页/精确text；模型不能自填有效金融引用或把candidate升级。失败可保存unresolved，不输出假漂亮总结。
- scope固定runtime instance/generation/workspace/principal/source_scope_sha/fact selection/memory_generation/tools；root Gateway将提供可信lease expiry头，Agent预算不能依前端倒计时。
- 持久steps/events/findings。execution-event-v1含单调event_seq、agent_id、label/state/public_summary、timestamp，仅公开阶段/工具/用量/错误，不发私有CoT。≥3实际阶段，SSE可读取持久事件+轮询，刷新不重新发模型。最终commit之后呈现“已保存”。

## owner / 交付

worker只新增业务命名空间、对应tests与自己的handoff；根runtime/main/Conversations/网关政策由主控注册。API constructor/DTO先落有限handoff，随后可继续开发；关键依赖不确定直接明确问主控而非猜函数名。按C01+C02+S01一组独立SHA，S02+A01+A02第二组独立SHA；A03 UI由前端owner另做。

代表性预算：1–3关键逻辑/契约+固定10–20意图题，真实单/多provider各一典型例子需配置；不要把fake provider计成真实AI能力、测试数计成功能数。控制核心主路径和真实性，其他边界P2后续。无财务真人签核、无部署/大额外部费用/新子代理/推main。
