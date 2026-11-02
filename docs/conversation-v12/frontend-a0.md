# V1.2 前端 A0：影响分析、页面状态与待冻结合同

日期：2026-11-02。状态：**前端设计提案，等待主控冻结 API；未实施 A3/B2，未运行测试。**

本次唯一写入为本文。仓库 `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`；读取时分支 `codex/conversation-memory-v12-20261102`，HEAD `1f0a3d4131480ac0ea742772127afac3c892fc7c`。初始 `git status --short` 已有 `?? docs/conversation-v12/`，不将该目录其他材料视作本次产出，不提交、不暂存、不修改数据。

已阅读 handoff 五份文档（含 README）、`product/ux-simplification/verification.md`、实际路由/导航/问答/来源选择/历史恢复/PDF/模态框及相关 E2E 与运行器。本文只讨论当前仓库实现；旧验收记录是回归目标，不是本分支本次重跑结果。

## 1. 最窄页面与代码影响面

保持现有五个顶级导航，将“年报问答”入口改为“研究助手”，目标 `/conversations`。旧 `/research?mode=qa` 仍是独立原文核验/历史问答页，不重定向、不迁移旧 Run；在研究助手和旧页间各放一个普通兼容链接。保留 `company/run/return_task` 等现有深链语义，`qaPath()` 继续生成旧地址。首页、研究任务、企业与年报、报告业务不重做。

| 实际文件/模块 | A3/B2 最小变化或复用边界 |
| --- | --- |
| `frontend/src/product/productRoutes.ts` | Page 新增 `conversations`；建议详情 URL `/conversations?conversation=<uuid>`，避免引入路由库。新增重复参数检查与独立 `conversationPath()`；不把 company/task/run 当新会话授权。保留旧函数语义。 |
| `frontend/src/product/FinancialProduct.tsx` | 在现有壳内分派新页；沿用 popstate/historyEpoch 和 main 聚焦。会话导航不携带旧任务/报告身份。当前 AppShell 以 route key remount，未决 operation 必须跨卸载保留，不能靠组件 state 恢复。 |
| `frontend/src/product/AppShell.tsx` | 替换一个导航项及对应 active/breadcrumb 逻辑；旧 QA 页可归到研究助手导航，页内标题仍明确“原文问答”。不增加第六项导航。 |
| 新增 `Conversations.tsx`、`conversationApi.ts`、`conversationState.ts`、局部 CSS module | 列表、新建选择、只读详情、发送与查证的独立 DTO/验证器；消息和引用可按实际复杂度拆小组件。不修改 `ResearchRun` DTO 或旧摘录校验。 |
| `ResearchSourceSelection.tsx` | 复用 GET `/research/sources` 的 options 合同和 checkbox 交互模式；整个组件绑定 ResearchRuns、detachRun、旧 POST prepare，不宜直接挂入新页。新建小型 Conversation 来源选择器即可，首轮不抽象改造旧组件。 |
| `ResearchRuns.tsx` / `requestOwnership.ts` | 借鉴同步 ref 互斥、不可变请求快照、view epoch、迟到响应失权、sessionStorage 仅存 operation 线索；会话快照需另含 conversation_id/op，而非套用单 document 身份。 |
| `StatusNotice` / `WaitingNotice` / `DiagnosticDetails` / `Icon` | 直接复用展示；UUID、revision、SHA 收入详情。等待文案不虚构实时工具进度。 |
| `VerifiedExcerpt` / `ReportExcerpt` / `excerptBlocks` / `qaReading` | 仅在新 DTO 与这些组件的输入合同等价时适配原文块；宽表保留原单位、年度列和局部横向滚动。 |
| `ResearchAnswerView.tsx` / `researchHistory.ts` | 旧组件严格依赖 `verified_excerpts`、原文拼接与旧可信焦点，不能装载自由解释或把新消息强转为 ResearchRun。保留原实现。 |
| `ResearchPdfDialog.tsx` / `QADialog.tsx` / `PdfPage` | 复用真实 PDF、来源复验、原生 modal 和卸载清理；按完整引用身份挂载。新页以适配后的 PdfCitation 调用，不用模型 URL。 |
| B2 新增 `ResearchPreferences.tsx`、`memoryApi.ts` | 同页“我的研究偏好”面板/对话框，不新增顶级设置页，不接入第三方记忆服务。摘要由后端管理，无前端摘要编辑器。 |

