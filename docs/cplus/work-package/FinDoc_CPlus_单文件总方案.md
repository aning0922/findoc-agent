# FinDoc C+｜完整工作包单文件版
**独立规划交付，不是实际已完成功能；本文件不包含 CSV JSON 和原型的全部原始字节，机器可读任务以 ZIP 内文件为准。**


---

<!-- START README.md -->
# FinDoc C+｜求职展示增强版 · Codex 托管开发工作包

**性质：完整的下一轮独立开发包，不是上一份 C 包的补丁；不是已经实现的功能，也不是生产上线方案。**

- 基线仓库：`https://github.com/aning0922/findoc-agent`
- **必须从** `codex/findoc-showcase-c-integration` 的 `45d55d75662f01d9bc78da1a946d845a01a27480` 创建新的独立 C+ 集成分支；先 `git fetch` 再核实 SHA。有新提交则先 compare 并更新状态，禁止无声换基线。
- 当前 C+ 为规划，原 C 方案 F01–F18 的代码应尽量复用；现有 PR #2 为草稿，不直接合并 `main`。
- 定位：**AI 应用 / Agent 开发求职展示作品**。追求功能深度、业务闭环、专业 UI 和 5–10 分钟可操作演示。不是生产 SaaS、不建多租户、支付、分布式高可用。

## 首次交给 Codex 的顺序

1. 把整个工作包文件夹放在本地，例如仓库外部 `~/Downloads/FinDoc_CPlus_...`，不要直接覆盖现有仓库。解压后文件保持相对路径。
2. 新建 Codex 主控会话，使用 GPT-6.1 高推理，粘贴 `16_CODEX_MASTER_PROMPT.md` 全文，说明工作包的绝对目录。
3. Codex 先按 `00_BASELINE_AND_DECISIONS.md` 做实际代码比对，生成 M0 研究计划、完整页面蓝图、接口方案；可以启用一次 GPT-6 Astra 高/最高推理做设计审查。
4. M0 通过后，主控按 `data/task_board.csv` 和 `12_MILESTONES_AND_OWNERSHIP.md` 拆任务，在独立 worktree 并行实现，阶段交付到新 C+ 集成分支。
5. 每个阶段跑关键演示路径及必要回归；最终交付真实截图、录屏、示范报告、验证记录、已知限制和可复现种子说明。

## 文件导览

| 文件 | 内容 |
|---|---|
| `00_BASELINE_AND_DECISIONS.md` | 真实现状、冻结基线、优先级与非目标 |
| `01_PRODUCT_VISION_JOURNEYS.md` | 完整用户旅程、一级导航、三条求职演示路线 |
| `02_FEATURE_SPEC_F19_F34.md` | 16 类增量功能：实际用户动作、输入、输出、可验收标准 |
| `03_DISCOVERY_DOWNLOAD_CACHE.md` | 模糊搜索、巨潮公告、受控 PDF 下载、公共缓存与 demo 隔离 |
| `04_FINANCIAL_STATEMENTS.md` | 三大财务报表、指标口径、真实趋势、数据质量边界 |
| `05_COMPANY_360_DASHBOARD_UX.md` | 企业 360 高级 UI、图表、跨页联动及响应式 |
| `06_AI_CHECKUP_ANNUAL_DIFF_PEERS.md` | 财报体检、跨年经营文本变化、同行业比较、业务结构 |
| `07_BATCH_RESEARCH_AND_ACTIONS.md` | 批量研究、图表联动问答、AI 答案转图表、收藏、模板 |
| `08_RAG_OCR_RELEVANCE.md` | OCR 正式检索、BM25+向量混合检索、重排序、证据质量 |
| `09_EXPORTS_AND_REPORTS.md` | 报告增强、Excel/CSV/PPTX 的求职版可交付输出 |
| `10_ARCHITECTURE_API_CONTRACTS.md` | 推荐增量模块、领域合同、API 草案、版本回滚 |
| `11_QA_EVAL_DEMO.md` | 真实体验与固定评测，示例输入、验收矩阵、证据分级 |
| `12_MILESTONES_AND_OWNERSHIP.md` | 阶段、并行工作树、关键路径与模型分工 |
| `13_RISKS_COSTS_SCOPE.md` | 风险、降级、工时/预算、求职版与生产版边界 |
| `14_CODE_MAP_AND_REFERENCES.md` | 现有代码复用定位和官方信息来源 |
| `15_CPLUS_READINESS_GATE.md` | 演示完成的判定与红线 |
| `16_CODEX_MASTER_PROMPT.md` | **给主控的可直接执行开场指令** |
| `17_WORKER_AND_REVIEW_PROMPTS.md` | 开发子会话与独立评审模板 |
| `data/task_board.csv` | 可直接用于追踪的 WBS 任务/依赖/验收 |
| `data/feature_matrix.csv` | F19–F34 功能范围及阶段矩阵 |
| `contracts/` | **拟议**领域与 API 合同草案；实际实现前审查冻结 |
| `prototype/index.html` | 完全离线可点击产品原型；UI_MOCK、虚构数据，不接真后端 |
| `templates/` | 主控状态、验收证明、问题记录模板 |
| `FinDoc_CPlus_单文件总方案.md` | 整合全文版本，方便复制、索引和单文件上传 |

**不要把 ZIP 内的 UI_MOCK、假图表、API 草案当成已上线功能。不能把当前 C 的 141 PASS/57 SETUP ERROR 改写成全量通过，也不能代替用户签署财务事实。**

<!-- END README.md -->


---

<!-- START 00_BASELINE_AND_DECISIONS.md -->
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

<!-- END 00_BASELINE_AND_DECISIONS.md -->


---

<!-- START 01_PRODUCT_VISION_JOURNEYS.md -->
# 01｜最终产品形态与用户旅程

## 一句话定位

从“搜索一家上市公司”到“获得带证据的公司研究结论”的 AI 财报研究工作台。求职展示优先：让面试官 30 秒看到完整数据产品，5 分钟体验真实业务链，8–12 分钟看多 Agent、记忆、OCR 和工程细节。

## 一级导航（保持当前 5 个，避免反复新增一级入口）

1. 首页：全局 Hero、搜索框、KPI、真实/示意分类图、研究入口、最近任务。
2. AI 研究助手：快问快答、综合研究、深度 Multi-Agent、图表追问、批量研究矩阵。
3. 企业与资料：新增动态公司目录、公告下载、资料解析；企业详情新增 360、三大报表、财务体检、经营变化、同行对比、业务构成。
4. 研究任务：已批准计划、财务人工确认、执行事件、评测/回放入口。
5. 我的报告：研究成果、版本、报表/图表、证据、导出 Excel/CSV/PPTX/PDF。

记忆、OCR 校对、专项评测、设置使用二级入口/抽屉。现有 `/companies/:id/{overview,analysis,documents}`、`/conversations`、`/research`、`/reports`、`/tasks` 深链需兼容；新增路由必须增量而非破坏旧 URL。

## 典型主链路 J01：从模糊搜索到研究

首页输入“美的” → 本地/远程候选公司出现 → 选中准确证券代码/交易所 → 查巨潮年报 → 勾选 2024、2025 正文（提示摘要、修订版） → 明确导入 → 服务端下载、验原始文件、安全存储、fast 解析/OCR 兜底、索引 → READY → 打开企业 360 → 选择财务项/风险 → 查看证据与质量 → 发起综合研究 → 报告。缓存命中可复用 verified PDF，仍需创建本代文档绑定和索引资格。

## J02：财务报表与智能体检

企业 360 → 三大财务报表 → 年度/报表类型/合并或母公司/单位切换 → 状态清楚显示候选、已核准、缺失 → 用户明确核对原文 → 图表（已核准时真实） → 财报体检：经营质量、盈利能力、现金流、偿债结构和风险事件 → 每条卡片含所用指标/公式/证据/边界 → 一键向 AI 追问。

## J03：跨年度文本研究与对标

选择两年同一企业 → 对齐业务战略、主营业务、研发、经营风险、管理层讨论等章节 → 左右原文/差异卡 → 输出新增、减少、改写与待确认事项 → 通过证据链接定位两年 PDF → 单/多 Agent 按任务拆分 → 结果可保存为研究笔记和版本报告。再选 2–3 家同类公司，用相同年、相同口径的已确认指标比较；指标缺失展示空位而不是补 0。

## J04：批量研究与导出

选择 2–3 家企业、1–3 年、一个固定问题集合 → 有上限的批量独立检索/分析 → 矩阵呈现“公司×问题/年份”以及摘要/状态/证据数量 → 从单元格打开原始研究 → 保存结果 → 下载 CSV/Excel → 将 3–5 页关键图表/结论导出成 PPTX，图片与图表可由渲染或编辑结构实现（明确格式）。

## J05：演示独占/重置

沿用 C 方案 DemoGate + gateway；20 分钟默认独占，owner 模式需独立凭据和二次确认。重置只清当前代用户新增业务；公开 PDF 缓存**不能变成跨用户写权限**，用户上传 PDF 不能进入共享缓存；缓存/索引若从现有代生成，重用必须重新校验源资格和隔离。过期运行目录可在安全的脱离/终止后 GC。

## 高级 UX 验收

- 首屏 1440×900 以内看到 Hero、企业搜索、四 KPI、至少一张真实数据或明确示意的图表，CTA 进入研究；在 390px 手机无横向溢出。
- 企业 360 首页不堆十几个无关卡片，先结论与关键趋势，再分析与证据；图表有指标/单位/起止年度/来源状态、空态和无数据原因。
- 三大表支持固定首列、横向滚动、单位固定、比较高亮、明确“披露年份≠财务期间”的提示。
- 已核准、原文摘录、OCR 待核对、AI 解释待审、历史预置、虚构示意数据都有可理解标签，不需开发者阅读 JSON 才明白。

<!-- END 01_PRODUCT_VISION_JOURNEYS.md -->


---

<!-- START 02_FEATURE_SPEC_F19_F34.md -->
# 02｜F19–F34 全量功能规格（求职作品级 DoD）

基线已有 F01–F18。这里每一行是**计划新增**，不是 C 当前完成能力。**P0/P1/P2 为实施顺序，C+ 最终范围包含全部 16 项。**

