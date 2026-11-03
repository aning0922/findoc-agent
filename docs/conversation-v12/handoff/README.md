# FinDoc Agent V1.2 — Conversation & Memory 交付说明

计划日：2026-11-02。**规划材料，未开始代码开发，也未修改远程仓库。**

## 真实基线

- 仓库：`aning0922/findoc-agent`
- 已核验 `main`：`1f0a3d4131480ac0ea742772127afac3c892fc7c`（Merge PR #1）
- 当前技术：React 19 + TypeScript + Vite、FastAPI、SQLite、Milvus Lite/BGE、LangGraph == 1.2.13、OpenAI 兼容 Chat Completions。
- 现有 `app/api/research_runs.py`：独立单次持久问答。`app/research/models.py` 的回答内容严格限定为经验证原文，不可原位修改为自由生成。
- `app/research/task_checkpointer.py`：绑定现有研究任务执行身份的 checkpoint，不可直接挪作会话 checkpointer。
- `app/chat/service.py` 与 `/chat`：旧单文档聊天／SSE 传输，不代表线程级记忆。
- `app/agent/runtime.py`：旧有限单文档工具调用，已有受控 loop，可借鉴模式但不能直接当多轮 Agent。
- `app/agent/financial_analysis.py`：已确认财务事实的确定性分析入口；复用校验和 Decimal，而不是新写计算公式。
- `product/ux-simplification/verification.md`：近期 UI 工程验收记录，必须保持回归。

## 版本目标

围绕已授权年报连续对话，追问自动明确指代，经过服务端校验的工具能读取原文和已确认财务事实；历史会话持久保存；用户可明确批准少量跨会话研究偏好并随时删除。对外产品名称“财报研究助手”或“研究助手”，不是万能聊天机器人。

> 业务边界：单人本地工作空间（当前 `demo`），不宣称用户登录、多租户、生产级安全隔离；财务金额只来自有效核准事实或带状态的原文摘录；模型解释是待人工语义审核的内容。

## 推荐阶段与周期（Codex 辅助开发估算）

| 阶段 | 主要交付 | 预计 |
| --- | --- | --- |
| A0 | 影响分析、合同冻结、页面流程原型 | 0.5–1 天 |
| A1 | Conversation 数据库、HTTP 接口、幂等／恢复 | 1.5–2 天 |
| A2 | LangGraph 对话编排、指代消解、只读工具、结果隔离 | 2–3 天 |
| A3 | 连续对话页面与证据栏、移动布局 | 1–1.5 天 |
| A4 | 对话契约／浏览器端到端测试 | 1–1.5 天 |
| B1 | 记忆 CRUD、确认与删除、审计 | 1–1.5 天 |
| B2 | 短期摘要、受限召回、前端记忆管理 | 1.5–2 天 |
| G | 真实模型与真实年报验收、风险复检、公开演示 | 1–2 天 |

**总量建议按 10–14 个开发日安排**；实际估时需在 A0 依据现有依赖与测试耗时修订。每阶段可独立验收；A4 是优先可交付的求职版本，B2 形成长期记忆版本。

## 明确不做

新增财务指标和扫描版 OCR、股票预测、跨租户共享记忆、自动 ACCEPT/SAVE/RESUME、无界工具循环、复杂 Multi-Agent、语音、主动后台长期任务、自动把年报／未经证实的模型输出写入记忆、把旧静态历史演示伪装成真实模型运行。

## 文档索引

- [01_PRODUCT_UX.md](01_PRODUCT_UX.md) — 业务场景、交互原型与边界
- [02_TECH_DESIGN.md](02_TECH_DESIGN.md) — 图状态、持久化、接口、模型预算及可信数据线
- [03_PHASES_ACCEPTANCE.md](03_PHASES_ACCEPTANCE.md) — 子任务、验收、风险、质量闸口
- [04_CODEX_KICKOFF.md](04_CODEX_KICKOFF.md) — 可直接贴进 Codex 的开场任务指令

参考：
- https://docs.langchain.com/oss/python/langgraph/add-memory
- https://docs.langchain.com/oss/python/langgraph/persistence
