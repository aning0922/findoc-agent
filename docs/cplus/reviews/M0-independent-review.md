# FinDoc C+ M0 独立产品／架构审查

日期：2026-11-03。性质：针对当前 C 接口的设计审查；下列新增合同均是**待 root 冻结与实现的建议**，不是已实现 API。

## 结论与范围

**建议有条件通过 M0 方向，但工作包的两个 JSON sketch 不能原样冻结。** 必须先纳入下列八项合同修正，才能让 DATA/FINANCE/RESEARCH/UI 开始按共同接口开发。这些 P0 是“如果按草案直接接线，会破坏主链或可信边界”的设计阻断，不是本轮已复现的 C 生产漏洞。允许叶子模块用冻结后的 fixture 并行；不能把 fixture、候选图或架构评审当 C+ 验收。

- 本工作区开始 tracked/untracked clean，保留旧分支，从精确 `45d55d75662f01d9bc78da1a946d845a01a27480` 新建 `codex/cplus-m0-review`。未 fetch/更换基线；远端新状态由 root 核对。
- 实读工作包 `/Users/aipuli/Downloads/FinDoc_CPlus_求职展示增强_完整工作包_20261103` 的 README、00、02、03、04、05、08、10、11、12、15 和 `contracts/CPlus_{API,DOMAIN}_SKETCH.json`；另外读了直接相关的 06、07、09。未把外部工作包复制到业务目录。
- 读取现有 finance_v2、disclosures/download、document preparation/source、parse-v2、selected RAG、conversation tools、showcase scope/jobs/findings/store、reports、runtime 装配、demo process/budget/launcher、productRoutes/AppShell/相关 UI；具体位置见各节。
- 本轮只写此文档。不读 `.env`、密码、私有数据或真实业务/预算数据库；不调用付费 provider，不启动其他 agent/会话，不修改集成树或业务代码。

## 可立即冻结并派工的 M1 最小切片（优先于后文扩展选项）

root于审查中提供 `8c2c451` ADR/UX、`40ea97d` D01；已通过Git对象只读查看ADR、UX、D01报告和公开PDF封面预检JSON，**未切换本审查源码基线**。认可root五入口、`/cplus`新增命名空间、20MiB、串行batch、同一5元账本的方向；下文裸路由建议均可统一加 `/cplus`，既有API不改。以下是三个worker现在即可采用的最小冻结建议，不要求先完成后文所有M3/M4扩展：

| Owner | 立即实现/交付 | root必须承担的窄接线 | 本阶段不扩张 |
|---|---|---|---|
| DATA | fixed-origin discovery、candidate snapshot、import coordinator、cache broker port和fake实现；`POST /cplus/discovery/imports`支持下述“导入并建公司” | controller broker唯一writer、私有ticket通道、current generation检查、原upload接线 | 不共享OCR/dense；20MiB；动态公司首验SSE海尔，HK等未支持市场显式拒绝；GC先dry-run |
| FINANCE | 独立v3 time union/cells/reviews/receipts/trends；fixture+真实PDF候选解析 | owner=True mutation、能力注入、source final guard、公司360数据adapter | OCR财务确认不开放；ROE只释义；不改旧fact/迁移 |
| RETRIEVAL | fast scope hybrid adapter；typed OCR enrollment/context/verifier；单次有界OCR answer；retrieval diagnostics | 同一UI transport、同一bounded Provider/store预算、publication guard、源索引阶段接线 | 不先重造multi-agent jobs/新队列；OCR-only不进旧Conversation/TurnResult；不改legacy READY |

**选择最小OCR执行端点：** M1先实现 `POST /cplus/research/answers {operation_id,context_id,context_revision,context_sha256,question}` 和 `GET /cplus/research/operations/{op}`/`GET /cplus/research/answers/{id}`。用户明确提交后：reserve op+budget→当前typed scope验证→有限检索→如有足够证据最多一次同guard模型调用（可复用现有选择引用JSON模式）→独立CPlusEvidence逐条校验→带context/Memory/源guard的immutable answer发布。无证据直接不足，不强行调用。输出 `cplus-research-answer-v1`，findings+typed refs+coverage+data/review axes，来源未绑定企业则不得宣称企业身份。GET不调用模型，UNKNOWN原UUID只读恢复。界面在现AI助手内增加context transport，保留计划型单/多Agent旧链；OCR演示是真实“资料问答”而不是伪造已有多Agent完成。后文3.1的full job port为M3按需复用执行器的扩展，不是三个worker开工前置。

**最小score桥接：** fast旧对话adapter仅输出有真实dense cosine且通过原0.55门槛的合法fast hits，RRF只排序、独立trace保存fusion分；lexical-only首版不进入旧路径（明确降级能力）。showcase/CPlus新工具使用独立versioned relevance policy与typed refs，不把fusion score写成cosine；所有结果仍exact/typed验证。这样M1能做真实before/after和OCR，不需全局修改旧RAG gate。增加lexical-only到旧对话需root后续单路径gate变更+评测，不列为生产安全重构。

**最小broker实现：** 当前单controller内一个PublicPdfCacheBroker实例+controller-held候选/ticket SQLite、有限private prepare/read接口，复用现InternalBoundary类似的instance认证和generation fence；不建消息队列/分布式锁/独立服务部署。磁盘上限/拒绝继续下载先实现，自动LRU淘汰与完整真实GC可作为D05独立验收，不能为了它阻塞首次官方导入。旧C14530与旧controller完全不动，C+另根另端口。

D01已提供当次公开观测证据（不是本审查重发网络）：A/H相同orgId、代码600690/06690与市场须组成证券身份；中文全文1225038336、245页、1,823,191 bytes及SHA `14186f9f9b47f687c527ba14825664f3b09e51759d581636cddcc248f26e3660`。条件可用不是官方长期API承诺。root的6题dense基线没有直接命中委托理财短语；旧C物理70页委托理财引文是**另一条历史失败证据**，评测不能把两者合并冒称本轮before命中。root React三宽8视图为UI_MOCK，不是M1真实接线验收。

## P0 冻结清单

