# A1 持久化独立审查

日期：2026-11-02（Asia/Taipei）。固定审查快照：`e458389d6b483493dce440df77f93f2d5fcaad27`。使用 `git show e458389:路径` 阅读 `app/conversations/{schema,models,repository,service,api}.py`、只读 history app 差异和相关测试定义，没有以当前工作树的 A2/Memory 修改替代 A1 证据。目标为 findoc-agent 独立 worktree `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`。本轮只新增此报告，未改代码、测试、数据库或 Git，也未运行测试。

## 结论

发现 **1 项 P2 失败收口缺陷**。持久化的主要安全方向成立：并发登记、预算预留、claim fencing、终态事务与读回、只读 GET、删除墓碑均有明确实现。没有发现候选答案绕过提交直接公开、同 op 重放再次执行 handler，或删除改动旧 ResearchRun 的证据。下面 finding 影响被校验拒绝后的会话可用性，不是候选结果泄露。

## Finding A1-01 — [P2] 提交阶段的确定性候选校验失败会遗留永久 running

位置（均为 e458389 行号）：

- `app/conversations/service.py:97–100`：最终 `repository.finish` 位于 handler/revalidate 的异常处理块之外。
- `app/conversations/repository.py:383–398,400–421`：finish 事务最终调用 `_turn` 做候选读回校验；校验失败抛错并回滚，已登记 running/claim 保留。
- `app/conversations/repository.py:256–274`：原文拼接、越界焦点、无效 context provenance 被转成 `conversation_integrity_error`。
- `app/conversations/repository.py:336–340,566–570`：残留 running 阻断新 Turn 和删除；只有启动 `recover_interrupted:423–433` 收口。

具体触发：给 A1 的 injectable handler 返回一个构造合法的 `ExecutionResult`，其中 result 为 `clarification`，resolved.company_id 是不在会话冻结来源中的企业。`ResolvedQuery` 本身允许该字符串，故 handler 正常返回，来源复验通过；finish 的 `_turn` 校验发现越界，事务回滚。API 返回503；随后同 operation 重放返回202 running、handler不再执行，新 operation 和 DELETE均409 busy。GET保持running且不修复，当前进程无法释放此会话，直到服务重启。

同样可用合法 `TurnResult(source_quote)` 搭配不等于原文拼接的 answer_text 触发。现有 `tests/test_conversation_a1.py:538–555` 已直接验证这两种候选被仓储拒绝后仍为 running，提供了回滚结果的源码证据；但它没有通过 service/API 验证拒绝后能够收口。本轮未运行这些测试，不将其当作新PASS。

这违反冻结 backend-a0 第3.3节“已登记 turn 的模型/引用/预算失败写 terminal Turn”的预期。仓储回滚候选本身是正确行为，缺口在 service 没有区分已确定未发布的候选验证失败与持久化结果不明。

窄修复建议：为提交前的候选语义/schema校验增加明确的、可区分于数据库损坏/IO/commit不明的异常；失败时保留原 claim，在独立短事务把该 Turn 收口为固定安全 `failed/error`（例如 result_validation_error），resolved=null、无refs/analysis，不重跑 handler。可以将候选验证前置，但事务内的范围/provenance复验仍须保留。不能简单 catch 所有 `conversation_integrity_error` 后盲写错误：已存数据损坏应继续 fail closed；提交成功但读回失败应继续依原 operation 只读查证，不倒退已提交终态。

建议补一条 service/API层故障注入：handler仅执行一次并返回上述越界resolved或非法原文；旧 op 能GET确定失败、新 op可以登记；另保留现有 commit失败/commit成功后readback失败测试，证明不把UNKNOWN误判为失败或重放模型。

## 已核实的边界

### 并发登记与 operation

`repository.py:176–213,322–353` 在 BEGIN IMMEDIATE 中先检查同 operation/request hash，再做 scope/admission/busy 检查；同 op优先返回旧记录，不因新轮running误报busy。schema的workspace operation唯一约束、seq唯一约束和partial unique running索引形成数据库兜底。只有 register返回created=True的执行路径会调用handler，重复请求不重跑。request hash包含kind/target和规范化请求（不含operation本身），跨动作/会话复用同op会冲突。create/turn DTO在入口规范排序，但不去掉原问题正文，异载荷仍能冲突。

`service.py:57–78` 提前查询旧operation，因此正常重放不会再次prepare来源。并发首次请求可能都做只读prepare，但登记事务只让一个进入handler；这不构成两次模型执行。没有发现GET、状态查证或404触发重POST的服务端路径。

### 提交读回与取消

`repository.py:355–381` 预算先落盘，model reservation设provider_outcome=unknown；claim必须匹配且Turn仍running。`_finish_in:383–398` 在同事务更新operation、Turn并校验读回，commit由connection context完成；`service.py:100` 仅在finish成功后读取公开结果。commit/随后GET失败时API返回脱敏503，不返回output内存候选。

取消在 `service.py:84–92` 使用原claim写interrupted；若该写也失败则保留running供启动恢复。`recover_interrupted`只封存旧轮，清claim，不恢复handler；旧claim随后reserve/finish均被fence拒绝。同步provider线程不能真正取消，A2必须只让service持有发布权；A1本身没有独立后台发布通路。

