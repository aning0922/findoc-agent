# FinDoc C · M0 独立产品 / 架构评审

日期：2026-11-03（Asia/Taipei）。范围：B01 独立评审；只提交本文件，不实现业务、不部署、不合 main。

**结论：可以继续 B02 合同冻结、独立 UI 和合成数据 spike；当前不能签署 M0 全部通过，更不能宣称 C 版功能已实现。** 推荐独立控制库 + 每代独立子进程 gateway，复用 V1.2 的确定性财务与来源校验；需要先冻结下面 6 项 P0。这里的 P0 是进入相应实现/验收前必须解决的合同缺口，不是声称已在公开环境复现的漏洞。第 8 节已窄复核主控新候选，明确哪些已覆盖、哪些只需补几条规则；Navy 选择沿用主控决定，不再重开设计比较。

## 1. 核验范围与证据等级

- 工作树：`/Users/aipuli/.codex/worktrees/ce18/findoc-agent`；初始为干净 detached HEAD，已新建 `codex/showcase-b01-review`。基线 `92f7fa13a8b1905f3810ef66bc1c5713b4724947`；`git merge-base --is-ancestor c8be308 92f7fa1` 成功，V1.2 底座为 `c8be30808a3ac8c6d13daa5fd9d43c0ea1212c78`。本评审未重新 fetch，也不对远端当前 HEAD 作新声明。
- 主审真实读取工作包 README、00、01、02、03、04、05、06、07、08、09、10、12、14、原型 README/index.html，以及当前 STATE/DECISIONS/KNOWN_ISSUES；下文源码定位以该基线为准。
- 主审读取 `app/api/runtime_factory.py`、`app/api/app.py`、`app/documents/service.py`、`source_service.py`、`source_repository.py`、`preparation.py`、`in_process_dispatcher.py`、`app/rag/parse/mineru_adapter.py`；财务 `financial_analysis.py`、`financial_fact_schema.py`、`financial_reviews.py`、`revenue_research.py`；`app/research/models.py`、`app/reports/contracts.py`；`app/conversations/graph.py`、`tools.py`、`models.py`、`repository.py`；`app/memory/schema.py`、`repository.py`；前端 AppShell、ResearchHome、tokens、shell、ResearchDashboard、productRoutes、package.json、vite.config。三个只读子核查补读 processor/fast parser、metric extraction、report service/persistence、conversation context/summaries 和 memory models/service/API。
- 实际执行：Git 状态/祖先关系检查；离线 Playwright Chromium 打开原型，截取登录和首页的 `1440×900 / 1280×800 / 390×844`，测量 DOM。阻断所有非 file 网络请求，没有启动业务 runtime。**证据等级仅 UI_MOCK + 源码静态评审**。不把浏览器渲染当作认证、后端或真实数据通过。
- 临时视觉检查文件在 `/tmp/findoc-m0-review-ce18/`，不纳入版本库、不作为永久验收附件；可用原型文件复现。未跑业务测试、真实 OCR、BGE/Milvus 重启、官方站查询、付费 API/模型；未读取真实数据库、原 PDF 或密钥。历史 V1.2 测试数字不计入本次。
- 配置记录：派工请求 Astra / ultra；本主审的实际运行模型/推理档位没有可独立核验的会话元数据，故不自证。三个已开始的内部只读核查实际 spawn 参数均为 `model=gpt-6-astra, reasoning_effort=ultra`；这是调度记录，非模型身份探测。收到资源约束后未再扩展代理/会话，子核查均已收敛且未写文件。

## 2. 必须冻结的 6 项 P0

| ID / owner | 代码或规划中的具体缺口 | 最小修正与完成判据 |
|---|---|---|
| P0-1 · B02 / UX | 当前产品首页仍以待核对任务为第一内容；原型只有一套配色，缺完整空态/重置失败态，不能替代两套 token 比较。 | 按第 3 节对同结构、同数据、同状态截图比较一次并锁定；首页 CTA 接到实际路由，三图具有单位、来源状态和可读数值替代。视觉通过不等于数据通过。 |
| P0-2 · L01–L04 / Demo | 现有 runtime 无 DemoLease 网关；请求取消不能证明线程停止；状态机缺 activation/readiness 与恢复的精确边界。 | 按第 4 节统一保护全部业务读写，授权时固定代际/上游；撤销先于 reset；确认旧进程组退出后发布新代；到期和失败均关闭访问。用合成双客户端在途请求 spike 证明。 |
| P0-3 · L01 / 财务 owner | 共享账号与授权操作者未分开；旧确认接口会写 `local_operator`。公开 status 还与“正确凭据后才透露占用”冲突。 | 共享凭据不得换取 owner 权限；正式财务接受/固化等敏感写、接管、恢复和评测分开授权。公开状态不暴露占用余时；秘密、操作恢复、票据策略见第 4 节。 |
| P0-4 · O01–O03 / 资料 | 正式 parser 固定 fast；source 读取按当前全局 parser_version/attempt 重算；扫描封面即使 OCR ready 仍不满足身份准入。 | 冻结不可变 ParseArtifact、当前指针、历史读取和身份复核合同；真实引擎独立 spike，扫描身份与财务接受分开，不能把 manual_check 自动放行。 |
| P0-5 · F01 / S01 / H01 | 05 与 07 的 Findings 字段/枚举不一致；图表、原文、AI 解释的信任轴未完全分开。 | 冻结一个判别联合 DTO；数值走服务器事实/Decimal，OCR 引用不等于原图准确，解释审核不等于财务 acceptance；保留 v1 原文/六项事实合同。 |
| P0-6 · A01 / M01 | 多 Agent 还没有共享预算账本、确定 scope 和删除竞态合同；memory generation 不能代替 lease generation。 | 按第 6 节冻结 job scope、plan 绑定、预算预留、UNKNOWN、DB 二次召回过滤及提交复核；不自动重放，不让旧摘要复活已删除记忆。 |

