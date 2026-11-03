# A03/C02 研究工作流 UI 交接

基线 `2db02f814fa12ecdf2ec5574fb9b8ceb1976ff45`，分支 `codex/showcase-a03-ui`；前序 `af45521` 是只读壳，本次在其后新增执行与报告路径。未修改 Conversations/FinancialProduct/ReportPreview/AppShell 热点；主控接线 `ShowcaseResearchPanel({conversationId,onModeChange?,initialQuestion?,initialJobId?})`，按 onModeChange 为非 quick 隐藏旧 composer，历史仍保留。

已只读核对 4eab 最新 `app/showcase_research/{models,api,service,jobs,store,findings}.py`：IntentRequest 的 requested_mode 已落盘；plan/job 创建及各模式的 GET job/history/events 已落盘。计划必须匹配同会话、模式、intent、目标、企业、年度、指标和 scope_hash；按服务端返回的 plan_id/revision/sha 明确 checkbox 确认，POST job 只传批准标识，不传 scope/事实/金额。GET job/events 轮询真实已持久事件，失败可只读刷新；无虚构计时阶段或 CoT。服务端 budget/工具/子 Agent 用量只读展示，未知 token 不补造。provider_error 说明规则回退。

结果仅接受严格 kind/身份和 data_origin=live/seed/fake 的 DTO；模型解读标待审，numeric_claim_unverified 标未核实，unresolved 显示核对来源行动。财务结论标为保存时结果，当前资格须重新核验。来源跳转要求完整 company/document/revision/hash/physical_page/parser/evidence_id 与非空原文，固定 revision 进入旧 EvidenceWorkbench；仅 ID 的模型引用不造出处。需要财务核对时可明确发起 handoff，任务链接继续由真人核对，不自动 ACCEPT/SAVE/RESUME；同一次已创建任务按钮禁用，服务端仍是唯一去重权威。

S03 实际报告服务已接 `POST /showcase-reports/drafts {operation_id,job_id}` 与 `POST /showcase-reports {operation_id,draft_id,title,notes}`；只对完成并保存的 job 显示明确草稿/创建按钮，响应核对 `verified-report-job-v2` 的 job/data_origin/state 和 report_id/revision。版本链接指向受控 print；不传客户端 findings、来源或金额。主控补充的 `GET /showcase-reports/operations/{operation_id}` 用于报告 UNKNOWN，404 保持未知而不重放；报告 operation 和 `/research/operations` 属于不同账本，不交叉查询。该报告 GET 补充在读取时仍是主控集成树未提交变更，集成测试应以最终 SHA 为准。

每个写动作先把 UUID、action、模式、CID 与必要已选 intent/plan/job 引用存 sessionStorage `findoc:showcase-research-operation:<conversationId>`；硬 reload 后只读 GET 原 operation，按需只读重建 intent/plan/job 并重新校验，未知继续保留。存储不可用/损坏时在首 render 就禁写。该前缀加入 demoHintBoundary；本分支基线晚于 O03、早于并行 F03，主控合并时须同时保留 F03 的 finance-v2 prefix。CID 与模式切换按 key 卸载，abort+epoch 丢弃旧操作、历史和迟到事件。

## 模拟验证

Node 24 build/lint PASS，保留现有及组件 effect/ref/deps warning 与大 chunk 提示。Vite + Chrome headless，所有 `/api` 由 fixture 拦截且 UI_MOCK：1440/1280/390 PASS，含 quick/研究模式、requested_mode、意图、handoff 不重复、计划确认、job、3条事件、缺事实行动、未核实数字、ID-only 不造来源、fake 报告草稿/创建；意图/计划/job/报告草稿/报告创建分别模拟响应丢失，硬 reload 后用原 UUID 的正确账本 GET 恢复且无新增 POST；不同 CID 的迟到事件不显示、无横向溢出。另跑 Demo 存储窄集（新 prefix 包含在内）；fixture 无真实模型、真实财务签核或真实报告。模拟不证明 S01/A01/A02 或 S03 的真实联调与成本。

复跑：frontend 下先 `npm run dev -- --host 127.0.0.1 --port 5180`，再 `CHROME_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node e2e/showcase-live-research-workflow.mjs`；切会话壳用 `node e2e/showcase-live-research-shell.mjs`。截图 `/Users/aipuli/.codex/visualizations/2026/11/03/01a19f9d-a871-7520-aed9-dd6d22774d1a/a03/workflow-{1440,1280,390}.png`。真实 provider、gateway、报告 operation 最终接线及真实 PDF 引用点击均待主控在授权预算内验证，不能把 mock PASS 描述为真实模型效果。