### GET 只读与恢复入口

`repository._read:55–60` 每个读取使用query_only事务。history/detail/turn/operation只校验和投影，不写恢复、不做来源字节IO、不调用handler。`app/api/research_history_app.py` 在ResearchOwner取得之后、开放请求之前构造ConversationRepository并recover；挂载router时不传service，`api.py:76–77` 因此不注册POST/DELETE。启动迁移/恢复写不被误称为GET写；历史app仍是无模型执行依赖的读取入口。

### 删除与旧历史

`repository.py:556–591` 在写事务内检查operation/busy、校验全部Turn，更新操作墓碑，再删除conversation及其cascade内容；重复delete op返回同回执，create/send旧op因resource_deleted拒绝复活。保留的operation只含身份/状态/request hash，不含问题或回答正文。没有SQL更新旧research_runs/template_tasks；schema没有到ResearchRun的级联删除。若未来research_run_id实际启用，旧Run内容保留仍须用户说明。

### 完整源身份与上下文 provenance

`_scope:131–165` 比较完整Identity JSON、canonical/hash、selection序列化与所有child rows；`register:331–335` 比较完整冻结selection，再事务内来源admission；service在登记前和候选提交前各做外部来源复验。`finish:410–419` 再在提交事务检查来源资格。历史只投影DB current_at_read，与冻结合同一致。

`ResolvedQuery`限制context引用数量/唯一UUID；`_turn:263–271` 要求context turn在同workspace/conversation中、seq较早、状态completed/refused且payload digest一致；跨会话/未来/中断Turn不能成为已提交provenance。此处验证“出处身份存在且可引用”，不证明具体指代语义正确；A2仍需从有效已提交历史构造焦点，不让模型自由决定可信context IDs。拒答历史可提供待澄清焦点，但不能作为财务真值。

## 留给集成阶段的待验项（非 A1 finding）

- Graph通过 `ExecutionResult.admit` 接入财务组的同事务再次核验，且绑定实际candidate所用refs/组；当前仓储只要求财务结果有callback，不能单凭存在callback宣称已验证事实。属于A2适配器审查，不以尚未接线报告A1缺陷。
- Memory源Turn detach、摘要清除、generation/provenance失效应与删除conversation同事务完成；这是Memory/会话集成项，e458389尚无Memory删除集成，不重复列缺陷。
- 正式runtime须在同一ResearchOwner生命周期构造service、恢复并挂路由；A1只读history已接线，不把A2 runtime尚未完成视为A1缺陷。
- A2应证明实际model/tool每次调用先reserve，禁止SDK/Graph自动重试，迟到结果只能经同claim提交。需要实际故障注入而非A1 fake通过数量。

主控提供的48 PASS/联合旧241 PASS为外部本轮协调信息，本审查没有重跑、也未将这些数字当作独立审查执行证据。报告结论仅对应e458389固定快照；当前工作树后续修复可由主控按具体commit复核。

## A1-01 处置复核 — 847b19c（2026-11-02）

**窄复核结论：A1-01 在固定快照 `847b19c67a297b7c9f20490bec4e04bd6e732b2c` 中已修复，可关闭此 finding；原 e458389 的发现和证据保留。** 本次通过git show读取修复及测试定义，仅做静态复核，未执行测试，不扩大为A2全量通过。

- `repository.py:38–42` 新增专用 CandidateValidationError；`finish:457–459` 首先解码/校验已存Turn、claim和scope，然后才在 `462–483` 独立验证新候选。非法原文、越界company及无效context身份等确定性候选错误被转为该专用异常；尚未发生候选写入，connection context回滚并释放该事务。
- `service.py:97–104` 只catch CandidateValidationError，使用原turn/claim再次finish为 `failed/result_validation_error`，不携带旧resolved/refs/analysis，也不重调handler。第二次finish仍执行fence；若收口写本身失败，异常继续传播，保持UNKNOWN/启动恢复路径。
- 既存Turn/scope解码在专用catch之外；候选引用历史的payload hash不一致在 `repository.py:480–481` 抛普通ConversationError，也不会被候选catch转换。实际写入/读回 `_finish_in` 在 `496–497`，位于新候选catch之外；sqlite错误、commit错误和随后get_turn错误均不会触发“候选无效”的第二次终态写。因此这次修复没有将所查的库损坏或提交结果不明路径一概收口为已确定失败。
- `tests/test_conversation_graph.py:445–471` 新增company/quote两个参数场景，走真实service/router，断言failed、安全空证据、resolved=null、同op重放相同结果且handler次数仍1、active_turn_id解除、新operation可返回200。它直接覆盖原finding的两个触发。
- `tests/test_conversation_a1.py:351–385` 仍保留写阶段异常后running/不重放，以及commit成功后公开读回失败、随后GET恢复已完成结果的用例。此处确认的是测试定义保留，不是本审查运行结果。

主控转述的A2相关136 PASS/较早316 PASS未在本轮独立执行或核验，不计入本报告验证数量。Graph财务admit callback与Memory删除集成仍按此前待验项留给相应集成/G审查。