普通 GET 经 `/api` 代理，Vite 会去掉该前缀；继续沿用现有 fetch/no-store/AbortController 模式。新的写 API 使用显式 method，不能把只支持“有 body 即 POST”的 `json()` 帮助函数误用于 PATCH/DELETE。不引入 SSE、聊天 SDK、全站状态管理或新设计系统。

## 2. 页面状态流与可见文案

页面按三个相互独立的维度管理：列表/详情读取状态、当前会话来源资格、当前写 operation 状态。不要让一次 GET 错误抹去未决操作，也不要把来源失效映射为“会话不存在”。

紧凑文本原型（A0 无界面代码）：

```text
1440：[原产品导航] [会话列表/新建] [企业·冻结年报 / 来源按钮]
                                 [用户问题 → 已解析对象 → 助手内容 → 引用]
                                 [问题输入                         发送]
                                 来源/PDF：按需从右侧展开
390 ：[菜单] [会话]  财报研究助手  [来源]
      [冻结范围摘要] → [单列消息与引用] → [输入 / 发送]
      会话、来源、PDF、偏好：一次只开一个抽屉，关闭回原位置
共用：空会话=选年报入口；多轮=消息+引用；缺事实=前往核对；UNKNOWN=只读查询
```

| 状态 | 可见内容和主要动作 | 网络/边界 |
| --- | --- | --- |
| 初次空页 | 标题“财报研究助手”、2–3 个问题示例、“选择年报并新建会话” | 只 GET 列表/来源。点示例只填输入草稿，不创建/发送。 |
| 来源选择 | 企业筛选、明确 checkbox、已选 n/4、不可选原因；“创建会话” | 0 份不可创建，第 5 份不可选；1–4 个唯一 document ID。跨企业选择显式呈现，不推断同名版本。 |
| 创建中 | 保留所选摘要，“正在创建会话” | 同步 ref 抢占后仅一次 POST，不同时发送首轮问题。 |
| 已创建空会话 | 顶部冻结来源摘要，空消息提示，输入框 | 来源以创建响应/详情为准；可输入但必须另点“发送”。 |
| 多轮只读恢复 | 已保存消息、解析对象/年份、引用、当前来源状态；“继续提问” | GET 详情不补写 Turn、不运行模型、不计算、不确认财务数据。 |
| 本轮提交中/运行中 | 已提交用户问题与“正在处理并核验”；旧回答仍可读 | 不显示未提交助手草稿，不提供重发/自动继续；禁止同会话第二次提交。 |
| 完成 | 原文摘录、已确认数据或待审解释分块；引用按钮 | 仅以已提交且通过 DTO 校验的终态发布回答；不以 HTTP 200 或 checkpoint 宣告成功。 |
| 需要澄清 | 服务端澄清问题，“请明确企业/年份” | 用户下一次明确发送形成新 operation；前端不猜测指代。 |
| 缺少确认事实 | “尚无可用于正式计算的已确认事实”；“前往核对” | 仅服务端受控跳转；不从原文计算同比，不自动 ACCEPT/SAVE/RESUME。 |
| 来源失效/无法核验 | 历史消息仍可读，“当前来源已失效/暂不可核验”；“重新读取状态” | 撤下当前有效声明；禁用新发送直至服务端重新确认可写；换源只能明确创建新会话。 |
| UNKNOWN | “结果尚未确认”；唯一主要动作“查询本次状态” | 只 GET by-operation；不重发 POST。技术详情可看 op ID。 |
| 已保存失败/拒答/中断 | 展示真实服务端终态与原因 | 不把 refused 当系统异常。终态已查明且服务端允许时，才可明确发送新问题，新 operation 不叫“恢复”。 |
| 读取失败/损坏/404 | “暂不能读取历史/记录未找到”；“重试读取” | GET 重试不变成创建；保留未知 operation。 |

文字流程：空页 → 选 1–4 份 → 明确创建 → 冻结来源的空会话 → 明确发送 → 提交中 → 已提交终态或 UNKNOWN → GET 查证。历史入口、刷新、Back/Forward、重新聚焦只走读取支路。换来源 → 新建选择，不覆盖原会话。来源筛选变化不偷偷取消已选项；显示不在当前筛选内的已选摘要，移除需用户动作。

历史恢复属于“读取历史”；在此之后按发送按钮才是继续会话。用户在 A 会话发出请求后切到 B，A 的迟到返回不得覆盖 B、清空 B 草稿或移动 B 焦点；A 的 operation 仍可在回到 A 后查证。取消浏览器等待/卸载不等于取消服务器执行。

