# Showcase 最小接口合同 v1.0（M0 已冻结，2026-11-03）

基线：V1.2 `c8be308`。实现只追加；以下是研发合同，不代表端点已经存在。
浏览器 `/api/*`；现有 Vite 去掉 `/api` 后转后端。因此 Python 路由采用 `/demo/*`、`/dashboard/*` 等，不重复前缀。生产同源网关可提供相同映射。
所有 mutation 使用 UUID `operation_id`，严格禁止额外字段；同 operation + 同请求复读既有结果，冲突返回 409；未知结果 GET 查证，不自动换 ID 重发。

## Demo controller / Gateway（owner：Demo worker；runtime 接入：主控）

独立 `demo_control.db`，每代 `active/<generation>/`，immutable seed manifest。Controller 是唯一对浏览器开放的后端；代际子进程 runtime 绑定 loopback 并校验每代随机 internal secret。主控新增 child entrypoint 接到 `create_runtime_app(root)`；不修改旧入口默认行为。

- `GET /demo/status`：公共只返回 `schema_version=demo-status-v1,service_state=ready|resetting|degraded,ttl_minutes,conflict_policy`，不泄漏占用情况/余时/身份。认证成功冲突才显示余时。
- `POST /demo/login`：`{operation_id,username,password}`；服务器 env 配置固定用户名与密码哈希（只接受 20/30 分钟），常数时间验证。成功 Cookie `findoc_demo`（HttpOnly/SameSite，HTTPS Secure）、`Cache-Control:no-store`；同有效 Cookie 登录复用绝对到期时间。
- `GET /demo/session`：200 `{schema_version:demo-session-v1,state:active,expires_at,server_now,remaining_seconds,lease_generation,seed_version}`；401 `{detail:{code:unauthenticated|expired|taken_over,message}}`。不返回 raw token/hash/internal root。
- login 423 `{detail:{code:occupied,message,remaining_seconds,expires_at,takeover_available,lease_generation}}`；错误凭据统一 401，验证前不能查占用。
- `POST /demo/takeover`：`{operation_id,username,password,owner_password,confirm:true,expected_generation}`。默认 wait_only 拒绝；takeover_enabled 必须 owner hash 验证+二次明确确认；公共 takeover 此版关闭。expected_generation 是 CAS 查找线索，服务器重验，失败 409；并发只有一个成功者。
- `POST /demo/logout`：`{operation_id}` 当前 Cookie 验证；撤销、复位，Cookie 清理。Cookie/operation 重复请求可查已完成结果，但不能让撤销 token 访问业务。
- `GET /demo/operations/{operation_id}`：登录/接管前凭据用安全 POST 查证或当前 Cookie 鉴权；不允许仅凭公开 UUID 重发 token。原始token不放operation响应；operation UUID不是授权。登录结果恢复必须重新验证凭据并绑定原operation/request hash；若无法恢复cookie则显示明确重新申请，不允许GET公开换发token。
- `GET /demo/resets/{reset_id}`：脱敏 `state,phase,error_code`，有效当前租约/对应请求所有权才可查询。
- 503 reset_failed 时状态 degraded，禁止所有业务；新 lease 只在 copy/hash/child health 成功后签发。请求若同步耗时先给 resetting/operation，不假装登录成功。

网关所有业务 GET/POST/SSE/file/legacy API 都先校验 active+expiry+generation（无公开绕行）；每个请求捕获固定 runtime handle，不允许等待后重新查全局 current 写库。旧响应最终提交给浏览器前再次查代际，迟到可丢弃；旧进程终止后强杀有界，旧目录不删、不映射至新代。流式每事件校验、断开撤销连接。绝对 expiry 由服务器访问检查+周期 sweeper，不依赖前端计时。reset 串行锁/SQLite 事务，不持数据库写锁等待模型热身；恢复失败关闭。服务重启先校验存量 slot/child，再清理或 degraded，不信任旧 PID 复用。Cookie mutation 验证允许 Origin，拒绝跨源；JSON/header/content-type 与基本限频。Header 只由网关注入，禁止转发浏览器同名 internal header。

