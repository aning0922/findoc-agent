# V1.2 设计与存储职责

精确合同见 [contracts.md](contracts.md)、[architecture.md](architecture.md)、[backend-a0.md](backend-a0.md)；运行与边界见 [user-guide.md](user-guide.md)。

| 存储 | 拥有的状态 | 不承担的职责 |
| --- | --- | --- |
| Conversation 主表 | 冻结来源、用户消息、已提交回复、operation 回执、claim、结构化焦点 | 不覆盖旧 ResearchRun，不自动续跑未完成轮次 |
| ResearchRun | 某次原文检索的不可变引用与证据子记录 | 不保存自由聊天正文，不改变原文拼接合同 |
| 经营任务 / TaskCheckpointer | 原经营研究阶段、人工等待及明确继续 | 不作为聊天 saver 或长期偏好仓储 |
| Memory | 当前已确认枚举研究偏好、revision/generation、无正文审计回执 | 不存财务真值，不替用户接受候选或扩大来源授权 |

ConversationService 负责登记、单次执行、终态事务及提交后严格读回。ConversationGraph 不配置 saver，每轮从主表重建有限输入，thread_id=conversation_id 仅作跟踪。跨重启可读取同一会话及执行下一次明确发送，启动只封存被中断轮次；GET/焦点恢复不恢复执行。

服务端解析公司、年度、指标；完整问题保留原谓词/否定/限制，只有省略追问被补全。多主体、未知主体、范围外年度和未解除澄清屏障不会悄悄改选资料。每轮和最终提交复验完整来源身份。

原文工具复用 answer_selected/generate_once，引用经过旧 Result 精确原文校验。财务工具恢复服务器上的完整已确认事实，检查 local_operator、披露口径、期间及 Decimal，再调用既有 FinancialAnalysisService；最终事务重新检查来源/确认撤销/完整事实组。工具白名单没有 ACCEPT/SAVE/RESUME。调用前持久预留预算，SDK、Graph、客户端不自动重试。

写入未知时只用原 operation 查询已提交状态；相同 op/载荷读回，不同载荷冲突。只有原 POST 明确表明未登记的精确状态/错误码才释放待定操作；后续 GET 404/410、通用409/5xx或超时均不构成再次 POST 授权。供应商已执行但响应丢失时，不承诺供应商端计费 exactly-once。

B2 最近8轮/4096 token、摘要512 token、偏好256 token分别限额。摘要只保留焦点、进度、待澄清、覆盖游标及有界 provenance（至多32旧轮ID，保留2版），没有用户正文、回答、金额或偏好正文。第10轮起的新 POST 准备阶段派生写入，Graph/GET只读；偏好每轮 fresh recall，使用 generation fencing 和来源轮次排除，删除后不从旧摘要复活。模型不参与摘要生成。

前端 `/conversations` 的“研究助手”使用独立消息与来源归属；旧 `/research?mode=qa` 深链保留。PDF动作由服务端完整身份生成，前端再次核验来源与实际文件。自由解释在本版关闭，interpretation_status=not_generated；原文核验不能被解释为真人财务语义审核。