## 3. UNKNOWN 与并发：必须冻结的恢复缺口

提交前生成 UUID operation_id，建立 `{conversation_id, operation_id, text, view_epoch}` 不可变内存快照，同步 ref 占有发送入口；只用 React disabled 防双击不够。sessionStorage 仅存会话+operation 的恢复线索，不缓存权威答案/来源资格/偏好正文。存储不可用应提示跨刷新恢复线索受限，服务端历史仍是权威。

网络中断、5xx、响应 JSON/身份/完整性校验失败、浏览器 abort 均可能已执行，统一进入 UNKNOWN；重新挂载、focus、在线事件均不能重发。GET by-operation 返回 running 则继续等待提示，返回终态再校验读回；轮询如实现必须只读、有频率/次数上限、不可见时暂停且卸载清理，第一版手动查询即可。

404 不证明请求从未执行（原请求可能仍在登记），显示“尚未查到，未再次提交”，不清掉未决状态或发新 operation。409 必须有机器可读原因和是否已登记的明确语义：同 op 不同载荷、同会话其他标签 running、来源失效不能统一处理为“未执行”。两个标签的串行保证来自后端；跨标签广播只作刷新提示，不是锁。

**交接建议的创建/记忆写 API 恢复尚不闭合：**

- 创建会话也可能成功但丢响应。请求须有 operation_id，提供创建 by-operation 的只读查证，或等价的可精确查证合同；否则无法安全解除“创建中/未知”，不得自动再建。
- POST/PATCH/DELETE 偏好以及 DELETE 会话也须独立 operation 与读回语义。GET 列表缺少某项不能单独证明某个 DELETE 已成功。要求可读取操作回执/墓碑，且回执不保存已删除偏好正文。
- interrupted/unknown、active turn、可否开始新请求必须由服务端给出明确语义；不要仅按前端超时解锁。

这些是 A0 API 需求，不是已存在接口。主控可等价实现，但需在 A3/B2 前冻结。

## 4. 实际 API 字段需求（建议字段名，待主控统一）

所有响应需要版本字段、明确类型/枚举、稳定身份及机器错误码。写请求不传 workspace/owner、source_revision、trusted fact ID、模型选择或工具参数。所有范围/引用身份由服务端产生并复验；前端校验只能防误显示，不能替代权限与数值校验。

