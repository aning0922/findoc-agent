# C+ 求职演示候选交付

基线 `codex/findoc-showcase-c-integration@45d55d75662f01d9bc78da1a946d845a01a27480`；独立分支 `codex/findoc-showcase-cplus-integration`。最终HEAD由Git和[草稿PR#3](https://github.com/aning0922/findoc-agent/pull/3)记录，base保持原C，未合并main、强推或公开部署。

## 可体验成果

|路径|实际证据|
|---|---|
|现代首页、官方企业/年报搜索、显式下载/缓存/READY与恢复|M5-official-reset、M1-M2-native、原三宽首页截图；5READY公开年报，原V1/V3 manifest重验相同|
|企业360五KPI含Decimal负债率、三表/实际期间/口径/原PDF、体检输入/下一问|[桌面](evidence/M5-followup/overview-1440.png)、[手机](evidence/M5-followup/overview-390.png)、[体检](evidence/M5-followup/checkup-1440.png)、G1-G5-native真实记录|
|四类结构化模板、同年两公司对标、双年三主题/业务环形|四actual template_runs保留原后续selector失败；scope、核心5cell与原文结果实际可读，模板版本固定|
|单/多Agent真实工具交接与报告|原单2025固定E01-15与额外2024/25双年路线分别保存；相同问题/来源/事实选择，双方两年引用。阶段事件/工具/报告重读不追加模型调用|
|异步可取消AI批次|[实际矩阵](evidence/M5-followup/one-fault-three-results-1440.png)：3AI返回+1来源缺失UNKNOWN，恢复原PDF、GET不重放、历史可查；旧revision只取消queued|
|图表→原文→记忆→删除|[最终实际回执](evidence/M5-followup/point-memory-final.json)：同比较期点位、显式scope、实际location/image、收藏、新context/BGE召回、删除后不命中。实际长表回退原页，不冒充精确quads|
|真正图表报告草稿及精确版本导出|native chart报告rev1/record_refs重读一致、三格式真实HTTP；精确deep-link服务端SHA、原生CSV/Excel/PPTX、PDF，撤销权限不降级泄露|

## 可直接检查的新版业务文件

[PDF](examples/cash-template-nonnumeric.pdf)、[PPTX](examples/cash-template-nonnumeric.pptx)、[Excel](examples/cash-template-nonnumeric.xlsx)、[CSV](examples/cash-template-nonnumeric.csv)均来自同一真实双年cash模板版本，精确ref/字节SHA见 [manifest](examples/manifest.json)。10个真实候选点、3条程序规则、业务趋势和新真实非数值AI待审解释同版保存。不是原始年报PDF，不授予人工核准。

原AI说明曾把年份金额顺序写反，失败工件/QA仍保留。新增non_numeric_review_v1隔离金额/年份/比率/数词输出，原child answer留作审阅但不作为独立报告导出；不自动重试。新真实单次解释已发布非数值草稿。独立Astra复核关闭已知错配/PDF规则JSON右溢，6页PPTX逐页查看；6页浏览器PDF只目视首末，全文检查无input_refs。不能夸大成所有AI语义正确或PDF所有页逐页审阅。

## 演示、运行和边界

本机入口 **http://127.0.0.1:14540**，当前预算模型已启用、默认20分钟wait_only、V3种子。最新测试已logout200/旧会话401/controllerready；固定凭据仅在ignored600服务端配置。验证端口14542已停止，旧C14530未修改。关闭本机进程后按[RUN_LOCAL](RUN_LOCAL.md)重启，不承诺无人服务后台永久运行。

[三条5–10分钟面试路线](INTERVIEW_DEMOS.md)及[录屏SHA索引](recordings.json)区分原无模型A/B/C与新真实模型、文件、同图点补证。webm只保留本机ignored data，不将本机路径称为线上可播放地址。

[固定24题矩阵](eval/CORE_EXECUTION_MATRIX.md)按actual execution/program checks/human acceptance分轴；13项required-tier已执行不等于13正确，未运行/错误/UNKNOWN保留。本人财务核准0，precision/MRR人类相关性标签为空。原C历史57fixture ERROR未被本轮局部绿色替代。

最后费用：原同一5元账本123 physical SDK rows、保守预留 **2.468274元**、旧UNKNOWN4、实际账单未观察，无新额度/退款/代签。主控/3可见worker按阶段实际调节Sol/Terra/Astra与High/Medium/Ultra，记录见orchestration.json。最终正常push、同HEAD CI与分支SHA由PR记录；不将CI绿色当真实业务/模型验收。

人工剩余：本人核对财务原PDF与确认，人工语义/相关性标注；见[HUMAN_PENDING](HUMAN_PENDING.md)。新机器还需匹配seed bundle/模型权重，Git不包含原PDF/私有DB/凭据。其余有限支持和单期无趋势图限制见[KNOWN_ISSUES](KNOWN_ISSUES.md)。