| ID | 草案不能直接采用的点 | 最小冻结决策 / 出口 |
|---|---|---|
| P0-01 | StatementCell 的时间域、authority、receipt 混合；statement-reviews 将 review/confirmation 合并 | v3 独立记录与 owner confirmation；显式时间 union、披露/定义/金额单位身份；review 与确认分开；旧 v1/v2 不改 |
| P0-02 | 动态下载没有可信预置 SHA；共享 cache 没有导入 token 与可撤销代际能力 | server-owned candidate snapshot/token；控制侧唯一 cache writer；每代独立绑定；公有 bytes 不携带业务权限；GC 排除规则先冻结 |
| P0-03 | 把 OCR hit 直接投给旧 PreparedDocumentSelection/quote verifier | 新 typed OCR selection/ref 与检索资格；不改旧 READY；接通 scope→retrieval→finding→publication 全链，不能只接 FTS |
| P0-04 | RRF 分数直接塞旧 cosine score，或检索排序就算语义支持 | 分离 rank score 与 relevance gate；保留 exact verifier；showcase 和旧对话各有明确适配层与回退 |
| P0-05 | BatchPlan 直接包含客户端 plan+explicit_confirm，默认自动创建子 job | 冻结真实 child plan ID/revision/hash 清单并显式批准；持久 child operation 映射、dispatch CAS、取消边界、总预算 |
| P0-06 | `/reports/.../export` 模糊指向旧报告；用 v2 revision 更换内容 | typed ReportRef + 新增 v3 组合快照；旧 v1/v2 只读投影；导出冻结 manifest；授权失败不降成 freshness unavailable |
| P0-07 | 新公司沿用 C 启动器默认示意曲线、候选与已确认共线、图表追问携带值作权限 | 360 默认真实/空态，候选显式开关、示意隔离；导航携带版本化 scope/ref，服务器恢复权限，点击只生成草稿 |
| P0-08 | C+ worktree 启动器默认新账本，或复制旧账本后各自花钱 | root 显式注入原 C 同一个 canonical ledger；缺失拒绝；不能复制、补建或改 cap；所有模型入口共用 guard |

## 1. 财务 v3：最小可冻结合同

**当前证据。** `app/finance_v2/models.py:11` 的 ExtendedMetricV2 明确只允许 instant、consolidated 和三项资产负债指标；`contracts.py:48` 的 Confirm 只接 review_id/hash/confirmed。`service.py:49,76,224,249,266` 已有 owner 能力、source guard、确认/撤销和 Decimal 准入；`store.py:21,40,52` 独立 append-only 表并附加 source DB 检查。`runtime_factory.py:326` 以私有请求标记和 owner expiry 构造能力。旧 `ConversationTools.financial`（`app/conversations/tools.py:141` 附近）仍要求 annual period 与旧明确 fact selections。不能让 v3 receipt ID 自动被旧路径认作旧 fact ID。

冻结 `statement-cell-v3` 为不可变候选记录，字段至少：

```text
cell_id, cell_revision, payload_sha256, extraction_version, metric_definition_version,
company_id, document_id, source_revision, content_sha256, parser_version,
report_year, disclosure_version, statement_kind, row_key, raw_label,
time = {kind:'instant', as_of_date}
     | {kind:'duration', period_start, period_end, period_type:'annual'|'quarter'|'ytd'|'other'},
scope:'consolidated'|'parent', basis, currency, raw_value, raw_unit,
normalized_unit, normalized_decimal:string|null,
evidence_refs:[EvidenceRef], limitation_codes:[], extraction_status:'candidate'|'unsupported'
```

日期用 ISO date 严格解析；instant 不允许 start/end，duration 不允许 as_of_date、start<=end。report_year 是报告标签，不能替代数据期间。现金流表的期末现金仍用 instant。财务 `scope`/basis 是指标口径，不是假定每份 PDF 唯一口径。披露版本包含实际 document/source revision；同公司同期间同指标不同版本不得 latest 自动覆盖，用户明确选择版本。归母净利与合并净利使用不同 row_key/定义。

把草案 `authority`、`DataOrigin.data_origin` 拆为独立轴：`data_origin=live|preset_demo|illustrative|fake`；`source_kind=fast_text|ocr_artifact`；`source_status=current|stale|unavailable|unknown`；`transcription_review=unreviewed|human_reviewed|not_applicable`；`financial_review=unconfirmed|local_operator_confirmed|revoked`；`interpretation_review=ai_unreviewed|not_applicable`。`source_kind=fast_text` 或 excerpt exact-match 不能自动把转录/金额变为 human_reviewed。UI 的“已核准/候选”等是这些轴的投影，不能反向作为权限入参。适配旧域时映射旧 `current_valid/current`，不改历史 enum/hash。

建议后端路由（下文全部不带 `/api`；浏览器同源代理才加 `/api`）：

- `POST /financial/statements-v3/collections {operation_id, document_id, expected_source_revision}`：显式提取，不是列表 GET 顺手提取。返回 collection_id、immutable cells、实际阶段。
- `GET /financial/statements-v3/collections/{id}`、`GET /companies/{id}/statements-v3?...`：只读；year/kind 仅筛选，响应必须给候选版本和完整 temporal key。
- `POST /financial/statements-v3/reviews {operation_id, cell_refs:[{cell_id,cell_revision,payload_sha256}]}`：最多建议 64 个明确行，唯一性检查，返回 review_id/hash/可审项；非 owner 可以准备 review，但不能签名。
- `POST /financial/statements-v3/confirmations {operation_id,review_id,review_sha256,confirmed:true}`：gateway owner=True + 服务端 root/instance/generation/owner expiry；最终提交再次验源、值、review hash 和 owner。只收引用，拒客户端金额/status/actor。人必须实际逐条核对并点击；开发 agent 不代签。
- `POST /financial/statements-v3/confirmations/{id}/revoke {operation_id,reason}` 同样 owner gate。GET operations 保留 UNKNOWN，不擅自重新提交。

receipt 冻结完整选中 cell hashes、source identity、review version 和真实 actor/时间；撤销另存事件，不能更新原候选为永久可信。current financial eligibility 由当前源+未撤销 receipt 每次重建。OCR 候选首版可查看，但**不进入本次 v3 财务确认入口**；将来若允许，必须另有用户对照 PDF 原图与单位/时间/口径的明确流程，不能借 OCR indexing consent 实现。