| 接口 | 前端最低需求 |
| --- | --- |
| 已有 GET `/research/sources` | 已实现 `schema_version=research-source-options-v1`、`max_selected_documents`、`documents[{document_id,company_id,report_year,report_type,source_file,status,selectable,reason}]`。该目录不带 revision，不能自行制造冻结快照。新页上限取合同与 4 的较小值；不调用旧 prepare 当作已创建会话。 |
| POST `/conversations` | 建议 `{operation_id,document_ids,title?}`；响应含 conversation 完整身份、冻结来源和创建回执。单独创建，不隐式发送 text。 |
| GET `/conversations/by-operation/{operation_id}`（新增需求） | 精确创建操作回执与 conversation_id；404/登记中/终态语义。路由须与详情路径无歧义。 |
| GET `/conversations?cursor&limit` | `{schema_version,items,next_cursor}`；每项 conversation_id/title/status/created_at/updated_at/source 摘要，最好含 active_turn 简要身份。P0 分页，不假装跨全库搜索；搜索若保留需冻结后端 q 合同，否则暂不做。 |
| GET `/conversations/{id}` | conversation_id/title/status、`source_scope_sha`、冻结 sources、当前 source_states、`can_send`/阻断原因、active_turn、按 seq 排序的已提交 turns。较长历史需分页/游标且保留顺序；未加载旧消息不能被解释为不存在。 |
| 冻结 source / 当前状态 | `{document_id,company_id,company_name?,report_year,source_file,source_revision,content_sha256,parser_version?}`；source_states 与文档+revision 一一对应，`current/expired/unavailable` 等枚举、reason、checked_at。不可把历史快照标记当当前有效。 |
| POST `/conversations/{id}/turns` | `{operation_id,text}`；同步完成或 202 的返回形态需冻结。必须返回相同 conversation/op、turn_id、seq、status；running 时 answer=null，终态含已提交 payload、ended_at、完整性信息。 |
| GET `/conversations/{id}/turns/by-operation/{op}` | 相同 Turn DTO，no-store。可区分尚未找到、running、completed/refused/failed/interrupted；定义 unknown 是客户端不确定态还是持久状态，禁止两边枚举混用。 |
| Turn / answer payload | `user_text`、`resolved_query` 与可读解析范围（企业/财务年度/指标/需澄清项），`research_run_id?`，answer_mode/outcome、`answer_text`、`evidence_refs`、`verified_financial_fact_refs`、`interpretation_status`、safe reason/error、可选有序脱敏 tool_events。旧摘录若内嵌仍走原验证器。 |
| evidence_refs | 每条具有引用编号/ID、document/company/report_year、revision、chunk_id、physical_page、source_file、原文 text、kind、parser_version、内容 SHA 或对应来源快照。关联到该轮冻结范围；新消息不能复用上一轮引用编号当全局身份。 |
| verified_financial_fact_refs | fact 身份、当前资格/状态、财务年度、报告年度、metric、单位/币种/口径、Decimal 字符串值及证据绑定；比较结果由已有服务返回值与局限。前端只格式化，不新增计算公式。 |
| actions | 例如 `{kind,task_id?,company_id,document_id?,source_revision?}` 等受控结构，而非模型任意 href。核对跳转需要可核验的现有 task/source 身份；没有匹配任务时不能臆造 task ID 或进入即创建任务。 |
| DELETE `/conversations/{id}` | operation_id/并发条件/删除回执及可读结果；是否允许 active turn 时删除需冻结。建议 running/UNKNOWN 时禁删以缩小恢复面。明确仅删除会话，不删除旧不可变 ResearchRun、事实、PDF，也不暗删长期偏好。 |
| GET `/memories` | 已确认条目 `{memory_id,type,key,value,revision,confirmed_at,updated_at,source_turn_id?}`，分页如有需明示；类型白名单、长度限制由后端合同提供。 |
| 偏好候选 | 当前 Turn 的结构化候选及来源 user turn、type/key/value；尚未确认标识，不纳入 GET 已确认列表。不从 answer_text 提取“记住”触发写入。 |
| POST/PATCH/DELETE memory | POST `{operation_id,type,key,value,confirmed:true,source_turn_id?}`；PATCH `{operation_id,expected_revision,value}`；DELETE operation_id + expected_revision（或等价并发保护）。409 要求重新 GET 后人工决定，不能自动覆盖。新增统一操作查证或等价只读回执。 |
| B2 召回/摘要元数据 | Turn 可含实际应用的 memory_id+revision（不是财务证据）；summary covered_through_seq/version 仅作诊断。删除后新请求不得从摘要/缓存复活旧偏好，由后端保证，前端不自建注入。 |

消息状态与内容类型分开：clarify/needs_human_review 可是已提交的业务 outcome，不必伪造系统失败；服务端最终枚举必须冻结。新 DTO 不应仅把 `completed` 映射为旧 `answered` 以绕过旧摘录合同。

## 5. 引用、可信焦点与偏好交互

每条助手消息依次展示：服务端解析的讨论对象/年度 → 答复类型 → 已提交内容 → 本轮引用与唯一主要下一步。标签区分“原文摘录”“已确认数据”“AI 分析待人工语义审核”；引用身份核验通过不等于因果解释已审核。服务端不提供可信焦点字段时，不从生成文本提取金额并造出“本题可信焦点”。

点击引用，先按该条文档/revision/company/页码适配 `PdfCitation`，复用 ResearchPdfDialog 的 source → 字节 SHA → 物理页复验。历史来源失效保留已存原文，撤下当前 PDF/有效徽标；不跳到同名最新报告替代旧引用。右侧来源栏按需打开，默认不永久占三栏。工具进展仅展示服务端安全摘要，无原始 prompt/思维链。

偏好候选写明“建议保存的研究偏好”，显示待保存原句与类型；用户明确点击“保存偏好”才 POST。发送“以后关注现金流”只完成 Turn，不代表偏好已保存。管理面板 GET 已确认列表，编辑和删除各自明确动作；删除说明“后续请求不再使用，已保存历史回复仍保留”，不承诺备份清除。空白、重复、敏感内容及财务事实由服务端拒绝，客户端只做相同规则的即时提示。保存/编辑/删除 UNKNOWN 均提供独立查证，不显示成功 toast 后乐观移除。

