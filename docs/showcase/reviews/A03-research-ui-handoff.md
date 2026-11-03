# A03 UI 有限合同（进行中）

基线 `2db02f814fa12ecdf2ec5574fb9b8ceb1976ff45`。props `{conversationId,onModeChange?,initialQuestion?,initialJobId?}`；quick 使用旧 composer，synthesis/deep 只在服务端真实合同稳定后启用解析/计划/启动。没有向后端传来源、事实权限或金额。

2026-11-03 读取 `/Users/aipuli/.codex/worktrees/4eab/findoc-agent/app/showcase_research/models.py`：`IntentRequest` 目前只含 operation_id、conversation_id、text，缺主控要求的 requested_mode；发送未支持字段将被 strict schema 拒绝，不可默默忽略模式。Group2 plan/job/events 的最终返回与路由代码尚未落盘；报告 worker 的 `models.py` 和 S03 交接文件目前不存在。UI 不会以猜测 DTO 发付费/写入请求，也不声称任务/报告可用。

已确认只读 `GET /research/conversations/{conversation_id}/links` 返回 `{conversation_id,items:[{intent_id,task_id,state}]}`，每个 Task 仍使用现有研究路由，不能替代人工财务核对。发现新增后端合同后需按真实代码补齐 requested_mode、提案/计划身份、operation UNKNOWN、job/events/results 和报告交付，再执行对应 UI 检查。

## 当前可交付的协议壳

`ShowcaseResearchPanel` 导出三模式与 onModeChange，默认 quick 明确指向旧 composer；研究模式有独立问题草稿但不发送。CID 改变时 key 强制卸载旧状态；关联 Task 只用已确认的只读 links DTO，GET 失败、加载和空态分别显示，旧 CID 迟到响应不会覆盖新会话。`initialJobId` 暂显示不可读取提示，不猜 job DTO。尚未新增持久化 operation key，也无任何变更写请求。

Node 24 build/lint PASS（保留现有 lint/build warning）；Vite + Chrome 假接口 1440/1280/390 PASS：模式切换、CID 切换清空草稿、旧响应失效、禁用未冻结写入口、无横向溢出。截图 `/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9d-a871-7520-aed9-dd6d22774d1a/a03/shell-{1440,1280,390}.png`；fixture 显示 UI_MOCK，无模型调用。复跑：frontend 先开 Vite 5180，再 `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node e2e/showcase-live-research-shell.mjs`。

**未完成，不可作为 A03/C02 验收**：意图解析 requested_mode、plan/job/事件、结果与引用、财务 handoff 发起、报告草稿和 UNKNOWN 恢复均尚未实现。最后复查 owner models 仅新增 PlanRequest/JobRequest 类型，router 仍没有计划和任务路由且 IntentRequest 无 requested_mode；报告 owner 目录仅缓存无 models.py/S03 交接。等真实合同落盘后在本分支续做，完成全流程再由主控接线。
