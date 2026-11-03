# G4：结构化研究模板与图表报告草稿

任务：四种有限、版本固定的工具流程及“复制当前图表到报告草稿”。基线 `a2c778dd915ceb7703db52260672a436366069b4`；独立分支 `codex/cplus-g4-templates-drafts`。提交 SHA 由最终交接消息提供。

## 完成内容

- `POST /cplus/template-runs`，`GET /cplus/template-runs/{run_id}`，`GET /cplus/template-runs/operations/{operation_id}`。严格 `template_id=overview|cash|peer|changes`、`template_version=cplus-template-v1`、问题和显式来源；可选解释默认关闭。
- 概览：一家一份年度报告、本期核心五指标及主要业务/经营风险摘录。现金流：同公司两份不同年份报告、现金流与归母净利润对照、原有体检规则及程序期间变化。同行：显式 2–3 公司各一份同年报告、核心指标矩阵及各公司竞争披露。经营变化：同公司两份不同年份报告、原有三个主题双侧原文服务。
- 只从当前报告年度的完整年度期间/年末候选选择核心五指标，保留真实 `time`，不把同一报告的比较列重复算成本期。没有唯一候选就保留缺值；同行缺一家公司候选也保存明确不可比矩阵。程序计算沿用原服务的 Decimal 结果；口径未知时不显示可比变化。年份不相邻时标作期间变化，不称同比。
- 使用同一 `StatementService`、`CheckupService`、`AnnualDiffService`、`PeerComparisonService`、`HybridRetrievalService`，没有另造 PDF 数值解析或模型客户端。可选解释最多调用一次既有 hybrid answer；年度差异子服务固定 `generate_explanation=False`。
- 模板不可变对象为 `template-run-v1`，`run_id`、版本1、精简 collection refs、本期 financial_points、分类型输出、来源、可选待审解释、创建时间、`financial_authority:false`。父操作及每个子操作编号均在派发前落库；任何未知状态保留编号，POST 同编号只读原状态，不再派发子任务。
- `POST /cplus/report-drafts` 只接受 `operation_id,trend_id,chart_kind,metric_keys`，拒绝浏览器金额/坐标等多余字段。重读真实不可变 `statement-trend-v3`，重新选取和核验原单元格、实际期间、来源与回执。保存即创建 `chart-report-v1`、`report_id`、版本1、draft，保留所选指标及 `cell_id/cell_revision/payload_sha256`，不增加财务资格。
- 两个对象独立 Store，沿用 owner/哈希/严格原操作语义。最终 COMMIT 内保持根 publication guard、来源读锁、原 statement 回执读锁及同步身份回调；拒绝 WAL 回执栅栏。历史 GET 仅投影当前来源状态，不覆盖不可变快照，不重检索或调用模型；返回前再校验身份，身份失效不能被历史来源降级掩盖。
- 前端模板组件支持 `companies?` 与全部 `sources`；显式来源、可编辑问题、二次确认、默认关闭的一次 AI 选项、不同结果结构、PDF 物理页链接、版本与同比释义。新 `CopyChartToDraftButton` 保存原操作后才 POST，结果未知时仅 GET 查询，刷新后也恢复原编号；成功后跳转既有报告页。两个入口存储失败都阻止首次 POST。

## 主控装配合同

本提交没有修改根运行时、导出注册、企业页接线或报告页。以下由主控落在原有装配位置，不能新建第二套运行时：

```python
from app.research_templates_v1 import TemplateRunService, create_template_run_router
from app.chart_report_drafts import ChartReportDraftService, create_chart_report_draft_router

# 位于 register_cplus_runtime 内，复用现有局部服务、身份与 guard。
shared = dict(
    statements=statements,
    identity_validator=validate_identity,
    publication_guard=publication_guard,
    commit_check=lambda identity, payload: validate_identity(identity),
)
templates = TemplateRunService(
    root, checkups=CheckupService(statements), annual_diff=annual,
    peers=peer, hybrid=hybrid, **shared,
)
chart_drafts = ChartReportDraftService(root, **shared)
app.include_router(create_template_run_router(templates, identity_provider))
app.include_router(create_chart_report_draft_router(chart_drafts, identity_provider))
# 建议按现有命名装入 state，供根注册器读取；名称不是 worker 的强制外部协议。
app.state.cplus_template_service = templates
app.state.cplus_chart_report_service = chart_drafts
```

