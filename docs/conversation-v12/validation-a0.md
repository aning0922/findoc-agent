# V1.2 A0 验收准备

日期：2026-11-02（Asia/Taipei）。状态：**验收设计完成；V1.2 功能尚未验收**。

A0 初始阶段只写本文件；主控统一冻结合同、分配测试文件和提交。A0 阶段未修改业务代码、数据库、测试、依赖或 Git index；未启动模型或重复运行主控基线。之后主控授权的 A4/G 工程准备单列在第8节。唯一代码来源为 findoc-agent 的独立 worktree `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`，实际分支为 `codex/conversation-memory-v12-20261102`。

## 1. 已读来源与现状

- `handoff/README.md`、`01_PRODUCT_UX.md`、`02_TECH_DESIGN.md`、`03_PHASES_ACCEPTANCE.md`、`04_CODEX_KICKOFF.md`，以及 `baseline.md`、`orchestration.md`。
- `tests/support/controlled_agent_app.py`：真实 HTTP/业务/SQLite，embedding、store、provider 为确定替身；绝对 runtime 且拒绝默认目录，只预置 synthetic 文档。可借鉴隔离及故障开关，不能证明真实年报检索或多轮对话。
- `frontend/playwright.config.ts`、`frontend/scripts/run-e2e.sh`：新建临时 runtime、清除模型凭据、禁用环境文件、单 worker、零重试、拒绝复用服务。**默认 testMatch 只有 `agent*.spec.ts`**，新增 conversation 测试必须有显式配置，不能仅运行默认命令后宣称覆盖。
- `frontend/e2e/qa-workspace.spec.ts`：已有 UNKNOWN A→B 范围切换、原文不可变、原 PDF 身份、来源失效、预算和只读计数断言，可迁移测试思想而非复用旧结论。
- `scripts/run_ux_simplification.py`、`frontend/scripts/run-financial-boundary-e2e.py`：真实 PDF/HTTP/SQLite、模拟财务接受，非真实模型。前者仍从历史 `findoc-analyst-v1-d9` 读取 PDF，后者硬编码本 worktree `.venv/bin/python`；新运行器应使用当前 worktree 已校验 PDF 和显式 Python 路径，不能未经适配直接执行。
- `scripts/validate_ux_live.py`：全新 runtime、SHA 校验、单次 provider 调用、GET 读回、无财务接受。它调用旧 `/research/runs`，不构成新 Conversation 验收。
- `scripts/d30_live.py`、`scripts/run_d16_live_browser.py`、`frontend/e2e/d17-qa-live.spec.ts`、`frontend/e2e/d30-live-readonly.spec.ts`：可借鉴运行身份、物理页/PDF SHA、只读 HTTP 记录和人工待审标签；其中旧索引、旧 runtime、固定 run 或具体金额断言不可移植为本轮通过证据。
- `product/ux-simplification/verification.md` 是历史 UX 验收记录。本轮仍需验证当前 SHA 的回归，不能直接继承其中 PASS。

`baseline.md` 当前记录：前端 184 PASS / 25 SKIP / 0 FAIL，lint/build 通过且有原有提示；后端初次 328 PASS / 3 FAIL 是缺 PDF 导致并提前停止，随后主控运行 `not local_data` 基线。**本文件不推定该后台运行结果**。四份 PDF 复制与 SHA 相符由主控记录，本聊天未重新摄取或修改。依赖审计 1 high 的归因仍待主控处理，不能遗漏。

配置仅进行静态检查：授权的 `findoc-rag/.env` 存在，`LLM_API_KEY`、`LLM_MODEL`、`LLM_BASE_URL` 均非空；未输出值。此结果只满足现有运行器最低字段要求，供应商可达性、余额、模型能力均 **UNVERIFIED**，不代表 live 可用。未发网络模型请求，也未改旧仓库。

## 2. 证据与通过规则

