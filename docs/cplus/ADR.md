# C+ M0 ADR · FROZEN v1

状态：**FROZEN v1（2026-11-03）**。主控已实读并采纳Astra Ultra独立审查129d8d4→3ae6b43的八项P0合同修正；下列冻结决定覆盖早先草案中的“待审”项。工作包JSON仍为原文输入，不能当成已实现OpenAPI。

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


## 冻结补充与最小实现取舍

- **路由**：新业务统一 `/cplus` 前缀（浏览器另加/api），精确接口与ports见 contracts/API_V1.json、contracts/PORTS_V1.md。官方联网查找改显式POST search operation，GET只读已存snapshot。所有操作绑定trusted generation/instance/principal；未知结果保留同UUID查询。
- **动态导入**：company_id可空，但必须confirmed及create_company为true且UI明确“导入并建立企业资料”；先固定官方candidate下载并核对PDF唯一法定全称/代码/市场再创建本代公司；已有主体冲突needs_manual_review，不拼全称/静默改名。默认A股SSE/SZSE，其他市场可显示候选但导入unsupported。
- **最小cache边界**：首版discovery搜索/候选/导入coordinator和PublicPdfCacheBroker均在C+ controller进程实例化；同进程ticket调用取代额外内部HTTP队列，child从不接收可写cache目录、原始外部URL或任意cache fetch能力。root注入CapturedGenerationBinder，只向捕获的当前child private channel调用既有company/upload；每次前后lease fence。这样满足控制侧唯一writer，避免不必要服务部署。worker以authorize/fence和binder callback开发，root独占demo app注册。
- **财务v3**：采用review完整time union及多轴状态，collection显式POST、review准备与owner确认/撤销分离，不给OCR财务确认。普通同比只有earlier>0；<=0返回reason，不自动用abs公式；如需abs指标另名absolute_base_change-v1。v3 receipt不进入旧v1/v2事实集合。
- **检索score**：CPlus RetrievalCandidate独立dense_cosine/lexical_rank/fusion_score/rerank字段。旧fast会话兼容adapter只接受有真实cosine并通过旧0.55门槛的fast hits，RRF只排序，lexical-only不伪造成cosine；新CPlus工具用显式versioned relevance policy和typed verifier。
- **OCR最小真链**：typed enrollment→独立context→单次有界answer，schema cplus-research-answer-v1；最多1次同guard provider，GET纯读取。旧非READY document不改状态、不进旧conversation/ResearchRun。研究助手同一入口按legacy_conversation/cplus_context选择transport。源/artifact/metadata/选页/记忆generation在最后COMMIT重查；OCR不授财务能力。优先真实派生扫描样本，无法证明企业身份则只解读该文件转录。
- **批次**：显式可能付费的preparation先生成真实child intent/plan；approve只接已存immutable manifest及child plan triples。默认串行1job，内部仍最多2agents，CAS queued→dispatching，UNKNOWN不重发，取消仅未dispatch；不加新队列/多租户。
- **报告**：typed ReportRef区分legacy_v1/showcase_v2/cplus_v3/preset_archive；C+组合快照另存且旧revision不改。显式POST导出产生immutable manifest，GET下载同bytes；冻结来源/当时status/renderer/time，权限拒绝不能降级成historical正文。XLSX保留Decimal文本原列，便利数字列仅无损≤15位，防公式注入。
- **当前范围**：二年格力三表、海尔新官方来源、至少一组分部、OCR派生单页、2x2批次。没有数据不画0；360默认真实/空态、候选显式切换、示意独立虚构企业。保留5个一级导航，全部高级模块二级接入。
- **资源**：root launcher必须显式指向原C既有canonical ledger，先只读校验路径/0600/单link/同Git common-dir/schema/cap5，缺失拒绝；不调用constructor创建新额度。M0无付费，后续真实provider仅root统一执行。

八个review P0已在**合同层**解决，不代表对应业务代码已经完成。实现阶段仍须逐项验收。原包字节保留，CSV使用CRLF在归档目录允许cr-at-eol；主控owned文件diff检查正常，初次归档whitespace告警未冒充PASS。