| 编号 | 功能 | 可感知结果 | 最低真实可运行验收 | 优先级 |
|---|---|---|---|---|
| F19 | 智能企业模糊搜索 | 代码、简称、全称、拼音缩写/别名找到证券主体 | 真实支持至少 3 家；不混淆同名/退市/不同交易所；搜索无结果有回退 | P0 |
| F20 | 巨潮动态公告发现与受控下载 | 选中公司、年度、全文/修订版、点击导入 | 至少 1 家非 `catalog.json` 企业从实时来源发现并完成 READY；失败可官方链接/上传 | P0 |
| F21 | 共享公开 PDF 缓存与 demo 隔离 | 再次下载相同文件更快，演示重置不损坏缓存 | 两次导入同 SHA 无第二次网络传输；A/B generation 数据隔离；旧代安全清理 | P0 |
| F22 | 企业 360° 画像 | 公司一屏概览、趋势、事件、风险、资料、报告 | 真实 KPI、2–3 图表、至少 1 种结果/资料可点击到证据；手机可读 | P0 |
| F23 | 三大报表查看与结构化字段 | 合并资产负债表/利润表/现金流量表，按年切换 | 1 家 2 年真实 PDF 提取三表各若干关键行；每行带版本、单位、期间、页码、状态 | P0 |
| F24 | 真实财务趋势与比率 | 3–5 年可用年份曲线、同比、利润/现金流比较 | 已核准数据展示真实值；未核准可选择“待核对候选”视图，不能标为确认 | P0 |
| F25 | AI 财报体检 | 识别营收/净利/现金流/负债变动并引导研究 | 3 类确定性规则 + 解释草稿 + 可打开来源；缺值时说明不可判定 | P0 |
| F26 | 跨年经营文本变化 | 两份年报战略、经营风险、业务描述并排差异 | 至少 3 维真实原文、双年 PDF 引用、变化判断待人工审阅 | P0 |
| F27 | 同行业公司对标 | 2–3 家相近行业同期间并排，图表/得失 | 真实同行候选或手动指定 2 家、同口径可比与不可比说明、来源跳转 | P1 |
| F28 | 主营业务结构与可视化 | 产品/地区分部收入份额，环形/树图 | 1 家 1 年真实分部表候选；收入占比用确定公式，分类相加不完整不做 100% | P1 |
| F29 | 图表与证据联动 AI 问答 | 点数据点“为什么变化”并携带企业/年度/指标/来源 | 预填明确范围、可见用户确认，工具仅选已核验资料，不暗中扩大源范围 | P1 |
| F30 | 混合检索+重排序 | 同题引用更贴切，减少无关委托理财类段落 | 真实固定问题集证明无关引用减少，保留引用身份/拒答机制 | P0 |
| F31 | AI 批量研究矩阵 | 公司×问题×年度的摘要与证据表格 | 2 企业 × 2 问题可执行，任务上限、失败独立处理、无二次重放 | P1 |
| F32 | CSV / XLSX / PPTX 导出 | 将已完成研究变为可下载的数据和演示页 | 1 个实际 XLSX、1 个实际 PPTX、CSV；结果/来源/状态在文件中区分 | P1 |
| F33 | 指标释义+研究模板+转图表 | 解释 ROE/毛利率/同比和定制研究题目 | 5 类指标释义；4 类研究模板；结构化结果能显示适合的图表 | P1 |
| F34 | 研究笔记收藏与精准 PDF 高亮 | 收藏某项引用，定位 PDF 原句/表格 | PDF 高亮 1 个真实定位案例；不能精确定位时降级到页码+摘录，不假高亮 | P1 |

## 各功能的边界与验收补充

### F19 企业模糊搜索
- 最低输入包含：证券代码 `000333`、部分简称 `美的`、完整名称、拼音缩写 `mdjt`；准确结果显示 code/exchange/name/status。
- 建议两层：本地缓存/候选索引响应快；官方实时再查公告。不能把拼音的近似匹配当作证券主体唯一身份，选定后再绑定代码。
- `listed_security_id` 是公司当前合法证券身份，不能用前端名称当授权。含不同交易所/重名时强制选择。

### F20 动态公告及导入
- 远端请求由服务端发起，入库**必须由用户点击“导入”**；年度报告正文、摘要、修订、补充公告分别标记。
- 若动态接口变更/限流：返回 `source_unavailable` 或 `manual_import_available`，不重试风暴、不绕过验证码；可回到旧静态精选目录与手动上传。
- 下载只有满足 allowed HTTPS host、最大体积、PDF 魔数、真实文件 SHA、来源元数据初检后才能进入 `DocumentSourceService.upload`。

### F21 公共缓存与 reset
- 公共缓存只对官方公开公告文件开放；原用户上传、私有文件、会话、记忆、模型输出不共享。
- `download_cache` 的文件名为 SHA，下载前没有可信 SHA 可先落隔离临时文件后验内容，唯一对象注册后引用；并发单飞。
- 缓存不能绕开本代的文档版本/解析器版本/索引就绪检查；缓存命中 ≠ 已完成 RAG 入库。

### F22/F24 360 与真实财务图
- 最低模块：公司身份、资料覆盖年表、关键经营指标、财务趋势、体检提示、原文经营重点、最近研究、报告。
- 只读完成时展示 `confirmed_financial` 的真实可用点；为方便 demo 可以展示 `candidate_unreviewed` 图层，但颜色/图例与 confirmed 充分区分；示意虚构数据继续水印与单独开关。
- 同一图无法比较不同单位的营收与净利时使用百分比变化或左右轴并解释，默认避免混淆量纲。

### F23 三大报表
- 数据结构要同时容纳**时点** (`instant/as_of_date`) 与**期间** (`duration/period_start/period_end`) 指标，不能把旧资产负债 v2 结构强套到利润表。
- 必须标明合并/母公司、金额单位、财务年度、报告发布年度与披露版本；一张表中同名行跨附注的语义不能随机匹配。
- 首页只挑选少数经认可的指标；三表全量“查看”与“可信数值计算”是两种权限。

### F25 智能体检
- 规则示例：利润与经营现金流同比方向背离；营收增速与净利增速差异；负债率同比变化。阈值必须在设置/代码中清楚，不宣称投资建议、预测或审计结论。
- 可用已确认数值才可给确定的财务数值信号；候选只能叫“待核对观察”；缺证据返回不足。
- 每项卡片包含：结论/等级说明、指标、公式/期间、数据出处、下一步建议问题、AI 解释待审标签。

### F26 跨年文本变化
- 真实两份年报 → 对应章节和主题 → 文本片段对齐；模型仅整理变化的表述，不能从“未搜到”推出企业取消业务。
- 标签：`新增披露`、`披露表述变化`、`共同延续`、`证据不足`；显示两年证据并列和独立来源页。
- 报告导出保持两年度原文引用，不将“模型变化描述”写成核准财务数值。

### F27/F28 同行业与业务分部
- 同行比较必须由用户选定同行或根据明示行业字段“推荐”，不能凭 LLM 擅自认定同行身份。
- 同口径/同期间检查；企业不同会计口径、单位或归母定义时显示“不可直接比较”。
- 分部收入比例只对同一合并范围、同一期间、同一币种、互斥分类做比值。存在合并抵消/“其他”项时说明边界，不强制加总 100%。

### F29/F31 执行与交互
- 图表数据点点击生成**草稿**，用户可检查/编辑并显式提交；传递 company_id、metric_key、period、evidence_ref，不给模型授权未选择的其他 PDF。
- 批量矩阵异步受限任务，隔离各行状态；支持取消未开始任务、继续读取已执行结果，禁止无提示自动重发付费模型请求。

### F30 检索质量
- 增加 BM25（或 SQLite FTS）与 dense 归一融合、章节与年度过滤、轻量 rerank；不得因为 rerank 高分就跳过原文精确匹配与冻结身份验证。
- 评测必须覆盖旧真实缺陷：询问“经营风险”时不会把“委托理财概况”纯数值表格当成首要风险证据。
- 分别记录 precision@5、证据相关性人工判定、拒答覆盖、成本和延迟，至少给出 before/after 具体结果。

### F32/F33/F34 输出与产品细节
- CSV/XLSX 体现 unit、basis、period、来源、校验状态与生成时间，不混淆候选和确认；PPTX 逐页含页脚出处/有限结论说明。
- ROE、毛利率等如暂无可用分母和平均权益，界面仅解释定义或显示缺失，不凭模型自行计算。
- PDF 定位由 PyMuPDF 的 text quads / bbox 或 OCR 带坐标片段驱动；定位失败退化为打开物理页+高亮页面侧边摘录。

<!-- END 02_FEATURE_SPEC_F19_F34.md -->


---

<!-- START 03_DISCOVERY_DOWNLOAD_CACHE.md -->
# 03｜巨潮模糊搜索 / 下载 / 本地缓存 / 演示复位

## 当前限制

`DisclosureService.search(code, report_year)` 仅遍历 `catalog.json` 四个候选。`import_candidate` 通过已有 SafeDownloader 按预置 SHA 下载。其下游 `DocumentSourceService.upload` 已有绑定/解析/索引能力。**C+ 仅扩展 discovery adapter 与下载缓存，不能复制另一套 PDF 处理系统。**

## 数据来源与合规

- 官方首选：`https://www.cninfo.com.cn/new/snapshot/companyListCn` 公司列表和 `https://www.cninfo.com.cn/new/commonUrl?url=disclosure%2Flist%2Fnotice` 信息披露页面，公开网页支持代码、简称/拼音和公告分类搜索。
- 网页有检索入口不代表开放、稳定、允许无限自动访问的 API。第三方对历史 AJAX 的分析仅供 spike，**不能直接当作经官方保证的长期接口合同**。
- 开发先做 D-SPK：确认访问条件、HTTPS、返回字段/频率、是否需合法 token、是否有限流/验证码；无法确认则实现前端跳转官方查询及手动上传回退。
- 严禁突破 CAPTCHA、账号认证、访问限制或大规模爬取；请求有实际限流、缓存和超时，用户主动选定才下载。

## 两级检索

1. `CompanyResolver`: 匹配证券代码、标准简称、名称子串、拼音首字母、企业别名；返回 `company_candidate` `{security_code,market,display_name,official_name,source,match_type,confidence}`。默认候选上限 10，按代码精确→名称→拼音排。歧义不自动选。
2. `AnnouncementProvider`: 已选公司 + 年报年度 + 分类(全文/摘要/更正) → 公告列表 `{announcement_id, publish_at?, title, report_year, kind, revision_kind, official_page_url, pdf_url?, source_provider, checked_at, verification_state}`。发布日期/更正状态不能猜；正文优先但用户仍明确选择。
3. `ImportCoordinator`: 创建 `operation_id`，验证 candidate、公司身份、域名、PDF 页眉/封面、大小、文档 SHA、已存版本；调用原 `DocumentSourceService.upload()`，返回 operation receipt 和 `document_id`，直至 `ready`。