根网关的 mutation allowlist 需要允许两个精确 POST 路径；各 GET 仍然只读。不要把操作查询 GET 改成重新运行入口。

在**原**报告/导出注册表中加入两域，不新增报告列表：

| domain | schema | id | store/table | revision |
| --- | --- | --- | --- | --- |
| `template_run_v1` | `template-run-v1` | `run_id` | `templates.store.path` / `snapshots` | 1 |
| `chart_report_v1` | `chart-report-v1` | `report_id` | `chart_drafts.store.path` / `snapshots` | 1 |

注册器应从 owner 匹配的不可变 `snapshots.payload` 计算原始 payload hash，不能对附加 `historical_snapshot/current_source_status` 的 GET 投影计算原始 hash。保存对象有 `selected_sources`、`collection_refs`、唯一 `financial_points`；模板另有 `memory_generation`。复用根导出解析、展示权限与提交栅栏：来源失效保留历史标记；身份失效拒绝；回执检查必须逐点匹配快照里的 `receipt_ref` 并保持锁至导出提交。递归投影器可识别现有 financial_points 和 evidence_refs；新增域仍须由 exports owner 完成 schema/API 枚举、标题及单注册表列表接线。

企业页在原模板入口传入 `companies` 与全部已核验来源；当前企业的来源过滤由组件执行，同行可显式勾选第二/第三企业的同年报告。无需调用 `onResearchDraft` 才能运行模板；该回调仅保留原“另准备研究助手问题”兼容入口。

```tsx
import {CopyChartToDraftButton} from '../reportDrafts/CopyChartToDraftButton.tsx';
// 在持有实际服务器 trend.id 的原图表位置，传入当前图形和明确显示的指标。
<CopyChartToDraftButton trendId={trend.id} chartKind={chartKind} metricKeys={metricKeys}/>
```

组件跳转 `/reports?cplus_domain=chart_report_v1&cplus_result={report_id}`。主控在原报告页读取这两个参数并匹配原注册表项目，不要另建报告保存动作；POST 复制已经保存版本1。

## 实际验证

- `.venv/bin/pytest -q tests/test_cplus_g4_templates_drafts.py --disable-warnings`：**15 passed**。生成中文 PDF，真实原装配身份/guard/SQLite/原财报提取/FTS/三主题/同行/体检服务；dense 与 embedding 为受控替代。覆盖四流程、当前期与比较列、缺值、严格输入、scope、不可变恢复、可选 fake provider 成功/超时各一次、来源/回执变化、WAL 拒绝、独立写线程在最终提交回调观察两个读锁、查询途中身份失效。全部回执变化为测试替代，没有人工核准。
- Node 24 执行 `tests/cplus_g4_templates_drafts.cjs`：**PASS / UI_MOCK_ACTUAL_REACT**。独占随机本地 Vite、真实 React 组件、API 全拦截、非同源请求阻断并检查为零；四类输出、同行跨年拒绝、AI 默认关闭、模板与图表 504 后刷新只读原操作恢复、报告域跳转、首次存储失败两入口均 POST0、390px 整体无横向溢出。检查了 `evidence/G4-templates-drafts/ui-mock-mobile.png`，表格使用局部滚动，双侧摘录在移动宽度纵向显示。
- Node 24 `tsc -b frontend/tsconfig.json`、Ruff 检查限定 Python 文件、`git diff --check`：PASS。

证据仅为 `UNIT_SYNTHETIC` 和 `UI_MOCK_ACTUAL_REACT`；真实 SDK/BGE/Milvus/原私有运行配置与账本读取/人工财务核准均为 0。未操作 14540/14542，未执行真实 PDF/provider/browser 业务验收，未推送。本任务交付有限工作样例；根装配、真实运行以及导出文件验收仍由主控完成。
