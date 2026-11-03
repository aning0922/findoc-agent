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
