# F01/F02 extended finance v2 — frozen implementation handoff

2026-11-03，工作树 `/Users/aipuli/.codex/worktrees/4eab/findoc-agent`，新分支 `codex/showcase-f01`，基线集成 `c826a05b573beef55111bb5d137f87ba000e9adf`。L01旧分支保留。范围仅新增 app/finance_v2、tests/test_finance_v2.py、本交接文件；不改旧指标/事实/迁移/runtime/gateway/UI。本节在实现前落盘，作为主控接线小合同。

- Constructor: `ExtendedFinanceService(root: Path, sources: DocumentSourceService, *, confirmation_kind="local_operator")`；仅在给定代际 root 创建独立 `finance-v2.db`，无旧 migrations 注册变更；root必须为主控当前 runtime 的固定root。
- `create_finance_v2_router(service, *, owner_authorizer=None)`；owner_authorizer是主控注入的服务端可调用验证器，确认/撤销路由未注入时503关闭。主控仍必须将这些写登记owner-only，不向Agent工具暴露。开发/测试不执行真人签核。
- POST `/financial/extended-metrics/collect {operation_id,company_id,document_id,expected_source_revision}`：只有服务器 `parsed_evidence` 返回的immutable geometry可收集 total_assets/total_liabilities；精确总计标签、明示时点列、人民币单位、合并范围需全部证明。返回 `schema_version=extended-metric-collection-v2,metrics[],limitations[]`。候选持久不可变，歧义/缺项unsupported，零模型。
- GET `/financial/extended-metrics?company_id=`：`schema_version=extended-metric-list-v2,company_id,metrics[],limitations[]`。每项按API_MINIMUM `extended-metric-v2`，保留report_year与period(as_of_date年份)分离；旧源/回执失效不冒充current confirmed。
- POST `/financial/extended-reviews {operation_id,metric_refs:[metric_id...]}`：保存确定性候选选择快照 `review_id,review_sha256,metrics[],acceptable`。不做确认，不接受客户端金额。
- POST `/financial/extended-confirmations {operation_id,review_id,review_sha256,confirmed:true}`：只允许明确真人+主控owner gate，服务端重验source/immutable evidence后追加独立v2 receipt；测试配置只写 `simulated_test`，生产分析绝不admit simulated_test。此任务真人执行数0。
- POST `/financial/extended-confirmations/{receipt_id}/revoke {operation_id,reason}`：同owner-only，append-only撤销；不修改历史回执。
- POST `/financial/extended-analyses {operation_id,metric_refs:[metric_id...]}`：严格只收已选ID，重验local_operator有效receipt+当前源+相同公司/版本/口径/时点，Decimal计算 `total_liabilities / total_assets * 100`，0分母/负值/不同版本/时点failclosed。衍生值保留formula/input_refs/来源，分析不签原始事实。不实现净利率。
- GET `/financial/extended-operations/{operation_id}`：只读查证结果；所有写UUID幂等，同UUID不同动作/请求409，UNKNOWN不自动重做。

读取真实资产：已ls核对集成树 `data/showcase-source-preflight-20261103/{gree-2024.pdf,gree-2025.pdf,midea-2024.pdf,midea-2025.pdf,preflight.json}`。仅只读其中有充分layout的一份作为候选证据，原PDF不修改；解析/保存至新临时root，fake embed/index明确标注、LLM0、human approvals0。实现与实际检查结果后续追加，不预先标PASS。

F01协议实现：`contracts.py` 为strict请求，`models.ExtendedMetricV2`为strict输出（首片只允许instant的2原始指标+debt_asset_ratio，不声明净利率/流量支持）。明确unsupported无可用值、period来自as_of_date、原始CNY与衍生PERCENT分离；confirmed输出必须携带local_operator回执。未修改旧3×2合同或迁移。F02具体提取/服务接线与实测证据在后续独立提交追加。