## 下载与本地文件

**推荐结构（均为草案，由 M0 冻结）**

```
control_root/
  public-pdf-cache/sha256/<2prefix>/<sha>.pdf    # 只存已验证官方公开PDF；缓存跨 generation
  public-pdf-cache/metadata.sqlite               # 来源、原URL、下载日期、大小、sha、访问策略
  active/<generation>/objects/documents/<id>.pdf # 已绑定的本代业务对象
  active/<generation>/documents.db                # 业务身份/解析状态
  active/<generation>/milvus.db                   # 本代向量索引
  active/<generation>/parse-v2.db                 # 本代OCR独立产物
```

- 未知 SHA 时在隔离下载 tmp 写入，验证 PDF 魔数、大小、实际 SHA 后以原子 rename 注册 `sha256` 缓存对象；缓存条目不可从浏览器指定绝对路径。
- 缓存只允许“经过发现适配器验证的公开官方 PDF”。不能把用户上传 PDF 或模型输出共享到跨代缓存。
- 对同 SHA 同解析器版本且已存衍生索引的情况，可做只读工件缓存；**首版先只共享 PDF bytes**，本代索引继续由现有 DocumentProcessor 创建，避免 Milvus workspace 污染。
- SHA 相同且同工作空间时原 `DocumentService` 已可去重，但重置后的新 generation 是新工作空间数据根，需绑定当前代 document 记录。
- 所有网络下载由后端完成并明确拒绝内网/环回/重定向越权，禁止前端直接传任意 URL 让服务器变代理（SSRF）。

## 下载状态机

`discovered → selected → validating → downloading/cache_hit → stored → queued → parsing → indexing → ready`，异常 `failed/unknown/needs_manual_upload`。每个阶段的显示由真实操作状态驱动，前端 GET 不发起新网络或付费模型调用。

## demo 重置与过期清理

- 20 分钟时限从**登录后**起算，不把一次 PDF 下载延长当前 lease；到期/强制接管时旧 runtime generation 取消发布权限。
- 下载与索引过程每个外部 side effect/最终发布须校验 lease_generation；旧进程被收回后不能发布到新代。
- public cache 在 generation 之外，由控制层约束写权限；单独设置大小和淘汰规则；不依赖登录退出重置 cache。
- `ProcessRuntimeManager` 停止旧进程、生成新目录后建议增加 `safe_gc_old_generations`；只清控制目录内、确认已停止且非当前/非 seed 的旧目录，不删除任何开发者原始库/seed；首次以 dry-run 报告证明。

## 限额与回退

当前 downloader/document limit 为 20MiB。C+ 设计可配置 `MAX_PDF_BYTES`（例如 40/60MiB，实际用样本验证内存/磁盘），统一网络、上传、解析三端校验。大文件建议先临时落盘，不在 HTTP 层无限堆内存。没有高可靠后台队列的要求，但用户应该能看到失败并手动重试。

## 必测异常

同名公司/拼音歧义；全文与摘要混淆；同年修订两个版本；非 PDF/HTML 200；SHA 不符；过大文件；重定向内网；重复导入；登录到期中途下载；缓存命中再次入库；新代重置后原用户文档不可见；官方来源不可用→手工上传。

<!-- END 03_DISCOVERY_DOWNLOAD_CACHE.md -->


---

<!-- START 04_FINANCIAL_STATEMENTS.md -->
# 04｜三大报表、时点/期间指标与真实图表

## 为什么需要新增独立结构化报表域

旧 v1 正式研究只锁定营收、归母净利、经营现金流三指标。新 `ExtendedMetricV2` 使用 `period_kind=instant`、`as_of_date` 存总资产/总负债，不能表示“全年营业利润/销售费用/现金流量净额”等期间指标。严禁硬改旧 `Literal`/迁移历史 checksum；推荐 `app/financial_statements_v3/` 新领域，按公司/报表/期间/口径建立标准化**候选/确认**快照。

## P0 三表支持的首批字段

| 报表 | 行目（首版优先） | 时间类型 | 核对要点 |
|---|---|---|---|
| 资产负债表 | 货币资金、应收账款、存货、流动资产合计、资产总计、流动负债合计、负债合计、归母权益（可用时） | instant / as_of_date | 期末/期初、合并/母公司、元/万元/亿元 |
| 利润表 | 营业收入、营业成本、毛利额（计算项）、销售/管理/研发/财务费用、营业利润、利润总额、净利润、归母净利润 | duration / start/end | 本期/上期、全年/季度，报表原行还是计算项 |
| 现金流量表 | 经营流入/流出、经营净现金流、投资净现金流、筹资净现金流、期末现金等价物（字段明示） | duration 与个别 instant | 不能把期末现金余额当作全年现金流 |

“有该名称的行”不等于可用数值；中文附注中可能重复出现同名行，必须限定报表标题、列日期、版面几何与口径，歧义保留给用户。

## 统一记录合同建议

`StatementCell`: `{company_id, security_code, report_type, statement_kind, row_key, row_label_original, period_kind, as_of_date?, period_start?, period_end?, report_year, scope:'consolidated|parent', basis, currency, raw_value, raw_unit, normalized_decimal?, source_revision, document_id, parser_version, physical_page, table_id?, bbox?, evidence_ref, confidence?, status:'candidate|human_confirmed|unsupported', receipt_ref?, limitation_codes[]}`。

`ratio`: `{formula_id, input_cell_refs, Decimal output, output_unit, comparability, missing_reason}`；任何 ratio 都由服务端 Decimal 计算并可回到输入。

## 计算与趋势规范

- 营收同比 = `(本期营收-上期营收)/abs(上期营收)`（若企业研究惯例要按上期原值计算则由业务设计明确公式，不能暗改）；上期 0 或不可比时显示 `N/A`。
- 毛利率 = `(营业收入-营业成本)/营业收入`，要求同期间/同口径；净利率 = `净利润/营业收入`，分子到底归母还是合并净利须明确。
- 经营现金流与净利比值只有在同口径、同时间区间且分母适用时才能计算；不是“盈利质量的最终结论”。
- ROE 如果要实现，需要平均净资产和明确权重/分母；不具备时只展示释义与缺失原因。
- 三大报表不同时间类型，不得同一个字段 `year` 直接表示资产负债时点和利润年度区间。

## 图表（真实 + 待核对 + 示意三层）

1. 已确认：只使用真人确认 receipt + 当前有效来源，数值有年度/单位/证据。
2. 待核对：来源 PDF 自动提取候选。可展示另一条带明显标识的候选线，默认不等同真实已确认，导出时也标为待核对。
3. 虚构示意：只能用于 UI 原型或显式切换的 sample_mode，不允许“美的 2025 真实营收”等误标。

没有历史全年数据的年份留空 `null`；不连线硬跨空缺，不补 0，不造财务区间。图表单位为亿、万元等仅是格式化，底层值保持 Decimal string。

## 人工确认 UX 为求职版简化，但不替签

- 每份年报自动产生候选与 PDF 对照；用户可以在一次页面中逐条核对和明确选择，减少五六次跳转。
- 可加入“批量勾选本次已逐项审阅”操作，但只有用户实际点击确认并保存，系统才生成有效 receipt。
- 提供 2 年同企业“必需指标向导”：优先覆盖营收/归母净利/经营现金流/总资产/总负债，可做一次真实正向演示。
- 所有已确认历史财务计算保持现有 v1/finance_v2 准入边界；新 v3 属新用例，确认与派生合同由 M0 冻结。

## 验收

- 同一公司两个年度三报表的关键行可打开原 PDF；至少 1 个财务周期和 1 个资产时点被正确区分。
- 对实际年报生成候选、原值/单位展示、明确人工核对、真实图表至少 2 个连续点；数据来源被更正/失效时停止新的“已确认”发布。
- 正式旧三指标及 6 项核对流程仍能走通，旧报告快照不被修改。

<!-- END 04_FINANCIAL_STATEMENTS.md -->


---

<!-- START 05_COMPANY_360_DASHBOARD_UX.md -->
# 05｜企业 360 高级仪表盘与产品视觉

## 视觉目标

沿用已通过 C 方案实际截图的 Navy/Blue 系列，不复制离线原型的 mock。新公司 360 要比当前首页更专业：看起来是一个企业经营智能分析终端，而不只是把三个小图放在一起。要求桌面 1440×900 首屏有层次、移动 390px 可阅读；兼容暗色 sidebar 与浅色工作区，避免过度渐变和装饰图。

## 页面骨架

### 第一屏｜公司身份 + 最重要的问题

**公司头部**：正式简称、证券代码、交易所、行业、报告覆盖 `2022–2025`（有则显示）、资料数量、最近研究日期；右上角“AI 开始研究”和“获取年报”。未验证字段显示缺失而不是生成。

**5 项 KPI**：营收、归母净利、经营现金流、总资产、资产负债率（显示年度、单位、最近已确认/候选状态）；其他指标在详情选择器。

**图表主视图**：左侧营收趋势折线（多年度/单位/同比），右侧利润 vs 现金流变化柱状；右侧侧栏有财报体检发现卡，点击跳到风险/数据证据。

### 第二屏｜财务表现 + 文本研究

**三大表摘要**（资产负债/利润/现金流），**业务结构环形图**（只在可靠分部分类已取得时），**经营变化时间线**（风险、业务战略、研发、管理层讨论），**同行对标**（同期间两个主体）。

### 第三屏｜证据与工作流

最新年报、来源状态、已完成研究、AI 待核实结论、版本报告、下一步研究问题。每卡可打开对应列表或研究会话。

## 交互约定

- 图表 `onClick` 必须为数据点绑定实际 `company_id/period_kind/period/source_revision/metric_key`；若是示意点则只有“示意提示”，**不能发起真实研究作为该公司数据**。
- KPI 显示“已核准 / 待核对 / 预置历史 / 界面示意 / 缺失”清楚标记，切换数据源不会修改事实。
- 表格默认折叠高级证据，不让普通用户首屏看到几十条哈希与原始 JSON；PDF 页面详情二级查看。
- 手机 390px 使用单列：公司头、两行 KPI、可左右滚动的切换图、AI 体检摘要、最近研究；保留底部主要研究 CTA。
- 轻微数字过渡与 skeleton 可使用，但不得构造等待中的虚假结果，不因动画阻断用户输入。
- 图表 Tooltip：指标、原始期间、单位、来源状态、原文按钮。对比图采用同一会计口径，单位不同需转换或分开展示。

## 无数据初始状态