派生结果 `derived-metric-v3 {formula_id,formula_version,input_refs,normalized_decimal,unit,comparability,status,reason_codes}` 全部 Decimal。默认普通增长率 `(later-earlier)/earlier*100` 仅 earlier>0；earlier<=0 时返回不可计算，差额仍可显示。工作包的 abs(earlier) 可以另定义 `absolute_base_change-v1`，必须另名“相对绝对基数变动”，不能同一“同比”字段时而采用两种公式。跨零利润需显示由盈转亏/由亏转盈，不能据增长百分比评分。ratio 负/零分母分别处理；资产负债率为百分点差；ROE 缺平均权益/定义则只释义。同比要求 duration 同长度/同季度或明确 annual；同年 1月1日与12月31日仅称两时点变化。图表缺年 null、不跨缺点连线。v1/v2/v3 DTO 不同名冒充：用于统一趋势的 adapter 返回 `{domain, record_ref, original_receipt_ref}` 并逐域准入，绝不互造 receipt。

**必须定点检查：** duration/instant 非法组合；同报告本期/比较期；负数/零/缺失；双披露歧义；模拟 receipt 不准入；owner 在提交前到期；来源更正/撤销后 chart/checkup/peer/export 不新增“当前核准”值。真候选可先完成，但 HUMAN_REVIEW 正向保持 human_pending。

## 2. 公共 PDF cache、导入 token 和 GC

**当前证据。** `disclosures/service.py:48,106` 是静态 search/import，候选硬校验 SZSE、公司名称、code；`download.py:42` 强制 expected_sha、最多20MiB，逐跳 HTTPS host/public DNS IP pinning、PDF魔数；`source_service.py:123` upload 接续既有 pipeline。`documents/service.py:110,177` 内容寻址/上传去重不能等于跨代共享资格。`demo/process.py:146` 停旧进程后 materialize 新代，没有旧目录 GC 实现。不要将全市场匹配硬塞进旧静态目录分支。

**冻结 discovery 身份：** CompanyMatch = `{provider,listed_security_id,security_code,exchange,official_name,aliases,match_type,identity_status,checked_at}`。模糊置信度只排序，不授权；同名/同 code 不同交易所必须选定。AnnouncementCandidate = `{candidate_id,provider,announcement_id,security_identity,report_year,kind,revision_kind,published_at?,official_page_url,pdf_locator,metadata_digest,checked_at,expires_at}`；缺发布/更正信息为 unknown。客户端 import 只给 `{operation_id,candidate_id,company_id?:string|null,candidate_digest,create_company_if_missing?:true,confirmed:true}`，不接受 raw URL、absolute path、任意 SHA 或公司名替换。服务端恢复并核对本代公司绑定；动态解析封面需候选身份匹配，不匹配进入 needs_review 而不是先把资料归给公司。

**法定全称与新公司最小入口（P0，不能用简称创建）：** D01 topSearch只提供zwjc简称；`SourceService.assess`（source_service.py:37–53）将Company.name与封面法定全称精确匹配，`CompanyService.create`（companies/service.py:19）又必须有name。冻结上述import body：有company_id为“导入到已选企业”；company_id=null且create_company_if_missing=true为用户明确点击“导入并建立企业资料”，否则422。先落import operation/ticket→隔离下载官方bytes→仅封面/明确公司信息页提取**唯一**法定全称、证券代码、报告年度和全文语言类型，与选中candidate的market+code核对（market由已选官方证券身份决定，代码/全称须PDF有证据）→按本workspace exchange+code查已有公司→无则调用现CompanyService.create(法定全称,code,exchange,country)，有且法定名相符则复用→调用原SourceService.upload。不能从简称拼“股份有限公司”，不能以orgId唯一区分证券；摘要/英文版另选，当前首验中文全文。封面有多个名字/代码或提取失败→needs_manual_review，用户可明确补全并在新操作中提交核验；先不创建业务公司/上传。若已有同market+code但name冲突→needs_manual_review，不静默patch公司。公司创建成功后上传失败/断线不回滚删除公司，保存created_company_id和phase；恢复按唯一market+code和本操作绑定读回，不重复create或新UUID重放。CompanyRepository已有workspace/exchange/code唯一冲突检查；碰撞时重新读并严格比对，不吞异常当成功。ticket在创建公司前绑定security_identity+明确create consent，创建后只允许一次补绑实际company_id，不能重新定向。缓存公共bytes与公司写入是两种不同副作用，均应准确记录完成阶段。

**GET 与实时发现的冲突必须明说：** root ADR已选择明确搜索GET可做有界官方metadata读取，本review接受此简化（无PDF下载、无财务/导入权限）；若需要持久搜索操作也可采用以下分阶段方案。推荐 GET discovery 列表只读最近发现结果；用户“联网查找/刷新”走 `POST /discovery/searches {operation_id,query/selected_security,year,kind}`，执行有限官方请求并保存候选 snapshot；GET search operation 读回。不让 GET 公司360触发外部请求/写 candidate token。采用root在线GET search时，只允许明确有界metadata请求/运行性缓存；服务器可缓存candidate snapshot但其ID没有导入权限。可执行import ticket只在用户POST选择后登记，不下载PDF或自动建公司。UI进入360或定时刷新不能默默启动线上发现。

**推荐 token/控制边界：** 在控制层登记不透明 `import_token`（不可猜 UUID/随机值），绑定 `{operation_id,instance_id,generation,principal,security_identity,company_id?,create_consent,candidate_digest,url_digest,expires_at,allowed_action}`。浏览器拿不到 cache path；进程间请求须验证私有通道/current generation，token 本身不是 owner 财务能力。导入 reservation 落盘后才下载。控制侧 cache broker 是唯一 writer，业务子代只通过这个受限能力取得公开 bytes；不把可写 cache 目录交给任意上传链。token 重复只查询同请求 outcome，同 op 不同 body 冲突；旧 generation token 不得 rebind 到新代。同 SHA 的新代导入需要本代新 token。

第一次未知 SHA 不能调用现有 `download(url, expected_sha)` 后假装已校验 publisher digest。新增 server-only downloader 模式 `download_public_candidate(verified_candidate)`，保留全部现有 TLS/public-address/redirect/size/magic 限制，返回 computed_sha + resolved_url/bytes/public-provenance；在 claim 中区分“实际内容哈希”和“已有可信预置哈希匹配”。暂存→完整验证→原子登记 immutable SHA对象（含实际大小），失败不登记。默认20MiB；只有三个入口统一验证和样本证据后再放大，不直接用草案60MiB。

存储可用 `<CPLUS_CONTROL>/public-pdf-cache` 与 `active/<generation>` 兄弟目录，但只有显式 root config 可设置。索引只记录官方公开来源+SHA，不记录客户上传 metadata/会话/笔记；不得因上传文件 hash 恰好命中就将上传来源公开。缓存不提供跨用户的“是否已上传”目录。公告版本→SHA 映射必须有 metadata_digest/验证时刻，不用 URL 充当永久内容版本。同一固定 candidate/SHA 再导入可不联网；明确刷新发现的新版本不能沿用旧URL映射宣称最新。

