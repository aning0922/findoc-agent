# FinDoc C+ 求职展示候选交付

## 版本与状态

- BASE：`codex/findoc-showcase-c-integration@45d55d75662f01d9bc78da1a946d845a01a27480`。
- C+：`codex/findoc-showcase-cplus-integration`，代码审查检查点 `49330cf8e37b971d63af6ce5fa3e191d996b1643`；最终提交由同分支Git HEAD及草稿PR记录，不以文档自指SHA伪造最新状态。
- M0合同冻结3c73732；独立Astra Ultra/High审查、root独占热点集成、Sol/Terra/Astra随任务调整。可见chat和设置见orchestration.json。
- F19–F34均有可操作实现/真实限定样例。当前42任务35VERIFIED、6PARTIAL、1交付收尾（PR创建后更新）；部分为模型/人工语义/财务确认未验，不能写全绿。
- 本机14540，独立cookie、20分钟、wait_only、modeldisabled；原C14530与原C/V1.2/main保留。未公开部署/自动合main/强推/代签财务。

## 用户能看到的成果

|页面与动作|实际截图/证据|
|---|---|
|首页真实预置候选曲线/KPI/任务环/搜索|[桌面](evidence/M5-interview/home-final-1440.png)、[1280](evidence/M5-interview/home-final-1280.png)、[手机真实viewport](evidence/M5-mobile-viewport/home-viewport-390.png)、[手机向下滚动的图表](evidence/M5-mobile-viewport/home-scrolled-390.png)|
|360两年五KPI/折线、三表、三规则体检|[360桌面](evidence/M5-finance/company360-1440.png)、[手机](evidence/M5-finance/company360-390.png)、[三表](evidence/M5-finance/statements-1440.png)、[体检桌面](evidence/M5-finance/checkup-1440.png)、[体检手机](evidence/M5-finance/checkup-390.png)|
|官网新公司/年报、缓存、恢复|[实际结果](evidence/M5-official-reset/result.json)，修复后拼音/代码跨generation共用PDF并重新建立本代绑定|
|双年三主题、产品地区结构、四格矩阵|[三主题](evidence/M5-interview/annual-three-topics-1440.png)、[结构](evidence/M5-interview/segment-donut-1440.png)、[四格](evidence/M5-interview/batch-matrix-1440.png)、[逐格耗时/引用](eval/results/batch-v3-fixed/performance-summary.json)|
|点图→原文→收藏→真实BGE查询→删除|[实际路径](evidence/M5-point-memory/result.json)、[页面](evidence/M5-point-memory/point-memory-1440.png)|
|同版本CSV/Excel/PPTX/打印PDF|[原生导出](evidence/M5-native-exports/result.json)、[CSV](evidence/M4-native-exports/real-peer.csv)、[Excel](evidence/M4-native-exports/real-peer.xlsx)、[PPTX](evidence/M4-native-exports/real-peer.pptx)、[新版2页PDF](evidence/M5-native-exports/real-peer.pdf)|

手机部分Chrome fullPage工件出现截图拼接重复。未据此宣称可用性通过：另用390×1000实际viewport与真实scroll检查，DOM hero/root各1，scrollY=1000后hero移出视区，图表/卡片正常且无横向溢出。原fullPage工件作为历史保留，主手机交付采用viewport。

## 三条原始录屏

实际自动Chrome录屏，未剪辑成真人验收；无provider调用、无财务本人签核。5–10分钟讲解节奏见[INTERVIEW_DEMOS](INTERVIEW_DEMOS.md)。二进制保留本机被忽略目录，完整路径/字节SHA见[recordings.json](recordings.json)：

- `data/cplus-delivery-media/route-a-official.webm`：官网搜索、明确导入、READY与360，约1.2MB。
- `data/cplus-delivery-media/route-b-chart-memory.webm`：比较期点位、FTS/context、原文收藏/跨context真实语义查询/删除，约3.2MB。
- `data/cplus-delivery-media/route-c-annual-batch-templates.webm`：三主题、业务环形、四格计划/批准/完成、两种模板、原文定位，约19MB。

GitHub只含公开截图/候选文件和录屏索引，不把本机data链接伪称线上可播放视频。部署者可自行选择录屏发布，主控没有公开上传。

## 运行、证据与回退

[RUN_LOCAL](RUN_LOCAL.md)包含此机准确Python/Node/seed/export renderer路径、私有配置要求、同账本模型可选参数。V3manifest d96b934...、bundle c45d3cb...完整SHA见该文；真实PDF/模型权重/私有数据库不入Git。原Cseed byte SHA已核验未改变。

[验收汇总](EVAL_RESULTS.md)将18场景与固定24题、真实/fixture/模型/人工分开。实际最终精选90PASS/3SKIP/5SWIGwarnings，Node24 build/lint exit0但chunk/hooks warnings保留。真实四格修复后119.413秒、34exact引用、GET不dispatch；原260秒UNKNOWN未重放。导出最终权限缺口经Astra独立复现、root修复、独立撤销403/恢复原bytes&ETag复验关闭，并补真实Chrome下载。

剩余六项PARTIAL主要是：真人财务核准、人工检索语义标注、真实AI体检/跨年解释与完整模型E2E。4次C+真实供应商请求均ReadTimeout/UNKNOWN，完整新真实模型答案PASS0；当前同一5元账本77次、预留1.441018元、实际账单未知。停止进一步付费诊断；其他所有可独立完成的本地模块/页面/演示已执行，未用mock补模型结果。

恢复：退出重新物化V3seed，不清原数据库；程序UNKNOWN只查原operation；官方限制使用官网/手动上传；复杂表格unsupported保持；本人核准步骤见[HUMAN_PENDING](HUMAN_PENDING.md)。无新增费用/正式发布需要请求批准，后续若购买服务或提高5元cap才另行征询。