P0-1 是 B02 视觉完成条件；P0-2/3 是可写演示开放前的硬条件；P0-4/5/6 的合同应先冻结，但其真实能力验证可分别在 M2/M3 完成，不要求 M0 做完整业务实现。

## 3. 首屏和两套 token 的一次性判准

### 3.1 实际观察

`frontend/src/product/ResearchHome.tsx:17–34` 只有研究 Hero、继续核对、最近完成，没有新搜索/KPI/三图；主要 CTA 仍到 `/research?mode=operating`。`AppShell.tsx:10–16` 已有五导航，应复用；`AppShell.tsx:42–61` 已有抽屉键盘焦点处理，不应复制原型时丢掉。现有 `productRoutes.ts:6–39` 保留任务、run、report revision 深链。

随包原型 `index.html:4–12,27–45` 有较完整视觉层次和明确示意标记，但所有数字/登录都在前端模拟。实际渲染结果：

| 视口 | document scrollWidth | Hero 高度 | KPI 顶部 / 第一排图表顶部 | 判断 |
|---|---:|---:|---:|---|
| 1440×900 | 1440 | 301px | 490 / 701px | 首屏可识别品牌、CTA、四卡和图表轮廓；Hero 与区段间距占用较多。 |
| 1280×800 | 1280 | 301px | 490 / 701px | 首屏图表主体过少；压缩 Hero/间距比新增更多卡片更有效。 |
| 390×844 | 390 | 269.4px | 426.4 / 750.4px | 无整体横溢；“企业价值”末字落到下一行，图表被推到下屏，10–11px 说明/按钮偏小。 |

这不是手机功能失败的复现；主要是 B02 待修布局。原型 `showApp()` 同时用于预览/登录且重新设置本地倒计时；`simulateOwner` 不构成授权。空态、重置进行/失败、真实 owner 无权态、图表表格替代尚不能从该原型验收。切换指标有动作，推荐问题仅 toast，没有实际预填业务输入。

### 3.2 两套候选与选择规则

使用同一 DOM、同一测试数据和交互，只切 CSS 语义 token。以下是候选，不是已渲染两套的声明：

| token | A · Navy / Blue | B · Ink / Teal |
|---|---|---|
| nav / canvas / surface | `#111B30 / #F5F7FB / #FFFFFF` | `#173D38 / #F5F6F3 / #FFFFFF` |
| text / secondary | `#17243A / #617084` | `#263B36 / #61706A` |
| primary / accent | `#3F67DB / #147E78` | `#096E66 / #274F78` |
| warning / danger | `#8A5A16 / #A53838` | 同 A，保持状态语义一致 |
| 尺寸与字体 | 两套统一：正文 16px、次文 14px、图表/辅助文字至少 12px；系统中文字体；数字 tabular；8pt 间距；侧栏 224–240px；卡片 16–20px。 | 同 A；不靠更换布局赢比较。 |

B 取自当前 `frontend/src/product/tokens.css`，A 对应工作包候选方向；不能把二者已有色值当成两套高保真已经交付。扩充 `chart-series-* / status-* / focus / border / radius / spacing`，业务组件不要继续各自硬编码一套颜色；任务失败色与财务正负变化色分开。

一次比较：每套提供登录、首页有数据/空态、占用/无接管权、接管确认、恢复/失败、过期/被下线，以及研究/报告代表性视图；三种宽度至少检查核心首页与登录。所有真假标签、键盘焦点、无溢出、无遮挡是硬门槛。其后按首屏层次 30、图表可读 25、跨页一致 20、操作与状态 15、中文排版 10 评分，80/100 为本项目建议门槛；得分相近优先复用成本低者。没有实际截图不填分数，主控选一次后停止无界配色循环。

首屏建议：1280×800 下至少看见一张图的部分有效绘图区；Hero 压到约 220–240px，待核对移动到最近活动。390 下先保证搜索、主 CTA、四 KPI 清晰，允许图表下滚；修单字孤行，tooltip 以键盘/触摸及表格替代补齐。普通文本对比度 4.5:1、控件可点击区域约 44px 可作为本项目检查目标。倒计时不每秒播报，modal 保留焦点闭环。`frontend/package.json` 已有 Recharts 3.10.1，无需另引图表体系。

### 3.3 Dashboard 最小输出合同

建议 `/api/dashboard/overview` 返回 `schema_version, lease_generation, snapshot_at, seed_version?, data_origin, kpis[], task_counts, recent_items[], suggestions[]`。先定义“企业=关注还是已入库”“财报=ready 还是全部”“研究=Task 还是含 DeepJob”“报告=报告实体还是 revision”；一个快照内聚合，不把所有 GET 返回长度直接相加。环图各状态互斥且总和等于该口径任务数；零任务为空态，失败不能画成零。