cache命中→重新校验 bytes SHA→**copy**到本代对象→本代 metadata/binding/parse/index。不得硬链接可写本代对象到共享 cache（本代损坏会污染所有代）；不得复用旧 workspace、Milvus、financial receipts。结果分别返回 `cache_status`、`document_id`、`import_state` 和 `document_state`；当前 import completed 只是 uploaded，不是 READY。GET进度不启动 index/重下载。上传提交后连接丢失：保留UNKNOWN，读 ledger/本代SHA+binding映射恢复，不自动重复网络/上传。

代际复位/GC：到期检查在 broker开始/等待网络后/发布共享条目前及本代最终绑定时执行；本方案旧 token 到期未提交的下载不再注册新的cache条目，临时文件可清理；已经合法注册的公开对象可留存，与旧代权限无关。旧进程仍可能完成旧代写，但不允许进入新代；只有确认整组进程退出后清其目录。GC 只由root持有 reset lock执行：校验控制根、数字generation、规范路径、无symlink、非active、非seed、非cache、非ledger、非原C/开发根，进程身份不明则跳过。先dry-run清单，再对临时fixture做真实删除证明。保留最近一个退役代用于UNKNOWN/诊断（明确有保留期限）；cache LRU/byte cap独立，已打开/导入中的对象pin，不能删除仍占用对象或manifest后留不一致。无权把本任务的设计审查等同实际GC授权执行。

### 2.1 控制侧 cache broker 的最小落地协议

不向child传可写共享目录或可自由fetch的URL。建议root在**C+自己的controller进程**内实例化 `PublicPdfCacheBroker`，通过独立loopback内部HTTP入口（不经公开 `/api` proxy，继续拒绝外部 `/internal/*`）提供两个能力：`prepare(import_ticket)` 与 `read_ready(import_ticket)`。内部认证复用当代instance/generation/private secret的能力校验，secret不可记录、不可给浏览器；broker从控制层当前活跃handle核对，不能只相信child自报generation。

控制侧持有官方discovery snapshot索引；公开用户选择导入时，先登记operation与绑定候选/本代company的ticket。company identity由root在当前活跃代只读验证，或通过受信child读接口确认，不用浏览器名称。`prepare`只接受ticket ID，URL/host/SHA/expected_metadata从控制侧记录恢复；child不能提供URL覆盖，也不能用任意checksum探测缓存。`read_ready`仅返回该ticket获准的已完整核验bytes/sha/size/固定public provenance。网络尚未完成返回真实pending，GET read_ready绝不启动下载。可用异步任务+poll，原操作UUID在control和child ledger关联；控制侧metadata不包含私有文件/模型输出。

child只调用现有upload形成**当前代**document（copy bytes），再按已有解析索引流程读READY；upload final binding与broker完成分别做lease/generation复核，迟到旧请求只能查旧op状态不能向新代绑定。当前静态import保持原服务，动态import新adapter走这个port；只有root负责gateway/process/disclosures热点注册。broker并发single-flight键为公开candidate版本摘要，完成后按内容SHA合并；未验证的用户上传不参与single-flight或cache登记。

独立根/端口冻结：C+ controller、seed materialization、worker roots与测试port由root新建并记录；**不触碰现有C的14530、旧controller或其active目录**。唯一跨工作树复用的非公开运行资源是第8节的同一授权成本账本；不复制旧运行库。首次cache/GC验收必须使用C+ disposable根，不用旧C目录做证明。

## 3. OCR 受限研究资格，不伪造 READY

**真实断点：** `DocumentTaskPreparer.prepare_many`（`app/documents/preparation.py:96`）要求 READY、matches_cover；`ConversationRepository.create/_scope`（repository.py:138,183）保存严格旧 Identity；`showcase_research/scope.py:28,85` 从旧conversation selection恢复并复验；`Findings.quote/revalidate_quotes`（findings.py:40,92）只认旧 parsed_evidence。`ParseV2Service.snapshot/quality/search`（`app/parsing/service.py:83,373,437`）有artifact/output hash、页坐标与source校验，但identity_assessment仍manual_check。**只把OCR塞入Milvus或给旧document写READY，不会安全补上这条链。**

冻结 `ResearchSourceRef` discriminated union：

```text
fast: {kind:'fast', document_id, source_revision, content_sha256, parser_version,
       company_id, report_year, ...旧完整source identity}
ocr:  {kind:'ocr', document_id, source_revision, content_sha256, metadata_sha256,
       artifact_id, artifact_output_sha256, artifact_adapter_version, config_hash,
       selected_pages, identity_binding_ref, ...原PDF identity}
```

`EvidenceRef` 对应两种严格模型；OCR还需physical_page、line/cell IDs、exact_transcribed_text、bbox/quads、页面尺寸/坐标系、页转录状态。保留原PDF parser_version与OCR adapter_version为两个字段，不能互换以伪造旧revision。证据键含 artifact hash+page+line span，禁止chunk_id单独充当引用。

最小增量是 `retrieval_v2.ScopeReader`/`EvidenceVerifier` 统一**新研究**引用接口；旧 fast adapter 原样调用旧 preparer。OCR adapter 经当前文件hash+metadata身份+指定artifact/output hash+完成页检查后颁发仅 research 的能力。只选partial artifact中completed页，显示 pages_processed/total，不宣称全文覆盖。不能静默取 active/latest artifact。

非READY扫描文档如何选源需root显式接线：新增版本化研究selection/绑定记录（独立research-context sidecar，可选关联原conversation_id；OCR-only不得要求先创建旧conversation），接入已有showcase执行器的scope provider，保持旧会话 source_payload/schema/checksum 不变。UI用同一研究助手，来源选择区有“已验证原文”与“OCR待核对资料”，不能另造不互通的Agent平台。旧对话继续fast-only；OCR专属请求路由到这个versioned context，不塞入旧 TurnResult/EvidenceRef。新scope绑定本context存活、memory/preference generation、lease/instance；若关联原conversation，还须验证其存活，用户删原会话必须使关联context不可执行。

派生扫描样本若能由程序证明其来自已核验公开PDF固定页，可记录derivation binding供公司/年份身份查证；没有这个证明的扫描件只能显示用户绑定的未核验身份，禁止把它作为该企业正式企业结论。若需要提升公司身份，独立显式人工绑定review，不等于财务确认。T15可先在已知派生样本展示有来源的OCR研究路径，但必须标清限制。