B1 未就绪时 A3 不展示可点击但无法工作的“保存偏好”按钮。不把候选、localStorage 或旧摘要作为确认依据。已应用偏好列表是解释辅助信息，不能改来源范围。页面注明本地单人空间及必要问题/证据会发送给配置的模型供应商，不伪装登录/多租户隔离。

## 6. 1440 / 390 与 focus、scroll 锁的最窄方案

- 1440：保留现有产品导航；内容区左侧窄会话列表、中间弹性消息列，右侧证据按需展开。使用 `minmax(0,1fr)` / `min-width:0`，避免三个永久侧栏加壳挤压正文。
- 390：消息单列，会话列表/来源/PDF/偏好以互斥抽屉或模态框呈现；底部输入在页面布局内 sticky，适配 `100dvh` 与 safe-area，不用覆盖正文的全局 fixed 高度。键盘出现后发送按钮可见、textarea 可滚动；用户上翻时不强制滚到底部，新消息有返回底部入口。
- 长企业名/UUID/无空格文本允许换行；表格只在自身容器横滚，容器可聚焦并有标签，禁止整页横向溢出。技术身份默认折叠。
- 一个页面最多一个本地模态框，打开 PDF 前先关闭来源/偏好框；产品导航打开前关闭本地抽屉，避免多个 overflow 保存/恢复互相覆盖。断点切换和路由切换都卸载模态框，而非隐藏仍处于 `:modal` 的 dialog。
- 沿用 QADialog 的 showModal/close、原 overflow 值恢复、opener 仍连接才聚焦、Esc 清理；不强制恢复到已卸载按钮。路由导航由壳聚焦 main；同页查证只更新 status，不抢输入焦点。
- **实际复用缺口：**QADialog 的 Tab 查询目前未包含 textarea，AppShell 导航的自定义 trap 也只针对导航控件。偏好编辑/新会话对话框若含 textarea，要在批准实施时补齐可见且非 disabled/inert 的可聚焦元素与回绕，不直接照抄现状声称键盘完备。新增区域避免正 tabindex，status 用 aria-live polite，不在每次轮询重复朗读整条消息。
- 来源失效撤下 PDF 时可保留带错误信息的 modal 供用户关闭；关闭、卸载、Esc、Back、断点切换后的 body overflow 必须回到之前值，`:modal` 数量归零，输入/按钮与页面滚动均可用。不因“暂停/错误”把仍 showModal 的节点仅做 CSS 隐藏。

## 7. 实施顺序与验证命令

本轮仅静态分析；下列命令均为后续执行计划。Node 要求 `>=24 <25`。不得在本 A0 运行会写数据/构建产物的验证程序；旧 verification 的通过数不抄作本次通过数。

1. 主控先冻结上述创建/Turn/operation/来源状态/动作 DTO 与错误语义；A1/A2 交付真实持久接口与只读恢复。冻结前前端不编造 mock DTO 当正式协议。
2. A3 最先加路由壳与只读列表/详情，再做来源创建和单 Turn，最后多轮、引用及响应式。每次先验证 GET 零写与迟到请求归属，再补业务界面。
3. A4 以隔离 runtime 与真实 HTTP/SQLite 覆盖浏览器旅程；模型/向量替身明确标记。B1 合同完成后才实施 B2 偏好管理。G 另做有限预算真实年报/模型验收，不用 fake 通过替代语义审读。

前端常规命令（仓库根目录）：