`ChartSeries` 建议包含 `company_id, metric_key, metric_definition_version, unit, currency, period_kind, points[]`；点包含 `period/as_of_date, report_year, value_decimal?, state, fact_refs[], source_revision, disclosure_version, validated_at`。`data_origin=confirmed_financial|demo_sample|runtime_statistics|preset_case` 和 `source_status=current|stale|missing` 分开。sample 只在单独视图出图，不能混进真实系列；无值保持 null/原因，不补零。当前确认资格由服务端复核；前端只作格式化，不推算正式同比。点击证据时服务端再验证权限/版本。

## 4. DemoReset / gateway 的最小可行隔离

### 4.1 为什么选独立控制层

`runtime_factory.py:207–246,254,320–342` 从同一 root 绑定 documents.db、objects、Milvus、agent-runs.db 和其余仓储；适合“一代一个进程、一套路径”。`DocumentService:54–58` 也保存固定端口引用，故首版不必给每张旧表增加 lease 字段。反过来，在同一个 app 中替换全局 current DB 会让旧调用拿到新资源，不可采用。

`app/api/app.py:100–126,136–173` 当前直接注册并接收业务请求，没有 DemoLease；`in_process_dispatcher.py:50–53` 用 `asyncio.to_thread`，关闭 HTTP/取消 task 不等于工作线程终止。`app.py:128–134` 的 `/health` 只证明存活。`runtime_factory.py:373–389` 隔离 factory 仅校验绝对路径且不是默认 root，尚未实现 generation allowlist。

最小部署形态：唯一公开 gateway/controller，独立持久 `demo_control.db`，只读 seed，`active/<generation>-<instance_id>/` 子进程。runtime 只经私有 loopback/Unix socket 被 gateway 访问；生产代理和开发 Vite 都不能旁路。Vite 当前 `/api` 会剥前缀转发（`frontend/vite.config.ts:12–16`），须明确外部 `/api/*` 到内部原路由的映射，避免双重剥前缀。公共预览用独立固定静态快照，不能代理 active runtime 的 GET。

这是受控代码的路径与生命周期隔离，不是同一 OS 用户下防恶意子进程的安全沙箱；本阶段无需因此建设多租户容器平台。

### 4.2 不变量和状态机

1. **入站绑定**：每个业务请求检查 `ACTIVE + token hash + lease_generation + expires_at`，在同一控制状态快照固定 `runtime_instance_id + endpoint`；读取大请求体或等待后再次确认资格，不允许改投新的 current。所有读、写、PDF、导出、SSE 都受保护，不能只拦 POST。
2. **旧代永不变新代**：目录、端口实例、进程句柄不可复用为另一代；不用可变 `current` symlink 让旧进程重新解引用。旧结果只可能留在隔离的旧目录或被终止，不能复制进新代；网关在返回响应/推送事件前复查，撤销后关闭流，禁止跨代自动重试 POST。
3. **撤销先行**：SQLite 短事务 CAS 撤销旧 lease 并登记唯一 reset；关闭入口/流 → 终止并确认旧 runtime 进程组退出 → 新目录复制 → manifest/库与索引验证 → 启动 → readiness → CAS 当前 reset/目标代际后发布。复制/启动等长操作不持有控制库写事务。
4. **失败关闭**：停止超时、磁盘/校验/启动失败、控制库不可读、启动恢复未完成，均不能继续代理旧业务或签发 active lease。保持 `RESETTING/DEGRADED` 和脱敏 reason。controller 重启先恢复/核对 reset、进程实例和期限，不能仅见 PID 存在就信任原路由。
5. **绝对期限**：成功 activation 才设置 issued/expires；刷新与标签复用不续租。每次 admission 按服务器时间判断，到期清理 sweeper 只是辅助；expiry、logout、takeover 复用一条撤销/reset 路径。任务 deadline 不晚于 lease deadline；到期前开始的结果也不能在到期后继续向用户发布。
6. **新代准入**：readiness 至少核对 instance/generation、seed manifest、数据库可读与预期计数、必要对象/索引可用；不能只 GET `/health`。readiness 不调用付费模型。恢复无人认领时进入 AVAILABLE；有经过验证且仍有效的申请者才签发 ACTIVE。
7. **路径/种子**：只接受服务端生成且位于指定 active root 的路径；seed、真实 runtime、Git/证据目录禁止成为 reset 目标。可写文件不与 seed 共用 hardlink，拒绝逃逸 symlink。seed 数据库来自一致导出/停止后的快照，不能只复制正在写的 SQLite 主文件而忽略 WAL。删除只清理已确认退出的已登记旧代，不接受页面传路径。

### 4.3 控制 DTO / 权限 / 幂等