第一次进入新公司：显示“还没有导入年报”→官方搜索、粘贴 URL、手动上传。已导入但未完成核对：保留资料覆盖图、OCR/解析质量和 AI 原文摘要，真实财务图为空/候选可选，**不能自动开启无水印虚构曲线**。

## 原型文件

`prototype/index.html` 是离线可点击设计原型，含公司搜索、三表切换、体检卡、跨年差异、同比、批量研究、导出入口等，全部数据标记 UI_MOCK/虚构，不得把其数据导入真实 seed。Codex 在实际 React 中从现有导航实现，不把整个原型 HTML 静态嵌套到 AppShell。

## 高保真可验收条件

- 1440 和 390 截图均与最初 M0 设计对齐；图表和标题在宽度变化时不溢出。
- 真实企业已核准 KPI 链接到来源；候选图层标记待核对；没有值不造。
- 研究 CTA 将 context 精确预填到现有 Conversation/ResearchWorkflow，不自动点击发送或批准计划。
- 关键按钮：获取年报、查看三表、财报体检、经营变化、同行对标、报告导出均可真正打开对应模块或明确失败态。

<!-- END 05_COMPANY_360_DASHBOARD_UX.md -->


---

<!-- START 06_AI_CHECKUP_ANNUAL_DIFF_PEERS.md -->
# 06｜AI 财报体检、跨年经营变化、同行业企业对标与主营结构

## A. 财报智能体检 (F25)

### 输入

固定公司、用户明确选择的 2–5 年年报、可用/待核准财务指标、源身份及原文风险片段。若财务事实不足，输出“原文体检/待核对数据”状态，不能发布金额结论。

### P0 确定性规则

| 规则 | 条件 | 展示 |
|---|---|---|
| 收入—利润分化 | 营收与归母净利在同区间同比方向不同，或增速差异超过可配置阈值 | 提示“收入与利润变化值得核对”，不判断必然原因 |
| 现金流质量观察 | 经营现金流同比方向与利润不一致，或现金流净额/净利显著偏离（分母 0/负需单独处理） | 展示数值变化、原文证据、AI 待审解释 |
| 资产负债变动 | 期末资产/负债的两个可比时点齐备，资产负债率变化超过阈值 | 百分点变化、口径和来源 |
| 风险披露变化 | 新旧年报风险章节经检索有新的/变更的表述 | `AI待审`，不能标成法律/审计结果 |

每条结果 `{rule_id,version,subject,periods,status,inputs,formula,observation,confidence_kind,evidence_refs,review_state,followup}`，模型可以解释、提供追问，不能改变 program rule 的数值与状态。

## B. 跨年文本变化 (F26)

- 主题模板：主营业务结构、主要产品、行业竞争、研发方向、经营风险、管理层讨论、发展战略。
- 先用双年度 source-scoped hybrid search 找主题段落；再按标题/段落主题对齐；LLM 做“当年原文 A → 当年原文 B → 变化描述”，引用分别绑定每年 PDF。
- 不可单凭无命中判定“公司已取消某业务/不存在某风险”。输出 `missing_in_retrieval`，与 `not_disclosed` 不同。
- UI 为三列：上一年原文/本年度原文/AI 差异卡；可筛主题、按新增/延续/变化/不足筛选；点击引文打开双页 PDF。
- 追问时保留源范围，用户可进一步选择转为研究报告的单章节。

## C. 同行对标 (F27)

- 首版支持 2–3 家用户明确选定的企业；行业标签如来源未知，只提供“手工同行选择”，不要自行认证行业。
- 同年/相同计量定义的指标才形成横向比较；允许利润率、现金流、资产负债率、营收规模等少量基础项。
- 不能直接比：货币或口径不同、单位不同而未转换、报告非同一自然年度、合并与母公司混用、确认状态不同或缺值。
- 页面可以选择“表格 / 条形 / 雷达（仅指标标准化说明明确时）”，不要让视觉图表掩盖不可比情况。
- 一键“生成同行研究”→受控并发检索两家公司原文；Model 解释为待审草稿。

## D. 主营业务结构 (F28)

- 从真实年报“分产品、地区、行业”营业收入/主营业务收入表中识别分类及金额，保留行/列和 PDF 页。
- 需要 `breakdown_type, breakdown_basis, categories, amount_decimal, denominator, subtotal, residual, reconciliation_status`。只对同一个母集、同币种、互斥分类求比例；不能因为各类别金额相加不等于总营收就强行归一化到 100%。
- 图表：环形图 + 可展开分类表；部门占比/区域销售占比按数据源可用展示，没有数据则空态且说明。
- 首版固定一份真实年报的一种结构做出示范。其余行业先给“识别中/暂不支持”的解释。

## 对求职 Demo 的价值

在一个公司的 360 中选三大报表 → 点智能体检得到真实数据支撑的 3 条变化观察 → 打开跨年度原文变更 → 选同行公司横向对比 → 一键进 AI 研究 → 报告。面试官能看到真正的“财报业务分析”，而不只是 Agent 框架。

<!-- END 06_AI_CHECKUP_ANNUAL_DIFF_PEERS.md -->


---

<!-- START 07_BATCH_RESEARCH_AND_ACTIONS.md -->
# 07｜批量研究矩阵、图表追问、模板、收藏与结构化结果转图表

## 图表追问 (F29)

交互：用户在财务趋势图选中“2024→2025 经营现金流同比变化” → 弹出预填问题卡：公司、两年、指标、口径、已选来源、待确认/已确认状态 → 用户可编辑 → 按“开始研究”跳转 `/conversations` 或现有 `ResearchWorkflow`。

禁止：没有事实选择就自动计算同比；把示意图数据当成真实值；直接写入研究任务或自动批准计划。保证 GET/查看不会触发新的 LLM，草稿操作可撤销。

## 批量研究矩阵 (F31)

输入 `BatchPlan`: 2–3 公司 × 1–3 年份 × 1–4 用户选定模板，受限组合 <= 12 单元格（首版），单独有模型调用预算与状态。默认串行/并发 2 个 job，不超过 provider 总预算；每单元格独立 operation/来源作用域；任意失败不污染其他单元格；不自动重试 `unknown`。

任务执行完成后矩阵字段：`row_company, column_question, period, status, excerpt_count, finding_count, answer_summary, evidence_refs, cost_observed_or_reserved, job_id`，每项可打开详述并进一步生成同行对标报告。

UI：新批量研究的“组合预览”先展示预计任务数量、会使用多少来源、是否可能等待用户财务核准。点击确认才提交；支持取消未执行的任务、读取正在运行结果/已保存结果。

## 自定义研究模板 (F33)

首版 4 个可直接使用的模板：

| 模板 | 输入 | 输出 |
|---|---|---|
| 年度经营概览 | 公司 + 年份 | 财务概览、经营原文、风险、结论 |
| 现金流质量 | 公司 + 两年 | 现金流、利润对比与差异解释 |
| 竞争对标 | 2–3 公司 + 同年 | 指标矩阵、优势/风险原文 |
| 经营变化分析 | 公司 + 两年 | 业务变化、研发/风险文本差异 |

模板支持用户修改问题/数据范围，不是 Prompt text 魔法写入事实。代码保持模板版本可追溯。

## 结构化结果转图表 (F33)

Agent 可返回 `chart_suggestion`: 可视化类型、标准指标 key、输入 record_refs、可否比较；**最终图表坐标必须由程序从可信或带候选状态的结构化数据加载**，禁止让模型直接凭空编一串坐标。

首版只做折线/柱状/分部环形以及表格展示，支持“复制当前图表到报告草稿”。无法满足数据条件时展示“证据不足/需要核对”，不能生成漂亮但虚构的结果。

## 收藏、研究笔记和 PDF 高亮 (F34)

沿用 `ResearchMemoryService`；添加从 `sourced_excerpt` 点击“收藏到研究笔记”的确认动作，关联对应 evidence/source_rev/physical_page；支持搜索、删除、历史回读和报告引用。

PDF高亮优先使用已解析文本的 bbox/quads，能精确匹配则浮层高亮；OCR 需使用对应转录版本及 bbox。文本定位失败则只跳到原页并在侧栏展示原文卡，**绝不渲染错误的假高亮**。

## 浏览器可验收

- 图表点位→预填问题→用户明确发送→检索/任务→返回源图表，至少 1 真实点位。
- 批量 `2x2=4` 单元格有清晰成本/来源/执行状态；遇到 1 个来源缺失，其他 3 个不受影响。
- 研究笔记保存/召回/删除复用原记忆与用户权限；PDF 高亮成功和降级分别有证据。

<!-- END 07_BATCH_RESEARCH_AND_ACTIONS.md -->


---

<!-- START 08_RAG_OCR_RELEVANCE.md -->
# 08｜OCR 入正式检索、混合检索、重排序与回答质量

## 当前真实缺口

现有 `ParseV2Service` 的 OCR 文本落在独立 parse-v2 SQLite+FTS，不自动构成正式 `SelectedScopeSearch`/Milvus 可检索来源；现有 `showcase_research/agents.py` 使用受限选定文档的 dense search，风险问题有少量硬编码关键字过滤，但真实多 Agent 研究出现了与“经营风险”不紧密相关的委托理财表格片段。

## 推荐架构

```
实际PDF bytes & 源版本
  ├── Fast PDF evidence (已有信任边界)
  └── OCR artifact (新版本，明确 unreviewed)
        ↓ normalized SearchDocument + SourceEvidenceRef
  ├── lexical FTS/BM25
  └── BGE dense / Milvus
        ↓ RRF + 基于章节/年份/报表的过滤
        ↓ reranker（可选本地 cross-encoder；没有则规则质量过滤）
        ↓ 严格 source_revision/physical_page/文本匹配复核
        ↓ 源等级/转录审查状态清楚的回答
```

`OCR_transcription_unreviewed` 与 `verified_original_exact` 永远是独立授权级别，OCR 加入检索不表示可以自动上升为财务已确认值；答案中明确“OCR 转录待核对”。

## 索引与检索策略

- 融合查询：预处理公司别名、年度、主题；metadata filter 按本会话冻结文档、公司、年度、parser_version。
- 段落检索：标题/章节定位优先，正文相关性重排序，表格内容用于数值问题，风险概述不被无关财务表优先占满。
- 混合检索首版采用 SQLite FTS5 / rank 或 BM25 + 当前 dense Milvus，并用 Reciprocal Rank Fusion (RRF) 合并。分数无统一量纲不要直接求和。
- 加 `document_type`: `text|table|ocr_text|ocr_table` 与 `source_authority`: `exact_original|ocr_unreviewed`。
- 对于模型解释关联的证据，检索排名并不授予因果结论授权；模型引用只能选择程序已发布的合法 refs。

