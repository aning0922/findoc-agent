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
