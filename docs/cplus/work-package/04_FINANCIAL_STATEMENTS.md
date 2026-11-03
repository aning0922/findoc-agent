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