验收分四层独立记录：后端契约/故障测试、受控跨层浏览器、真实年报与真实模型观察、真人语义与财务核准。受控 provider 即使返回正确金额也只能证明协议与边界；自动 simulated_test 接受不能变成真人核准。

每次运行写独立 manifest：时间、worktree、HEAD 和 dirty 状态、命令、Python/Node/浏览器版本、runtime 根目录、source SHA、配置的模型标识（无密钥）、真实/替身组件、预算、退出码、PASS/FAIL/SKIP、retry 次数、未覆盖项。未提交阶段用 HEAD + 当前变更身份说明，不能声称证据绑定未来 commit。

每条用例保存 operation/conversation/turn、冻结来源身份、状态、provider **物理尝试数**、工具调用数、财务 ACCEPT/SAVE/RESUME 与记忆写次数的前后差值、HTTP 方法和必要截图。仅浏览器拦截请求不足以证明服务端没有重放，必须结合服务计数或隔离数据库读回。终态 payload/hash、旧 ResearchRun 内容及有效财务事实分开比较。

结果枚举建议：`PASS` / `FAIL` / `SKIP` / `NOT_RUN` / `BLOCKED`；运行返回的 `UNKNOWN` 是业务状态，不能被计为成功回复。仅在正确显示 UNKNOWN 且零重放的专门用例中，可把该边界断言计为 PASS。

## 3. C01–C20 覆盖映射

以下全为待实施/待运行计划；文件名称由主控后续分配，本聊天不先占用测试文件。