```bash
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

已经存在且可复用的 UX E2E 运行器（每次用未存在的输出目录；脚本会校验固定 PDF SHA，并在独立临时 runtime 中写测试数据）：

```bash
.venv/bin/python scripts/run_ux_simplification.py --out /tmp/findoc-v12-ux-baseline-01
.venv/bin/python scripts/run_ux_simplification.py --out /tmp/findoc-v12-qa-regression-01 --extra qa-workspace.spec.ts
.venv/bin/python scripts/run_ux_simplification.py --out /tmp/findoc-v12-reports-regression-01 --extra report-polish.spec.ts report-workspace.spec.ts
.venv/bin/python scripts/run_ux_simplification.py --out /tmp/findoc-v12-source-regression-01 --extra ux-simplification-invalidation.spec.ts
```

`scripts/run_ux_simplification.py` 当前先运行 `ux-simplification-journey.spec.ts` 再运行 `--extra`，支持真实 PDF/模拟模型的原旅程；资料按 `product/validation/sources.json` 及脚本中的相邻 `findoc-analyst-v1-d9` 路径寻找，需先只读检查文件存在及 SHA，不覆盖源文件。独立财务边界另可运行：

```bash
FINDOC_NODE24_BIN=/absolute/path/to/node24/bin .venv/bin/python frontend/scripts/run-financial-boundary-e2e.py
```

该占位路径必须换成本机已验证的 Node24 bin；运行器会生成自己的隔离数据/证据目录。默认 `frontend/playwright.config.ts` 的 testMatch 是 `agent*.spec.ts`，**`npm run test:e2e` 不会自动覆盖会话与这些 UX 规格**。

建议后续新增 `frontend/e2e/conversations.spec.ts`、`conversation-recovery.spec.ts`、`conversation-layout.spec.ts`、B2 的 `conversation-preferences.spec.ts`，以及专用 `scripts/run_conversation_v12_e2e.py`。建议未来入口如下，文件现在尚不存在，不能据此宣称已可运行：

```bash
.venv/bin/python scripts/run_conversation_v12_e2e.py --out /tmp/findoc-v12-conversations-01
```

专用运行器须显式匹配新规格，清理模型凭据、启用隔离 runtime、禁止复用正式服务、retries=0，并输出请求/模型/工具计数、状态、截图及 trace；新旧旅程可以共用已审查 fixture 工具，不能直接向旧运行器加 extra 就假定旧 controlled app 拥有新 API。

| 新 E2E 场景 | 必须断言的实际证据 |
| --- | --- |
| 新建/范围 | 0/1/4/5 份、不可选/重复 ID、创建响应丢失；双击只一次创建 POST；创建本身零模型调用；换源不改旧会话。 |
| 三轮/澄清/缺事实 | 展示服务端解析对象、同比与现金流焦点；缺事实不产生前端计算或自动核对写操作；澄清明确新 Turn。 |
| 历史/重启/Back/多标签 | 读取与刷新 API 写次数为 0，模型/工具计数不增加；服务重启内容和 scope 一致；A 迟到不能覆盖 B；两标签后端最多一个 active Turn。 |
| UNKNOWN | POST 已登记后丢响应、5xx、损坏 JSON/错误身份、404 查证、running/中断；此后所有恢复请求仅 GET，operation 不变，模型尝试不增加。 |
| 引用/失效 | 实际 PDF 字节 SHA/版本/物理页，错 company/revision/page 不展示；旧原文保留，当前有效声明撤下；重新聚焦零写。 |
| 1440/390 | 四核心状态：空会话、多轮、缺事实、失效/未知截图；documentElement.scrollWidth <= innerWidth+1；长文/宽表/长企业名、输入与发送无越界。 |
| 焦点/滚动 | 来源→关闭→PDF→Esc、偏好 textarea Tab/Shift+Tab、导航抽屉互斥；卸载/Back/断点变化/来源失效时无隐藏 modal 残留、body 锁还原、focus 回可用触发器/main；保留阅读位置。软键盘另作真人设备检查。 |
| 偏好 B2 | 未确认零 memory 写、新会话不召回；明确保存、编辑 revision 冲突、删除 UNKNOWN 查证；删除后新 Turn/新会话及旧摘要不复活偏好；历史回答不被篡改。 |
| 旧 QA / 经营研究 | `/research?mode=qa&run=...` 与 return_task 深链继续可读，原文拼接合同未变，ACCEPT/SAVE/RESUME 各自人工触发；既有报告与失效回归通过。 |

## 8. A3/B2 开始前需主控确定的清单

- 创建及其他写操作的精确 by-operation 恢复；UNKNOWN/404/409/中断的安全解锁条件。
- Turn/业务 outcome/解释待审/当前来源状态的最终枚举和版本，以及历史分页策略。
- 引用与已确认事实的最小 DTO、真实核对跳转构造、可信焦点是否提供；不提供即不做金额焦点卡。
- 新会话来源是否允许跨企业（现有来源目录支持共同选择；范围歧义由服务端澄清，不由 UI 缩成同企业限制）。
- 删除会话的活动请求规则、旧 ResearchRun 保留说明；偏好编辑/删除回执与后端摘要清除边界。
- 新会话专用隔离 E2E app/运行器由主控安排，不修改现有正式数据库或原验收快照。

本 A0 的交付是可实施的最小页面与合同需求清单；没有声明 API 已冻结、代码已实现、测试已通过、真实模型验收或发布已完成。