工具返回OCR sourced excerpt保留 `transcription_review=unreviewed`；AI解释另标ai_unreviewed。旧SourceReader.evidence只能校验fast；OCR verifier用quality+指定行/cell exact text+bbox边界检查，生成原图/文件链接 `/documents/{doc}/parse-artifacts/{artifact}/file#page=...`。最终发布还要重新查PDF、artifact、identity绑定/撤销和Memory generation；采用现有publication_guard模式覆盖最终结果COMMIT，不只在检索前查一次。新selection和OCR sidecar不能被旧facts reader读取为金额依据。

### 3.1 可直接派工的 enrollment / context / executor 增量

root补充核对的断点成立：`SearchHit.type`只允许paragraph/table/title；`FindingBase.transcription_review_status`不允许OCR状态；当前派生扫描document为legacy failed。故“给旧hit补artifact字段、仍走旧quote”与“先建旧会话再转OCR”两条都应禁止。不要用Pydantic `model_copy(update=...)` 绕过旧模型校验。

建议在新的 `cplus-research.db`（每代）建立四类append-only记录及operation ledger：`enrollments`、`research_contexts`、`context_events`、`job_bindings`，不向旧conversation_sources伪写READY source。enrollment最小请求：

```text
POST /cplus/research/enrollments
{operation_id, document_id, artifact_id, expected_source_revision,
 expected_artifact_sha256, selected_pages:[...], confirmed:true}
-> {enrollment_id, revision, sha256, source_ref:OCRSourceRef,
    identity_status, allowed_use:['research_excerpt'], financial_use:false,
    transcription_review:'unreviewed', completeness, limitations}
```

`confirmed`仅确认用户选择该资料用于研究，**不是身份或财务签核**。服务端snapshot核验当前bytes、metadata、artifact校验和与页状态；artifact属于同document/本代，不接受客户端text/bbox/source_status。要求选页1..pages_total、数量上限50且全部completed；artifact partial可用完成页但公开覆盖。若用户只是查询未验证扫描件，可给 `identity_status=user_bound_unverified` 并限“这份文档转录说明”，不能放入企业360已验证经营摘要。已验证派生样本通过保存的parent public PDF hash/page derivation证明可给 `identity_status=verified_derivation`；未有此证明就是unknown，不凭文件名升级。enrollment只描述能力，不改变artifacts.active、DocumentRecord.status、旧financial资格。删除/撤销enrollment增加context generation，已存结果历史可读、后续执行失败。

```text
POST /cplus/research/contexts
{operation_id, title, selected_sources:[FastRef|{enrollment_id,revision,sha256}],
 parent_conversation_id?:UUID}
-> {context_id, context_revision, context_sha256, sources, allowed_tools, limitations}
```

FastRef逐个走旧preparer；OCR逐个恢复enrollment，冻结artifact hash与页集。context是OCR-only会话的真正身份，不是假conversation_id。Context行存current runtime identity、scope hash、generation；界面研究历史将type标为 `legacy_conversation` 或 `cplus_context`。已有旧会话进入OCR时可显式创建关联context，UI提示“新的资料范围”，不改变旧source_payload。旧事实选择不会自动迁移；首版OCR context禁financial tool，fast-only/v3财务以后走单独typed capability。对应GET detail/events和显式DELETE context都按同一代际/operation协议；DELETE不是代替财务撤销。

**同一产品、复用执行机制的具体缝隙：** root将现有runner的source获取/quote/最终publication依赖收敛为 `ResearchContextPort`：`load_frozen(ref, identity)`、`select_for_query(frozen, query)`、`verify_excerpt(hit)`、`publication_guard(frozen)`；旧实现仍调用conversations/preparer/Findings，C+实现调用context/enrollment/type verifier。provider、reserve_call预算、AgentRunner轮数/工具白名单、events和UNKNOWN语义共用；不得另new一个不受guard的LLM客户端。新API可用 `/cplus/research/intents|plans|jobs`，使用context_ref；所有已存旧jobs/DTO原样读。现有 `sr_jobs.conversation_id NOT NULL` 不能塞context_id冒充旧会话：首版在sidecar job_bindings持有真正context与新job envelope，复用执行器/持久预算代码（必要的新job表以版本区分），不要重写另一套代理决策/调度平台。旧 `_execute`、`create_job` 和 `verified_job` 中直接conversations.selection调用必须由root逐处替换成port；只换search依赖不足。

**结果合同：** 新 `cplus-research-result-v1` 的 `CPlusFinding`和 `CPlusEvidenceRef` 保留四类语义发现，但采用前述多轴状态；OCR sourced excerpt为转录原句，不叫verified original。旧 `research-answer-v1` / TurnResult / ResearchFindingV2 不扩字段硬塞OCR。前端 `/conversations?context=<id>&research_mode=...&job=...` 在同一研究助手内按context type选择transport/DTO validator，复用模式选择、计划批准、事件与引用卡交互；旧 `conversation=` 路径不变。context/job ID匹配与epoch隔离必做。history列表聚合只读typed refs，不自动将旧聊天记忆写成新会话。报告adapter按result schema分派，C+OCR内容进入新v3 snapshot，旧v2report仍旧verifier。

M1出口必须真实观察“legacy仍failed→显式enrollment/context→同一研究页发问→bounded工具返回OCR ref→结果标未核对→原图物理页”，同时证明旧ResearchRun仍拒绝该source、财务确认仍不可用、artifact切换/源更改时结果不可新发布。否则只能叫artifact检索demo，不能说OCR已接正式研究。

## 4. Hybrid/RRF/rerank 的实际接入点

当前 `SelectedScopeSearch.search`（`app/rag/selected_scope.py:70`附近）是dense前后revalidate；showcase `AgentRunner.tool`（`agents.py:44`）取top6后按“风险”字样过滤；旧对话 `ConversationTools.source_quote`（`tools.py:59`）调用 `RAGService.answer_selected`（`app/rag/service.py:453`），还走table_context和selected evidence validator。它们不是一个可以全局替换score的空接口。

**分数P0：** `ConservativeScoreEvidenceGate.allows`（`app/rag/evidence_gate.py:43`）比较top1.score，`runtime_factory.py:80,193` 固定cosine阈值0.55。RRF(k=60)两路第一名分数仅2/61≈0.0328；直接填SearchHit.score全部拒答。把RRF归一成0.9也不能冒充cosine或语义置信度。

