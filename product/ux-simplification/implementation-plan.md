# FinDoc UX 简化迁移与验收计划

日期：2026-11-02。用户授权主控持续推进开发、复检、修正；附件阶段确认由本次授权覆盖。附件是 UX 目标，不是业务事实。

## 已核验基线

聊天原目录 findoc-v1-product-design 是 findoc-rag 的旧 feat/30d-foundation@60864ca；不在其上实施。正式来源 findoc-agent 的本机及远端 main 均为 cdbd08151cfa282b20f518a45b5350d5c7e62002，与附件一致，工作区干净。新 worktree 为 findoc-ux-implementation，分支 codex/ux-simplification-20261102。归档 findoc-analyst-v1 的 origin 为 findoc-agent-history，仅作历史。

## 页面、API、状态及恢复映射

| 旧功能 | 新呈现 | API/状态保留 | 失败恢复 |
| --- | --- | --- | --- |
| ResearchHome 多入口/历史/企业创建 | 开始、待办、最近完成三块；独立任务列表 | tasks GET 分页与 validateTask；事实只读资格查询 | GET 重读，不重新执行 |
| AppShell 全局企业切换 | 五个目的导航；企业筛选留在列表 | 原路由身份校验；任务冻结范围不变 | 非法地址明确返回入口 |
| ResearchCreation 专业版本先行 | 目标—年报—核对；上传原位补齐 | 已有 companies/documents/source API，歧义必须明确选择 | 上传未知按原身份查证，不重复创建 |
| OperatingTaskPanel 六槽列表 | 三指标×两侧矩阵及原位核对会话 | task active_input、slotFacts、来源与 receipt 校验 | 来源失效撤下金额；不从候选制造已保存事实 |
| FinancialSession 独立核对页 | 可组合嵌入会话，当前项 PDF 保持上下文 | review + checkedItems + ConsentModal；ACCEPT、SAVE 保持分开 | ACCEPT request_id GET；SAVE receipt_id GET；UNKNOWN 不重 POST |
| OperatingResearch 继续执行 | 六项就绪后的明确继续操作 | task GET、revision/checkpoint 校验、resumeFacts、operation POST | operation GET；不在 effect 自动继续 |
| ResearchRuns/AnswerView | 原文回答和证据优先，PDF 右侧阅读 | validateRun 与 verified_excerpts；来源/字节哈希/物理页 | 历史读取不调模型；失效引用阻断 |
| ReportHistory/Preview | 报告库直出与独立阅读，版本/导出/编辑清晰 | 精确 revision GET，编辑为新版本，导出再核验 | operation GET；历史不覆盖、失效不可导出 |

## 不可合并的事务

每个来源/年度的 ACCEPT 独立；ACCEPT 与 SAVE 独立；SAVE 后独立 GET 验证；多组保存与 RESUME 独立；RESUME 与报告生成/保存独立。界面引导不改 API。显式同意只授权当次点击的步骤，刷新与恢复不延续写授权。automatic_resume:false 保留。

## 阶段、职责与改动范围

- P0：主控 Home、AppShell、列表路由、加载 hook、统一 token；Terra/high 负责 ResearchCreation、OperatingTaskPanel、OperatingResearch、FinancialSession、EvidenceWorkbench 与专用组件。先做范围映射，再分组落地和回归。
- P1：Sol/high 负责 ResearchRuns、ResearchAnswerView、ResearchPdfDialog 可选侧栏、ReportHistory/Preview 及专用样式。不会重写回答语义。
- P2：主控整合 360/1440 布局、键盘/焦点、文案；Astra/high 独立检查安全和失败恢复，修复后再复验。
- 每阶段独立提交，保留可回滚边界。不发布、不推送生产。

## 验收证据

前端 lint/type/build/单测，现有后端确认/持久化/研究/报告合同测试，以及真实 Chromium→HTTP→SQLite→PDF 的隔离业务 E2E。关键：新用户、缺资料、六项核对、ACCEPT/SAVE/RESUME 分步结果与 UNKNOWN、来源失效、问答 PDF、不可变报告版本/导出、刷新不重复执行、360/1440 与焦点恢复。

隔离自动测试的人为点击只能标为 simulated_test；真实 PDF 不等于真人财务接受；模型/向量替身必须明确列出。若可用则补真实模型检索执行；任何真实模型或真人/5人可用性验收未完成的内容单独列明，不能由截图补足。