| ID / 阶段 | 后端或受控方法 | 浏览器 / live 补证 | 关键通过断言 |
| --- | --- | --- | --- |
| C01 A2/A4 | 同会话三轮“营收→同比→现金流”，捕获解析结构与工具参数；有/无确认事实两组 | 浏览器输入真实三轮；G 再观察真实模型三轮 | 企业、报告年度、财务期间、指标可追踪；不会用未确认原文计算同比；三轮 scope 相同 |
| C02 A2 | 双企业歧义上下文，测试“它”“上一年” | 展示澄清；G 一次歧义问题 | 不自行选择企业/年份；澄清前无越界工具/数值答复 |
| C03 A1/A4 | 同 runtime 真正停止并重建服务；读取旧会话、operation | 刷新、离开重开、Back/Forward、焦点恢复 | ID、scope、终态内容不变；GET 模型/工具/业务写增量均 0；新发送才新增 Turn |
| C04 A1/A4 | barrier 阻塞 provider 后两个并发请求；同会话与不同会话分别测试 | 两个真实浏览器 page 同会话发送 | 同会话至多一 active；第二请求按冻结合同拒绝/排队；无交错归属；不是仅验证禁用按钮 |
| C05 A1 | 相同 operation+payload 在 running/终态/重启后重投 | 双击、慢响应 | 相同 turn/status；provider 尝试不增加；每 operation 一条登记 |
| C06 A1 | 相同 operation 不同文本/载荷 | 客户端错误显示 | 409；旧 payload/hash/结果不变；0 新 provider/工具 |
| C07 A1/A4 | provider 超时、提交前异常、落库后响应丢失、读回暂时失败、提交未落库分别注入 | 真实 POST 送达后丢响应，UNKNOWN 仅查询；两标签/焦点/刷新观察 | 未知不假成功；查证只 GET；不自动 POST、工具或 provider 重试；重启 running 按合同中断，不恢复外部调用 |
| C08 A2 | scope 外 document/company/year、伪造 workspace/revision/fact ID | 改来源必须明确新会话；旧会话继续显示原范围 | 服务端上下文决定权限；拒绝越界或澄清；无静默换来源 |
| C09 A2/A4 | 仅隔离副本执行真实来源版本变更，覆盖缓存命中 | 打开 PDF 后失效，下一轮提问与历史查看 | 历史 payload 不变且标历史/失效；新回答拒用旧引用；旧 PDF 入口阻断、缓存像素撤下 |
| C10 A2/B1 | synthetic PDF/工具文本/历史中嵌入保存偏好及扩权命令 | G 可用用户消息注入观察，PDF 注入仍靠受控资产 | 无 memory/fact 写；无 ACCEPT/SAVE/RESUME；额外工具字段、未知工具拒绝 |
| C11 A2 | 未接受、已失效、非 local_operator、范围不匹配事实各组 | 提示去当前来源核对；G 验证缺事实路径 | 不精确同比、不把候选当确认事实；受控深链；财务写增量 0 |
| C12 A2 | 隔离 simulated_test 明确建立有效事实，调用现有 FinancialAnalysisService/Decimal | 浏览器区分已确认数据与 AI 待审解释 | 数值/单位/期间/计算结果与服务一致；双侧事实身份有效；模拟接受必须标记；不用于 G 真人核准声明 |
| C13 A2 | provider 伪造页码、chunk、document、revision、SHA、fact ID、数字和非法 JSON | UI 不显示可信成功或未经校验草稿 | 后端校验拒绝发布；不存在伪造 PDF/事实链接；解释待审标签不替代引用校验 |
| C14 B1 | 用户潜在偏好/模型建议生成候选但无确认 action | 未点击保存后开新会话 | memory 表与审计写增量 0；新 Prompt 无候选 |
| C15 B1/B2 | 明确确认独立 operation，重复/冲突/修改 revision 测试 | 保存→列表→新会话 | 只召回本地用户当前有效允许类型；不能改变 source scope；财务事实不作为偏好 |
| C16 B1/B2 | 删除后新轮/新会话/服务重启/旧摘要缓存路径 | 删除→重新打开管理→新会话 | 正文和检索入口移除；无旧偏好注入；审计不保留正文；日志/备份边界明确 |
| C17 B2 | 20+轮由替身生成，测 token、覆盖游标、摘要刷新及错误摘要 | 选长文本检查阅读，G 不用20轮收费验证 | 总预算有界；摘要非财务事实；删除偏好不从摘要复活；重启后指代仍可追溯 |
| C18 A3/A4 | 前端状态契约与键盘事件 | 390×900、1440×900 两尺寸真浏览器及 PDF canvas | 无页面横溢出/遮挡；抽屉关闭恢复焦点、滚动锁清理；原 PDF 身份正确 |
| C19 A1/A4 | 旧 ResearchRun 的 result/content/citations/integrity_sha256 前后读回；迁移新库及旧库副本 | 旧 `/research?mode=qa&run=…` 深链与 PDF | 原文摘录协议、字节/身份和不可变触发器保留；GET 0 provider/写；删会话不删旧 Run |
| C20 A4/G | 旧研究/报告/财务回归，计数与状态断言 | 最小旧经营旅程及 UNKNOWN/来源失效/报告版本 | ACCEPT/SAVE/RESUME 仍分别显式；只读恢复 0 POST；历史报告与导出版本不变 |

补充必测：创建 0/1/4/5 份及重复/失效来源；会话删除范围和重复删除；memory 修改 revision 冲突/删除幂等；空白/超长输入；非法 UUID/cursor/limit/额外字段；provider/工具/上下文预算的 off-by-one；引用验证后提交失败与 readback 不一致；路由离开后的迟到结果所有权；summary 版本和 provenance；无认证环境不接受浏览器自报 owner/workspace。

## 4. 新旧回归最小集与执行顺序

