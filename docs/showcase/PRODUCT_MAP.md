# F01–F18 复用与演示地图

目标：30秒第一眼、5分钟业务链、8分钟技术验证。真实/种子/示意分层。以下是范围地图，不是完成声明。

| 功能 | 真实已有底座 | 本轮用户可见增量 / 30–90秒验证 | WBS |
|---|---|---|---|
| F01 | 无auth；固定demo workspace | 登录→B占用→owner二次接管→A下线→恢复种子，真实双浏览器HTTP | L01–04 |
| F02 | ResearchHome待办/最近完成，Recharts已锁 | Hero搜索、4 KPI、折线柱环，tooltip/表格/来源标签，3宽度 | H01–03 |
| F03 | AppShell五导航、Conversations、任务深链 | 首页进入同工作区、资料缺失提示、核对后回会话 | U01/C02 |
| F04 | DocumentSourceService.upload仅记录source_url | 搜两企业正文年报→显式安全下载→真实PDF/解析；上传回退 | D01–03 |
| F05 | fast parser、MinerU输出适配器、DocChunk | 实际OCR扫描页→表格/原页并排→质量候选，非财务核准 | O01–03 |
| F06 | 三指标×两侧、Decimal、receipts | 独立v2总资产/总负债等2–4项+原文→图，不改旧迁移 | F01–03 |
| F07 | context规则、Graph白名单 | 10–20固定自然语言/追问→结构意图→程序授权或澄清 | C01 |
| F08 | RAG原文与固定经营研究解释 | 快速总结/综合研究区分已核准数值、原文、AI待审 | S01–02 |
| F09 | TaskRepository / PersistentTemplateService | 问答计划确认→研究→人工核对→报告→回问答 | C02 |
| F10 | 固定Graph、有限工具loop | Supervisor真实分派2子代理→工具→校验→汇合，单/多对照 | A01–03 |
| F11 | 枚举偏好MemoryService | 保存研究线索→新会话语义检索→删除后不复活 | M01–02 |
| F12 | 枚举analysis_focus/display_unit | 明确保存现金流偏好→推荐问题/图顺序变化→删除还原 | M02 |
| F13 | 历史事件、SSE基础 | 3+已持久阶段/工具交接→刷新恢复，无新调用 | A03 |
| F14 | immutable报告版本+Markdown | 摘要/图/证据→编辑新版本→实际PDF/Markdown导出 | S03 |
| F15 | agent eval基础 | 固定样本分母/路由/引用/拒答/召回/耗时调用对照，失败保留 | E01–02 |
| F16 | 静态历史demo与V1.2只读案例 | 3–5合法PDF+历史报告/会话manifest→generation复位一致 | E03 |
| F17 | 偏好保存；无任意语义笔记 | 收藏引用/备注→回看/关联报告→建议预填不发模型→reset清除 | M01–02/U01 |
| F18 | 现有导航drawer/PDF/基本a11y | 统一tokens、空载/失败、键盘和图表表格，三宽度实际走查 | B02/H02/G02 |

路线A：登录/首页/研究案例/双访客复位。路线B：官方资料或合法样本→真实解析/OCR→原文+候选/真人核准→综合解释→版本PDF。路线C：已选资料→深度计划→真实子代理/事件→报告→保存线索/跨会话召回/删除。

人工确认始终由用户执行；没有真人回执时，路线B展示原文+未核实解释和独立sample_mode，不声称已核准。G02真人走查是human_pending，自动化不能冒名通过。
