# FinDoc C+ 主控状态

2026-11-03 Asia/Taipei。目标：按完整工作包实施F19–F34、42任务，推进至M5求职演示候选；不把原C绿色CI视为C+新增验证。

## 基线与保护

- 新集成分支 `codex/findoc-showcase-cplus-integration`，工作树 `/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent`。
- 已git fetch，指定/远端原C均为 `45d55d75662f01d9bc78da1a946d845a01a27480`，无drift；V1.2仍c8be308，main仍1f0a3d4。未在原C/main/V1.2开发。
- 工作包目录36文件已逐字节留存 `work-package/`，原verify_package检查35个manifest文件、16功能、42任务、依赖图PASS。
- 原C公开seed manifest `efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4` 已验证；29,355,026byte bundle独立备份到本C+data/cplus-baseline-backup，SHA `3693670d2369e6bed5f4981108f00a62602686a6a72bc44a64dc997bc28a2afc`。独立解包至本C+data/showcase-seed-v1，原seed不动。
- **同一预算账本**继续使用原C `data/showcase-cost-control/provider-budget.db`绝对路径，不能复制或在C+重建额度。只读快照73calls、保守预留1.354700元/5元、UNKNOWN0、实际扣费未观察。M0真实模型调用0。

## 当前阶段

M0 IN_PROGRESS：root已真实读README/00/02/10/12/11/15、data、contracts、其余专项与现关键源码；Astra Ultra独立审查中；Terra High可点击React候选6ecb5ee待root审查；Sol High官方来源spike已发现海尔智家2025全文/摘要/英文元数据，待交接，不能据此声称动态导入READY。

B00基线VERIFIED；B01合同评审IN_PROGRESS；B02UI CANDIDATE；B03真实资产与旧dense检索基线IN_PROGRESS。ADR标为草案的项目不可当已冻结接口。主控不等待普通任务逐项用户许可；M0冻结后进入三条后端并行链及真实UI接线。

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

目前没有用户输入阻断。需要真人核准时先准备单页原PDF/指标/期间/单位/页码清单，由用户本人操作；候选路线可继续。官方动态源不可用则blocked_external+官网/上传回退，其余并行。现C OCR legacy failed不允许伪造READY，新typed OCR合同待Astra冻结。

下一个出口：独立review+可点击React审查→ADR/API冻结→M0提交→自动启动M1及M2可并行任务。不购买服务、不增加预算、不合main/强推/公开部署。
