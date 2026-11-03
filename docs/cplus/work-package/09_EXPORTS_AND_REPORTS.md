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