1. **A1**：新 conversation 仓储/API、全新及既有 SQLite 副本迁移、并发/幂等/终态不可变/GET 零写/启动 interrupted。所有 fake 无凭据、不加载 BGE/Milvus。
2. **A2**：解析、工具 registry/参数、范围/来源资格、财务服务复用、伪造输出、预算与异常。C01–C13 后端通过才进入浏览器跨层。
3. **A3/A4**：专用受控 conversation app + 显式 Playwright 配置，完整真实 HTTP/SQLite 与 provider 计数；只在窄专项注入传输故障，不能整段伪造 API 回复充当持久化 E2E。
4. **旧后端最小组**：`test_d21_research.py`、`test_d21_budget.py`（旧问答）；`test_companies_migrations.py`、`test_d10_migrations.py`、`test_d23_migrations.py`（追加迁移）；`test_document_sources.py`（来源）；`test_financial_reviews.py`、`test_d10_financial_facts.py`、`test_d11_financial_analysis.py`（确认事实/公式）；`test_research_workflow.py`、`test_revenue_research_api.py`、`test_d22_reports.py`、`test_d23_reports.py`（任务与报告）。以文件真实收集结果为准；fixtures 依赖不足不能报通过。
5. **旧浏览器最小组**：`ux-simplification-journey.spec.ts`（一次新 seed，显式模拟接受）；`qa-workspace.spec.ts`（旧问答/UNKNOWN/来源）；`ux-simplification-invalidation.spec.ts`（失效/PDF锁）；`report-workspace.spec.ts`、`report-polish.spec.ts`（版本/保存/历史）。按其运行器 seed 依赖顺序执行；重复种子不重复计数。只有发生相关改动/缺陷才扩大 financial boundary 全组。
6. **B1/B2**：C14–C17 和偏好确认/修改/删除/摘要专项；对话 P0 最小集再跑。
7. **阶段门禁**：主控合并工作区变化后统一跑后端 `not local_data`、前端单测/lint/build 和项目既有 quality 门禁，保留所有 SKIP。当前主控基线正在运行，本聊天不复制启动。local_data 单列、有明确源数据清单；基线排除不等于永远免测。

旧浏览器运行器应先适配路径再分派执行：当前 `run_ux_simplification.py` 的历史 PDF 路径与 financial boundary 的 `.venv` 假设不能满足唯一仓库要求。新 runtime 需 fresh root，不复用其他聊天数据库；需要 seed 时用本次运行生成的一致 SQLite backup，禁止删旧行“清空”不可变表。

## 5. 浏览器 390/1440、焦点与 UNKNOWN 详细断言

每个尺寸覆盖空会话、正常多轮、缺确认事实、运行中、拒答/失败、UNKNOWN、来源失效、长文本/表格、会话列表和来源/PDF 抽屉。页面 `scrollWidth <= clientWidth + 1`；表格可局部水平滚动，正文不得被缩成窄列。输入区可见、按钮可达，技术 ID 默认折叠。

- 键盘 Tab/Shift+Tab 到输入、发送、历史、来源、PDF、关闭；dialog 焦点限制于可见内容，Esc/关闭返回实际触发按钮。触发按钮被卸载时回到合理可见入口，不落到隐藏元素。
- 390px 打开/关闭会话和来源抽屉、PDF，再切换会话、路由、resize；检查 `document.activeElement`、body/html overflow 与实际滚动恢复。打开模态后注入来源失效/暂停/503，消失的 dialog 不保留锁；桌面不留下遮罩。
- PDF 通过真实 file endpoint 检查 document/revision/SHA 和物理页，至少一个实际 canvas 可见；仅截图或链接文本不足以证明 PDF 已打开。派生失效文件只在隔离副本修改，原 PDF SHA 前后相同。
- UNKNOWN：让 POST **到达并登记后**在浏览器丢响应；记录原 operation 并显示未知/查证，禁止虚假完成。点击查证、自动只读轮询、blur/focus、刷新、Back/Forward、离开重进均只能 GET。对比 provider/工具/Turn/财务写计数，确认一次登记、至多已发出的那次 provider 尝试。
- 同时覆盖 POST 未送达、服务端 running、已终态但响应丢失、by-operation 暂时503、重启 interrupted；未查到不能自动重发旧 POST。用户主动新 operation 应明确为新提问且保留旧未知身份，不成为隐式重试。

这些是局部键盘与布局断言，不冒充完整辅助技术可访问性认证。软键盘/真实触屏和读屏真人检查单列待验。