| 合同 / API | 最小字段及语义 |
|---|---|
| `DemoSlot`（私有） | `slot_id, state, generation, runtime_instance_id?, reset_id?, active_session_hash?, expires_at?, seed_version, updated_at`；CAS 写入，generation 永不倒退。 |
| `DemoOperation`（私有） | `operation_id, action, request_digest, requester_binding, state, reset_id, result_ref?, created_at`；同键不同内容 409，同键同内容只读既有结果。operation_id 不是授权凭据。 |
| `DemoSessionV1`（公开给本人） | `state, server_time, expires_at, remaining_seconds, lease_generation, viewer_can_takeover`；不返回原始 token、内部路径/endpoint 或其他访客身份。 |
| `POST login/takeover/logout` | body 最多为业务动作、operation_id、必要凭据/确认；客户端不能决定 TTL、代际或 root。耗时恢复返回 202 与 operation/reset ID，activation 后才签发 active Cookie。reset 查询须绑定已验证的申请者或 owner。 |
| `GET status/session/resets` | 未认证 status 只暴露服务可用性；认证后才返回占用与剩余时间。session 本人可读；reset 查询需要请求者凭证，不能靠猜到 ID。GET 不触发模型或重复 reset。 |
| 错误 | 401 无有效身份、403 无 owner/CSRF 授权、409 代际/操作冲突、423 已认证但占用、503 暂不可提供业务。轮询可以返回明确 RESETTING 状态，但业务路由关闭。 |

固定共享密码和 owner secret 分开，只在 controller 验证；密码哈希比较、token 随机且仅存哈希，HttpOnly/SameSite/Secure Cookie，变更请求 Origin/CSRF 检查、基本登录限速。owner 凭据不得下发 runtime、写 URL、前端 bundle 或日志；`viewer_can_takeover` 不授予权限。默认 wait_only，不启用公众互踢。

异步登录必须再冻结一个小细节：reset 进度的请求者绑定与最后领票方式。可用短期 HttpOnly pending-attempt 凭证，准备好后由同一请求者领取；它不具备业务权限。**只存 session 哈希时，丢失 Set-Cookie 不能凭 operation_id 重新恢复明文 token**；首版可明确返回无法恢复/占用并走受控恢复，不得为重试另开 lease。请求取消/申请超时后完成 reset，应 AVAILABLE，不占用一张无人持有的租约。

旧正式财务接口至少包含 `/financial-facts/confirmations`（`financial_reviews.py:158–165`）和 `/revenue-research/confirmations`（`revenue_research.py:125–136`）；后者硬编码 `local_operator`，前者来自 `app.py:74` 默认值。主控须列出接受、撤销、固化等完整写路由映射，默认拒绝未知写路由，不能只在 UI 隐藏按钮。首版建议正式签核仅授权 owner 人工执行；普通访客可读已核准 seed、操作非事实业务，练习确认走独立 demo_sample 语义。即使 owner 登录也不能由 Agent 自动代签。没有真人回执时用样例视图继续展示，不能伪造 seed receipt。

## 5. OCR、数据版本与三层可信内容

### 5.1 真实引擎和身份接入

`runtime_factory.py:220–234` 固定 `parse_fast_pdf_bytes`；`mineru_adapter.py:164` 只读取现成输出目录，不是运行 OCR。现在 `source_revision = hash(document_id, PDF_SHA, attempt, parser_version)`（`source_repository.py:18–20`）；`source_service.py:133–155` 读取时用当前全局 parser_version 再算一遍。故换一个 parser callable 或升级全局版本不足以保留历史来源，可能错标 OCR 为 fast 或使旧引用读不到。

更直接的主路径阻断：`source_service.py:23–32` 封面用 `get_text()`，扫描封面会 `manual_check`；`preparation.py:121–124` 明确只收三个 `matches_cover`。新解析 ready 不能绕过这一 gate。新增身份评估只证明公司/报告年/类型，不证明表中金额。

| 新合同（提案） | 必需内容 |
|---|---|
| `ParseArtifactV2` | `artifact_id, document_id, pdf_sha256, source_revision, engine_name/version, adapter_version, model_revision?, config_hash, output_sha256, status, physical_page_count, page_results[], created_at`。没有实际模型版本则空值/unknown；产物不可变，当前活动指针另存。 |
| `PageParseResultV2` | `physical_page` 1 起算，`method=text_layer|ocr, status, warnings, evidence_ids[]`；支持定位时保存 bbox、页面尺寸/旋转和坐标系；OCR confidence 可空且不是确认状态。 |
| `DocumentIdentityAssessmentV2` | `document_id, pdf_sha256, artifact_id, company_id, report_year, report_type, method, status, evidence_refs[], review_receipt_id?`；OCR 封面自动建议保持待核对，人工身份接受绑定快照。不得改旧 manual_check 为自动有效。 |
| retry / quality | `POST /api/documents/{id}/parse-retry` 收 `operation_id, expected_source_revision, parser_profile_id`，返回 job/artifact；`GET parse-quality?artifact_id=…` 精确读版本。不接任意路径、命令或客户端指定的可信版本。 |

新研究准入明确的有效产物，历史阅读按原 artifact，不静默跳到最新；旧产物被替代可保留只读并标 stale，不能自动继续计算。失败/partial 新产物不能覆盖旧完整结果；选定全部来源必须一致，不可悄悄删去 OCR 失败页后称“全文已处理”。索引发布绑定 artifact/source revision，异步结果只回所属 generation。