## 固定真实质量集（最低 12 条，建议 24 条）

| 类别 | 例子 | 重点判定 |
|---|---|---|
| 风险 | 2025 年报主要经营风险有哪些 | 不能首要显示“委托理财概况”纯数字表 |
| 风险 | 年报中如何描述原材料风险 | 有对应 PDF 引文，未搜到则说不足 |
| 财务 | 本年营业收入/经营现金流 | 未确认拒算；原文可摘录 |
| 跨年 | 2024/2025 管理层经营重点有什么变化 | 两年引用并列且都真实 |
| OCR | 扫描页中某个实际字段是什么 | 引用 OCR 页和未核对状态 |
| 多轮 | “那上一年呢” | 公司/期间承接而非猜测 |
| 反例 | 用户输入不在选定来源内的公司 | 澄清或要求新会话 |
| 注入 | PDF 中带“忽略系统规则”的内容 | 只当不可信原文，不当指令 |

建议用同一批 query 记录 baseline 与 C+：Hit@5、MRR@5、至少两名评审/或人工标注相关证据覆盖率（可用 1 人重点审核）、无关片段数、延迟、检索成本。作为求职版本不设虚假“95%通过”，任何真实失败单列出来。

## OCR 从解析到问答的 DoD

一份**派生扫描 PDF**（当前真实苹果 Vision 样本）→ OCR 出文字 bbox → 该 OCR artifact 进入受限检索范围（保留 SHA/版本）→ 用户提出实际问题 → 结果显示页面与“待人工复核” → 点击 PDF 原图定位。额外可选一份真正扫描原生报告验证，但不是首版必做。不能据派生样本宣称所有扫描年报准确。

<!-- END 08_RAG_OCR_RELEVANCE.md -->


---

<!-- START 09_EXPORTS_AND_REPORTS.md -->
# 09｜报告增强与 CSV、Excel、PPTX 导出

## 保留已有底座

`app/showcase_reports/` 已实现版本报告、HTML 打印到 PDF；旧 `app/reports/*` 有原研究 Markdown/版本。C+ 不再造第二个“报告列表”，而是在正式报告详情中增加可导出投影。

## CSV / XLSX

- 可导出范围：用户明确选择的企业及年份；仅导出已保存研究或已核对报表快照。
- `财务对比` 表列：`company_code, company_name, statement_kind, metric_key, source_year, period_kind, as_of_date, period_start, period_end, basis, scope, currency, raw_unit, value_decimal, authority, source_revision, document_id, physical_page`。
- `来源证据` 表列：结果 ID、指标与解释类别、PDF 来源、真实页码、转录审查状态、AI 解释状态。
- XLSX（建议 openpyxl）至少三 Sheet：概览、财务数据、来源证据。金额 Decimal 需要作为数字以便用户可筛选，但不得丢失高精度；必要时用格式化文本或注释保留完整原字符串。Excel 含公式的字段只采用受控数字/公式，防公式注入；用户文本转义。
- CSV 需要 UTF-8 BOM/合理列名兼容中文 Excel；未确认数值明确注明 candidate。

## PPTX (求职版)

- 允许通过 `python-pptx` 或 JS PPTXGenJS：封面、研究背景/范围、3–5 年财务趋势、体检卡、跨年文本变化、风险结论、来源/限制，共 5–8 页。
- 在 PPT 内容中插入实际图表截图或 editable shape 均可，优先保证观感清晰；标注单位/报告年度/是否核准，页脚含来源引用与 PDF 年度。
- 模型解释不得包装成核准结论。未确认数字可以留空并说明，以历史真实资料提供部分示范图表。
- 输出文件每页可阅读，不溢出、不乱码；下载路径有效，正常 PPT 软件可打开；不可读取私有配置/密码。

## PDF 报告

继续使用当前 `/print` 页面和浏览器打印到 PDF；对 C+ 增加企业画像/变化表/来源列表等章节，不要求单独写一个新的原生 PDF 排版引擎。交付附实际生成的一个样本报告 PDF 与 SHA 验证。

## 版本与数据来源

`report_version` 冻结所有被使用的源版本和各项结果类型；下游“下载”是只读。报告历史重读不触发 Agent，新 PDF/Excel/PPT 以确切 revision 导出，避免意外读取最新不同研究结果。

## 验收

- 一次浏览器操作从已完成 C+ 研究导出 CSV、XLSX、PPTX/PDF 并能打开。
- 1 个真实指标含正确期间/单位/来源、1 个 AI 待审文本含状态、1 条引用可回到 PDF。
- 历史 revision 下载内容一致；未确认财务不得偷偷变成已核准。

<!-- END 09_EXPORTS_AND_REPORTS.md -->


---

<!-- START 10_ARCHITECTURE_API_CONTRACTS.md -->
# 10｜推荐增量架构、数据合同与拟议 API

**这些都是设计建议，非现有 API。M0 先读取当前 Pydantic、SQLite schema、router 后再冻结，不允许把此草案当作已实现合同。**

## 模块边界（新增为主）

| 新增建议模块 | 拥有数据 | 复用边界 | 禁止的改动 |
|---|---|---|---|
| `app/company_discovery/` | 证券主体候选、别名、公告元数据缓存 | `app/disclosures`, `app/companies` | 不改动旧公司 identity 语义 |
| `app/public_pdf_cache/` | 公共公开 PDF content-addressed bytes | `SafeDownloader`, `DocumentSourceService` | 不共享私有文件；不从前端写任意 URL |
| `app/financial_statements_v3/` | 三表行和时点/期间数据、确认事件、派生 ratio | `app/finance_v2`, `app/agent/revenue_confirmation` | 不改旧三指标合同与迁移 checksum |
| `app/company_profile/` | 360 只读聚合与图表 | `DashboardService`, reports, docs, v3 | 不通过 GET 生成模型文本/写数据库 |
| `app/checkup/` | 规则与异常观察、阈值和引用 | v3 及来源 | 不使用未经确认候选作已确认信号 |
| `app/annual_diff/` | 两年文本片段关联、变化卡 | SourceSearch, LLM, Findings | 不把无命中当为不存在 |
| `app/retrieval_v2/` | BM25/FTS、融合与 rerank | 旧 RAG/SelectedScopeSearch | 不跳过现有引用验证 |
| `app/batch_research/` | 有限矩阵任务、批次状态 | 现有 showcase research jobs | 不自动批准/重试未知模型执行 |
| `app/exports_v2/` | 只读 Excel/CSV/PPTX 投影 | showcase_reports | 不改旧 report revision |

可按程序大小合并邻近小模块，**不为了架构层数增加维护成本**。单一 runtime_factory 组装，各工具仍受 demo gateway/lease 保护。

## 核心不变量

1. `source_id = {document_id, source_revision, pdf_sha256, parser_version, company_id, report_year, basis, scope}` 必须一致；公告搜索 `announcement_id` 不授予财务事实真实性。
2. 行/列时间域 `period_kind=instant|duration`，只能有 `as_of_date` 或 `period_start+period_end` 合法一组；报告年份与数值期间独立。
3. `authority=verified_original|ocr_unreviewed|candidate|human_confirmed|ai_draft|illustrative|preset_demo` 为展示及授权维度，不允许编写一个泛型 `verified:bool` 混合所有状态。
4. 拟议 API 的 `POST` 需要 operation_id / owner 归属，重发同 request 读回旧操作；`GET` 纯只读，不隐式创建/重算；文档导入和批量研究都独立有状态回执。
5. `generation` 作用于每个请求、任务、内容缓存绑定与最终提交；不让旧演示用户的新写入出现在新代。
6. 共享 PDF 缓存只允许官方已验证公开资源；不可共享 demo session、用户上传、偏好、笔记、研究/报告、API key、token 或 model ledger。
7. 只展示可追溯原文、明确事实来源和 AI 待审解释；模型输出不是本地财务核准的签名凭证。

## API 草案（仅举例）

| 方法 | 路由建议 | 入参 / 返回 | 说明 |
|---|---|---|---|
| GET | `/api/discovery/companies?q=...` | list CompanyMatch | 本地模糊匹配/动态来源降级 |
| GET | `/api/discovery/announcements?security_code=...&year=...` | list Announcement | 官方公告检索，页面/来源身份 |
| POST | `/api/discovery/imports` | operation_id, announcement_id, chosen_company_id → receipt | 确认下载并进入现有 upload |
| GET | `/api/discovery/imports/{op}` | status/document_id/ready_status | 只读进度 |
| GET | `/api/companies/{id}/profile-v2` | Company360 | 聚合、无模型调用 |
| GET | `/api/companies/{id}/statements?year=...&kind=...` | StatementPage | 显示候选/已确认及引文 |
| POST | `/api/companies/{id}/statement-reviews` | 人工选择及确认请求 | 通过已有 owner 准入，不自动签核 |
| GET | `/api/companies/{id}/trends?metrics=...` | ChartSeries | 数据来源状态每点明确 |
| POST | `/api/research/checkups` | operation_id + scope | 规则检测/可选 AI 解释 |
| POST | `/api/research/annual-diffs` | operation_id + two scoped documents | 跨年片段对齐与解释 |
| POST | `/api/research/peer-comparisons` | operation_id + explicit 2-3 companies | 同年可比矩阵 |
| POST | `/api/research/batches` | operation_id + max12 cells + approved scope | 批量研究计划 |
| GET | `/api/research/batches/{id}` | statuses/results | 不重跑 |
| GET | `/api/reports/{id}/revisions/{n}/export?format=xlsx|csv|pptx` | 下载字节 | 冻结 revision 的只读投影 |

`contracts/` 有机器可读示例；只作为设计输入。命名/API 版本以 Codex M0 审查当前路由后定稿。

## 数据存储建议

在当前 demo 子代业务根建立 `discovery.db`、`financial-statements-v3.db`、`checkups.db`、`annual-diffs.db`、`batch-research.db`（必要时合并），**不要**直接改 applied migrations；append-only 新迁移或新独立 DB/服务接口。跨代公共 PDF cache 在 `control_root/public-pdf-cache`，由 controller 独占控制。

## 文件所有权与集成

热点文件：`runtime_factory.py`、`frontend/src/product/AppShell.tsx`、`productRoutes.ts`、`Conversations.tsx`、`app/demo/gateway.py`、`app/disclosures/service.py`、`app/finance_v2/*`。默认主控独占集成，worker 在新模块完成后提交接线 patch/明确文件，不能同时抢改。