**代码依据**：`runtime_factory.create_runtime_app(root)` 已绑定同 root 的 documents.db/agent-runs.db/milvus.db/objects；`InProcessTaskDispatcher` 在 to_thread 处理，取消 async task 不证明同步线程停止。因此选择进程隔离，不覆盖活库。
**实测**：空临时 root，真实缓存 BGE+Milvus 初始化 8.682s，health/companies 200，总 8.704s；无 LLM 请求。不是完整 PDF seed reset 耗时，也不是部署性能保证。

## Dashboard（owner：Dashboard worker；runtime 装配：主控）

- `GET /dashboard/overview` → `schema_version=dashboard-overview-v1,generated_at,data_origin=local_runtime|preset_demo,kpis:{companies,reports_ready,research_completed,reports},task_distribution:[{status,count}],recent_research:[{id,title,status,href,origin,review_status}],suggested_questions:[{id,text,href}],companies:[{company_id,name,security_code}],limitations:[]`。
- KPI 从当前 generation 的真实表聚合，已入库财报按 documents READY + report metadata；完成任务按 payload 状态（不能把全部 tasks 算 completed）；reports 按 reports 一行一个，不按 revisions 加总。环图全部 task 同一分母，failed/refused 明确映射。
- `GET /dashboard/charts?company_id=&metric_key=&sample_mode=false` → `schema_version=dashboard-charts-v1,company_id,metric_key,unit,origin,points:[{period,report_year,value_decimal,source_revision,document_id,fact_ref,source_state}],comparison:[],empty_reason,limitations:[]`。
- 默认只 current_valid + local_operator + 可计算 + 明确披露版本的事实；歧义版本不自动选择。Decimal 以字符串传输。前端 Number 仅绘图坐标，不发布自行计算的财务差额/比例。源服务重验 revision。每点有 source identity；缺失不补零。
- `sample_mode=true` 的 series 完全分离、虚构企业名，`origin=illustrative` + 显著“界面示意数据”，不可返回 fact_ref 或写入 facts；preset_demo 历史仍保留实际审阅状态。前端请求失败不回落成看似真数值。一个只读SQLite快照聚合基础计数，`lease_generation/snapshot_at/seed_version`贯穿返回；独立v2 jobs在接入前不混算旧Task。
- 研究偏好只改变 metric/question 排序；不改变 scope/fact authority。服务端确定建议，点击预填，零自动模型调用。

## OCR / 文档 / 财务 v2

- 官方 GET `/disclosures/search?code=&report_year=` 返回 `{candidate_id,company_code,title,publish_date,report_year,kind:annual_full|summary|amendment,official_url,provider,downloadable}`；POST `/disclosures/import` 只收 candidate_id/company_id/operation_id（URL 另入口严格 allowlist/DNS每跳公网校验/超时/size/magic）。`DocumentSourceService.upload` 仍是企业绑定入口，source_url 只是声明，不代表已验证下载。
- `parse-artifact-v2`：`artifact_id,document_id,content_sha256,source_revision,parser_version,engine{name,version},state:queued|running|partial|completed|failed,pages_total,ocr_pages,created_at,pages:[{physical_page,method:fast|ocr,text,tables:[{table_id,cells[{row,column,text,row_span,column_span,bbox}],quality:preview_only|needs_review}],warnings}],error_code`。
- `GET /documents/{id}/parse-quality`、`POST /documents/{id}/parse-retry {operation_id,expected_source_revision}`；新解析产物 append-only，不能以旧 revision 新内容覆盖。旧 DocChunk.page 是物理1起页码，MinerU page_idx 需 +1；OCR coordinates 未校验不能冒充 verified geometry。OCR 输出永远候选。
- `extended-metric-v2`：`metric_id,company_id,document_id,source_revision,content_sha256,report_year,period,period_kind:instant|duration,as_of_date?,period_start?,period_end?,metric_definition_version,metric_key:total_assets|total_liabilities|debt_asset_ratio|net_margin,value_decimal,unit:CNY_YUAN|PERCENT,status:candidate|confirmed|unsupported,evidence_refs,confirmation_ref?,formula?,input_refs`。真实 confirmed 必须用户明示独立回执；代理不创建 local_operator。独立表/迁移模块，只由主控追加注册。
- GET `/financial/extended-metrics?company_id=`；POST `/financial/extended-analyses {operation_id,metric_refs}` 由服务端检查可比性/来源/确认/Decimal、零分母和负基数，禁止前端传金额。初版2–4项，不扩旧三指标CHECK约束。