最小引擎选择规则：O01 在隔离环境挑一个实际可运行版本，记录命令/依赖、模型版本、授权样本 SHA、页数、耗时/资源和失败原因。此次未安装或查询最新版，不推荐未经核验的版本/GPU 指标。可先交 parser adapter 与 UI，真实引擎未跑通仍标 UNKNOWN/blocked_external。

表格是明确限制：当前 `mineru_adapter.py:86–103` 未处理 rowspan/colspan 属性，产物缺旧财务抽取使用的 layout；`metric_extraction.py:165` 无 layout 返回空观察值。首版可标 unsupported/待人工查看，不能平铺错列后称复杂表格正确；这只阻断该表格的结构/财务承诺，不阻断其他文本和首页开发。

### 5.2 唯一 Findings DTO 与财务 v2

05 使用 `finding_type/claim_text/fact_refs/unresolved_question`，07 使用 `kind/text/financial_refs/unresolved`。窄复核后建议沿用主控候选的命名，统一为 `schema_version, finding_id, kind, claim_text, origin, evidence_refs[], fact_refs[]`，`kind` 固定四种；不为命名差异再引入另一份 schema：

| kind | 程序准入与展示 |
|---|---|
| `confirmed_financial` | 必须引用当前有效事实/receipt 或确定性 analysis；服务端恢复数值并渲染，保留 company、metric、财务期间、disclosure_version、source revision、币种/口径、formula/version。模型不能填 confirmed、金额或 receipt。 |
| `sourced_excerpt` | 必须匹配具体 artifact/evidence/page 与 text hash；`source_status` 与 `transcription_status` 分开。OCR “与提取快照相符”不等于“与 PDF 原图准确一致”，明确 `ocr_transcription_unreviewed`。 |
| `model_interpretation` | 引用现有 finding/evidence，保存 run/模型配置标识；默认 `interpretation_review_status=unreviewed`。引用身份正确不证明因果成立；用户审阅解释不产生财务接受回执。 |
| `unresolved` | 给 `reason_code, required_action`；缺数/缺证据保留空值与待办，不能附仿真的核准数字。 |

金额/比例/百分数只能来自确定性结构字段并通过引用渲染；不采用“LLM 自由写任意数字 + 简单正则扫数字”作为可信保证。原文中的数字可作为明确标注的引文展示，但不能自动转成财务事实。AI 解释不支持的数字断言应阻断/转未核实。数据 origin、source 有效性、transcription 审阅、interpretation 审阅是独立轴，不混成一个 `verified_data` 徽章。

复用边界：`research/models.py:83–109` 要求 content 等于原文拼接；`reports/contracts.py:126–139` 固定六事实/三分析，解释待审；`financial_fact_schema.py:26` 限定三指标。快读摘要、新指标、深度报告新建 v2 schema/renderer，不能删旧约束硬塞。`financial_analysis.py:91–159` 的事实身份、版本、口径与 Decimal 准入值得复用。

扩展指标首批建议总资产/总负债与由此计算的资产负债率，范围依真实可核样本选择。必须增加 `period_kind=instant|duration`、`as_of_date` 或起止期间、`metric_definition_version`、公式输入事实、缺失/不可比原因；资产负债时点值不能套全年流量合同。value 用 Decimal 字符串，零分母/负基数/不同口径显式处理；不能把 report_year 当数值 period。新层独立表与 adapter，不改旧迁移 checksum。

## 6. Multi-Agent / Memory 的最小合同

### 6.1 真实基础与 job

`conversations/graph.py:34–57` 为有限规则图、`checkpointer=None`、单轮 deadline 240 秒；不是已实现的多 Agent。`tools.py:133–157` 要求本轮 explicit fact_selections，并验证完整来源/receipt/period，FinanceAgent 不能因为“查到了事实”就绕过显式选取。v2 确认计划绑定服务器冻结的事实清单，或继续显式选择；自动挑选披露版本是另外一条需冻结规则。

最小实现可用 Supervisor + Evidence + Finance，程序 Verifier；最多两个工作子代理、每个一轮、无递归委派，至少一次根据计划条件选择任务，简单问答保留单 Agent。不同角色必须具有不同输入、工具白名单和结构输出；仅记录四个名称不能算协作。Finance 可使用确定性工具，不必为了角色数重复调用 LLM；真实模型参与情况逐角色记录。

| 合同 | 必需字段/约束 |
|---|---|
| `ExecutionScopeV2`（仅服务端构造） | `runtime_instance_id, lease_generation, workspace_id, principal_id, sources[], source_scope_sha, selected_fact_refs[], fact_selection_sha, memory_generation, allowed_tools[]`；子代理只能收窄；source 保留 PDF SHA、parser/artifact、期间、口径等完整身份。 |
| `CreateDeepResearchJob` | `operation_id, goal, document_ids[], conversation_id?, mode, approved_plan_id, approved_plan_revision`；批准绑定服务器保存的计划/范围，模型不能自设 approved。 |
| `Job / Step / Event` | `job_id, scope_hash, plan_revision, step_id, parent_step_id, role, attempt_id, status, provider_outcome, result_refs[], error_code, started/ended_at`；事件另有单调 `event_seq, public_summary`；partial/failed/interrupted/unknown 不改写为 completed。 |
| `Budget / Usage` | job 统一 `max_model_attempts, max_tool_calls, max_input/output_tokens, deadline, reserved_attempts/tools, actual_tokens?, usage_unknown`；意图、Supervisor、子代理、整理、重试共用账本，embedding/OCR 另记实际资源。 |

