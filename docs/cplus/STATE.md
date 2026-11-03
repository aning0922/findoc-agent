# FinDoc C+ · 当前单一状态

2026-11-03，独立分支 `codex/findoc-showcase-cplus-integration`。本文件优先于旧交付检查点；旧模型超时与未实现状态保存在 [e510876 状态](checkpoints/STATE-e510876.md)，没有覆盖原失败或将旧 CI 当成新功能验收。

## 起点与保护

- 指定原 C 基线和本次再次 fetch 后远端均 `45d55d75662f01d9bc78da1a946d845a01a27480`；原 C 工作树保留。V1.2 `c8be30808a3ac8c6d13daa5fd9d43c0ea1212c78`、main `1f0a3d4131480ac0ea742772127afac3c892fc7c` 未合并、强推或改作本轮开发起点。
- 原始完整包按 M0 阅读归档；M0 `3c737327198a55b72d02490a981b5259cd164ffa`，Astra Ultra 独立评审 `3ae6b43`，后续完成审计 `fc45f79` 与各领域独立复核均保留。原 C 36 项历史实现及其测试失败不因 C+ 变成全通过。
- V1 seed manifest `efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4`；V3 `d96b9340838c1d22619308d5d4492996f99ae03c52bf8a8a17eb6594ca139c3d`。最新实际重验相同。V3 bundle `c45d3cb8ec6ffb0d6ff411fe34fdffc9639fc49ad9e1615ed979a1d8dd10355e`；PDF/seed/模型权重/配置/私有库均未入 Git。
- 原始 ResearchRun、v1 三指标、v2 即时指标、ACCEPT→SAVE→RESUME 及已应用 migration 保持；新增 v3/独立 tool/analysis/report 域，不由 Agent 执行真人确认。

## 当前实现和可运行路径

|功能|实际路径与证据|有限支持或待人审|
|---|---|---|
|F19 模糊公司搜索|名称/代码/拼音，证券市场明确消歧；真实 hezj/600690|官方元数据长期稳定性未知|
|F20 动态官方年报|非旧目录海尔2025→显式下载→解析/BGE/Milvus→READY→360|美的2024封面缺代码时自动绑定拒绝，官方跳转/手工上传回退|
|F21 跨代公开缓存|拼音/代码查询命中同官方PDF；新代重新核验私有绑定，旧进程确认退出后回收|不共享上传、索引、会话、记忆或预算|
|F22 企业360|公司代码/市场/行业未知、实际覆盖、5KPI含Decimal资产负债率、工作流/保存版本；1440/1280/390真实UI|行业未知不猜测，原seed候选不冒充实时模型生成|
|F23 三大表|格力两年真实候选，时点/期间/口径/范围/币种/物理页；缺值明确不足|本人财务核准0；未知口径不晋级|
|F24 趋势|明确选择cell，5指标×2年；2025报告中的2024比较期保留真实time|所选同来源同内容重复提取合并显示，原记录保留|
|F25 AI体检|3程序规则+输入PDF/公式/期间/下一问；实际provider三条待审解释|规则观察不推断原因，不等于财务核准|
|F26 跨年文本|风险/业务/研发双侧原文，实际模型三主题解释；原超预算失败保留后以有界原文投影修复|缺证不判业务取消，变化语义待人工审|
|F27 同行对标|格力/美的同年5指标候选Decimal对照，2–3企业模板选择|未知/不一致口径明确不可比|
|F28 业务结构|真实产品/地区收入候选、残差、环形图及来源|有限表结构；没有数据不补零|
|F29 图表追问|服务端复验cell/hash/期间→显式context→真实原文；真实比较期点位|浏览器坐标/金额只作提示，未核准数据不授财务能力|
|F30 OCR/混合检索|真实Vision 68行/54cell→typed enrollment→FTS/context/bbox；BGE/Milvus/RRF/章节排序与原文校验|OCR转录与精确原文分层；cashflow无关命中保留，人工precision/MRR空|
|F31 批量研究|真实2×2计划/显式AI选项/批准/持久异步ACK/轮询/queued取消/历史；实际3AI返回+1来源故障UNKNOWN，恢复PDF后GET不重放|默认纯工具，AI每格最多1；预算actual bill未知|
|F32 多格式/PDF|精确domain/id/revision/SHA；CSV/XLSX/PPTX真实下载、PDF打印；真实双年Agent与图表草稿各三格式通过|单年度没有适合趋势时原版本PPTX只显示表格/不足说明；演示业务图使用真实双年/同期对比|
|F33 模板/释义/转换|4独立结构化流程overview/cash/peer/changes实际PDF运行；模板版本、同比限制；图表复制真正保存report draft rev1且record_refs重读一致|可选每模板最多1次AI，默认关闭；unknown只读原操作|
|F34 收藏/高亮|真实fast收藏→跨context BGE召回→删除不再命中；真实OCR bbox及原文quads/明确页码回退|人工语义接受另列，不把SHA正确当支持claim|

