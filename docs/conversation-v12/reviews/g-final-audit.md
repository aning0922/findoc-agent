# G 独立代码审查（修复前固定快照）

日期：2026-11-02（Asia/Taipei）。快照：`8638b057c3554066e0e97f646517da74dfc3af76`，以该HEAD相对本地origin/main的V1.2差异为范围。目标：`/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`（findoc-agent独立worktree）。后续并发改动不自动纳入本结论。除本报告外未写文件、数据库、代码、测试或Git；未调用真实provider、未运行大回归。

## 结论

**发现3项P2，建议修复并窄复核后再关闭代码闸口。** 未发现新的P0/P1证据。已关闭A1-01的专用CandidateValidationError修复仍保留，不重复报问题。本报告不是发布批准，也不代替正在进行的真实HTTP/SQLite/原PDF+替身模型浏览器验收或真实模型/真人语义核准。

以下源码行号全部指向8638b05，可用 `git show 8638b05:路径 | nl -ba`复核。

## G-01 [P2] 非省略的指标问题也被改写为取数原文，丢失用户明确问题

位置：`app/conversations/context.py:219–222`，调用后果见 `app/conversations/tools.py:80–82`。

触发：冻结单企业2025年报、无历史、无fact_selections；提问“2025年营业收入下降原因是什么？”。resolver得到metric=revenue、year=2025、无澄清reason，然后无条件将任何含metric的问题改成“甲企业股份有限公司 2025年度 营业收入原文”。原问题中的“下降原因”不进入当前RAG查询/证据资格判断；它与“2025年营业收入原文是什么？”产生完全相同resolved query。当前user_text也不在 `load_context` 的recent历史中，故追加背景不能挽回本轮语义。随后可以只返回金额原文并标completed，而没有找到用户询问的原因；已选择fact时则可能直接进入confirmed_metric，进一步把解释请求当作读取单值。

证据：本轮在内存中从固定快照AST抽出实际resolve函数、METRICS/LABELS及实际calculation_intent函数，以简单只读对象替身执行上述两个问题。两者输出完全一致：`intent=source_quote, text=甲企业股份有限公司 2025年度 营业收入原文, resolution=explicit, context_turn_ids=[], reason=None`。未加载数据库、未运行Graph或模型；此验证仅证明解析丢失意图，未声称模型实际生成某个错误答案。

窄建议：只有识别为受支持的省略追问时才构造独立取数请求；完整问题保留原始谓词、限定条件和否定语义，结构焦点另附。对于当前能力不支持的原因/预测/细分请求，应明确澄清或保守拒答；不要用“读取指标值”替换请求。增加相同企业/年份/metric下“原文金额”和“原因原文”的差异断言，并确保带fact_selections也不会自动变成单值回答。

## G-02 [P2] 新建/删除的确定登记前拒绝留下永久pending，使会话写入口锁住

位置：`frontend/src/product/Conversations.tsx:162–174,239–250`；阻断条件在 `163,182–184,240,273`，查证分支在 `209–237`。

触发A：来源目录读到可用年报后，另一标签/操作使来源失效；用户点击创建。前端先将create operation写sessionStorage，后端service在prepare或create事务admission阶段返回明确的source_not_ready/source_changed等409，且尚未登记该operation。create catch无差别将它标UNKNOWN，保留pending。用户只读查证永远得到404；重新选有效来源也因pending.length禁止创建。刷新同标签仍从sessionStorage恢复同一堵塞。

触发B：A标签显示会话空闲，B标签开始一轮；A点击删除。后端 `app/conversations/repository.py:641–646` 在登记delete operation前返回409 conversation_busy。前端delete catch仍永久保留delete pending，GET operation必然404。即使B已结束、A只读刷新成功，showConversation只清理send类终态线索（`142–148`），不会清理此未登记delete线索，A不能继续发送/删除，也不能创建新会话。

此处是收到原写请求的确定拒绝；不建议把后来GET404当作“肯定未执行”。现有send路径 `195–204` 已对有限登记前错误做了正确区分，create/delete缺少对应处理。

窄建议：分别冻结create/delete的登记前错误白名单，只针对原POST/DELETE响应、准确HTTP状态+错误码清除本次线索，保留草稿并强制只读刷新资格/active状态，由用户再次显式操作。网络错误、5xx、operation冲突和GET404继续保持UNKNOWN。测试应覆盖 stale目录创建409、双标签busy删除409，以及真实丢响应不解除pending。

## G-03 [P2] Memory恢复校验拒绝合法的“原操作已完成、资源后来已删除”回执

位置：`frontend/src/product/memoryApi.ts:32–36`，消费路径 `ResearchPreferences.tsx:35–44,46–47,88–98`。

触发：A标签创建或修改偏好已提交，但响应丢失，A保留pending；B标签看到该偏好并明确删除。后端 `app/memory/repository.py:234–236` 正确地将这个memory关联的所有历史operations设resource_deleted=1。A查原create/update operation，得到身份完全匹配的completed回执及resource_deleted=true；但前端强制 `resource_deleted === (pending.kind === 'delete_memory')`，因此抛错。每次只读查证都会重复拒绝同一合法墓碑，pending不会解除，整个偏好CRUD持续禁用。