现有 `models.py:261–263` 为单轮 2 模型/3 工具；`repository.py:369–393` 调用前持久预留并把 provider outcome 置 unknown。新 job 复用该模式，不给每个子代理发一整份预算。建议快速/综合/深度的模型上限先配置为 2/5/10（均含意图与整合），深度工具最多 12、并行工作子代理最多 2、自动 provider 重试 0，deadline 取任务配置与 lease 剩余时间较小者；这些是待 spike 校准的上限，不是已测吞吐/成本。UNKNOWN 不退款也不自动重放；新 operation 的显式重试须显示潜在重复调用。GET/SSE 重连仅重放已存事件，不执行模型。事件只给公开摘要，不输出私有推理。

### 6.2 Memory 的 scope、更新和删除

`memory/schema.py:7–20` 只容纳三个枚举偏好；`memory/repository.py:17` scope 固定 `("demo","local_operator")`，现有显式保存/幂等/expected_revision/删除墓碑和 context generation 可作参考。这个内部旧标识不等于共享访客拥有财务 owner 权限；同名 workspace/principal 的跨访客隔离仍依赖独立 generation 存储。

新增 ResearchMemory 用独立表：`memory_id, kind, text, revision, company_id?, source_conversation_id?, source_turn_ids[], evidence_refs[], created_at, confirmed_at, revoked_at?, source_status, embedding_model_version, embedding_revision`；内部另绑定 server scope。kind 首版仅研究问题、用户备注、收藏引用；保存须明确操作，Patch/Delete 带 `operation_id + expected_revision`。记忆文本即使含金额也不能成为 FinancialFactRef。

三种版本不能混用：`lease_generation` 管访客环境；`memory_generation` 管上下文失效；`source_revision/artifact_id` 管来源内容。召回先限制 server scope/企业/来源，再语义检索，再读 DB 过滤 revoked、旧 revision、失效来源；发模型前与最终事务提交前核对 memory generation。删除即使向量残留也必须立即不可召回；异步 embedding 回写带 expected_revision，旧结果不能复活已删/已更新条目。

旧摘要、召回缓存和正在执行的 job 也受删除影响；最小方案只注入当前有效笔记与结构历史，不回灌含旧金额/已删笔记的完整 assistant 答案。现有 `graph.py:101–104` 已有 memory admission 检查，但不是 lease fence。历史已发布回答可以保留只读，明确“删除记忆阻止后续使用，不自动删历史报告”；对话删除时，独立用户备注可保留并标来源不可用，引用收藏/来源依赖笔记失效不可召回，不能悄悄换来源。现有偏好解除 source turn 的行为（`memory/repository.py:125–137`）不应不加区分复制给引用记忆。

## 7. 接入点、可继续事项与最小验证

### 7.1 文件所有权与可立即继续的工作

| 工作 | 推荐新模块 / 唯一集成点 | 可以继续的边界 |
|---|---|---|
| Demo 控制 | 新 `app/demo/*`；私有子进程 launcher 复用隔离 factory；主控接 Vite/入口 | 先实现合成 seed、状态机和 gateway；不需读真实数据库或启动付费模型。 |
| Dashboard / 视觉 | 新 `app/dashboard/*`、Dashboard*、demo shell；AppShell/ResearchHome/productRoutes 由主控整合 | token、mock DTO、空失败态、聚合口径与跳转先行；无真人事实时 sample 独立。 |
| OCR / 官方导入 | 新 `app/parsing/*`、`app/disclosures/*`；DocumentProcessor parser/source_recorder/source_identity 与 SourceService 由主控接 | 合同和合成 adapter 可做；O01 真引擎/D01 官方可用性保持未验证。上传复用当前 20MiB 校验，增大上限前统一路由与服务限制。 |
| 财务 / 综合 / 报告 | 新 finance_v2、synthesis、reports/v2；复用旧 admission/Decimal | 先独立 union/schema 与 renderer；不伪造真人签核，不放宽旧 Result 或六项回执。 |
| 深度研究 / 记忆 | 新 deep_research、research_memory；`runtime_factory.py:324–342` 由主控注入 | 提取 scope/fact adapter；不要把依赖 TurnExecution 和单轮限额的 ConversationTools 原样当 job 执行器，不复用旧 TaskCheckpointer 身份。 |

三条演示路线保留：① 登录→首页→证据→退出/恢复；② 官方/合法预置资料→解析/OCR→身份/财务核对→报告；③ 深度任务→真实交接→保存研究线索→新会话召回→删除。F01–F18 不删除，下面仅说明新工作与复用层，全部仍需 C 版本直接证据。

| 功能 | 可复用 / 仍需新增 |
|---|---|
| F01 / F02 / F03 | 现有五导航/路由；新增 Demo 控制、Dashboard 聚合/三图、统一新手入口。 |
| F04 / F05 / F06 | 现有上传/fast/Decimal；新增官方源、真 OCR/版本身份、独立扩展指标。 |
| F07 / F08 / F09 | 规则上下文/原文与事实工具/旧任务；新增 LLM Intent、FindingV2、显式 handoff。 |
| F10 / F11 / F12 | 有限 Graph/枚举偏好；新增真实分工、语义研究记忆、首页与报告可见个性化。 |
| F13 / F14 / F15 | 已有工具事件/报告版本 Markdown；新增 job 阶段流、v2 图表报告/PDF、同题单多 Agent 评测。 |
| F16 / F17 / F18 | 已有页面和部分空失败态；新增合法可复原 seed、收藏笔记、统一 token/响应式与真实走查。 |