冻结 `RetrievalCandidate {ref, text, document_type, section_path?, lexical_rank?, dense_rank?, dense_cosine?, fusion_score, rerank_score?, retrieval_version}`。先在server-frozen refs内过滤，FTS和dense各top20，完整证据键去重，RRF k=60确定性排序，再本地轻量质量过滤/可解释rerank，取top5（参数均版本化）。不共享跨代FTS/dense业务索引；独立retrieval-v2.db/collection记录manifest，包括source/artifact/chunk/config/model version。查询不偷偷建索引；新索引是明确导入/OCR后续阶段或显式build操作。索引失效明确degraded/dense_only，而非空结果被当成业务不存在。

SQLite FTS5可选trigram处理中文；现有OCR search把整query转成单phrase且长度至少3，不是混合检索或BM25已完成。新查询拆分必须参数化/转义，短词走有说明的dense fallback/别名扩展；不存在的章节metadata不能伪造。报表年份过滤不替代指标期间过滤：2025年报可能包含2024比较值，不能粗暴丢弃。annual-diff左右scope分别检索并保留覆盖量。

root接线分两步：

1. **showcase新工具**注入hybrid service，返回typed合法refs；删除/替换旧风险字符串排序由root改agents热点。资料验证交给上述EvidenceVerifier，新增relevance policy拒绝弱命中，不用模型临时授权。
2. **旧fast会话**先用兼容adapter只返回可经旧quote/table验证的fast SearchHit；保留真实dense cosine与旧阈值语义，lexical-only不能伪造cosine。要开放lexical-only，则给这一条answer_selected路径注入显式versioned hybrid gate与完整评测；不要全局降低旧RAG门槛。OCR仍走versioned context/结果adapter，不能仅塞进旧hits。旧Task/financial extraction默认不改，明确适配后再开启。

经营风险误检不能靠全局黑名单删除“委托理财”：用户专问理财风险时它可能正确。规则采用query主题、章节标题、叙述/纯表比例、覆盖和重复度；避免一个“风险”字给整张金额表高分。无相关叙述则拒答/不足。冻结24题清单前后同PDF/SHA/artifact/query；至少经营风险、理财专项风险、原材料、跨年两侧、OCR、注入/越界、未核准财务。分别统计candidate ranking、identity-valid、人工semantic-support、拒答以及真实时延，不把rerank分当人审。可先offline deterministic rerank；本地cross-encoder权重可用性/加载时间另验证，未批准预算不启远端LLM rerank。

## 5. Batch：真实showcase子job、批准、取消、UNKNOWN

**当前约束：** `ResearchJobs.plan`（jobs.py:14）可能调用模型；intent也是付费阶段。`create_job`（:57–83）登记后立刻 `asyncio.create_task`；没有“登记但等批次取消”的公开接口。`sr_jobs.plan_id UNIQUE` 防同计划二次执行；`store.reserve_operation/reserve_call`（store.py:72,109）持久化UNKNOWN/计数。每job内部semaphore2，不是全进程模型并发2。`verified_job`只准completed；partial批次不能谎称完整报告。

冻结三阶段，拒草案 `plan + explicit_confirm` 的任意客户端计划：

- 本地/只读组合预览：公司×问题×实际期间<=12，展示scope、候选/确认缺口和费用说明；不调用模型。每格conversation/context由server解析，源数遵守现有max4；跨年任务每格明确两源。
- `POST /research/batch-plans {operation_id,cells:[{cell_key,conversation_id/context_ref,question,requested_mode}],preparation_confirmed:true}`：这是**显式可能付费**的计划准备。持久化批次/cell/intent-op/plan-op映射后复用真实intent/plan。返回每格准备状态和已生成child plan完整hash/revision。一个失败不废其他格；UNKNOWN只GET ledger，不换UUID。GET plans/operations无模型。默认准备也串行，费用算入batch与全局账本。
- `POST /research/batches {operation_id,batch_plan_id,batch_plan_revision,batch_plan_sha256,confirmed:true}`：批准不可变manifest，内含所有本次选中child plan triples、scope hashes、预算/模板/检索版本。未准备成功的格不能被隐式批准；用户修改/重选生成新manifest。group approval是对这些真实child plans的明确授权，worker只能调用同一create_job，不能改goal/permissions。每格独立持久job operation UUID、job_id、error、attempts/unknown、finding refs。

允许cell状态 `planned/preparing/approval_required/queued/dispatching/running/completed/partial/failed/interrupted/cancelled/unknown`，每状态含phase/time，UI不能用tick模拟执行。batch executor唯一claim，CAS `queued→dispatching` 后才调用create_job，先持久child UUID；调用结果丢失按同UUID GET `/research/operations/{id}`+job恢复，**不重POST**。启动重启后未知dispatch停在unknown/interrupted，GET绝不恢复付费运行。既有已保存结果可继续读。

`POST /research/batches/{id}/cancel {operation_id,expected_revision}`只取消尚未dispatch的queued格：与claim共享事务条件。已dispatch/running返回not_cancelled，不声称调用退款；部分取消不销毁已完成结果。首版不添加强杀在途SDK thread的新语义。旧代失效不再dispatch；最终结果沿用source/Memory/lease guard。

默认batch并发**1个job**（其内部最多2agents）；若要2 jobs并发，root注入全runtime共享provider semaphore2，不能两个各自Semaphore(2)声称总并发2。每格现有5/10次预算，批次额外固定max_attempts/token/deadline，准备intent/plan也计入。预算预览是上限/估算，实际扣费unknown单列；任何调用都必须落同一5元SDK ledger，不创建batch私有现金额度。先冻结2×2验收，12格只是上限，不保证在20分钟/剩余预算内跑完。无法运行的格明确budget_exhausted/expired，不能自动续租或换代重跑。

## 6. Report/export：复用旧报告但不改变旧内容

`VerifiedJobSnapshot`（`app/showcase_reports/models.py:34`）是单job、completed、固定findings；`service.py:131–169` revise只复制旧snapshot改title/notes。因此把annual_diff/peer/3表chart硬塞旧DTO或“修改v2 revision的snapshot”均不成立。草案 `/reports/{id}/revisions/{n}/export` 还会与旧v1报告域混淆。