这不是要求恢复已删除偏好。正确结果应是“原操作已查明，偏好随后已删除”，清除已查明的本机pending，再读当前列表；不得重POST或恢复旧value。

窄建议：回执验证接受create/update的resource_deleted=true（仍校验op/kind/memory身份及终态）；delete成功仍要求true。恢复UI根据resource_deleted显示删除提示，绝不把原value补回。增加原create/update丢响应→其他标签delete→查证旧operation的测试。

## 已审查的关键边界与证据

### 迁移、来源、旧合同

- 迁移注册只追加10/11/12；对origin/main的旧schema文件差异为空。对e458389的conversation schema差异为空，对71468aa的memory schema差异为空。因此没有发现通过改写已应用SQL改变checksum的情况。此为源文本检查，不是实际旧库迁移验收。
- v12 `context_schema.py` 只新增摘要表和不可更新trigger；FK使会话删除级联清除摘要。旧ResearchRun/Task表与原文模型合同未修改。
- repository仍保存并检查完整SelectedDocumentIdentity、canonical/hash及child rows；登记与发布事务复验scope，service在外部字节复验后进入提交。历史source_states仅DB资格投影，UI有对应说明。

### register/commit/readback、owner、取消

- BEGIN IMMEDIATE + workspace operation唯一 + 同会话running partial unique继续保障注册互斥。同op先返回旧记录，handler只执行created分支。预算在外部调用前reserve，失败不启动provider。
- CandidateValidationError仅对新候选确定校验错误收口；原记录/claim/scope解码、真正写入与commit不在该catch范围。A1-01已关闭，不重复报告。
- 主runtime `runtime_factory.py:210,320–335` 在ResearchOwner生命周期内recover会话并注入Graph/router；history app只挂无service会话路由和read_only Memory路由。GET不恢复Graph、不重算或更新摘要；摘要prepare hook仅在新POST登记之后运行。
- cancel后以原claim封存；保存失败保留running供独占启动恢复。late provider返回只能经过仓储fence，不获得发布权。Graph compile(checkpointer=None)，没有旧checkpoint自动续跑或TaskCheckpointer混用。
- 外部provider的实际处理/计费仍可能UNKNOWN；当前保证是应用不自动重发，不是供应商exactly-once。deadline在节点/调用前后检查，不应宣称同步provider线程能在240秒被强制终止。

### Graph财务真值与预算

- `tools.py` 只路由原文、确认事实或确定性比较。source_quote复用旧RAG/Result校验，且检查引用企业与resolved企业一致；完整问题被改写的缺口见G-01。
- financial验证每个用户提供的查找键，恢复实际source，比较完整冻结identity与期间；使用local_operator的FinancialAnalysisService，不自行重写公式。实际用于结果的groups在工具末尾复验字节与组；commit callback在调用方同一事务调用 `recheck_persisted_analysis_in`，比较完整groups并再次检查scope。没有把fact_id当授权令牌。
- runtime显式传 `llm_client.generate_once`，reserve model/tool次数在调用前落库；无Graph retry配置；结果经过service最终提交才公开。没有发现新增自动ACCEPT/SAVE/RESUME工具。

### 摘要/偏好与防复活

- 当前摘要是结构焦点，最多32个旧Turn的有界来源，保留两版；读取时重新derive比对provenance。load_context限制近期消息、摘要和偏好预算；摘要游标不连续则不采用。最近有效但歧义焦点阻断回退；未知主体规则和负计算检测存在。这里只证明控制流，不能声称中文意图覆盖率已达标。
- Memory只允许有限枚举，显式confirmed；没有模型/PDF自动写通路。每次读当前generation/items，source exclusions永久保留最小Turn ID；历史偏好候选不重新注入。Graph工具reservation和最终admit检查generation，期间改变则拒绝旧上下文候选。
- 会话删除在同事务调用Memory detach，再级联删消息/摘要；不删除独立确认偏好。偏好delete物理删除正文并使operations墓碑化；事件只存动作/ID，不存旧value。G-03是前端墓碑消费缺陷，不是后端复活问题。

### 前端恢复、PDF与旧深链

- pending采用sessionStorage并只序列化身份字段；避免此前共享localStorage数组竞争风险。同scope保留用户事实选择；切换scope清facts/chosen/error/PDF标志并abort旧reader。发送回执核对operation/conversation/user_text/fact selections，跨会话恢复不会将A结果merge到B。
- `conversationPdf.ts`先校验冻结scope完整身份、物理页和source，再checkSource真实文件；财务action使用冻结scope定位，不伪造EvidenceRef。ResearchPdfDialog继续独立复验。此为代码路径检查，未独立读取真实PDF验证。
- `/research?mode=qa`、run/return_task与旧经营任务/报告深链保留，新导航指向/conversations。AppShell URL/epoch key卸载旧页面，QADialog清理modal/overflow并恢复可用opener。动态弹窗切换、软键盘与实际焦点仍需浏览器/设备验证。

## 证据范围与处置要求