### 7.2 只做以下必要验证，不扩成全面边缘审计

| 验证 | 最小操作与准入证据 | 本次状态 |
|---|---|---|
| 视觉比较 | 同数据两套 token；核心三宽截图、主 CTA、空态/冲突/失败、键盘/图表替代。 | 原型单套 UI_MOCK 已查看；两套比较未做。 |
| Demo 隔离 | 临时合成 seed + 两个真实子进程/浏览器上下文；A 阻塞上传/模型，B 接管或 A 到期后释放；N+1 内容/计数等于 seed，A 无新代读写/响应；同 operation 只一次；在撤销后/发布前注入启动失败或 controller 重启仍关闭访问。 | 未执行；UNIT_FAKE/BROWSER_FAKE 待做，不能由静态评审宣布安全。 |
| 真实启动耗时 | 另在授权隔离样本上测 BGE/Milvus cold/warm、退出确认、seed/index 恢复；readiness 不发 LLM 请求。 | UNKNOWN；假依赖隔离实验不能推出启动性能。 |
| OCR 版本/身份/引擎 | 先合成 fast/OCR 产物验证旧引用不漂移、失败不覆盖；再真实扫描/混合页→身份待审→显式身份接受→研究；一张合并表格逐页对原图并保留 unsupported。 | 未执行；引擎真实证据与合同测试分记。 |
| Findings/财务 | 错公司/期/receipt/来源、OCR 候选、备注数值、模型百分比不能进 confirmed；合法原文/Decimal 可用；旧三指标与 ACCEPT/SAVE/RESUME 关键回归。 | 未执行；静态读取不能代替回归。 |
| Agent/Memory | 两子任务抢最后预算只能一方调用；预留后断线/重启保留 UNKNOWN；固定任务真分工；删除时故意留下向量/旧摘要/在途 job 均不新召回/提交；更新时旧 embedding 不回写。 | 未执行；真实模型/embedding 能力另记 REAL_DATA_REAL_MODEL。 |

D01 官方发现/下载必须后续查当前官方规则并实际验证；本次未进行外网调查，不能声称某旧 JSON API 可用。下载器仍需官方来源 allowlist、逐跳公网地址校验、大小/超时/PDF magic/SHA；手动合法上传/预置资料可继续其他路线。

## 8. 对主控 API_MINIMUM 候选的窄复核（最终补充）

只读文件：`/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/docs/showcase/contracts/API_MINIMUM.md`；读取时集成 HEAD 为 `972fd196a5e8c140f58ab49294389b030b5d71b4`、工作树干净，文件 Git blob 为 `88497ff0909b1dc37f5cfc63f17d97fab4679e72`。这是其他工作树的合同快照，不是本分支新增实现。本次没有 cherry-pick，也没有修改主控文件。

**已覆盖、可直接保留：** 第 9/21 行的唯一 gateway、每代 internal secret、固定上游 handle、全部读写保护、逐事件复核、expiry/失败关闭；第 28–33 行的 KPI 口径、Decimal 字符串、独立 sample 视图；第 38–41 行的 append-only OCR 产物与独立扩展指标；第 47–52 行的 Findings 判别联合、程序数值、持久事件、SQLite 记忆权威和报告版本。无需推翻这些决定或建设生产 RBAC。

以下是候选在冻结前**必须补清**的少量规则；对应此前 P0，避免把后端任务分给不同人后再解释口径：