## Intent / Findings / Multi-Agent / Memory

- POST `/research/intent {operation_id,conversation_id,text}` 只存提案，不创建Task/事实/模型之外业务副作用；`intent-v2{mode:quick|synthesis|deep,goal,company_ids,periods,metric_keys,actions,clarifying_question,requires_confirmed_facts,source_turn_ids}`；模型提议经 server frozen selection/white list 二验，不授权 workspace/fact IDs。失败规则兜底再澄清。
- POST `/research/handoffs {operation_id,conversation_id,intent_id,confirmed:true}` 重建现有 StartTask 合法请求；持久化关联，拒绝重复任务；人工 ACCEPT/SAVE/RESUME 单独界面动作，不由 handoff 自动触发。
- `research-finding-v2` 是 kind discriminated union：`confirmed_financial`（确定性 financial_refs）、`sourced_excerpt`（exact evidence refs）、`model_interpretation`（AI待审核，不能塞金额当已核准）、`unresolved_question`（缺项/行动）。共通 finding_id/text/origin；统一使用financial_refs（不再使用05里的fact_refs/claim_text或07的unresolved别名）。evidence_ref 复用 document_id/company_id/source_revision/content_sha256/parser_version/physical_page/chunk_id/text。数值陈述须由程序从 deterministic result 渲染或标未核实；不改旧 Result.content 原文拼接合同。
- POST `/synthesis/jobs` 和 `/deep-research/jobs` 仅在明确 scope + approved plan + operation_id 下启动；GET job/history 零模型。job scope 与 generation 固定，持久 jobs/steps/findings/event_seq。
- Supervisor 计划条件路由至少2不同子代理（Evidence / Finance，Risk可选）；不同工具白名单和结构化输出，经 verifier 核验再合并。上限10 provider calls/240s/2子代理并行/单工具超时，budget通过 server 配置收紧；失败不无限循环，不把固定4标签当协作。比较单/多真实调用、耗时与失败，不声称必更优。
- `execution-event-v1 {job_id,event_seq,event_type,agent_id,label,state,public_summary,timestamp}`。GET `/deep-research/jobs/{id}/events?after_seq=` 可 SSE、轮询兜底；只发已持久事件（>=3阶段），最终结果提交后展示，不展示私有思维。
- `research-memory-v1 {memory_id,revision,type:research_question|note|saved_evidence,text,source_conversation_id,source_turn_ids,company_id?,document_id?,source_revision?,confirmed_at,revoked_at?,embedding_model_version,memory_generation,source_status,embedding_revision}`；POST明确confirmed，PATCH/DELETE expected_revision+operation。GET `q/company_id`跨会话语义查询；SQLite是有效/删除/源资格权威，向量索引只是候选，最终再次过滤；过期源不得成为当前财务真值。与旧 MemoryService 枚举偏好并存，不改旧schema意义。
- 报告 v2 保存引用与 finding snapshot，版本不可变；GET `/reports/{id}/revisions/{rev}/export.pdf` 或受控 print route绑定明确版本；新生成/历史/seed/AI待审标签贯穿。打印成功需实际生成PDF查看，不把 window.print 调用等同导出成功。

## 测试预算与恢复

单任务1–3核心逻辑/契约+必要UI smoke；Demo额外双浏览器真实HTTP及旧迟到写入。每阶段主路径+1–2负向；15分钟以上全量套件移至M4，保留失败。UI1440/1280/390截图和CTA，真实OCR/LLM/财务真人独立标注。
每批独立SHA，主控review/cherry-pick/最短回归后集成。回退代码用revert，数据换全新隔离generation；不回写原库、不改旧迁移checksum、不删除历史材料。