## 6. G 真实模型验证方案（未授权执行）

仅在主控分派 G、冻结 API 和自动化闸口满足后实施；本轮无任何真实请求。读取授权配置但日志/截图/manifest 不写 key、完整环境、Authorization 或凭据 URL。模型标识可以在 G 运行记录中保存；供应商错误只记录脱敏类别，不回显原始异常中的凭据。

### 隔离和硬预算

- 新建专属绝对 runtime 和唯一证据目录，拒绝默认 runtime、旧 D16/D30/UX 数据目录、已有非空输出；源文件用当前 worktree 四份已固定 SHA 原件，只读校验与上传。仅复用模型权重缓存，不复用旧业务 SQLite 或已完成答案。
- 正式 runtime factory/HTTP/前端路径；实际 BGE、Milvus、provider 分别记录 observed 状态。未实际走过的组件不能仅因 create_app 成功就标 actual=true。
- 单 worker、retries=0；在最低实际 SDK/HTTP 发送边界计数并禁止 SDK 隐式重试，调用前持久写 attempt 记录。外层 complete 计数不能掩盖 SDK 重试。失败保存脱敏证据，不自动重跑补齐。
- 建议首批最多 **5 个新 Turn、全程最多 10 次物理 provider 请求、每 Turn 最多2次通用生成和3次只读工具调用**；与最终合同取更严格者。若 RAG 内部也调用 provider，计入同一全局预算，达到即停止且如实 NOT_RUN。每次设置输出 token 上限建议2048、单次超时45秒；预算值与供应商适配由主控冻结。
- HTTP 超时或响应丢失只读 by-operation；不得以“测试重试”触发新的付费调用。准备/上传/摄取阶段也纳入 provider 计数，不假设不会调用模型。整轮时间/费用不可预先宣称；实际 usage 缺失记 UNKNOWN，不能估成已计费准确值。

### 首批五轮与零调用观察

| 项目 | 行为 | 证据 / 限制 |
| --- | --- | --- |
| L1–L3 | 同公司两年冻结来源：“2025营业收入原文是什么？”→“同比变化呢？”→“经营现金流也这样吗？” | 实际解析/工具/引用/页码；没有真人核准事实时必须缺事实或原文路径，不自动给正式同比；AI解释待人工语义审核 |
| L4 | 歧义或范围外公司问题 | 澄清/拒绝，不能暗改 scope；不以模型合理文案替代后台过滤证据 |
| L5 | 用户消息要求忽略限制并自动接受财务值/保存偏好 | 不写财务/记忆；偏好如产生只能候选；PDF 内注入主要由受控测试覆盖，不能宣称此轮已测真实 PDF 注入 |
| R0 | 以上历史刷新、重开、服务重启、打开真实 PDF、operation GET | provider 增量0；payload/来源身份一致；前端 GET 请求记录与服务端计数同时存在 |

首批 G 不预置模拟已接受事实，也不替用户点击 ACCEPT/SAVE/RESUME。C12 有效财务公式的自动化由 simulated_test 证明；若需真实模型结合真人确认事实的完整链路，等待用户实际核准并另列结果，不以缺少该证据阻碍诚实交付局部观察。

记忆真实模型召回如需补验，应由主控另分配剩余预算或追加批次；C14–C17 已有替身合同测试不代表真实召回质量通过。不得为了凑20轮而消耗真实模型预算。

### 输出和停止条件

记录每个问题/解析查询、原始模型草稿与发布结果的区分、provider尝试/usage、工具参数和安全摘要、来源 tuple、引用原文/页码、财务事实状态、AI待审状态、读回 hash、无写副作用计数。保留失败、超时、拒答、UNKNOWN 与未运行，不覆盖旧输出。供应商额度/不可达、摄取失败、预算耗尽或边界违规则停止并报告；不改用替身假装 live 成功。

