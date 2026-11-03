# FinDoc C+ 主控状态

2026-11-03 Asia/Taipei。目标：按完整工作包实施F19–F34、42任务，推进至M5求职演示候选；不把原C绿色CI视为C+新增验证。

## 基线与保护

- 新集成分支 `codex/findoc-showcase-cplus-integration`，工作树 `/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent`。
- 已git fetch，指定/远端原C均为 `45d55d75662f01d9bc78da1a946d845a01a27480`，无drift；V1.2仍c8be308，main仍1f0a3d4。未在原C/main/V1.2开发。
- 工作包目录36文件已逐字节留存 `work-package/`，原verify_package检查35个manifest文件、16功能、42任务、依赖图PASS。
- 原C公开seed manifest `efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4` 已验证；29,355,026byte bundle独立备份到本C+data/cplus-baseline-backup，SHA `3693670d2369e6bed5f4981108f00a62602686a6a72bc44a64dc997bc28a2afc`。独立解包至本C+data/showcase-seed-v1，原seed不动。
- **同一预算账本**继续使用原C `data/showcase-cost-control/provider-budget.db`绝对路径，不能复制或在C+重建额度。只读快照73calls、保守预留1.354700元/5元、UNKNOWN0、实际扣费未观察。M0真实模型调用0。

## 当前阶段

**实时进展：M1/M2 后端与正式页面集成中，M3叶子模块并行。** 集成HEAD `5f590dd`（原C基线不变）；D02–D05、R01–R03、F01–F06、A01及正式发现/360组件已集成，但各自验收分层见TASK_BOARD。主控正在提交controller/private-child/旧检索adapter和正式导航接线。

2026-11-03 root真实HTTP新增：独立C+登录/实际BGE+Milvus启动、海尔600690动态搜索与2025年报发现、首次公开下载、下一generation命中相同SHA公开cache、重新建立本代企业与上传/索引、实际READY及source/metadata 200、原operation GET恢复、logout恢复seed。证据 `evidence/M1-official-import.json`。provider0/human0。首次脚本误读回执receipt字段而中断、启动时409 resetting均保留；未重发原导入。当前仅HTTP客户端，不等同双浏览器接管验收。

独立Astra High二次审查 `432824f` 复现2项P1：财务source journal检查先于实际读锁、retrieval外层guard退出晚于innerCOMMIT。已分配Sol High修复及真实SQLite并发回归；不能以nullcontext fake测试认为root完整跨库栅栏已验收。正式360与图表正在Terra High打磨；Sol High继续同行/有限批量。侧边栏名称已按任务更新，调度记录orchestration.json。

root当前精选集成测试10PASS/1SKIP（真实PDF opt-in未设置），RuffPASS，Node24正式前端buildPASS（既有chunk warning）。另一次测试命令误写两个文件名导致0 tests/exit4，已更正，不计通过。原账本未新建，C+新增模型调用仍0。真实财务候选HTTP、typed OCR HTTP/UI、模型回归、三宽正式浏览器、三脚本和导出仍未完成。

M0 FROZEN v1：root已真实读README/00/02/10/12/11/15、data、contracts、其余专项与现关键源码；Astra Ultra审查129d8d4已集成3ae6b43，八项P0修订纳入ADR/API/ports；React6ecb5ee→fc987a4已由root三宽实际复跑；D01 f413803→40ea97d真实官方17请求/全文PDF245页预检通过（不是READY）。

B00/B01/B02/B03达到各自M0层级：SOURCE_REVIEW/CODE_REVIEW/UI_MOCK/REAL_BGE_MILVUS，不能升级成业务完成。旧dense6题已实际运行，历史物理70页委托理财误引用另存且不伪称本轮同题重现。主控不等待普通任务逐项用户许可；M0冻结后进入三条后端并行链及真实UI接线。

## 原C遗留，不可擦除

原C36任务实现候选均集成，但F02/F03财务真人正向human_pending，C01/E02固定15题仅5intent partial/10skip、整题层级pass0，G01旧回归141PASS/57setup ERROR缺d21真实产物，G02真人走查未代办。详细状态仍保留docs/showcase原文。本C+在任务表逐项标PLANNED/IN_PROGRESS/CANDIDATE/INTEGRATED/VERIFIED/PARTIAL/BLOCKED_EXTERNAL，不以接口/截图代替真实业务完成。

## 功能矩阵

