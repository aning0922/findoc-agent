# 00｜真实仓库现状与改造决策

## 固定基线

核验日期 2026-11-03；默认 `main@1f0a3d4131480ac0ea742772127afac3c892fc7c` **不是**最新 C 方案。真实工作基线 `codex/findoc-showcase-c-integration@45d55d75662f01d9bc78da1a946d845a01a27480`，PR #2 目前是相对独立 V1.2 的草稿。主控开始前重新 fetch 与验证；所有声明提供 commit SHA。

## 已存在且必须复用

- 演示登录：`app/demo/*`，20/30 分钟会话、默认等待策略、owner 二次确认接管、代际隔离与 seed 复位。**不要重写登录、数据库复位或会话控制器。**
- Dashboard：`app/dashboard/*`、`frontend/src/product/showcase/ShowcaseDashboard.tsx`：Hero、KPI、折线/柱状/环形图；目前财务曲线优先是有标识的虚构示意，已确认财务数据可能为空。
- 官方下载：`app/disclosures/service.py` 的 `search()` 对固定 4 条 `catalog.json` 做名称子串/代码筛选；`SafeDownloader` 有受限下载与预置 SHA；`DocumentSourceService.upload()` 接续解析。**不存在动态巨潮全市场查询或任意 URL 入口。**
- 文档：`DocumentService` 原始文件对象存储/内容哈希去重、`DocumentProcessor` fast PDF → chunks → BGE-M3 → Milvus Lite；默认单 PDF 20MiB。
- OCR：`ParseV2Service` + macOS Apple Vision，独立 `parse-v2.db` 和 FTS，最多 50 页/180 秒；未将 OCR 候选默认升级为旧 RAG 正式索引/已确认财务事实。
- 财务：旧三指标 `revenue/net_profit_parent/operating_cash_flow` × 两侧事实确认；新 `finance_v2` 是**即时报表**总资产、总负债、资产负债率。`ExtendedMetricV2.period_kind='instant'`，不能直接用它存利润表/现金流量表的期间累计指标。
- 研究：`app/showcase_research/*` 已有结构化意图、单/双子代理、真实工具交接、已保存事件和分层发现；`app/showcase_reports/*` 有版本报告、打印 PDF；研究记忆 `app/research_memory/*` 真 BGE 语义召回；禁止重新造一套不互通的研究平台。
- 演示 seed：含两企业、3 READY PDF、2 历史研究、2 报告、OCR 样例，完整二进制 bundle 在原 Codex 本地不在 Git，重置通过代际拷贝恢复。下载的大文件暂存当前代，**不自动永久保存到所有新代。**

## 真实缺口（禁止假称完成）

1. 官方目录不是动态查询；发布日期、更正状态可能未知。
2. 原有 C 的真人 `ACCEPT → SAVE → RESUME` 与 v2 财务确认未执行；全部当前已确认财务图不能被虚构 KPI 替代。
3. 15 条固定评测仅 5 条 intent partial + 10 skipped；全层级 PASS=0；存在无关原文片段进入风险研究的真实案例。
4. OCR 是派生单页真实 Vision，但无法默认“扫描文件→正式 RAG”；不要把 OCR 转录等同于已验财务。
5. 较宽旧回归 141 PASS/57 setup ERROR，缺 `product/validation/d21-real-research.json`；远端绿色 Quality 不覆盖全部 C+ 新增专项测试。
6. 数据目录与 demo generation 的隔离关系要在新缓存设计中处理；当前 `ProcessRuntimeManager.reset()` 启新代，但没有独立的旧代文件 GC 证明。

## 正式决策

- 新阶段代号 **FinDoc C+｜企业研究与财报深度分析**；**16 个新功能 F19–F34**；已有 F01–F18 只做互通和必要修复。
- P0 先构建：**官方动态模糊搜索、公司 360、三大财务报表可阅读、真实趋势、AI 体检、跨年文本对比、证据检索质量**。没有这七项就不叫 C+ 核心完成。
- P1 继续：同行对标、主营业务结构、图表追问、批量研究、指标解释与模板、收藏、Excel/CSV/PPTX。
- OCR 入正式研究链路作为关键补口，不能把它推到“已完成”的小修项。
- 产品定位求职：固定典型资料可演示、一条从在线查找到报告的真实端到端主链路、视觉成熟；不追求大规模并发、多租户与商业运营。
- 数据可信：`source_revision + PDF SHA + 解析版本 + period_kind + as_of_date/period_start/end + basis + scope + evidence_refs + authority` 必须保留。**程序不能把未核验数字画成已确认事实，用户必须自己做确认动作。**
- 规划目标（并行辅助工程）：M0 0.5–1.5 有效开发日；核心功能首次可演示约 3–6 个有效开发日，C+ 全功能打磨另需约 3–8 日；OCR/外部接口/真实语义评测可能拉长。此为估算/里程碑，不做保证。