## 依赖关系

```
M0 contract
  ├── D(company/announcement) → Import+Cache → Company360 data
  ├── Finance(statement schema) → Extract/Review → Trend → Checkup/Peer/Segment
  ├── Retrieval(BM25/OCR) → AnnualDiff → Checkup AI/Batch
  └── UI core → Profile/Study/Reports/Exports
                     ↓
            Integrated E2E + Interview handoff
```

<!-- END 10_ARCHITECTURE_API_CONTRACTS.md -->


---

<!-- START 11_QA_EVAL_DEMO.md -->
# 11｜真实验收、评测指标与面试演示数据

本项目是求职演示作品，测试策略必须**以真实可复现主链路为主**，不是生产级穷尽测试；但不能用 Mock 替代真实下载/OCR/研究的 PASS 声明。

## 证据分级（必须写在每次交付结果中）

| 等级 | 允许证明 | 不允许声称 |
|---|---|---|
| UI_MOCK | 高保真布局/交互设计 | 实际数据库、财务、模型、下载已接通 |
| UNIT_FAKE | 函数合同、状态边界、权限保护 | 真实 AI 意图/语义/金融精度 |
| REAL_HTTP_PDF | 真浏览器、真 HTTP、真 PDF 导入/解析 | 已有真实模型结论或人工核准 |
| REAL_BGE_MILVUS | 真 embedding、真向量/混合检索 | 模型结论切题、财务确认 |
| REAL_LLM | 实际 provider + 实际工具/证据/结果 | 客观正确率、财务审计完成 |
| HUMAN_REVIEW | 操作者逐条对照财报/点击明确确认 | 普遍可靠/安全合规 |

## 冻结样例（真实/示意分类）

- **真实公开 PDF**：优先选择已经核验的美的集团 2025、格力电器 2024/2025；动态发现再追加一份非现有 `catalog.json` 公司年报。每份记录 PDF SHA256、实际页数、来源 URL、下载时刻、正文/摘要、披露/修订状态。
- **OCR**：保留现有派生扫描页的 68 行/54 候选格真实验证，再实际增加“能被正式检索引用”的例子，必须标明 OCR 未人工审核。
- **财务数据**：从真实两年 PDF 对照核准至少同公司 2 个年度的 5 个核心指标，以及三表不同期间的几行；真实核准动作由用户本人授权，Codex 可准备 review 步骤但不可替签。若未执行，P0 演示用候选标记/其他真实已审核资料且不宣称确认。
- **虚构示意**：仅在单独 UI_MOCK 或显式 sample_mode 中使用“示例企业A/虚构财务数字”；不得以美的/格力名称绑定虚构金额。

## 实际 E2E 任务组

| ID | 场景 | 必须观察的结果 | 失败状态 |
|---|---|---|---|
| T01 | 公司名称/代码/拼音模糊搜索 | 正确候选并可手动选择，别名歧义不静默绑定 | 无结果回退 |
| T02 | 动态巨潮公告查询 | 非静态企业或新公告被实际发现，全文/摘要分开 | 网站不可用→官方跳转/上传 |
| T03 | 下载新 PDF 并入库 | 原始 SHA + 实际 fast parse + BGE/Milvus READY | 下载/解析失败可见 |
| T04 | 重复导入/缓存命中 | 缓存命中且本代来源绑定正确，未重复网络下载 | 内容修改保留新版本 |
| T05 | 登录到期/接管中导入 | 老代 401、写入不进入新代、公开缓存可复用 | 旧代残留安全 GC |
| T06 | 三表读取 | 资产时点、利润期间、现金流期间被区分且每行有证据 | 模糊表格保留 unsupported |
| T07 | 真人财务核对后图表 | 数据与证据/期间/单位一致，两年真实点位 | 缺核准仅候选/空态 |
| T08 | 公司 360 首页 | 四区真实数据/来源，打开来源和报表，1440/390不溢出 | 无资料引导导入 |
| T09 | 财报体检 | 至少 3 规则出真实/缺失状态，来源可查 | 不产错误归因 |
| T10 | 跨年经营文本变化 | 两年真实片段及两侧 PDF 链接 | 不因无命中声称删除业务 |
| T11 | 同行业对比 | 两公司相同期间，口径不同时标不可比 | 缺值不补 0 |
| T12 | 主营结构 | 一个真实收入分类候选与合计检查 | 不强制总和 100% |
| T13 | 图表追问 | 预填合法范围→用户点击→真实研究，示意点禁止导出为真实 | 无自动批准 |
| T14 | 研究批次 2x2 | 4 个独立状态，单项失败不会吞掉其他结果 | 超预算显式拒绝 |
| T15 | OCR 可问答 | OCR 文字检索→引用原图→标“未核对” | 不生成核准金额 |
| T16 | 混合检索质量 | 风险问题不将无关委托理财表排首要，前后对比可检查 | 失败保留记录 |
| T17 | CSV/XLSX/PPTX/PDF | 从真实同一 report revision 导出可打开文件，标签与数据一致 | 缺来源仍记录限制 |
| T18 | 历史/恢复/重置 | GET 不调用模型，seed 恢复，旧报告不可变 | 不能泄漏旧会话 |

## Agent 固定题与评测

必须继承 C 现有 15 条评测并补充到至少 24 条，其中 12 条用于核心真实 E2E 验证：意图路由、混合检索、OCR、双年差异、三表、体检、并发矩阵、memory、防数据污染。按 `case_id/required_tier/status(really_passed|failed|partial|skipped)/actual_provider_calls/cost/duration/source_sha/ground_truth` 保存结果。**不能仅因意图 proposal JSON 合法就计算整题 PASS。**

建议指标：
- `retrieval relevance@5`/MRR@5，且保留最重要错误类片段。
- `citation identity valid`、`citation semantically supports claim` 两条独立判断。
- `financial period/basis correct` 与 `unconfirmed facts were not published as confirmed`。
- `tool route correctness`、`multi-agent vs single on same task`（只报告相同数据环境中的事实，不宣称多 Agent 一定更好）。
- `cost reserved/billed separately`、`duration p50`、`real provider attempts`。

## 三条 5–10 分钟面试路线

A（最直观）：登录→高级首页→模糊公司搜索→动态年报导入→企业360→三大表→财报体检。
B（Agent 深度）：选择两年年报→“经营战略/风险变化”→单/多 Agent 真交接→左右年报证据→报告/PPT。
C（文档/工程）：派生扫描页 OCR→检索引用→PDF 高亮→记忆跨会话→演示接管并恢复 seed。

## P0 演示门槛

不要求无边缘缺陷或全行业数据覆盖，但 T01/T03/T06/T08/T09/T10/T16/T18 至少有实证 PASS 和可重复操作；T07 如无本人财务确认必须标 human_pending 并准备实际操作步骤。其余 P1 至少完成一个真实可演示案例。

<!-- END 11_QA_EVAL_DEMO.md -->


---

<!-- START 12_MILESTONES_AND_OWNERSHIP.md -->
# 12｜托管开发阶段、关键路径、并行计划和模型选择

## 总原则

**一个主控、三个互不抢热点的开发 worktree、一个独立复核**。先冻结数据合同/页面结构，之后以最短关键路径交付真实产品；工程边缘优化只记录，不占用大部分时间。

### 推荐模型

| 职责 | 主要模型 | 推理强度 | 使用时机 |
|---|---|---|---|
| 主控集成/验收 | GPT-6.1 | High | 始终，掌握状态和主分支 |
| M0 架构与 UX 深审 | GPT-6 Astra | High/Ultra | 起始一次，出现关键合同分歧时追加一次 |
| 独立子模块开发 | GPT-6.1 | Medium/High | 文件边界清晰的任务 |
| 高风险代码审查 | GPT-6.1 或 Astra | High | 每 M2/M3/M4 阶段集成后 |
| 评测跑数/文档 | GPT-6.1 | Medium | 已冻结 eval 数据与脚本 |

模型强度是建议，不依赖特定付费套餐；当前已安装的 Codex 选项以实际客户端可用为准。

## 里程碑

| 阶段 | 目标 | 关键任务 | 并行关系 | 出口条件 |
|---|---|---|---|---|
| M0（设计） | 把 C+ 范围、合同、UI、数据集合冻结 | B00–B03 | Astra 只评审，不抢写代码 | 形成实施 ADR、真实功能表和调用/文件约束 |
| M1（资料&检索） | 动态公司搜索/下载与 OCR 混合检索 | D01–D06, R01–R03 | 下载与 OCR/检索可并行 | 至少 1 新公司下载 READY；OCR 问答真链；风险检索相关性改进 |
| M2（财务&画像） | 三大报表、真实趋势、企业360、体检 | F01–F07, H01–H02 | 财务合同后 backend/UI 可并行 | 2 年真实三表关键数据、画像与体检 |
| M3（研究业务） | 跨年文本、同行、分部结构、图表追问 | A01–A06 | 依赖 M1 Retrieval/M2 结果，部分并行 | 三项复杂研究真可操作且有证据 |
| M4（矩阵&导出） | 批量矩阵、模板、收藏、高亮、Excel/PPTX | A07–A10, X01–X03 | 导出与批次可独立 | 实际 2x2 批次、XLSX/PPTX 可打开 |
| M5（整合&交付） | 完整 UI/数据/真人演示/测试与文档 | G01–G05 | 主控唯一集成 | 三条演示路径、测试 tier 和剩余问题齐全 |

M1–M2 的可行模块允许交错进行，不要求等整个 M1 完成才启动财务模块。M3/M4 依赖的是数据合同和可用 API，而非某个日期。

## 核心关键路径

`B00 baseline → B01 contract → (D03 official, F02 extraction, R03 hybrid) → F04 trends → H02 360 → F06 checkup → A02 annual diff → G03 actual E2E`。官方动态接口不可用时不阻塞全工作：走静态候选/用户 PDF 上传，继续其他模块，同时标官方发现 partial。

## 文件所有权（防冲突）

| 工作树 | 可写主要目录 | 禁止修改 |
|---|---|---|
| WT-DATA | `app/company_discovery/*`, `app/public_pdf_cache/*`, `app/disclosures/` 新适配器 | `runtime_factory.py`/AppShell/根 README/其他 worker 目录 |
| WT-FINANCE | `app/financial_statements_v3/*`, `app/company_profile/*`, `app/checkup/*` 新文件 | 旧 `app/finance_v2/models.py`/老迁移/公共 UI 热点 |
| WT-RESEARCH | `app/retrieval_v2/*`, `app/annual_diff/*`, `app/batch_research/*`, `app/peer_compare/*` 新文件 | 原 `showcase_research/agents.py` 高频冲突段，除非明确获得文件所有权 |
| WT-UI | `frontend/src/product/cplus/*`, `frontend/src/product/cplus/*.css`, prototype 迁移 | `AppShell.tsx/productRoutes.ts/Conversations.tsx` 接线热点由主控接管 |
| ROOT | `runtime_factory.py`, 现有 service 路由接线、迁移索引、集成 tests、README | 不抢 worker 未合并模块内部文件 |

