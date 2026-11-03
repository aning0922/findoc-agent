# Showcase 最小接口合同 v0.1（M0 候选，独立审查后冻结）

基线：V1.2 `c8be308`。实现只追加；以下是研发合同，不代表端点已经存在。
浏览器 `/api/*`；现有 Vite 去掉 `/api` 后转后端。因此 Python 路由采用 `/demo/*`、`/dashboard/*` 等，不重复前缀。生产同源网关可提供相同映射。
所有 mutation 使用 UUID `operation_id`，严格禁止额外字段；同 operation + 同请求复读既有结果，冲突返回 409；未知结果 GET 查证，不自动换 ID 重发。

## Demo controller / Gateway（owner：Demo worker；runtime 接入：主控）

独立 `demo_control.db`，每代 `active/<generation>/`，immutable seed manifest。Controller 是唯一对浏览器开放的后端；代际子进程 runtime 绑定 loopback 并校验每代随机 internal secret。主控新增 child entrypoint 接到 `create_runtime_app(root)`；不修改旧入口默认行为。

- `GET /demo/status`：公共只返回 `schema_version=demo-status-v1,state=available|occupied|resetting|degraded,ttl_minutes,conflict_policy`，不泄漏占用余时/身份。认证成功冲突才显示余时。
- `POST /demo/login`：`{operation_id,username,password}`；服务器 env 配置固定用户名与密码哈希（只接受 20/30 分钟），常数时间验证。成功 Cookie `findoc_demo`（HttpOnly/SameSite，HTTPS Secure）、`Cache-Control:no-store`；同有效 Cookie 登录复用绝对到期时间。
- `GET /demo/session`：200 `{schema_version:demo-session-v1,state:active,expires_at,server_now,remaining_seconds,lease_generation,seed_version}`；401 `{detail:{code:unauthenticated|expired|taken_over,message}}`。不返回 raw token/hash/internal root。
- login 423 `{detail:{code:occupied,message,remaining_seconds,expires_at,takeover_available,lease_generation}}`；错误凭据统一 401，验证前不能查占用。
- `POST /demo/takeover`：`{operation_id,username,password,owner_password,confirm:true,expected_generation}`。默认 wait_only 拒绝；takeover_enabled 必须 owner hash 验证+二次明确确认；公共 takeover 此版关闭。expected_generation 是 CAS 查找线索，服务器重验，失败 409；并发只有一个成功者。
- `POST /demo/logout`：`{operation_id}` 当前 Cookie 验证；撤销、复位，Cookie 清理。Cookie/operation 重复请求可查已完成结果，但不能让撤销 token 访问业务。
- `GET /demo/operations/{operation_id}`：登录/接管前凭据用安全 POST 查证或当前 Cookie 鉴权；不允许仅凭公开 UUID 重发 token。具体重试响应不可泄漏 secret。
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
- `sample_mode=true` 的 series 完全分离、虚构企业名，`origin=illustrative` + 显著“界面示意数据”，不可返回 fact_ref 或写入 facts；preset_demo 历史仍保留实际审阅状态。前端请求失败不回落成看似真数值。
- 研究偏好只改变 metric/question 排序；不改变 scope/fact authority。服务端确定建议，点击预填，零自动模型调用。

## OCR / 文档 / 财务 v2

- 官方 GET `/disclosures/search?code=&report_year=` 返回 `{candidate_id,company_code,title,publish_date,report_year,kind:annual_full|summary|amendment,official_url,provider,downloadable}`；POST `/disclosures/import` 只收 candidate_id/company_id/operation_id（URL 另入口严格 allowlist/DNS每跳公网校验/超时/size/magic）。`DocumentSourceService.upload` 仍是企业绑定入口，source_url 只是声明，不代表已验证下载。
- `parse-artifact-v2`：`artifact_id,document_id,content_sha256,source_revision,parser_version,engine{name,version},state:queued|running|partial|completed|failed,pages_total,ocr_pages,created_at,pages:[{physical_page,method:fast|ocr,text,tables:[{table_id,cells[{row,column,text,row_span,column_span,bbox}],quality:preview_only|needs_review}],warnings}],error_code`。
- `GET /documents/{id}/parse-quality`、`POST /documents/{id}/parse-retry {operation_id,expected_source_revision}`；新解析产物 append-only，不能以旧 revision 新内容覆盖。旧 DocChunk.page 是物理1起页码，MinerU page_idx 需 +1；OCR coordinates 未校验不能冒充 verified geometry。OCR 输出永远候选。
- `extended-metric-v2`：`metric_id,company_id,document_id,source_revision,content_sha256,report_year,period,metric_key:total_assets|total_liabilities|debt_asset_ratio|net_margin,value_decimal,unit:CNY_YUAN|PERCENT,status:candidate|confirmed|unsupported,evidence_refs,confirmation_ref?,formula?,input_refs`。真实 confirmed 必须用户明示独立回执；代理不创建 local_operator。独立表/迁移模块，只由主控追加注册。
- GET `/financial/extended-metrics?company_id=`；POST `/financial/extended-analyses {operation_id,metric_refs}` 由服务端检查可比性/来源/确认/Decimal、零分母和负基数，禁止前端传金额。初版2–4项，不扩旧三指标CHECK约束。

