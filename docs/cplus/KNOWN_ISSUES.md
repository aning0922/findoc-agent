# C+ 已知限制与人审边界

2026-11-03当前状态。原“4次模型请求全部超时”的检查点已由新真实成功更新；[原记录](checkpoints/KNOWN_ISSUES-e510876.md)仍保留，旧UNKNOWN4未重放或退款。

## HUMAN_PENDING

- 本人财务核准0。三表候选、Decimal比率、趋势/同行、AI解释都不等于确认。正向owner确认图表需用户本人对照PDF/期间/币种/范围操作；不由Agent代签。原v1 ACCEPT→SAVE→RESUME不变。
- 人工检索相关性/引用支持claim/年度标签正确性、单多Agent质量比较未标注。precision@5/MRR为null，固定题executed不等于正确率，AI自评不替代人审。

## 有限支持 / P2

- 巨潮是实测公共网页adapter，访问条件可能变化。合理频率和HTTPS、限量下载，不绕过验证码/限制；官网跳转/手工上传回退。美的2024封面缺证券代码时自动绑定拒绝，显式上传仍保持basis unknown，不能自动改为已核验。
- 3家公司/5份完整年报，有限三表和分部模板；未知行业/口径/币种/合并范围不补造。复杂表格保留unsupported。缺值/不同比较期/非正分母不补零或乱算同比。
- OCR仅macOS Vision真实执行，Linux OCR未验。转录待审/身份未核验，不进入旧READY或财务事实。OCR词法检索与fast BGE dense分层，不能声称OCR已进入同一dense库。
- 经营风险章节排序已有真实before/after；现金流问题仍有行政类无关首条，E01-01实际模型如实报告缺证。人工相关性统计未完成，不能用精确引用SHA代替相关性。
- 原单年度overview PPTX保存5候选点和真实AI，但没有可用双期趋势图；该失败发现保留。受支持的双年cash/真实同行/两年chart draft可展示业务图，不补造额外年份。
- 全量版本列表在重复研究很多时较慢；精确报告deep-link已先筛domain/id/revision再重验，真实原生闭环通过。旧30秒脚本GET超时、首次未等待资料导致selector失败均保留。脚本错误输出移除可能含会话信息的传输日志；对应测试会话已登出撤销。
- 原生同图点到原PDF场景若长表原文无法精确匹配，明确降级原页（本次最终点图实际page_only），不伪装高亮成功；真实OCR坐标和匹配原文quads能力另有受控/真实OCR证据。
- XLSX保留Decimal字符串；PPTX图形用浮点仅作可视化，精确金额看表格/CSV。单/多Agent长解释在PPTX可明确标注节选，完整文本在CSV/XLSX；没有假装全文都在每页。
- Git不包含PDF/seed/模型权重/私有DB。新机器需提供bundle及本地依赖；中文渲染需要有效字体/fontconfig。默认bundled LibreOffice缺字体初次失败已保留，CJK配置后逐页复查。
- 大chunk、hooks lint与SWIG warnings保留；原C旧57fixture setup ERROR不会被C+绿色洗掉。没有生产高可用、多租户/极限并发或公开发布验收。

## 已修复且留有反例

年度AI提示预算重复来源元数据、排序前过度验证耗时、公共cache搜索提示进入版本key、已保存文件忽略parent撤销、恢复AI计划误报零调用、legacy纯工具恢复误禁用、重复相同提取视图、深链接混合多revision/全量耗时，均有独立提交与证据。UNKNOWN仅查询原操作，不自动重新执行。原始模型超时、输入预算拒绝、FTS五来源422、脚本失败与哈希不一致均按原层级保存。

已知cash年份金额错配另经a1920c0非数值模板政策处理，真实新单次解释成功且无数字，Astra复核f657917关闭已知样本；原child供审阅但不可独立报告导出。规则字符门禁可能保守误伤普通词，仍不能代表语义验证。PDF不再把规则JSON当原文，段落可断行；修正6页PDF仅检查首末，6页PPTX全部查看。
