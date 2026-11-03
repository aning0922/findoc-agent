# C+ M0 ADR · 独立审查前草案

状态：DRAFT，等待固定45d55d7源码上的Astra独立审查，再明确标记FROZEN。工作包contracts是输入，不是已实现OpenAPI。

1. 独立C+branch/DB，旧ResearchRun/v1三指标/v2 instant和已应用migration不改。所有GET业务读取不重算/发模型；官方搜索GET可发明确搜索的受限官方元数据请求，但不下载PDF或授予资格。
2. 新API优先/cplus命名空间避免与旧/companies /financial /reports产生同名语义；operation_id UUID、语义digest、UNKNOWN不自动重发；mutation的最终发布由捕获当前generation/instance/principal的root边界保证。
3. 公司候选选择后绑定security_code+exchange，名称不是授权。官方网页AJAX仅实际观察的有条件adapter，不视为开放稳定API；海尔为非旧目录目标，全文/摘要/修订分开，未知字段null。
4. 跨代cache只共享官方公开PDF字节，不共享索引/上传/会话/研究/凭据。未知SHA先隔离下载并验magic/长度/实际SHA、封面身份；原旧SHA强校验downloader合同不放宽。controller拥有cache写入口，child仅请求有限announcement能力；最小broker合同待审。导入仍调用本代SourceService.upload/processor，缓存命中不等于READY。首版仍20MiB，不为新样例自动放大。
5. GC仅对controller自身标记的已退出旧代，先dry-run与PID/birth/pgid退出证明；无symlink、不碰seed/cache/budget/其他开发库。共享cache不受generation reset清理。
6. StatementCellV3：完整source/parse/evidence身份；instant恰有as_of_date、duration恰有start/end，报告年份不能替代财务期间。raw_decimal+unit+normalized_decimal CNY保留；合并/母公司与basis明确。candidate/confirmed/unsupported和来源/转录/解释审阅分轴。确认只从服务端review快照、owner gate和本人明确动作生成receipt，不能接收客户端编造金额/authority。
7. 趋势/体检/同行/分部使用程序Decimal，同scope/basis/period/currency再计算，候选只叫待核对观察、confirmed需有效receipt+current source。上年0/负/缺值单列，年份缺口null，分部不完整不强制100%。ROE无平均权益只解释不计算。
8. 混合检索：旧dense+独立FTS trigram、RRF rank融合、段落/章节/表格轻量rerank，先后验证固定源身份。旧风险题委托理财误命中保留before/after，词命中诊断不能冒充人工precision。
9. OCR不能伪装legacy SearchHit/fast evidence或READY。独立typed OCR SourceEvidenceRef包含artifact/hash/engine/page/bbox/transcription_unreviewed，显式enrollment及当前scope，原图链接；禁止财务计算授权。研究接线最小合同待Astra审核，复用现provider/研究界面/报告adapter，不新造脱节平台。
10. 有限batch≤12格，首验2x2，串行默认、最多并发2，每格明确plan/source/approval/operation+独立失败；UNKNOWN不重发，取消仅未开始。复用现showcase jobs与总provider账本。24固定题中的核心12需实际tier证据，不只intent JSON。
11. 导出冻结同一服务端report revision及业务附件快照；只读CSV BOM/XLSX三sheet/PPTX5–8页/PDF复用print，候选/AI审阅/来源/财务期间同步，Decimal原字符串保留，防公式注入。C+附件版本不回写旧report snapshot。
12. 同一既有5元ledger跨C与C+保留，local launcher显式指向既有ledger而非默认创建C+额度；所有provider物理call只root派发并持久预留。M0无付费call。任何新预算/公开部署/不可逆合并须另有用户授权。