冻结 `ReportRef {domain:'legacy_v1'|'showcase_v2'|'cplus_v3'|'preset_archive',id,revision,payload_sha256}`。同一个UI报告中心聚合这些引用，ID不能跨域猜。旧v1/v2/archive仅read adapter，原payload/checksum/打印仍保留。新增 `report-snapshot-v3` 持有 typed sections（statement/checkup/annual_diff/peer/batch/text/chart）和不可变source/result/formula/ref hashes；原v2报告可作 `parent_report_ref` 引用或精确拷贝已存内容并记录hash，绝不覆盖原record。新报告必须显式保存；不因为打开公司360就生成报告。

最小端点：`POST /cplus/reports/drafts {operation_id,result_refs,parent_report_ref?}`、`POST /cplus/reports {operation_id,draft_id,title,notes}`、GET固定revision。result_refs只允许server已有结果/版本，不接收模型/浏览器金额或chart坐标。创建当前可信快照时复验source/receipt/Memory并覆盖最终COMMIT；新adapter不得复用旧报告catch-all把权限拒绝变成“来源不可用仍返回正文”。权限先单独验证，freshness失败只影响获准读取的历史投影。partial batch可保存partial章节，但逐格状态原样保留。

导出建议修改草案为 `POST /exports-v2 {operation_id,report_ref,formats:[csv,xlsx,pptx],export_profile_version}` → immutable `export_id/manifest`，GET `/exports-v2/{id}/files/{format}`只下载。这样生成文件和保存export manifest不是GET隐藏写操作。直接旧revision GET纯内存导出也可，但不能同时承诺动态freshness水印与每次字节完全相同；首版冻结export生成时间/当时状态/renderer版本后保存文件更明确。manifest含input report hash、file sha/bytes、generated_at、source_status_as_of、saved_authority；下载时当前status另查/响应metadata，不修改原文件。失效后仍可读获授权历史导出，但显著“历史/当时核验”，不能声称当前有效；新confirmed报告必须重新准入。

XLSX精确Decimal以文本原列为准，只有<=15有效数字且无损可表示才给便利数字列，保留原字符串、单位/期间/状态和出处。CSV对 =,+,-,@/制表/回车开头的不可信文本做防公式注入的显示转义，原始值另typed field/明确编码；不把模型/公司名称当公式。PPTX同一snapshot5–8页，所有模型解释/OCR候选/示意保留标签，缺值不画0。模板版本、固定时间/排序/ZIP时间可固定，重复download SHA一致；不以“生成成功”代替实际Office打开与逐页QA。以上只是后端合同，不授权本轮生成或上传导出文件。

## 7. UX冻结：公司360作为新入口，不另造平行平台

当前 `productRoutes.ts:1–31` 只有home/tasks/companies/overview/documents/analysis/research/reports/conversations；`AppShell.tsx:10–15` 五个一级入口已够。建议保留五入口：**首页 / AI研究助手 / 企业与资料 / 研究任务 / 我的报告**。360在企业下替换/扩展overview，不把三表、体检、同行都塞进一级sidebar。root独占route/AppShell/Conversations接线；worker只写cplus叶子模块。

| 功能 | 建议落点与scope | 当前可复用 | 实际缺口/不能假装已有 |
|---|---|---|---|
| F19–21发现/下载/cache | 企业目录“获取年报”三步：选主体→选公告版本→确认导入 | Company/DocumentLibrary、静态disclosures、上传进度 | 拼音/动态数据、token/cache、GC；官方不可用须回退，05的“粘贴URL”改为“打开官方查询/上传”，不暴露任意URL代理 |
| F22 360 | `/companies/{id}/overview`，顶部明确source-selection snapshot | Shell、公司详情、Dashboard图表样式/资料卡 | profile聚合、覆盖年表与5KPI逐点authority、没有数据引导 |
| F23/24/28 三表/趋势/分部 | `/companies/{id}/statements?kind=&selection=`、趋势/业务结构二级tab | v2表格/PDF对照、Decimal格式化、Recharts | duration/v3行、合并vs母公司、候选图层、分部互斥/总额/抵消；不补100% |
| F25体检 | `/companies/{id}/checkup?result=` | 新signals算术风格、已核准facts/原文 | versioned规则+AI解释分层；三类规则insufficient也要显示，不能伪评分 |
| F26跨年 | `/companies/{id}/changes?comparison=` | 双源研究、引用卡/PDF | 左右固定版本+3主题对齐；missing_in_retrieval不能称未披露/取消业务 |
| F27同行 | 公司360“对比”→`/comparisons?selection=` | 公司选择、真实来源 | 2–3公司手选/行业来源、期间/口径可比矩阵，不用LLM认证行业 |
| F29/33图表追问与模板 | 同一ResearchWorkflow，保留return context | question draft、mode、job deep link | `context_ref`恢复实际来源/指标/期间；不凭question字符串恢复authority；模板版本，图表建议仅record refs |
| F31矩阵 | `/tasks?view=batch&batch=`，普通/批量二级tab | jobs/events/UNKNOWN读回 | 组合/准备/批准/每格状态/取消，明确付费边界 |
| F32报告导出 | `/reports?domain=&report=&revision=` | 既有报告中心、print、archive | typed domain、v3 sections、export manifest/文件状态 |
| F34收藏/高亮 | 引文卡“收藏”→现有研究笔记；PDF evidence viewer | `ResearchMemoryService.validate_refs`（service.py:157）已有saved_evidence与artifact行校验 | UI接线、精确bbox/quads定位；失败页级降级，不再建收藏库 |

所有selection/context由server恢复，URL只是导航。新参数重复、非法ID、旧generation、不同company组合要拒绝/清空；改变scope同步卸载旧结果并用abort+epoch隔离迟到响应，不能回退到上一公司的图。360首屏company身份→覆盖年表→5KPI→趋势+体检，第二屏三表/变化/同行，第三屏资料/最近研究/报告；390单列、键盘可访问、滚动表格局部容器，状态区用人话，hash只放技术details。

C当前 `ShowcaseDashboard.tsx:206` sample初值来自 `VITE_FINDOC_SHOWCASE_PREVIEW_CHARTS`，启动器设置为1。C+的新公司360不能继承该默认。没有confirmed时真实图为空，明确手动开启候选层；示意模式单独“示例企业”，不能沿用美的/格力名称。图表点击不创建job：只打开context预览并让用户提交。KPI所谓“最新”仅在用户选定的版本集合内确定，不从多版本自动选latest。

## 8. 跨C+ worktree共享既有5元账本