实际执行：固定commit读取、关键全diff及源码/测试定义审阅、旧schema文本差异比较、G-01纯函数内存验证。未运行数据库测试、迁移、provider或浏览器，不产生新的PASS数量。不能将主控/QA报告的通过数列为本审查独立执行结果。

未验证：原始验收资产SHA、真实provider有限多轮结果、真人local_operator正向业务完成、移动软键盘/完整辅助技术、正在联调的E2E最终状态。它们是独立验收边界，不作为代码缺陷或擅自扩大scope。

建议主控修复G-01/G-02/G-03后提供固定修复commit，针对这三项进行窄复核并保留本报告历史。本轮没有发布批准、合并或远程操作。

## 三项 finding 修复窄复核 — 337916f（2026-11-02）

固定快照：`337916f015289791c7e89ecdfe235e4c739da3d3`。后端修复 `c103ab3baa67f22304a7dd9ec3ea96eb56a5a964`，前端修复337916f。**G-01/G-02/G-03的原触发均已修复，可关闭这三项代码finding。** 原8638b05报告完整保留。本次没有发现修复范围内新的有充分证据的缺陷；不是对全部新增代码重新全审，也不是发布或E2E批准。

### G-01：关闭

`app/conversations/context.py:208–245` 仅以有限取数/比较语法进入财务工具；提供fact_selections不能把原因或限定口径问题变成single metric。完整问题保留谓词/限定/否定，仅确认为省略追问时补成独立问题。自由原因解释返回interpretation_not_supported澄清；明确“原因原文”保留原问题走source_quote。`graph.py` 增加对应能力限制说明。

独立执行了固定快照resolve纯函数内存验证：无facts/有facts两种情况下，“2025年营业收入下降原因是什么？”均为clarify + interpretation_not_supported，原问题保留；“2025年营业收入下降原因原文是什么？”均为source_quote，原问题保留。使用简单只读对象替身和实际AST函数/负计算检测，无数据库、检索或模型调用。此结果直接覆盖原G-01；不能据此声称实际原因引用质量通过。

读取新增 `tests/test_conversation_graph.py` 的G01用例定义：覆盖完整取数与原因原文区别、真实传递到search/provider参数、带查找键不访问财务服务、自由解释零工具/模型、限定季度比较澄清。原“只摘录同比原文”现在保留完整请求后由旧D26保守拒绝；测试已保留该限制，不再靠删掉同比词来绕过旧门禁。本复核未执行这些测试。

### G-02：关闭

`Conversations.tsx:165–188` 使用awaitingCreateResponse区分首次POST结果与后续operation GET；仅在POST尚未成功返回、且属于明确来源409白名单时清本次pending，保留draft/selected并设createNeedsRefresh。成功POST后的GET错误、5xx、损坏JSON、operation conflict不走解锁。来源GET成功才解除刷新要求，没有自动重POST。

`conversationApi.ts:146–160` 的delete分类要求错误来自DELETE，并限409 conversation_busy/410 conversation_deleted。`Conversations.tsx:253–277` 清本次delete线索后要求刷新；busy状态只读刷新后仍受active_turn约束，410则保持发送/删除关闭并提供返回入口。GET404/410以及其他方法不会授权清理delete pending。

后端 `api.py:88–92` 将登记前来源selection_changed统一映射source_changed，覆盖原create事务校验窗口；已登记后来源失败仍由service写失败Turn，不返回该登记前409。新增A1测试定义分别证明未登记op不存在/handler零调用和已登记失败有终态回执。

新增 `frontend/tests/conversationAuditRecovery.test.ts:18–100` 覆盖有限分类、保留无关operation、来源GET/详情GET先于下一次用户明确写入、DELETE方法绑定及UNKNOWN保留。它们是helper级替身测试定义；实际React按钮/多标签联动仍以主控正在补的浏览器Gcases为准，本轮没有宣称浏览器已通过。

### G-03：关闭

`memoryApi.ts:32–44` 接受create/update的合法completed+resource_deleted=true，同时仍要求准确operation/kind/memory身份；delete仍必须resource_deleted=true。新memoryOperationNotice明确“原操作已查明，偏好后来已删除”，不包含旧值。

`ResearchPreferences.tsx:35–47` 恢复只读回执后清pending/editor，墓碑先移除本机旧item并设loaded=false，再GET最新列表；后续列表失败不会重新显示为可编辑旧偏好。正常write后查证遇到同类墓碑也使用相同行为。没有自动重新POST、没有从旧响应恢复value。

新增前端测试定义 `conversationAuditRecovery.test.ts:102–130` 覆盖create/update响应丢失、另一次DELETE、原operation GET墓碑、GET当前空列表，以及错memory ID/非法delete回执拒绝。此处是静态核对，不是本轮执行通过数。

### 证据与剩余验收

本轮仅追加本节、阅读两个固定修复commit及测试定义，并运行上述4个纯函数输入检查；未改业务代码/测试/Git，未运行provider、数据库回归或浏览器。主控提供的后端183 PASS、前端209 PASS/25 SKIP、build/lint通过没有转写为独立执行证据。浏览器Gcases补测、真实模型与真人核准仍独立待验；关闭三项代码finding不等于最终发布批准。
