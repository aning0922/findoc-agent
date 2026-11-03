# C+ 已知限制与未通过项

## 外部模型与人工

- **BLOCKED_EXTERNAL**：同一5元账本新增4次C+SDK调用全部ReadTimeout/UNKNOWN。无法确认供应商认证POST健康或实际账单；不推断供应商整体故障。已停止进一步诊断/自动重试。程序规则/双侧原文/纯工具批次可运行，真实新AI解释、多Agent解释及完整问答评测不宣称通过。原C历史模型结果只作历史展示。
- **HUMAN_PENDING**：没有代用户点击财务确认。v1 ACCEPT→SAVE→RESUME与独立v3 owner gate保持，正向确认图表需用户本人操作。来源封面身份核验、数值提取、模型解读都不等于财务核准。
- 人工检索语义标注未进行，precision@5/MRR为null。固定24问题只有分层组件证据，完整模型答案PASS0；原15题历史5partial/10skip保留。

## 本轮已复现并修复（历史失败保留）

- 原多库读锁/innerCOMMIT栅栏、研究记忆嵌套写锁、fast收藏错误字段422、OCR历史freshness、报告年与比较期间混淆，已分别修复并独立复验；原Astra报告留存。
- 官网证券match_type进入公共版本摘要，拼音与代码查询导致同PDF重复下载。d7b4160修复，只排除搜索提示，完整候选SHA仍覆盖全部字段；真实新generation跨查询cache命中已验。旧key不迁移，首次新key可冷下载一次。
- 首轮真实2×2 start260秒HTTP503，最终效果UNKNOWN未重发。51b791e将候选排序后逐条调用原verifier补足top-k，无跨次来源缓存/不放宽准入；worker四格HTTP119秒与主控native四格均已通过。HTTP超时未扩大。旧失败档案batch-v3-corrected保留。
- 首页原默认公司覆盖了有数据企业，预置曲线空态；现按明确选择或预置有数据企业绘图。真实首页1440/1280/390已复测。
- 打印原21页通用字段堆叠，已改业务表/来源节选；新版实际2页，逐页PNG查看无遮挡。旧21页证据未替换。CSV在Git被CRLF转换曾影响SHA，现.gitattributes -text，实际Gitblob字节与工件一致。

- 最终Astra复现导出父会话撤销后已生成文件可读P1，47e5d23下载重新复验精确domain/id/revision/SHA展示权限；受控HTTP撤销403/恢复原bytes和ETag/不rerender，独立841927f复验关闭；真实Chrome导出11检查复测通过。

## 限定支持范围/P2

- 动态巨潮为实测公共网页adapter，不是稳定API授权承诺；限频、短超时、验证码/限制不绕过，官网跳转/手动上传回退。美的2024封面缺证券代码自动导入拒绝，使用明确手动上传，并保持basis unknown/候选；未弱化自动身份闸门。
- 三家公司五份完整年报、有限三表/产品地区模板；复杂表格可unsupported。未把未知同行行业/币种/合并口径自动补齐；缺值不补0。财务比较候选明示，未全行业覆盖。
- OCR仅本机macOS Vision真跑，68行/54cell文件转录；原扫描文档legacyFAILED保持。未声称OCR身份已核验、财务已核准或OCR dense向量召回。LinuxOCR未验证。
- 部分现金流问题首条仍为管理信息，精确六题对照保留，不把全文引用exact验证当语义正确。RRF/章节启发式不冒称训练式cross-encoder reranker。
- 纯工具批次非新增付费多Agent实证。取消只对未dispatch格有效，UNKNOWN不自动重跑。
- XLSX/PPTX需独立renderer Python依赖，LibreOffice中文渲染需系统字体/fontconfig。Git不含私有/公开PDF种子二进制与模型权重，不能声称clone即完整运行。
- UI长原文/完整哈希部分页面较长；模板竞争对标先生成单企业草稿，其他企业需显式选择；不是自动同行报告。peer/segments可选图表草稿回调尚未全部挂载，360点位追问已贯通。
- Node构建大chunk warning、React/hooks lint warnings、SWIG DeprecationWarnings保留。原C旧57fixture setup ERROR未因C+局部绿色而消失。无生产高可用/并发规模验收。