## Intent / Findings / Multi-Agent / Memory

- POST `/research/intent {operation_id,conversation_id,text}` 无业务写副作用；`intent-v2{mode:quick|synthesis|deep,goal,company_ids,periods,metric_keys,actions,clarifying_question,requires_confirmed_facts,source_turn_ids}`；模型提议经 server frozen selection/white list 二验，不授权 workspace/fact IDs。失败规则兜底再澄清。
- POST `/research/handoffs {operation_id,conversation_id,intent_id,confirmed:true}` 重建现有 StartTask 合法请求；持久化关联，拒绝重复任务；人工 ACCEPT/SAVE/RESUME 单独界面动作，不由 handoff 自动触发。
- `research-finding-v2` 是 kind discriminated union：`confirmed_financial`（确定性 fact_refs）、`sourced_excerpt`（exact evidence refs）、`model_interpretation`（AI待审核，不能塞金额当已核准）、`unresolved`（缺项/行动）。共通 finding_id/claim_text/origin。evidence_ref 复用 document_id/company_id/source_revision/content_sha256/parser_version/physical_page/chunk_id/text。数值陈述须由程序从 deterministic result 渲染或标未核实；不改旧 Result.content 原文拼接合同。
- POST `/synthesis/jobs` 和 `/deep-research/jobs` 仅在明确 scope + approved plan + operation_id 下启动；GET job/history 零模型。job scope 与 generation 固定，持久 jobs/steps/findings/event_seq。
- Supervisor 计划条件路由至少2不同子代理（Evidence / Finance，Risk可选）；不同工具白名单和结构化输出，经 verifier 核验再合并。上限10 provider calls/240s/2子代理并行/单工具超时，budget通过 server 配置收紧；失败不无限循环，不把固定4标签当协作。比较单/多真实调用、耗时与失败，不声称必更优。
- `execution-event-v1 {job_id,event_seq,event_type,agent_id,label,state,public_summary,timestamp}`。GET `/deep-research/jobs/{id}/events?after_seq=` 可 SSE、轮询兜底；只发已持久事件（>=3阶段），最终结果提交后展示，不展示私有思维。
- `research-memory-v1 {memory_id,revision,type:research_question|note|saved_evidence,text,source_conversation_id,source_turn_ids,company_id?,document_id?,source_revision?,confirmed_at,revoked_at?,embedding_model_version,memory_generation}`；POST明确confirmed，PATCH/DELETE expected_revision+operation。GET `q/company_id`跨会话语义查询；SQLite是有效/删除/源资格权威，向量索引只是候选，最终再次过滤；过期源不得成为当前财务真值。与旧 MemoryService 枚举偏好并存，不改旧schema意义。
- 报告 v2 保存引用与 finding snapshot，版本不可变；GET `/reports/{id}/revisions/{rev}/export.pdf` 或受控 print route绑定明确版本；新生成/历史/seed/AI待审标签贯穿。打印成功需实际生成PDF查看，不把 window.print 调用等同导出成功。

## 测试预算与恢复

单任务1–3核心逻辑/契约+必要UI smoke；Demo额外双浏览器真实HTTP及旧迟到写入。每阶段主路径+1–2负向；15分钟以上全量套件移至M4，保留失败。UI1440/1280/390截图和CTA，真实OCR/LLM/财务真人独立标注。
每批独立SHA，主控review/cherry-pick/最短回归后集成。回退代码用revert，数据换全新隔离generation；不回写原库、不改旧迁移checksum、不删除历史材料。