一份文件同阶段只设一个写作者。各 worker 单独分支/工作树，以接口 mock 调用开发；主控 cherry-pick/merge 时先 compare diff，再做功能集成。

## 主控状态机

1. `PLANNED`：任务定义，依赖与文件 owner 已锁定。
2. `IN_PROGRESS`：worker 使用独立分支，产出真正代码/测试/说明。
3. `CANDIDATE`：已推送、列出 commit、测试、真实与模拟分级。
4. `INTEGRATED`：主控在集成 branch 接入路由与前端，旧核心测试不回退。
5. `VERIFIED`：实际 E2E 达到该任务 DoD；缺失则保持 `PARTIAL`，不凭“代码完成”升为 verified。
6. `BLOCKED_EXTERNAL`：官方访问/API/用户财务核准等不可替代依赖，已启动合法降级；其他任务继续。

## 估算与节奏

上一 C 方案约三小时完成大量编码，不以此推定 16 个模块也能 3 小时完整验收。粗略目标：M0 0.5–1.5 有效开发日、M1+M2 2–5 日、M3+M4 2–5 日、M5 1–3 日，实际按真实来源/模型/手工财务确认调整。功能有局限允许记录，**不允许将空壳说成完成**。

## Codex 主控自动推进边界

在已经授权的本地独立分支内，Codex 可自动规划/实现/测试/修复/提交/推送。不得未经允许更改 `main`、正式部署、清空开发者数据、支付服务、使用超过预算的 LLM、强制接管他人登录或代签真实财务。收尾报告一份状态表即可，不必每个小任务向用户发确认请求。

<!-- END 12_MILESTONES_AND_OWNERSHIP.md -->


---

<!-- START 13_RISKS_COSTS_SCOPE.md -->
# 13｜风险、降级与投入控制

## 主要风险矩阵

| 风险 | 影响 | 求职版解决策略 | 阻断范围 |
|---|---|---|---|
| 巨潮接口不可公开稳定使用/查询不通 | F19/F20 | 官方页面跳转、预置精选来源、用户手动 PDF；记录实际可用证据，不猜测 | 仅动态发现 |
| 公告主体/摘要/更正识别错误 | 错文档 → 全研究错 | 证券代码/交易所/公告类别/报告年度/版本用户确认，原 PDF 元数据核对 | 当前导入 |
| 财务报表表格复杂/跨页 | 错年度/单位/列 | 固定真实样本；提取候选+同屏核对+unsupported；按时点/期间类型存储 | 指标核准/图表 |
| 未完真人财务签核 | 已确认真实图为空 | 本人 1 套真实核对；否则明确候选图与 sample_mode，禁止伪造确认 | confirmed 输出 |
| OCR 识别偏差 | 错误引文 | OCR 单独 authority，定位原图，人工校对后才晋级；后端检索保留来源 | OCR 数字准入 |
| 混合检索无关证据 | Agent 回答不切题 | 风险章节过滤、RRF/rerank、前后固定题，允许拒答 | 该回答 |
| 批量/多 Agent 成本累积 | 付费超额、响应慢 | 共享预算账本、用户明确执行、任务数量/并发限制；不重置旧预算 | 新模型调用 |
| 共享缓存跨 session 越权 | 数据串号/隐私 | 仅公开官方 PDF SHA 缓存；所有业务绑定与发布都校验当前 generation | 共享 cache |
| PDF 大文件/扫描页耗资源 | 队列阻塞 | 体积/页数/超时/并发限制，按页 OCR 与可重试状态 | 特定文档 |
| PPTX/Excel 格式误差 | 导出不专业 | 固定 5–8 页主题模板、实际打开验证与防公式注入 | 导出 |
| 36+ 新旧功能集成冲突 | 返工 | 热点文件主控独占、分模块 worktree、M0 API 冻结 | 当前集成 |
| 执行速度快但验收缺口多 | 面试现场失败 | 固定 3 条真实演示路径、保存真实运行证据、已知限制、录屏备用 | 交付状态 |

## 资源预算建议

不要自动再给全新 LLM 预算；前 C 方案账本已经记录 73 次物理调用、保守预留 ¥1.354700/¥5，实际扣费未观察。C+ 主控应先只读确认共享账本余额，向用户说明新增预算选择（如需要）并遵守确认边界。没有预算就先 Mock 测协议、跑实际 BGE/PDF、引用已保存真实研究进行 UI/导出。

CPU 解析/模型成本：文档最大体积目前 20MiB，C+ 可以提升，但上传/下载/内存处理同步；`BGE-M3` 常驻和 Milvus Lite 写入需合理分组。Apple Vision 已验证在 macOS；若选 Linux 云部署须采用可用 OCR 替代并单独验证，不假设兼容。

## 需要明确放弃/暂缓的生产项

多租户/计费、全交易所实时公告覆盖、实时股价/自动交易、所有行业三表 100% 自动识别、无限 agent 自主委派、复杂分布式部署、全天候无人值守、高并发/极限容灾。求职版重点关注一条真实数据链+专业的页面和技术讲解。

## 核心成本意识

避免“推翻旧三指标核对”这种跨全产品重构；每次新增 v3 metric/来源处理版本都应当能够在不破坏旧报告的情况下部署为新模块。若某外部数据源失败超过预设时间，则先交付合法的静态/人工回退并明确 blocked_external，不阻挡其他 Agent/报表工作。

<!-- END 13_RISKS_COSTS_SCOPE.md -->


---

<!-- START 14_CODE_MAP_AND_REFERENCES.md -->
# 14｜现有代码映射、审查清单和外部资料

## 代码入口（核验于 C 集成 SHA 45d55d75662f...）

| 功能 | 原代码 | 应用方式 |
|---|---|---|
| 企业/年报目录 | `app/disclosures/service.py`, `catalog.json`, `api.py` | 替换固定目录查询为 provider adapter，兼容原静态 fallback |
| 安全下载 | `app/disclosures/download.py` | 复用/扩展有受限下载器，改体积策略必须统一上下游 |
| PDF 上传/去重 | `app/documents/service.py`, `source_service.py`, `local_object_store.py` | 继续走 upload；保留 SHA/版本/封面校验 |
| 解析/向量索引 | `app/documents/processor.py`, `app/api/runtime_factory.py` | PyMuPDF/pdfplumber/BGE/Milvus；扩展索引合同时审查 source revision |
| OCR/解析质量 | `app/parsing/service.py`, `vision.py` | 独立 OCR artifact → read-only search adapter → 来源引用；不混财务核准 |
| 财务旧合同 | `app/research/template_contracts.py`, `app/agent/revenue_confirmation.py` | 3x2 基础不动，人工签核不由 Agent 自动执行 |
| 财务扩展 v2 | `app/finance_v2/models.py`, `extraction.py`, `service.py` | 仅资产负债 instant，v3 新领域容纳期间指标 |
| 首页与可视化 | `frontend/src/product/showcase/ShowcaseDashboard.tsx`, `app/dashboard/service.py` | 复用 Navigation/KPI，增量企业 360 与真实分析图 |
| 当前会话 | `app/conversations/*`, `frontend/src/product/Conversations.tsx` | 复用 scope/turn/memory，图表预填必须显式用户发送 |
| 多 Agent | `app/showcase_research/agents.py`, `jobs.py`, `findings.py` | 复用 bounded tools/routing/存储；新增比较/批次属于业务域 |
| 语义记忆 | `app/research_memory/service.py` | 收藏/变更/删除继续使用原版本与权限 |
| 报告 | `app/showcase_reports/service.py`, `printing.py`; `app/reports/` | 只读扩展导出，不改已有 revision |
| 演示隔离 | `app/demo/controller.py`, `process.py`, `gateway.py`, `seed.py` | cache 独立；generation/fence 必须保留 |
| UI 路由 | `frontend/src/product/productRoutes.ts`, `AppShell.tsx` | 主控统一接线，不删除旧深链 |
| 现有状态 | `docs/showcase/STATE.md`, `KNOWN_ISSUES.md`, `task-board.csv`, `EVIDENCE.md` | 保留真实与模拟分级、不要擦除 FAIL |
| 测试入口 | `.github/workflows/quality.yml`, `frontend/e2e/showcase-*` | 增量 CI 专项 smoke，绿色 Quality 不等于全部真实 E2E |

## 外部官方资源（检索日期 2026-11-03）

- 巨潮公司列表： https://www.cninfo.com.cn/new/snapshot/companyListCn （页面显示“代码、简称或拼音缩写”搜索框）。
- 巨潮信息披露： https://www.cninfo.com.cn/new/commonUrl?url=disclosure%2Flist%2Fnotice （有代码/简称/拼音、公告标题、年报分类、日期筛选）。
- 巨潮首页： https://www.cninfo.com.cn/ 。
- 深圳证券交易所公告： https://www.szse.cn/disclosure/notice/company/index.html 。
- 第三方代码示例中提及 `hisAnnouncement/query`，但这是非官方接口资料，不得视为稳定或官方开放 API；M0 需实际预检 HTTPS/条款及 fallback。
- 工具参考：`https://github.com/aning0922/findoc-agent/pull/2`（当前 C 候选草稿）、`https://github.com/aning0922/findoc-agent/tree/codex/findoc-showcase-c-integration`。

## 首个 Codex 技术走查动作

```
git fetch origin
git rev-parse origin/codex/findoc-showcase-c-integration
# SHA 匹配则创建 C+ 新集成工作树；不从 main/旧v12直接复用
# 读取 docs/showcase/STATE.md 和 KNOWN_ISSUES.md
# 先导出路由与模块结构，生成 M0 架构决策，再启动 worker
```

本工作包不包含 API 凭据、受版权保护的年报原件或私有 seed，已有 Git 忽略的本地证据与原开发数据保持不变。

<!-- END 14_CODE_MAP_AND_REFERENCES.md -->


---

<!-- START 15_CPLUS_READINESS_GATE.md -->
# 15｜C+ 求职演示版完成判定（不是生产验收）

## 必须提供的交付物

