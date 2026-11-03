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