## 完成审计 G1–G7 收口

- G1/G5：`evidence/M5-followup/profile-native.json`；真实五KPI、比率缺输入、三表口径、三规则/不足、来源入口、下一问和保存版本链接。unknown-basis 无真实样本，不以合成测试冒充；逐条财务原文本人确认未做。
- G2/G3：`batch-pure-controls.json` 10检查、`batch-ai-controls.json` 11检查；实际正在执行时取消只queued3，实际一PDF失效只1UNKNOWN、3真实AI返回，PDF原SHA恢复。原260秒超时、脚本失败仍保留。
- G4：四模板真实原文/财务结构化结果；最初native总FAIL是后续selector/未等待资料，与四个已成功模板分开。真实chart draft保存/重读；修复重复视图及focused registry后，`reviews/G4-template-chart-native.md` 原生闭环通过。
- G6：领域业务导出含企业名称代码/期间/口径/页码/Decimal；同版本真实财务候选与AI、真实双年图表/Agent报告文件。新域权限独立8/8受控验证；单期无趋势图限制保留。新双年AI模板/真实业务图文件及非数值解释合同已独立复核关闭；原年份金额错配和PDF JSON右溢负例保留，详见 reviews/M5-template-known-findings-closure.md。
- G7：固定24题累计 **13 required-tier executed**（并非13正确/全部通过）：E01-01/06/14/15、CP16/17/18/19/20/21/22/23/24；完整机器记录见 `eval/CORE_EXECUTION_MATRIX.md`。原不同题Agent v2、原同题单2025 fixture、额外两份2024/25相同scope对照分别保存，不混成同一次执行。人审接受0。

## 当前运行与预算

本机入口 `http://127.0.0.1:14540`，独立cookie/20分钟/wait_only/V3种子；最新主控已启用部署者私有模型配置及原5元账本，模型只在显式请求后调用。仅验证用14542已停止；旧C14530未动。固定密码和owner密码仅在ignored 600配置，本文件不含凭据。

当前费用检查点：123 physical guarded SDK rows、保守预留2.468274元/原5元、旧UNKNOWN4；真实账单未观察。额外双年deep8及synthesis5使用相同两份公开年报，双方均引用双年原文。起初12-call试验窗口在deep8后因余量不足未启动synthesis；新独立5-call窗口仅启动此前未开始的synthesis，原全局5元ledger从未重置。最终双年模板、点图、修正后非数值模板各实际1次新SDK均完成；最新修正后解释returned且不含数字，仍ai_unreviewed。最后logout200、旧会话401、controller ready。没有再重放原4条UNKNOWN。

## 验证、交付与下一步

隔离checks环境最终选择性命令：155PASS/3SKIP/5warnings（C+、demo、launcher、runtime startup；3 opt-in真实PDF未设置），无FAIL；新域独立8PASS、numeric门禁及原G4边界22PASS、打印业务视图1PASS、child导出隔离与原8边界9PASS分别留证，不能相加当功能数量。真实PDF/OCR/BGE/Milvus/LLM/浏览器/人工轴分别记证据，不能相加为功能或准确率。C+模式显式build通过，保留大chunk/SWIG/hooks警告；CI构建已加入C+环境开关，默认非C+构建不能充当C+ bundle验证。

42任务39VERIFIED/3PARTIAL，PARTIAL为真人财务核准与人工相关性/评分分轴；模块实际路径和原失败均保留，普通开发不再逐项请求许可。主控独占runtime/AppShell/routes，3可见worker按任务真实改名并切Sol/Terra/Astra与推理设置，详见 orchestration.json。无 main merge、force push、公开部署、代签或新购服务。

草稿PR [#3](https://github.com/aning0922/findoc-agent/pull/3)，base原C；最终HEAD以Git/PR同分支记录为准，不在文档自指伪造SHA。M0–M5求职候选已形成，真实双年文件/同图点定位删除闭环、README、四格式示例和录屏索引完成。最终正常push/同SHA CI由PR记录，CI不替代真实业务/模型验收。本人核对与语义标注步骤在 HUMAN_PENDING，允许保持候选交付。
