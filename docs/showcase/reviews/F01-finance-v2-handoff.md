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

## F02 implementation and handoff

F01 commit：`21ef4a070057a963ae43b3ce32b7663dcaa4bebb`。F02 在同一新分支接力，最终 SHA 由交割回复给出。本树无旧模块/主控热点改动。

实际实现：

- `extraction.py` 只读取服务器保存的 `PDFLayout`。精确匹配合并资产负债表（含续表）、项目行、完整日期列、资产总计/负债合计（或负债总计）、人民币单位及企业会计准则声明。日期拆字仅按真实bbox拼回，金额必须整格合法且完整落在相应日期列；不从文本找第一个数。母公司、合并/公司混合视图、合并金额格、重复日期、冲突金额、无单位/日期、未来于报告期末的时点均unsupported。
- 首片只支持现有fast-pdf的不可变layout；未知/OCR parser保持unsupported，等待v2 artifact/身份/转录审核adapter，不能因为OCR ready直接准入。每项保留原标签/原金额/原单位、金额行cells、日期列cells、合并标题cells、单位cells、layout SHA、evidence_id/物理页、完整PDF/source/parser身份和basis refs。
- `FinanceStore` 仅创建当前root的 `finance-v2.db` 与fv2_*表/不可变触发器。旧documents库以URI `mode=ro`附加，用现有 `verify_selection_in` 加最终公司/证据/geometry复核；不写旧库、不调用旧迁移。当前最终跨库事务要求source非WAL；检测WAL时503 `source_wal_atomic_fence_unsupported`，不宣称覆盖此竞态。
- collect生成候选；GET按当前源和回执重新分类。当前源失效时status=unsupported/value_decimal=null，历史金额只在historical_value_decimal中保留。不同披露版本不自动选择或合并。
- reviews/receipts/revocations/analyses均追加快照，哈希校验；独立operation ledger先预留UNKNOWN再执行，相同ID同请求复读、不同请求409，UNKNOWN不自动重放。operation查询结果明确historical_snapshot=true，不是当前事实资格授权。
- analysis仅接收选定metric_id列表；真实当前local_operator回执才可进入内核，测试回执一律排除。相同企业/文档/来源版本/PDF SHA/合并范围/会计基础/定义/时点方可用Decimal计算负债÷资产×100；资产<=0、负债<0拒绝。明确ROUND_HALF_EVEN、6位小数、formula/input_refs/confirmation_refs；重放也复核原回执与当前来源。没有计算真实未确认候选的“正式比率”。

### Root integration signatures

```python
from app.finance_v2.service import ExtendedFinanceService, OwnerAuthorization
from app.finance_v2.api import create_finance_v2_router

service = ExtendedFinanceService(runtime_root, source_service)
router = create_finance_v2_router(service, owner_authorizer=owner_authorizer)
# 主控唯一负责 app.include_router(router)
```

`owner_authorizer(request: Request) -> OwnerAuthorization | Awaitable[OwnerAuthorization]`。对象字段精确为：

- `runtime_root: Path`：必须等于此service固定generation root；
- `principal: str`：服务器确定的owner审计身份，不接收浏览器actor；
- `expires_at: float`：服务器Unix截止时间，service在入口和最终receipt/revoke事务复验，不应给无限期能力。

按主控确定的接线：只在 `showcase_generation` 非空且通过 child `InternalBoundary` 的runtime注入验证器；验证 gateway注入的 `X-Findoc-Owner-Authorized:1` 和固定 `X-Findoc-Generation` 相符，否则403。不要直接信任公开浏览器同名header。经典入口不注入验证器时确认/撤销503关闭；callback必须返回上述对象，返回True不能授权。

需主控登记的native-operation mutations：

| 路由 | 权限 |
|---|---|
| POST `/financial/extended-metrics/collect` | 普通有效lease |
| POST `/financial/extended-reviews` | 普通有效lease（只保存选择快照） |
| POST `/financial/extended-analyses` | 普通有效lease，但服务端只admit已有真实有效确认 |
| POST `/financial/extended-confirmations` | owner-only，并注入可信owner header；仍要求真人明确confirmed=true |
| POST `/financial/extended-confirmations/{receipt_id}/revoke` | owner-only，同上 |