| 候选位置 | 必须修改的具体内容 | 最小执行方式 |
|---|---|---|
| Demo 第 11/14 行 | 公共 status 仍区分 available/occupied，暴露了“是否有人使用”，与正确凭据后才可查占用的规则冲突。 | 公共只给 service_state=ready\|resetting\|degraded；available/occupied 与余时放认证后的 login/conflict。 |
| Demo 第 15–21 行 | 只有 takeover 验 owner，旧正式财务写没有 owner-only 名单。 | 增加下述五条现存写路由的 step-up gate；共享 lease 可读财务/预览候选，其余非签核业务照常；不重写旧业务权限系统。 |
| Demo 第 17–21 行 | `GET operations` 描述里混有未命名的 POST 查证；`copy/hash/child health` 没明确 activation CAS、旧进程组退出确认和 readiness 内容。 | 明确一个 POST 恢复/领票契约，或首版同步登录并明确丢票恢复；原操作请求者绑定不能仅靠 UUID。写明撤销→确认旧进程组退出→复制验证→readiness→CAS 发布；health 之外核对实例/seed/业务只读探针。 |
| OCR 第 38–39 行 | append-only 方向正确，但读接口没有 artifact 参数；缺每份产物的 adapter/config/output 身份；扫描封面尚无研究准入。 | quality/history 可按 artifact_id 精确读，活动指针独立；增加 adapter_version/config_hash/output_sha256（模型有则 model_revision）；增加独立 DocumentIdentityAssessment 和人工身份接受，不放宽旧 manual_check。 |
| 财务第 40–41 行 | total_assets/liabilities 是时点值，当前只有 period，可能与 net_margin 等期间值误比较。 | 增加 period_kind、as_of_date 或 period_start/end、metric_definition_version；服务端检查口径与日期；不扩旧三指标表。 |
| Findings 第 47 行 | exact evidence refs 不能表达 OCR 转录尚未核对，统一徽章易暗示原图/解释均可靠。 | 沿用 kind/claim_text/fact_refs/unresolved 命名；evidence 增 artifact_id（适用时）及 transcription_status，解释独立 interpretation_review_status；事实资格只由服务端确定。 |
| Job 第 45–49 行 | 有调用次数上限，但未写共享预留/UNKNOWN；approved plan 未绑定 revision、source/fact selection。Intent 虽无业务写也会发生模型费用。 | 同一 job 账本包含意图、子代理、整合与重试；调用前持久预留，UNKNOWN 不自动退款重放；plan_id/revision 绑定冻结来源和显式事实清单；deadline ≤ lease expiry，自动 retry=0。 |
| Memory 第 51 行 | DB 过滤正确，但缺 source_status/embedding_revision，以及调用前/提交前失效检查与旧摘要处理。 | 增这两个字段；明确 server scope + lease_generation 与 memory_generation 不同；删除/update 递增 memory generation，旧向量/旧摘要/在途结果不能进入新上下文或提交；历史保留与引用失效按第 6 节。 |

### 8.1 共享 lease 与 owner 真人操作的最小方案

不新增用户注册或 RBAC。controller 在当前会话保存 `owner_elevated_until`，例如 `POST /api/demo/owner/verify {operation_id,owner_password}` 成功后设为 `min(当前 lease 到期, now + 5min)`；期限为建议值，主控可配置更短。能力绑定当前 session hash + generation，接管/登出/到期即失效，不能靠前端布尔值。共享密码永远不能完成 step-up，owner 密码不转发给 runtime。

网关按 HTTP 方法 + 规范路由匹配下列 owner-only 写操作（浏览器外部带 `/api`，表中为现存内部路径）：

| 方法 / 内部路径 | 语义 / 真实位置 |
|---|---|
| POST `/financial-facts/confirmations` | ACCEPT，`app/api/financial_reviews.py:158`。 |
| POST `/financial-facts/persisted` | SAVE，`app/api/financial_reviews.py:238`。 |
| POST `/financial-facts/acceptances/{receipt_id}/revoke` | 撤销事实接受，`app/api/financial_reviews.py:231`。 |
| POST `/revenue-research/confirmations` | 旧兼容收入确认，`app/api/revenue_research.py:125`；必须同样拦截，不能遗漏 legacy。 |
| POST `/research/tasks/{task_id}/resume` | 显式 RESUME，`app/api/research_tasks.py:82`。 |

新扩展指标身份接受/财务接受接口按相同规则登记。共享 lease 的财务 GET 与 `/financial-facts/reviews` 等候选预览可用；通过旧有效 seed 事实进行只读分析不需要重新签核。三步仍是独立按钮：真实人看 PDF 后 ACCEPT，明确 SAVE，再 RESUME；step-up 本身不签核，Agent/handoff 不代点。普通访客可继续资料、会话、记忆和其他已授权功能；缺真实事实的路线保留待审或 demo_sample。将来若要公开访客实际签核，需要另定义可信 actor/receipt 语义，此版不做。

### 8.2 新增证据的归属与限制

主控消息及候选第 24 行报告：全新临时空 runtime，真实缓存 BGE+Milvus，ready 8.682s、health/companies 200，总 8.704s、LLM 0；脚本位置为集成树 `experiments/showcase/runtime_startup_spike.py`。本次按收敛要求未重跑或独立审查脚本/输出，因此记录为**主控报告的空 runtime 启动证据**。它可解除“完全没有实际启动时间”的不确定性，不能推导完整 seed copy、索引恢复、旧进程停止或端到端 reset 的时间/正确性；第 7 节相应项目仅本评审未执行，后续不必无理由重复空启动测量。

主控报告已独立查看 `370e3d0` 两套 token 截图并选 Navy，登录/状态流仍在修订。本评审接受 Navy 为后续方向，不要求重开颜色选择；第 3 节的缺口特指随包单套原型，不是对该新提交的截图评价。新原型修订与状态流由主控按已定判准验收，本分支未移用其证据。

## 9. 交割判断

建议主控将本报告的最小合同合入 B02 决策后，分别推进 Demo 合成隔离、视觉双 token、OCR/语义记忆适配器。无需为等待真人财务签核、外网官方源或 OCR 设备暂停所有工作；这些保持 human_pending / UNKNOWN / blocked_external 并使用明确的样例/原文路线。

M0 尚待：第 8 节合同补充落定、主控进行中的原型状态流修订验收，以及完整 seed/reset spike 的范围/负责人落定；Navy 已按主控决定继续，空 runtime 启动证据不再重新要求。真正的跨代隔离仍须在 M1 可写演示验收前实测。**本评审完成不等于 M0、M1、真人签核、合并或发布通过。** 产物只包括本文件；业务文件、数据库、PDF、密钥和其他工作树均未修改。