人应对照真实 PDF 核对数值/单位/期间、引文是否支持结论、追问解析与因果解释。工程只能给出“真实调用已观察、引用身份校验通过/失败、语义待审”；不能由模型自评宣布正式财务接受、生产可用或全面准确率。

## 7. 主控后续分派条件

等待主控冻结 API/状态/终态发布合同及分配新测试 app、后端测试、Playwright spec/config 和 G 运行器的独占文件。建议优先明确：UNKNOWN/interrupted 的服务状态；by-operation 404 语义；同会话冲突/排队策略；工具和物理 provider 全局预算；删除会话/旧 ResearchRun/摘要/偏好边界；摘要中偏好删除策略。

本报告为 A0 准备交付；C01–C20 均未因本文件创建而获得功能 PASS。

## 8. 后续获授权的 A4/G 工程准备记录

主控随后授权本聊天独占新增 conversation fixture、E2E/live 运行器、Playwright 配置和 `conversation*` E2E 文件。依据正式 `contracts.md` 与 `backend-a0.md` 第3节编写；未改业务代码、旧测试、旧 controlled app、正式数据、Git index 或依赖。

当前文件：

- `tests/support/conversation_app.py`：以正式 `runtime_factory.create_runtime_app` 装配新/旧业务；替换重依赖为确定 model/retriever/indexer，保留 HTTP、SQLite、PDF parser、source guards 和服务端提交。outgoing socket 与越界 SQLite 被阻断，默认真实模型调用为0。业务路由尚未接入正式 factory 时明确报错，不能用伪 API 顶替。
- `scripts/run_conversation_v12_e2e.py`：校验当前 worktree 四 PDF SHA、新建 runtime/端口、去除凭据、Node24、零重试、独立 manifest/log/trace。另有 `--legacy-proof-only` 和 `--migration-proof-only`，提供历史回归所需不同版本的全新 seed。
- `frontend/playwright.conversations.config.ts`、`frontend/e2e/conversation-{helpers.ts,api.spec.ts,browser.spec.ts,memory.spec.ts}`：15 项可收集测试。覆盖创建/Turn operation、冲突、三轮、范围/澄清、并发、错误引用/供应商错误、删除 tombstone、真实来源绑定纠错、旧ResearchRun不变、偏好CRUD/拒绝不合格值、390/1440 PDF/焦点、真实POST丢响应后的UNKNOWN查证。**目前通过收集检查及下述两项A1 API测试，尚未执行A2/B2/浏览器新功能测试**。C12财务正向、C16实际上下文注入/摘要删除、C17长会话和真实重启专项仍需随后端/前端实际实现补足；不把编号出现在测试名当成完整覆盖。
- `scripts/validate_conversation_v12_live.py`：显式 `--execute-live`、最多5新Turn/10物理provider请求、单次输出上限、SDK重试0、独立实际BGE/Milvus观察计数、原始SHA/结果/只读计数、财务写路由白名单。仅通过AST与`--help`检查，**未执行live，模型请求0**；仍需在G前对实际DTO/异常状态做集成复核。

### 已实际执行的旧回归与失败

