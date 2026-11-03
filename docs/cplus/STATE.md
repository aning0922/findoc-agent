# FinDoc C+ 主控状态

更新：2026-11-03，M5演示与交付收尾。独立集成分支 `codex/findoc-showcase-cplus-integration`；当前代码检查点 `49330cf`（文档/演示脚本仍有在途更新）。完整提交链以Git为准，任务证据见[TASK_BOARD](TASK_BOARD.csv)和[EVIDENCE](EVIDENCE.md)。

## 起点与保护

实际fetch/compare原C远端/指定基线均 `45d55d75662f01d9bc78da1a946d845a01a27480`；V1.2仍 `c8be30808a3ac8c6d13daa5fd9d43c0ea1212c78`，main `1f0a3d4`。C+从原C独立worktree开始，未在上述分支开发/合并/强推/部署。原工作包逐字节保留work-package，35manifest文件/16功能/42任务核验通过。M0 `3c737327198a55b72d02490a981b5259cd164ffa` 冻结；Astra Ultra独立产品/合同评审 `3ae6b43`，后续Astra High多次独立边界审查。

原C36项是实现候选，原15题5partial/10skip、完整问答PASS0；旧回归141PASS/57fixture setup ERROR、财务本人签核待完成，原证据未改写。

原C种子manifest `efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4` 和bundle SHA `3693670d2369e6bed5f4981108f00a62602686a6a72bc44a64dc997bc28a2afc` 保留。V3追加种子manifest `d96b9340838c1d22619308d5d4492996f99ae03c52bf8a8a17eb6594ca139c3d`，bundle SHA `c45d3cb8ec6ffb0d6ff411fe34fdffc9639fc49ad9e1615ed979a1d8dd10355e`；5READY公开PDF、实际OCR、5历史归档、5指标10候选点。所有原seed文件SHA不变，二进制未加入Git。

## 真实功能矩阵

|功能|可操作实现与真实证据|仍待完成/范围|
|---|---|---|
|F19 公司模糊搜索|官网名称/代码/拼音候选、证券市场消歧，实际hezj/600690浏览器|官方接口长期稳定性未知|
|F20 动态年报|海尔2025非旧catalog公告→受控下载→fast解析/BGE/Milvus→READY→360|美的2024封面缺代码自动拒绝，显式手动上传回退|
|F21 公开缓存|实际新generation跨查询cache_hit=true；旧进程退出/旧代自动GC/原seed不变|owner双浏览器接管另有M1真实证据；公共缓存不含上传/笔记|
|F22 企业360|真实资料覆盖、三表、五指标、折线/柱状、业务结构、研究入口；首页有真实预置候选曲线|无数据不补造，财务候选待核对|
|F23 三大表|格力两年各38候选cell、美的四列表核心五值，期间/时点/单位/原PDF页|有限模板；正向本人核准HUMAN_PENDING|
|F24 财务趋势|明确cell选择后Decimal投影；2025报告2024比较期实际浏览器核验|已确认曲线本人签核待完成|
|F25 AI体检|三类程序规则真实PDF+HTTP；独立AI解释API/页面|真实C+模型调用4UNKNOWN；解释验收BLOCKED_EXTERNAL|
|F26 跨年文本|同企业双年风险/业务/研发双侧摘录与原PDF链接，缺证不推断删除|AI解释未验证；实际native三主题对比已通过|
|F27 同行对标|格力/美的2025同期间五指标候选Decimal比较、真实导出|行业为手选；未知口径拒绝比较|
|F28 业务结构|格力真实产品/地区收入候选，残差与待核对状态，环形组件|有限表结构；实际native环形/表格已通过|
|F29 图表追问|真实2024比较期点→服务端不可变cell复验→固定scope→检索原文|模型解释未验证；示意数据不授予来源身份|
|F30 OCR/混合检索|真实Vision68行/54cell、typed enrollment/FTS；BGE+Milvus+RRF+启发式排序，六题精确对照|OCR非dense向量；人工相关性precision/MRR空值；保留现金流无关首条|
|F31 批量矩阵|显式2×2计划/批准/四独立状态；首轮260秒UNKNOWN后修本地多余复验|修复后四格HTTP与主控native已通过；纯工具批次，非新真实LLM多Agent验收|
|F32 文件导出|同domain/id/revision/SHA的CSV/XLSX/PPTX实际下载与打开；6页PPTX；新版2页PDF逐页查看|renderer依赖和字体见RUN_LOCAL|
|F33 模板/释义|4模板、5释义、三表到图；2模板UI_MOCK动作已验|两种模板实际双源工具研究已通过，不把mock当后端|
|F34 收藏/高亮|真实OCR bbox、PDF exact quads/降级；真实fast收藏→跨context BGE查询→UI删除后不再命中|未代替人类语义审阅|

## 验证与费用

- 当前精选C+及原demo/launcher/runtime回归：90PASS/3SKIP（真实PDF opt-in未设置），无FAIL，5SWIG warnings。新cache18PASS、排序后复验针对性8PASS。此前误写测试文件名的exit4、默认Python缺httpx等执行错误均未计PASS。
- 原生主路径21检查PASS（两个独立Chromium、实际OCR/图表/接管旧HTTP401）；修复后无模型19个真实HTTP路径PASS；导出M4/M5各11检查PASS；图表→收藏/跨context查询/删除8检查PASS。具体分母分证据保存，**不能相加当功能数量或模型准确率**。
- Node24 build/lint命令exit0。构建大chunk warning及React/hooks lint warnings保留，不能称0warnings。
- 同一原C ledger：77物理调用（原73+C+4），保守预留1.441018元/5元，UNKNOWN4，实际账单未观察。4次C+均ReadTimeout，没有观察到新真实LLM成功。停止进一步诊断，不重置额度/退款/自动重放；本轮修复0provider。
- 正向真人财务确认0；公开部署0；main merge0。真实LLM完整固定题通过0，不能用工具结果冒充AI总结。

## 当前调度与下一步

主控唯一修改runtime_factory/AppShell/routes/controller等热点；root+3可见worker，各自独立分支/SHA。名称与Sol/Terra/Astra、推理设置按任务通过桌面工具动态更新，具体见orchestration.json。

当前：Sol High真实四格耗时修复与精确引用复核；Terra Medium完成UX/模板叶子复核；Astra High做最终独立边界审查。主控已完成native C/D/E路线、三宽截图/原始录屏、18场景证据映射；继续最终权限原生下载与交付README/草稿PR。普通任务自动推进；仅模型供应商真实成功与本人财务核准保留外部/人类缺口。