## 独立M0评审纳入项（已选择，不扩成生产RBAC）

- owner step-up：POST `/demo/owner-authorize {operation_id,owner_password,confirm:true}`，必须当前有效Cookie、Origin检查，grant绑定session hash+lease_generation，期限min(lease到期,now+5min)，接管/登出/到期失效、响应只含can_review=true；接管仍独立验证owner密码。敏感正式财务写不凭共享密码放行；真人仍需逐步明确ACCEPT/SAVE/RESUME，Agent工具中不暴露owner-authorize/财务写。
- 已核对owner-only路由：POST `/financial-facts/confirmations`、`/financial-facts/persisted`、`/financial-facts/acceptances/{receipt_id}/revoke`、`/revenue-research/confirmations`；任务resume `/research/tasks/{task_id}/resume`（prefix已真实核对为/research/tasks）及评测执行/控制恢复。其余mutation采用显式路由白名单，新增未知写默认拒绝直至主控登记。普通访客保留企业/资料/会话/任务启动/报告/偏好非事实操作；模拟财务练习仅独立sample视图，不写local_operator。
- readiness不得只看存活/health：每代内部接口检查instance_id/generation、seed manifest摘要、SQLite表可读和预期计数、对象哈希/必要索引；真实seed拷贝需停止源或SQLite一致backup，拒绝symlink逃逸、不hardlink可写库。长恢复不占控制事务；旧进程组未确认退出时DEGRADED，不发布新代。
- 登录恢复选择202 pending协议，reset超时/失败返回明确状态；若断线后Set-Cookie丢失，不能凭operation_id换票。pending无业务权限，过期申请复位完成后AVAILABLE。本版选择pending-attempt cookie：POST登录/接管认证成功后登记attempt并设置短期HttpOnly cookie，202时前端GET reset进度；POST `/demo/claim {operation_id}` 只由同pending cookie领取，服务器CAS单次签发，拿不到cookie保留原操作占用状态而不另开lease；cancel/5min超时后reset完成回AVAILABLE。GET `/demo/operations/{operation_id}` 只给当前lease或同pending绑定的脱敏状态，不能换票。
- OCR身份：新增DocumentIdentityAssessmentV2 `{document_id,pdf_sha256,artifact_id,company_id,report_year,report_type,method,status,evidence_refs,review_receipt_id?}`。扫描封面不会因OCR ready自动越过旧matches_cover准入；v2研究通过独立显式身份核对适配，不改旧preparer准入。`artifact_id/engine版本/adapter版本/config_hash/output_sha256/model_revision或unknown`绑定不可变产物，active指针另存；历史按原artifact读，失败/partial不能替代当前完整产物。parse-quality支持artifact_id精确读取。
- Findings信任轴独立：data_origin/source_status/transcription_review_status/interpretation_review_status；OCR引文只表示与提取快照一致，未人工对原图核对时显示ocr_transcription_unreviewed；解释审阅不产生财务回执。模型不可自填confirmed_financial金额/refs，程序读取已选择事实渲染。
- deep scope仅服务端构造：runtime_instance_id/lease_generation/workspace/principal/sources+source_scope_sha/selected_fact_refs+fact_selection_sha/memory_generation/allowed_tools。批准plan绑定revision和scope hash；2子代理不递归委派。全job共享预算10模型尝试（含intent/supervisor/整理）/12工具/并行2/deadline=min(240s,lease余时)，token上下限配置，provider自动retry=0；调用前原子持久预留，UNKNOWN不退款不自动重放。
- Memory三轴分离：lease_generation、memory_generation、source_revision/artifact_id；召回候选后DB过滤有效revision/墓碑/源，发模型前及最终提交复核memory_generation；旧embedding回写带expected_revision，不能复活删改内容；不回灌含已删笔记的完整旧assistant答案。历史已发布回答保留只读，删除仅阻止后续使用。