1. `--legacy-proof-only --out data/conversation-v12-validation/legacy-proof-01`：**1 PASS**，约2分钟，原 `ux-simplification-journey.spec.ts`，真实四PDF/HTTP/SQLite，原独立前端测试入口，模拟接受与模型/检索替身。不能称为新研究助手或正式前端完整验收。全新 runtime 在报告生成前经 SQLite backup 导出一致 clean seed，原报告行没有删除或改写。proof 为该目录 `report-test-proof.json`，用于 `FINDOC_REPORT_TEST_PROOF`。
2. 使用上述 report proof 运行 `test_d22_reports.py test_d23_reports.py test_d23_migrations.py test_d24_exports.py`：**80 PASS / 3 FAIL**，87.42秒。3 FAIL 为 D23 migrations 还需要独立 `FINDOC_MIGRATION_TEST_PROOF`，不能使用要求v9报告表的report seed代替v8。其余原报告契约通过。
3. `--migration-proof-only --out data/conversation-v12-validation/migration-proof-01`：从空目录按现有 migrations 前8条构造全新v8库及真实PDF源记录；不降级已有库、不DROP新表、不删除历史报告。生成 `migration-test-proof.json` 供 `FINDOC_MIGRATION_TEST_PROOF`。
4. 用新v8 proof 重跑原 `test_d23_migrations.py`：**2 PASS / 4 FAIL**，0.94秒。此时后端追加migration10已落盘，3项原测试仍要求最后migration固定为9，另1项将10当“未知版本”插入，触发版本主键重复。这是旧测试固定版本假设与追加迁移的冲突；没有改变旧断言或截断当前迁移列表来报绿。待主控分配后修订测试范围/未知版本选择，并保留对旧v8→v9校验、失败回滚与旧表不变的全部原义；新v10完整迁移由后端专属测试验证。
5. 主控随后明确授权独占修订 `tests/test_d23_migrations.py`：保留v8 seed和对v9的全部旧约束；改为精确验证 `log[8]` 的v9 checksum及整个log等于实际MIGRATIONS的version/name/checksum；unknown使用max版本+1参数化SQL。重跑精确D23组 **6 PASS / 0 FAIL，0.72秒**（当时完整迁移为1–10）。未截断产品迁移，未删新表。
6. `--a1-only --out data/conversation-v12-validation/a1-api-01`：**2 PASS / 0 FAIL，约1.2分钟**。明确使用真实ConversationRepository/Service/API及A1官方`fake_handler`，以当前四真实PDF建立来源；覆盖create operation重复/冲突/只读精确回执、非法范围和自报workspace拒绝，model计数不增加。不是A2语义/图或真实模型验收。此模式仅在正式factory尚未接入Conversation路由且显式A1开关时装配实际service；默认A2模式不会偷偷退回fake_handler。

静态工具检查：三个新增Python文件AST通过，专属Python文件及授权修改的D23测试ruff通过；Playwright显式配置收集15项。新功能正式装配、Graph和Memory集成仍在其他聊天开发，本聊天没有在缺路由时伪造API来取得语义通过。

联调待核：读取时后端 `Action.allowed_href` 的open_source路径为`/documents/{id}/source/file?source_revision=…`，前端 `safeConversationAction` 接受的是`/api/documents/{id}/file?...#page=…`，两者静态不一致。待前后端责任聊天统一实际合同，不能通过放宽E2E身份断言掩盖。尚未运行新浏览器，故不将静态发现写成已观察运行失败。

本聊天未重跑主控完整后端。主控另报告完整 `not local_data` 为645 PASS / 20 deselected / 3 ERROR，错误是D22缺旧proof且maxfail3提前停止；相关旧后端196 PASS另记，不与本聊天80项机械相加。所有这些记录均不构成V1.2功能验收，也不抹去较早缺PDF/缺proof失败。

### 后续 build 修复与 B1 对齐

主控报告完整 build 被 `conversation-memory.spec.ts` 的重复 `value` 字段构造触发TS2783阻断。已改成四个完整的无效字段场景（非法财务值、未确认、伪造workspace、非法key），请求只拼接operation/type和单个场景对象，保留每项无效value与422断言。Node v24.19.0、Vite **8.2.4** 的 `npm run build` 完整通过（tsc -b + Vite）；仍有既有大于500kB chunk提示。

依据实际 `app/memory/candidates.py`，C14输入改为明确支持的“记住：我更关注现金流。”，断言候选的完整key/value/source_turn_id/confirmation_required；不假定任意自然语言均能生成候选。删除回执校验revision递增。上述B1端到端断言尚待v11/runtime及Graph集成后执行，未把后端模块31PASS转换为浏览器通过。

财务来源PDF正向入口已见前端实现与专属单测；真实浏览器正向场景需要实际A2已确认事实结果，待A2集成后追加。不会伪造EvidenceRef或整API结果来使该路径先通过。
