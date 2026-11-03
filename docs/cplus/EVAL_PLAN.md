# C+ 真实评测与资源预算

继承C15固定题原文及历史5partial/10skip，不追溯改成PASS。扩展至少24，核心12按真实业务tier逐项记结果，不用proposal JSON合法代表问答通过。

证据：UI_MOCK、UNIT_FAKE、REAL_HTTP_PDF、REAL_BGE_MILVUS、REAL_LLM、HUMAN_REVIEW分别记录。API词命中诊断不是人工相关性；citation identity与semantic support分开。每次结果含source SHA/原始输出/失败/UNKNOWN/physical call/费用预留及实际扣费观测状态。

P0：T01/T03/T06/T08/T09/T10/T16/T18至少一条可重复实际证据；T07无本人签核则human_pending+一页操作清单。其余F19–34每项有实际可操作模块和一个真实样例，不能仅入口/mock/API壳。

B03先在全新物化seed上复跑旧dense风险查询（无LLM），固定原始top5/页码/身份，后同PDF/同问题对照FTS+RRF/rerank。人工precision@5/MRR需相关性标注；未标注保持null。失败和无关委托理财表保留。

真实计划：官方新企业发现/下载/解析/BGE、跨代公共cache命中与私有文件不共享、旧代接管/GC、两年三表时点/期间、候选趋势与三规则、3维双年文本、2公司同行与真实分部、图表追问、2x2批次、OCR引用+原图、收藏真实高亮与降级、同revision四格式实际打开、GET无模型和种子reset。

费用只用原C既有5元总账本，M0快照73calls/保守1.354700元，实际账单未观察；新C+不得另建ledger。worker禁止真实provider，root先跑PDF/BGE/协议fake，接线完整后再对核心用例少量真实LLM。每次call持久预留、UNKNOWN不退款/不重发；到限停止新模型调用、其他离线工作继续并说明缺口。不为得到漂亮分数无限重复。

官方HTTP每秒≤1、短超时/有限响应/metadata缓存；captcha/限制不绕过，明确BLOCKED_EXTERNAL并官网跳转/上传，静态目录是fallback而非动态成功。PDF先20MiB统一上限，macOS真实Vision保留，Linux OCR未测不声称。

测试预算：每任务1–3必要合同/真实smoke；阶段做关键联合回归，避免无变化重复大套件。C旧57fixture setup errors独立保留，受控CI成功不替代新业务。三条5–10分钟实际路线A资料→360→体检，B双年→Agent→报告/PPT，C OCR→检索/高亮→记忆→接管恢复。
