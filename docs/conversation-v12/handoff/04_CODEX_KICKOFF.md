# 04｜发给 Codex 的开场指令

你是 FinDoc Agent V1.2 的主控工程师。目标不是完成一个聊天 UI，而是**在现有可信年报研究系统上完成可持久化、多轮、受控工具调用、带可管理长期偏好的财报研究助手**，并保留全部已验证的业务约束。

## 仓库与基线

仓库：https://github.com/aning0922/findoc-agent

规划时 GitHub main SHA：`1f0a3d4131480ac0ea742772127afac3c892fc7c`。你必须首先读取当前实际仓库、工作树、远程 main 和最近提交；如 HEAD 已变化，基于最新真实状态做差异审查，不直接覆盖提交。新建独立分支或 worktree，勿在用户已有改造分支做未经审查的修改。

务必先阅读交付包：`README.md`、`01_PRODUCT_UX.md`、`02_TECH_DESIGN.md`、`03_PHASES_ACCEPTANCE.md`，并实际检查 `app/research/models.py`、`app/api/research_runs.py`、`app/research/task_checkpointer.py`、`app/agent/financial_analysis.py`、`app/api/runtime_factory.py`、`app/companies/migrations.py`、`frontend/src/product/ResearchWorkbench.tsx`、`product/ux-simplification/verification.md`。

## 不可突破的工程边界

1. 不修改或弱化旧 ResearchRun 原文摘录协议、不可变历史、确认事实的受控计算、源身份复验。
2. ConversationGraph 与 TaskGraph 各自使用独立线程状态；不让已有 TaskCheckpointer 去存聊天记忆。
3. 任何模型或 RAG 自由文本不得自动写入 MemoryStore 或变成已核准财务事实；记忆必须用户明确确认。
4. 所有模型和工具结果需有可观测的稳定状态；UNKNOWN/GET 不能暗中重放模型或写操作。幂等键冲突必须安全拒绝。
5. 现有 ACCEPT、SAVE、RESUME 必须仍由人明确动作触发。不得为减少交互而自动合并业务操作。
6. 对外宣称的生产/用户/模型验收须与真实证据一致：fake 的浏览器测试绝不能算完整真实模型与真人金融审核。
7. 当前系统只有本地单用户演示空间；不得伪造多用户身份或越权设计。

## 实施方式

**先 A0 研究设计，再逐阶段执行 A1–A4、B1–B2、G。** 你可以在已确认合同下持续推进，不要为了微小实现选择频繁询问；但影响已冻结外部协议、需要新增付费平台或会改变业务安全要求时必须明确说明变更原因。

A0 产出：实现影响清单、技术数据流图、完整 API/SQLite schema 提案、页面状态流、分工顺序、风险表、原有测试运行基线。特别解释为何原 ResearchRun 不可直接复用为自由对话消息、为何原 TaskCheckpointer 不能当长期记忆，以及如何保证独立新 Conversation Store 的提交/Checkpointer 不一致时仍安全。

A1–A4 完成：可以选择 1–4 份年报开始会话；连续追问、会话列表和持久化恢复；能够在只读白名单工具中选择检索/确认事实/确定性比较；有原文证据，能拒绝缺资料/未确认事实；原有历史读取和研究流程回归通过。

B1–B2 完成：可明确确认、查看、修改与删除分析偏好；新会话召回正确的偏好；摘要/上下文 token budget 限定；不把报告事实或模型猜测写入长期记忆。

G 完成：新旧契约与 E2E、真实模型和实际年报的边界测试、手机/桌面与焦点检查、README 和演示路径、独立审计。提交独立分支，准备 PR。每阶段提供交付摘要、具体 commit SHA、通过/跳过/失败数、真实与 fake 的清晰界限、未解决阻断项和下一阶段条件。

## 最终报告必须回答

- 用户如何围绕同一公司连续追问？“它/那一年”解析错如何防止发布错资料？
- Chat/ResearchRun/经营任务 Checkpoint/长期 Memory 的四种存储如何分工？
- 一次模型调用后网络失败，如何读回结果而不重新收费、不执行第二次工具调用？
- 为什么一条记忆可以跨会话，但不能允许模型替用户确认财务值？
- 如何证明本次多轮结果不是纯测试替身伪造，以及哪部分真实模型回答仍待人工语义复核？

本指令只授权在 Codex 的开发环境里开展代码工作；当前 ChatGPT 仅规划，未直接修改正式仓库。