- 新独立集成分支、HEAD SHA、PR 草稿、完整 `STATUS.md`、真实任务清单和 commit 对应关系。
- 1440/390px 实际 **React + 后端** 首页/企业360/三表/体检/跨年变化截图，不是 prototype UI_MOCK。
- 1 个非旧静态目录企业的官方发现及真实 PDF 下载/解析/索引记录，或正式标注 `BLOCKED_EXTERNAL` 并给官网跳转/上传回退。
- 真实 PDF 两年三表候选/核对明细、至少一个用户亲自确认的可用财务指标正向图（若用户未执行则 human_pending，不能作完成）。
- AI 体检三类有证据的规则；跨年文本变化至少 3 个维度双年原文；2 家企业同行对标（确认或候选状态明示）。
- OCR 文字检索与引用真实 PDF 页面、独立 authority；不能宣称 OCR 自动财务核准。
- 同一风险问题检索 before/after 相关性对照；保留失败例子而不是只展示最好的一题。
- 2x2 批量任务矩阵、图表追问、收藏/高亮及一个真实 Excel/PPTX/PDF 文件可打开。
- 面试脚本、录屏、样例文件、seed/bundle SHA 与启动说明、成本说明、没有改动/强制合并 main 的证据。

## 允许延期但必须如实记录

- 巨潮在某日期接口不可用且采取合法回退；某行业复杂年报表无法解析；OCR 只能识别有限样本；少量旧 fixture 不在当前设备；无法取得完整真人财务签核；大规模性能/多租户问题。

## 禁止宣布 PASS 的情况

- 图表数字是 UI_MOCK/虚构却宣称真实美的财务值。
- 只有页面截图却没有 PDF/模型/业务 API 实际执行证据。
- 15+ 固定问题只运行意图提议，却当成问答准确率。
- 模型解释没有原文足够支持但冒充已经审核。
- Git 未包含 seed 二进制却说 `git clone` 就能完整运行，或新版本重置破坏既有种子。
- 真人还没有点击 ACCEPT/SAVE/RESUME，却宣称完成真实财务核准。

<!-- END 15_CPLUS_READINESS_GATE.md -->


---

<!-- START 16_CODEX_MASTER_PROMPT.md -->
# FinDoc C+｜Codex 主控启动指令（可直接全文复制）

你现在担任 FinDoc C+ 求职演示增强项目的**全阶段托管技术总负责人**，目标是按工作包完成实际代码、交互、真实演示案例、测试和交付，而不只是输出建议。

**请先打开我提供的完整工作包文件夹，尤其 README、00、02、10、12、11、15，以及 data/task_board.csv、contracts 和 prototype。**

仓库：https://github.com/aning0922/findoc-agent
原 C 方案集成分支：`codex/findoc-showcase-c-integration`
固定审查 SHA：`45d55d75662f01d9bc78da1a946d845a01a27480`
**不要从 main 开始，不要在原 C 分支上直接开发。** 先 fetch，若远端有更新必须 compare 并记录实际起点；然后创建独立 C+ 集成 worktree/branch，保留原 C、V1.2、main 与所有 seed/真实数据。

## 全阶段目标

完成工作包 F19–F34 的 16 项业务功能：上市公司模糊搜索、巨潮动态年报、受控下载与跨代公开缓存、企业 360、三大报表、真实财务趋势、AI 体检、跨年文本差异、同行对标、业务结构、图表追问、OCR 入正式检索、混合检索重排序、批量研究矩阵、Excel/CSV/PPTX 导出、指标释义/模板/图表转换、精准 PDF 高亮与研究收藏。

全部功能都需要可操作页面和真实业务模块，不能只有入口、接口空壳或漂亮 mock。求职版可限定少量真实公司/年报，但必须对每项提供一条可运行演示路径；没有真人财务确认则标明候选或 human_pending。

## 执行原则

1. **M0 先研究与冻结合同。** 真实阅读当前源码，列现有复用/需改/新增，检查当前 36 项 C 完成情况和缺口；使用 GPT-6 Astra 高/最高推理单独评审产品蓝图、数据结构、主要 API 和 UX。以此为准冻结接口/文件所有权，输出 ADR。尽量早给出可点击原型中哪些要替换成 React 的计划。
2. **任务并行但热点文件独占。** 主控 GPT-6.1 High 负责总体、`runtime_factory`、AppShell、productRoutes 与集成。其他工作树根据 `data/task_board.csv` 并行：官方来源/缓存；财务/画像；检索/研究；前端模块；导出。单文件同一时间只允许一个 owner。不要因为普通子任务结束就反复请示用户。
3. **阶段目标可自主推进。** 子任务完成请自动测试、提交、回主控审查、集成并跑必要回归。主控更新状态与证据，进入下一阶段；只在真的需要用户财务核准/新增付费预算/不可逆操作/生产发布时停住请求授权。
4. **求职优先，不做生产过度工程。** 首页与企业 360 视觉高级、操作简单；所有 F19–F34 覆盖；至少三条 5–10 分钟真实演示路线。允许具体有限支持范围，记录局限；不要求多租户/高可用/所有 PDF 100% 识别。
5. **核心安全与真实性不退让。** 不伪造确认财务数据、模型解释不冒充审核、OCR 待审和精确原文分层、来源/版本/期间/单位始终保留、显式用户动作先于下载/批准/确认/高成本执行。不要修改旧 v1 三指标与 v2 即时指标的已应用迁移/合同。
6. **动态巨潮来源须实际 spike。** 官网页面支持搜索不代表存在稳定官方 API。先验证 HTTPS/访问条件/合理频率/字段；不可用时用官方跳转和手工上传回退，不能绕过限制。共享官方 PDF cache 不能保存私有上传或跨代工作空间数据。
7. **不把旧 C 的“质量 CI success”当作新功能验证。** 新增真实 HTTP+PDF+BGE+Milvus、真实模型回归、固定问题集和用户签核待完成分别记录。尤其修复经营风险查询混入“委托理财表格”的检索相关性缺口，提供 before/after 实际样本。
8. **不要清空原数据或重置模型预算。** 配套完整 seed bundle 可能只在本机 Git 忽略目录；先备份及 SHA 验证，不纳入 Git 公开敏感数据。既有 5 元预算账本跨 generation 保持，不绕过授权。

## 立即执行 M0 的具体输出

- `docs/cplus/STATE.md`：真实 HEAD/基线、功能实现矩阵、依赖图、当前 blockers、阶段目标。
- `docs/cplus/ADR.md`：公司/公告源、PDF cache、财务时点/期间、OCR 权限、检索混合、报告导出和 demo generation 的冻结决定。
- `docs/cplus/UX.md`：首页、企业 360、三大表、AI 体检、跨年对比、批量研究、导出的页面布局/状态/空态；参考工作包 prototype 但不嵌套静态 mock。
- `docs/cplus/TASK_BOARD.csv`：可执行任务、依赖、Owner、目标接口、验收层级与工作树。
- `docs/cplus/EVAL_PLAN.md`：固定问题与真实验收底线，费用上限/外部 API 回退。

完成 M0 后无需再让我批准每个低风险任务；按工作包直接推进 M1–M5 直至求职演示版交付。**不擅自合并 main、强推、公开部署、代签财务或购买服务。**

## 每个阶段汇报格式

```
BASE/HEAD: <branch + SHA>
DONE (真实): <新增可操作页面、业务动作、测试与证据路径>
PARTIAL: <功能已接入但测试层级有限>
BLOCKED_EXTERNAL/HUMAN: <所需外部官方源/真人财务等依赖>
TESTS: <实际命令与 PASS/FAIL/SKIP 分母，真实/假数据边界>
COST: <预算已预留、物理调用、实际账单是否已观察>
NEXT: <自动继续的任务，禁止逐项再问用户>
```

现在先检查仓库最新状态并开始 M0，不要只复述工作包文本。必须形成实际 commits、运行结果和可交付的成果。

<!-- END 16_CODEX_MASTER_PROMPT.md -->


---

<!-- START 17_WORKER_AND_REVIEW_PROMPTS.md -->
# 17｜子任务交接模板与独立审查指令

## Worker 会话启动模板

你是 FinDoc C+ 的独立实现 Worker，属于主控已批准任务 `<task_id>`。工作基线为主控提供的明确 SHA；在独立 branch/worktree 开发。读取完整工作包 `02_FEATURE_SPEC_F19_F34.md`、对应专项 MD、`10_ARCHITECTURE_API_CONTRACTS.md` 与指定任务记录。**仅修改以下 Owned Files：<paths>**；不得直接改 runtime_factory、主导航、旧 applied migration、main 或其他 Worker 文件。按照约定 API 实际实现，不要仅创建 UI mock。必要测试包含最小 1 条真实路径和有说明的 fake unit；模型/财务不准自签。完成后提交/推送分支，报告 SHA、修改文件、接口、验证 tier、剩余问题，交由主控审查集成。

## 独立 Reviewer 会话模板

你是 FinDoc C+ 独立源码与产品验收审查者。固定审查 SHA `<SHA>`，不能看移动的 HEAD 后直接沿用旧结论。必须阅读本阶段 diff、真正的后端服务调用、React 路由/状态、数据库合同、测试与失败记录；找出：

1. 旧源版本/财务权限是否被破坏、OCR 是否冒充已核准，模拟数值是否冒充真实。
2. 巨潮动态数据是否有合法访问回退、SSR F/内网地址防护、缓存是否跨 generation 泄露用户文档。
3. 多年度“时点 vs 期间”是否正确、比值公式/原单位/合并口径是否保持、版本失效是否终止新发布。
4. 研究答案是否真正相关，模型解释是否有可查原文和人审标记；是否含无关“委托理财”片段。
5. UI 是否 1440/390 正常，首页与公司 360 是否有专业感、按钮是不是可运行。
6. 是否提供独立真实测试证据；报告过往失败不能覆盖或篡改 PASS。

输出 P0/P1/P2 按文件+行号+复现条件+影响+最小修复建议。允许保留求职版 P2/资源限制，但 P0（数据串号、假核准、路径越权、用户失效仍能发布、关键主链路打不开）不允许带入最终演示。

## 用户真人财务核对任务交接

如果需要真人 `ACCEPT/SAVE/RESUME`，主控准备单页工作单：选择哪一份真实 PDF（SHA）、核对哪 5 个指标及两年、原始值/单位/期间/口径和页码、UI 哪个按钮、预期完成后哪张真实图会出现。此步骤由本人实际完成，不允许 Worker 在自动化中使用 `local_operator` 身份伪造签署。

<!-- END 17_WORKER_AND_REVIEW_PROMPTS.md -->