|F|主要复用|C+新增/需改|当前|
|---|---|---|---|
|19|公司registry、静态目录|3主体模糊/代码/拼音与消歧|PLANNED|
|20|SafeDownloader、SourceService.upload|动态官方公告与非catalog READY路径|SPIKE|
|21|代际controller/原SHA去重|仅公开PDF共享cache、旧代安全GC|PLANNED|
|22|Dashboard/AppShell|真实企业360二级页/五指标/三图/证据|UI_MOCK候选|
|23|旧v1/v2财务/owner gate|独立v3三表、instant/duration及明确核准|PLANNED|
|24|Decimal及旧图表|真实候选/确认趋势、缺年null|PLANNED|
|25|旧研究/来源|三类规则与可选AI解释草稿|PLANNED|
|26|受限原文/子代理|双年三维对齐及双侧证据|PLANNED|
|27|明确公司选择/财务数据|同期间口径对标，未知行业手选|PLANNED|
|28|真实PDF表与单位|一组真实产品/地区收入分类，不强制100%|PLANNED|
|29|Conversation/ResearchWorkflow|点图预填明确scope，用户提交|PLANNED|
|30|BGE/Milvus、ParseV2|FTS/RRF/rerank、typed OCR入检索与before/after|BASELINE_RUNNING|
|31|旧showcase jobs/operation|2x2矩阵/显式批准/独立状态/取消未开始|PLANNED|
|32|旧版本报告及print|同revision CSV/XLSX/PPTX只读导出|PLANNED|
|33|旧研究问题/metric定义|4模板、5释义、程序数据转图|PLANNED|
|34|研究记忆/PDF.js|证据收藏、真实quads/ocr bbox高亮与回退|PLANNED|

## 依赖与并行

B00→B01/B02/B03→(DATA D02–D05 ∥ FINANCE F01–F06 ∥ RETRIEVAL R01–R03)→企业360/三表与体检UI→跨年/同行/分部/图表追问→批次/导出→T01–T18/24固定题/三脚本。

最多root+3实质开发工作树；复用原三个侧边栏chat，切到新C+任务分支并保留原分支。模型及名称每个阶段按任务调整，调度见orchestration.json。root唯一owner：runtime_factory、AppShell、productRoutes、Conversations、demo controller/gateway/process/child/seed、现disclosures service与旧finance_v2热点；leaf worker仅其新模块。

## 阻断与下一步

目前没有用户输入阻断。需要真人核准时先准备单页原PDF/指标/期间/单位/页码清单，由用户本人操作；候选路线可继续。官方动态源不可用则blocked_external+官网/上传回退，其余并行。现C OCR legacy failed不允许伪造READY，新typed OCR enrollment/context/单次有界answer已冻结，旧legacy READY合同保持。

下一个出口：自动启动M1 DATA/RETRIEVAL与M2财务纯提取并行；root接controller/private child、同账本launcher及业务UI。不购买服务、不增加预算、不合main/强推/公开部署。


## M1/M2当前批次

M0冻结提交3c737327198a55b72d02490a981b5259cd164ffa。三个可见worker已新建独立C+任务分支，实际模型切到Sol/high：DATA codex/cplus-discovery-cache、FINANCE codex/cplus-statements-v3、RETRIEVAL codex/cplus-hybrid-ocr。原C/Astra审查/UI分支均保留，未增加第四worker。

主控已实现同Git sibling既有ledger只读准入与--provider-budget-db（C+必须显式）、--cplus默认14540/无默认虚构财务曲线；新C+ cookie独立findoc_demo_cplus，避免同host不同port覆盖原C cookie。新C+本机私有登录配置已生成（600/gitignored，不输出），--check已通过且仍原账本73calls，未发provider请求。

D06代码已实现正向退休凭证、退出PID/pgid复核、GC dry-run与保留最近退役代；实际OS/private readiness HTTP假child三代运行删除1、保留2/当前3，seed与publiccache sentinel不变。25项必要边界测试PASS/ruffPASS，均fake或临时fixture；D06仍PARTIAL，等DATA后做真实cache/浏览器接管联合验收，不把fakechild称真实BGE/PDF。


## Latest integration checkpoint

Leaf integration through `e60b495`: P1 source/read-lock + before-COMMIT patches, realMidea corefive extractor9899d1f, actualcandidate peer6df6805, AIexplanation7bff253, 360 polish696e04b, templates9c9bef0, batchUI5d35a2b, peer/segment sourcechecks caeb566 and accessiblechartgroup e1b6c9c. Root assembly new F34 evidence/segments/peer/batch/AIexplanation wiring and source-bound multi-source draft navigation ready for next commit.

Actual main-path browser proof now PASS21, full details `evidence/M1-M2-native/result.json`; four previous failed attempts retained. Two independent Chromium processes, two realPDF UIcandidate collections, realVision68lines, typedOCR citation/highlight/favorite, owner-only confirmedtakeover and oldHTTP401. All1440/1280/390 nooverflow; primary1440/390 screenshots copied. Provider0/human0. SelectedC+suite36PASS/3SKIP; explicit publicseed Midea1PASS.

Still needed: realprovider regression with same73-call ledger/cap5; checkup explanatory UI, realannual/peer/segments/batch/newMidea2024fixture; Excel/PPTX service/render and report integration; delete/relevancefixed24questions/three actualscripts+video/curatedC+seed+draftPR. No user input needed; humanfinancial positive remainshuman_pending without blocking candidate path.
