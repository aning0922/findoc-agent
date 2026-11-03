# H01 Dashboard 交接

2026-11-03（Asia/Taipei）。分支 `codex/showcase-h01`，base `d6ccca07d46f5625bae8176166dc8b9f6e3b434a`。旧评审分支及 49e0eba 未重写。模型记录：派工为 Sol/high；本轮 developer 提供的实际模型标识为 gpt-6.1-sol，推理档位没有额外运行元数据证明。

## 已交付与接线

新增 `app/dashboard/service.py`、`api.py`、包导出和 `tests/test_dashboard.py`；未修改 runtime_factory/migrations/DocumentService、前端或 seed。已读 API_MINIMUM v1.0、M1-dashboard、主控集成树 M1_WIRE；建议链接遵循最后补充的 `question` 参数。

主控唯一接线示例（变量均为当前 generation 现有实例）：

```python
from app.dashboard import DashboardService, create_dashboard_router

service = DashboardService(
    runtime_root=runtime_root,
    workspace_id=DEMO_WORKSPACE_ID,
    tasks=task_repository,
    facts=revenue_service,
    memory=memory_service,
    lease_generation=generation,  # 普通本地模式可 None
    seed_version=seed_version,   # 无 seed 可 None
    preset_task_ids=frozenset(seed_manifest_task_ids),  # 可省略，默认空
)
app.include_router(create_dashboard_router(service))
```

`runtime_root` 只由服务端注入。constructor 不初始化、不迁移、不读库；核对 Task/facts/Memory 绑定到同一 documents.db，旧 Memory 仅允许 demo 范围。基础聚合连接以 SQLite `mode=ro + query_only + BEGIN` 打开，不存在的库不会被创建。Memory 可不注入，使用默认建议；真实图有事实组却缺 facts 服务时明确 503，不显示零或样例。

网关仍负责所有业务请求的 lease、expiry、generation admission；模块本身不是公开认证入口。外部 `/api/dashboard/*` 依现有代理剥 `/api` 到内部路由。不能直接公开该 child router。

## DTO 与语义

`GET /dashboard/overview`：

```json
{
  "schema_version": "dashboard-overview-v1",
  "generated_at": "<UTC instant>",
  "snapshot_at": "<UTC instant>",
  "lease_generation": 7,
  "seed_version": "v1",
  "data_origin": "local_runtime",
  "kpis": {"companies": 3, "reports_ready": 1, "research_completed": 0, "reports": 0},
  "task_distribution": [{"status": "running", "count": 1}],
  "recent_research": [],
  "suggested_questions": [{"id": "revenue", "text": "近年营业收入如何变化？", "href": "/conversations?question=<encoded>"}],
  "companies": [],
  "limitations": ["研究完成数为已保存历史状态；阅读结果时仍需重新核验来源。", "仅统计旧研究Task；尚未混入独立v2 jobs。"]
}
```

此 JSON 是结构示例，不是线上数据。companies 为当前 workspace 全目录；reports_ready 为 READY documents 与 report metadata 绑定的交集；reports 按 reports 头实体一行一个，不累加 revisions。所有 Task 在同一计数快照内经过原 TaskRepository.decode 的 canonical/hash/identity/budget 校验；execution_status=running 统一计入 running，其余保留合法原状态（含 failed/refused），环图与 Task 总量同分母。completed 仅统计 idle 的已完成历史，不声称来源当前有效。

recent 返回 task 深链和保守 `review_status=source_recheck_required`，不将历史结果标成当前财务核准。仅显式注入的 manifest task IDs 标 preset_demo，seed_version 不会把访客新任务误标成预置；聚合数据始终来自当前库。建议可读取已确认旧枚举 analysis_focus，现金流/盈利/营收仅调整排序，不调整事实或授权；href 只预填、不创建会话/选源/发模型。

`GET /dashboard/charts?company_id=<id>&metric_key=revenue&sample_mode=false`：

```json
{
  "schema_version": "dashboard-charts-v1",
  "lease_generation": 7,
  "seed_version": "v1",
  "snapshot_at": "<UTC instant>",
  "company_id": "<server company id>",
  "metric_key": "revenue",
  "unit": "CNY_YUAN",
  "origin": "confirmed_financial",
  "points": [{"period": 2030, "report_year": 2031, "value_decimal": "250000", "source_revision": "<revision>", "document_id": "<id>", "source_state": "current", "fact_ref": {"fact_set_id": "<id>", "fact_id": "<id>", "period": 2030, "receipt_id": "<id>", "disclosure_version": "<version>", "source_revision": "<revision>"}}],
  "comparison": [], "empty_reason": null, "limitations": []
}
```

只支持旧三指标 revenue/net_profit_parent/operating_cash_flow。复用 query_financial_facts(local_operator)、FinancialAnalysisService.admit_reference、最终 recheck_financial_analysis_sources，完整验证事实资格/来源字节/披露版本/币种/口径/全年期间及 Decimal，不调用计算或模型。每个财务 period 若有多个有效事实引用/披露版本，保守排除并返回 version_selection_required，不选最新、不混算；其他无歧义 period 可展示。最终复核失败则整个请求 503，不发布旧 points。

无事实为空 `no_confirmed_facts`；无合格事实/歧义为空 `no_eligible_facts`；未知公司 404；未知或重复 query/无效 metric/sample_mode 为 422；存储、Task 完整性、财务复核故障为 503。错误固定 `{detail:{code,message}}`，没有成功 KPI/points。所有响应 no-store。

sample_mode=true 无需真实公司，强制 fictional company `illustrative-company-a`、origin=illustrative、显著中文限制；独立固定示意系列，不返回 fact_ref、不生成事实、不在异常后自动启用。comparison 暂为空：当前合同没有定义第二企业/比较期间请求；前端柱图可消费同一合格 points，跨企业确定性比较留后续明确合同，不凭空发布差额。

## 验证与限制

执行命令：

- `uv run --frozen --group checks ruff format app/dashboard tests/test_dashboard.py`：完成。
- `uv run --frozen --group checks ruff check app/dashboard tests/test_dashboard.py`：PASS。
- `uv run --frozen --group checks pytest -q tests/test_dashboard.py`：最终 3 PASS（1.72 秒），5 条 PyMuPDF SWIG DeprecationWarning 保留。
- `git diff --check`：提交前执行。

测试等级全为 UNIT_FAKE，仅新建临时 SQLite/合成 PDF 与 simulated_test 回执。图表正向测试以纯内存 local_operator 读取投影替代（沿用旧测试模式），调用实际 FinancialAnalysisService 准入；不写 local_operator，不证明真人签核。覆盖基础快照计数、Task 损坏拒绝、已确认偏好排序、空库/缺库、独立示例与 query 拒绝、Decimal/财务 period 与 report_year、披露歧义、最终来源失效关闭。真实模拟回执也被实际 production 查询排除。

初轮测试出现 fixture 预置企业数预期错误和重复 kwargs 的测试构造错误，已修正；随后新增预置来源标签时一度导致空库失败，测试捕获并修正，最终空库通过。未删断言或用失败回退零掩盖。

未执行真实财务签核、现有真实库读取、真实模型/OCR、浏览器或主控 runtime 集成。未运行全量旧测试（本任务仅新增独立模块）；本次不声称 H02/H03/L04 完成或 UI 已接通。report KPI 计历史头数，不重新准入报告内容；recent 的当前来源资格留原阅读服务复查。基础统计单快照，图表资格由真实服务多次读取并最终复核，不宣称与 overview 跨请求事务一致。没有新增迁移或副作用。
