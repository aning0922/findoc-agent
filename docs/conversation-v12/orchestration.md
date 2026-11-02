# V1.2 主控与可见会话

日期：2026-11-02（Asia/Taipei）。本轮由用户明确授权主控持续实现、创建分功能可见聊天、按阶段动态调节模型与推理强度。

## 真实基线

当前聊天初始目录是 findoc-rag 的历史 worktree，未用于新功能开发。目标仓库为 aning0922/findoc-agent，2026-11-02 检查远程 main 与本地均为 1f0a3d4131480ac0ea742772127afac3c892fc7c。新建独立 worktree `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`，分支 `codex/conversation-memory-v12-20261102`。现有工作树、正式数据和冻结快照不覆盖。

## 职责和模型

| 可见聊天 | ID | A0 配置 | 所有权 |
| --- | --- | --- | --- |
| FinDoc V1.2｜架构与边界审查 | 01a19c91-6e91-7312-b147-a9cb316cb738 | GPT-6 Astra / high | 只读审查；独占 reviews/a0-architecture.md |
| FinDoc V1.2｜后端开发 | 01a19c91-7080-7700-b8b7-95e3b898c5ea | GPT-6.1 / high | A0 backend-a0.md；冻结合同后分派后端 |
| FinDoc V1.2｜前端与交互开发 | 01a19c91-732f-7d61-8274-0134bc8e1425 | GPT-6.1 / medium | A0 frontend-a0.md；冻结API后分派前端 |

主控负责合同冻结、文件所有权、集成、阶段门禁和唯一 Git 提交。开发聊天在受限文件范围内写代码；这按用户明确的可见分功能开发要求修订交接包中“主控唯一修改工作树”的建议。共享 migrations/runtime_factory 只有后端一名写入者。阶段结束才提交；不让多聊天争抢 Git index。

计划调整：架构 A0 和 G 最终审查使用 Astra/high；后端存储与安全边界 high，常规接线/修订 medium；前端交互实现 high，文案与常规修订 medium；测试运行与证据整理 medium，发现跨层缺陷升级 high。实际每次调整记录下表，不把计划当成已发生。

| 阶段 | 实际调节 | 原因 |
| --- | --- | --- |
| A0 | 创建上述三聊天与配置 | 持久化/来源边界需要独立审查，前端影响分析使用中推理 |
| B1 Memory并行 | 新建 FinDoc V1.2｜偏好记忆开发（01a19c9f-385b-7093-9459-74fafa5b44bd），GPT-6.1 / medium | 枚举偏好CRUD与回执独立实现，集成阶段再high；不写共享migrations/runtime |
| A0 验收准备 | 新建 FinDoc V1.2｜测试与验收（01a19c93-1676-7743-a92c-80bc2fe0af89），GPT-6.1 / medium | 独立梳理 C01-C20 与隔离测试入口 |
| A3 前端基础 | 前端聊天从 medium 提升 high | 请求归属、UNKNOWN 和模态焦点管理涉及跨状态边界 |
| A0 收敛 / A1 | 后端high→medium收敛DTO，再→high实现持久化 | 避免设计持续扩张，写入边界恢复高推理 |
| A4/G 准备 | 验收聊天medium→high | 真实HTTP/SQLite故障注入与跨层证据 |
| A3 基础轻量审查 | 架构审查聊天Astra/high→GPT-6.1/medium | 复杂架构已定，检查前端基础具体回归；G再升级 |

## 门禁

A0 → A1/A2/A3 → A4 → B1/B2 → G。业务合同不弱化；GET 不执行模型/财务写，UNKNOWN 只读查证。真实模型、真实来源、替身、模拟接受及真人核准分别记录。G 的真人语义核验不能由自动化替代。

## 用户仓库指正

用户追加要求当前项目统一使用 findoc-agent。全部工作聊天已同步，代码始终在该仓库独立worktree。Codex的项目列表仍指向旧目录；现有API无修改项目根目录能力，电脑控制访问Codex自身被工具拒绝，主控已明确请用户在项目设置更改目录。未绕过该限制修改内部状态文件。此UI归属问题不阻断正确仓库的代码工作。

## 已有阶段提交

- A0文档与合同：`4d88756`。
- Vite最窄修补：`3957f04`，安装后audit 0漏洞，最终新功能检查仍待执行。

## B1文件所有权调整

app/memory/**、tests/test_memory*.py归偏好记忆开发聊天独占；原后端聊天已撤回这部分写权限，仍独占Conversation与migrations/runtime/history装配。Memory只导出v11 schema，注册由后端A1之后集成；ConversationGraph摘要/召回归后端，前端偏好管理归前端。

## 后续阶段提交与调控

- B1独立模块：71468aa，31PASS/ruff；集成未冒充完成。
- A3/B2界面阶段快照：b5208c0，199PASS/25SKIP、Vite8.2.4 build通过，待真实接口E2E。
- A1持久化：e458389，最终48PASS、旧新联合241PASS（部分重叠，不求和）。
- A2：后端由high升xhigh，处理Graph/来源/财务提交资格。
- 轻量A1独立审查：GPT-6.1 medium→high，针对固定e458389快照；G再Astra/high。
- 前端常规接线修订、验收准备收敛：high→medium；有跨层复杂缺陷再升级。

## A2至G实际调度

| 阶段 | 实际调节与分工 | 原因 / 结果 |
| --- | --- | --- |
| A2正式Graph | 后端GPT-6.1 xhigh，完成后回high | 来源/事实资格、事务末复验、预算与UNKNOWN跨层边界 |
| B2有界摘要 | 后端high | 追加v12、派生摘要与generation fencing，不新增模型调用 |
| G最终独立审查 | 审查聊天升级GPT-6 Astra/high；修复后窄复核仍high | 原3项P2保留记录，后端c103ab3/前端337916f修复后均关闭 |
| G恢复修复 | 前端GPT-6.1 high，QA high | 未登记create/delete与已删Memory回执，避免UNKNOWN误解锁 |
| G真实检索证据诊断 | 后端high只读定位，再降medium修观测脚本 | 版本化检索绕过legacy hook，改物理MilvusClient.search，原失败不改写 |
| G手机表格 | 前端降medium，仅CSS与只读实际截图 | 补局部宽表排版；390/1440页面无横溢，原文/金额不变 |
| G交付文档窄审 | 偏好记忆聊天medium只读 | 指出v12文档过时、fresh runtime准备步骤和S4原句链证据缺口 |
| G回归 | QA保持high | 隔离旧UX/报告/财务/失效回归，按依赖顺序运行，不重复root后端全套 |

所有写代码聊天使用 findoc-agent 的同一隔离 worktree，按文件所有权并行；root是唯一提交者。不是让多个聊天同时任意改同一文件，也不把多聊天数量等同于正确性。动态配置由实际send_message_to_thread的model/thinking参数下发，未修改用户全局模型设置。各阶段原始可见聊天记录可以直接核验。

- 最终低成本交付一致性窄审：偏好聊天从GPT-6.1/medium切换GPT-6 Luna/medium，只读检查文档与真实/替身边界，无新实质不一致；没有检查代替HTML或真人语义。
- QA最终固定ad12570全21PASS、0失败/跳过/retry，S4原句独立UI写入/新context召回/删除后不复活通过，旧Agent/QA/阅读/报告/财务边界/来源失效全部按各自证据收口。root复核manifest和关键proof后准备本地交付提交；没有远程CI/push/合并或发布声明。