**直接源码缺口：** `scripts/run_showcase_local.py:228–230` 把ledger固定为当前PROJECT/data；`:96–102` 已允许同Git sibling读取provider配置，但这不等于账本也共享。`runtime_factory.py:239–243` guard是可选环境变量；`ProviderBudget.__init__`（app/demo/provider_budget.py:28–40）会创建缺失数据库。新worktree自行启动或复制一份ledger，都会破坏“同一轮总5元”的语义。

root最小修正：增加 server-only显式 `--provider-budget-db`（或受控启动配置），固定到原C既有canonical文件，预期位置：

`/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-cost-control/provider-budget.db`

本轮**未打开该文件，也未核实当前剩余额度**。root须核验实际路径及同一文件身份后注入。允许同Git common dir的指定旧worktree账本，要求绝对真实路径、非symlink/多hardlink、owner私有权限、既存schema与cap=5、非任何seed/active/cache/GC路径。不存在或身份不匹配则fail closed，C+ startup不可通过调用constructor补建。不能复制DB、重置calls、以新cap=5解释成新额度；不能把预算文件打入seed/cache/export。原C和C+所有provider wrapper指向同一个文件，不同进程SQLite BEGIN IMMEDIATE统一占额。

Provider/gateway子进程用同一guard，前端不接收path/secret；batch、plan、merge、annual diff、checkup解释、可选rerank均不得自行new未包装client。本轮授权是新功能工程，不自动新增provider费用额度。所有真实试验由root统一读剩余保守预留并安排；UNKNOWN/超时预留不退款，调用次数/token/保守元/实际账单unknown各自报告。离线开发不因额度耗尽停工；真实eval标budget_blocked不能fake补PASS。纯GET导出/查看不触发provider。

## 9. M0出口、阶段顺序和验收修订

先冻结四份领域文件/ADR（本review不代替root最终ADR）：(A) Source/Time/Authority/owner receipts；(B) Discovery token/cache/GC；(C) ResearchSource/Evidence/Retrieval分数与batch manifest；(D) ReportRef/export与导航。root收口冲突后再交叶子worker，禁止各自发明source_status/period/authority的不同含义。

最短可验证顺序：DATA discovery外部可用性spike与FINANCE v3纯提取可并行；RESEARCH先fast hybrid+relevance gate对照，再补OCR scope全链；UI用冻结DTO在cplus目录开发。先建立2年1公司三表候选→可审review→360/体检缺项路径；root准备用户人工步骤，用户签核发生后才跑confirmed正向。batch和exports依赖真实计划/结果合同，不能靠UI假任务先宣布F31/F32完成。

对工作包的具体修订：

1. 10/JSON中的authority/DataOrigin改为独立轴；review拆prepare/owner confirm/revoke；新增版selection_refs，不能只凭year/metric query自动选版本。
2. 03补未知SHA下载模式、server token、缓存copy而非hardlink、GC保护；05删任意URL代理入口。GET缓存/发现副作用采用第2节明确政策。
3. 08补旧0.55 gate与OCR旧conversation schema断点，冻结新typed refs及逐路径接线；“加FTS/Milvus”不能独立完成T15。
4. 07/JSON补付费计划准备、批准真实child triples、operation关联、CAS取消、重启UNKNOWN和全局并发；删客户端任意plan字段。
5. 09/JSON区分v1/v2/v3/archive report域；补immutable export任务/manifest、Excel15位精度边界与公式注入；GET不生成新报告。
6. 11/15存在T07口径差异：允许human_pending继续工程/候选演示，但不能把“C+全部完成”写PASS。建议最终状态为 `engineering_ready_with_human_pending`，HUMAN_REVIEW另列。T02/T20官方受阻可BLOCKED_EXTERNAL+回退，不改成动态发现成功。原24题真实覆盖、原15题partial/skipped和141PASS/57setup ERROR必须保留。
7. Cache与ledger是两种不同跨代资源：工作包“不得共享model ledger”应解释为**不可缓存/复制进跨代公开资源或暴露给用户**，不能禁止C/C+同一授权会话使用同一服务器账本；否则与总5元约束冲突。补第8节明确路径规则。

## 10. 本轮验证、未验证与指纹

执行的现有离线定点检查（只用临时synthetic source/SQLite、fake provider及模拟receipt）：

```sh
/tmp/findoc-m3-independent-env/bin/python -m pytest tests/test_finance_v2.py tests/test_parse_v2.py tests/test_disclosures.py tests/test_showcase_jobs.py tests/test_provider_budget.py tests/test_showcase_reports.py tests/test_showcase_local_launcher.py -q -p no:cacheprovider -k 'not real_pdf'
```

结果：**23 passed、1 deselected、5依赖弃用警告，5.24s**。证明现有合同/边界可作为复用基线，不证明任何C+模块已实现。未跑真实PDF候选、真实OCR/BGE/LLM、官方动态查询、GC、报表签核、batch或新导出；没有使用原型数据或构造替代缺失旧fixture。没有检查/消费真实账本，不报告剩余额度。官方访问条件最初来自工作包，随后只读了root D01固定commit的公开spike报告/封面预检；本轮未联网复验其API稳定性/权限。页面蓝图是建议，不是UI截图验收。

文件SHA256（全部基于精确45d55d7；下游如改动需重新对照）：

| 文件 | SHA256 |
|---|---|
| app/finance_v2/models.py | 545f3ae0456bf73a3cc27d82ca8fc100085050ccdcec683efa5574255022e8e2 |
| app/documents/preparation.py | 45574a00a8f716e703ea1b42dd7b960a523f15c20bc7b4519135834402f4a31b |
| app/showcase_research/scope.py | e863c587aa666b1310787c750a045a39692548fb1aa9c978db9a51bdbc05f18e |
| app/rag/evidence_gate.py | 4ea665fce89887e9ec850d08b5ab796942917be080d57f9ca98f521febe222c0 |
| app/parsing/service.py | d50ec3038082685de78b9e9932c066b13bb8ca06a2f45bc3de4118e998e19f62 |
| app/disclosures/download.py | 9363ffe3d410962094049c47b02ccaaab66ca76cb6d2cc483cad0dec11ca0a30 |
| app/showcase_reports/models.py | 37e87af2afcde79d3bf96eb56d2a437807ead6177f1ee87c10d1b7520a54460e |
| scripts/run_showcase_local.py | 75ee12f9a4af85d479a113213f9716e24701897aeb76ddb7bb871f3089a56ace |

交付后等待root针对冻结合同或后续候选复核派工；本审查不自行接管业务实现、其他会话或集成热点。
