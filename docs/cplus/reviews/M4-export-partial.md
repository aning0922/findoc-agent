# M4 export partial handoff

基线 `79456a4`，独立分支 `codex/cplus-exports`。本次仅实现 `app/exports_v2/csv_projection.py` 纯函数和一个安全测试：只接受显式 `showcase-report-v2` 保存快照、保留引用和审阅状态、UTF-8 BOM、防公式注入；缺失的期间/单位/数字留空。并非可用导出功能：尚无可信 domain/id/revision/SHA resolver、身份与publication fence、操作持久化、POST/GET、文件存储、XLSX或PPTX，因此不能接入UI或宣布X01/X02完成。`render_showcase_csv` 的调用者必须先授权并核验全部来源/身份/状态。

单测1 passed；没有真实报告、provider或人工财务确认。未读取私有配置或账本。已阅读Spreadsheets/Presentations/PDF技能并取得bundled runtime，尚未生成或渲染XLSX/PPTX。后续需要完成三sheet原Decimal文本、不可变files、5–8页PPTX与实际渲染检查；报告rev和历史source权限不得降级。