GET均由现有gateway lease保护。本提交没有修改gateway/runtime/UI。人工作业中不得让Agent代点确认；测试 `confirmation_kind="simulated_test"` 仅允许仓库外、目录名以 `findoc-finance-v2-test-` 开头的隔离root；该参数不在任何HTTP DTO中，模拟receipt不使GET显示confirmed，也不被生产analysis接受。

### Real PDF candidate evidence

只读原件：`/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-source-preflight-20261103/gree-2025.pdf`。

SHA256：`7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c`，解析前后均匹配。原件未修改，复制至全新临时对象库再用现有SourceService捕获/读取不可变layout。已用pdftoppm渲染并看过物理86/87页（印刷85/86页）；这是代理核对提取机制，不是用户财务签核。

| metric_key | as_of_date | report_year / period | 原文金额（人民币元） | 物理页 | 状态 |
|---|---|---|---|---|---|
| total_assets | 2025-12-31 | 2025 / 2025 | 391,371,999,819.49 | 86 | candidate |
| total_assets | 2025-01-01 | 2025 / 2025 | 368,031,704,522.86 | 86 | candidate |
| total_liabilities | 2025-12-31 | 2025 / 2025 | 241,580,719,144.79 | 87 | candidate |
| total_liabilities | 2025-01-01 | 2025 / 2025 | 226,518,009,574.89 | 87 | candidate |

期初原文是2025-01-01，**没有改写为2024年**。另用合成2031年报含2030-12-31列验证report_year=2031、period=2030分离。值归一化为Decimal字符串，unit=CNY_YUAN，period_kind=instant，confirmation_ref=null。

最终完整JSON证据：`/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-finance-v2-real-proof-n7a87t1w/finance-v2-evidence.json`。含当前source身份、每项原单元格/表头/单位/合并范围/证据页及替代项声明，不复制原PDF入Git。真实：官方PDF、fast parser、SQLite immutable evidence、来源复核；fake：embedding、vector index、chunk IDs。LLM=0、真人签核=0。该真实测试对 `/extended-analyses` 断言403，未产生local_operator receipt。

### Checks / replay / limitations

- PASS：显式真实资料运行 `FINDOC_FINANCE_V2_PDF_ROOT=/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-source-preflight-20261103 python -m pytest tests/test_finance_v2.py -q -s`，**3 passed，约13.44s**。
- PASS：`python -m ruff check app/finance_v2 tests/test_finance_v2.py`；git diff check。
- 默认不设PDF env时：2 PASS / 1 SKIP，真实资料项明确skip，不能当完整通过。显式env运行才有上面的真实PDF证据。
- 三项代表性检查覆盖：日期/单位/几何及冲突/母公司/缺失拒绝；严格API/幂等/owner缺失503及过期403/模拟回执不admit/不可变receipt/撤销/源对象变化后失效；一份219页真实PDF的4个时点候选和无确认分析阻断。
- 警告保留：PyMuPDF/Swig相关5条DeprecationWarning（SwigPyPacked/SwigPyObject/swigvarlink）；未隐藏，未宣称修复。
- 历史FAIL保留：首轮1PASS/1FAIL/1SKIP，失败为simulated_test测试root校验顺序不符；已将kind/root/source归属检查提前到创建v2库前，复跑通过。初轮Ruff有unused import及测试单行语句问题，已修正复跑通过。
- SKIP：真人local_operator确认与真实已确认比率正向路径、主控owner header/gateway/runtime接线、UI、OCR artifact、其他三份PDF、旧全量财务回归、生产/部署；没有补造真人签核。此提交只交2种真实可测新增候选指标和严格分析阻断，不能称全财务验收。
- 当前只支持有充分证据的PRC_GAAP合并年度balance sheet、明确日期列和人民币单位。没把期初自动改前年期末，不支持母公司混排/任意合并表格/模糊年度/未知OCR。WAL来源库保留关闭状态，后续主控如需要再专项设计。
- 回退为逆序revert F02/F01；finance-v2.db是generation-local，新代从受控seed恢复。不要修改旧3指标枚举/CHECK/迁移，不把simulated receipt写入正式seed。未push、部署或合并main。
