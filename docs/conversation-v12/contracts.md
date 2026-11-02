# V1.2 冻结合同（A0 主控）

2026-11-02 主控已阅读实际代码、frontend-a0.md、backend-a0.md 与独立 reviews/a0-architecture.md，批准 A1/A2/A3 依本合同实施。本文是冻结决定，backend-a0.md 第3节是精确JSON字段/HTTP状态/枚举规范（各key明确存在，nullable为null），不是仅供参考的草案。新问题由主控协调修订，开发者不得独自放宽旧合同。

## 冻结选择

- 主表权威、无saver、每轮有限Graph；重启中断旧running，不自动续跑。旧Chat/ResearchRun/Task状态不改。
- 新Conversation输出原文摘录、已确认事实、既有确定性分析、澄清/拒答；interpretation_status=not_generated。自由解释属于可选后续，当前不开放未经充分数值语义校验的解释通路。
- 内嵌旧Result验原文，不强制额外写旧ResearchRun；research_run_id=null合法，禁止伪造Run链接。
- create/delete/turn统一 GET /conversation-operations/{op}；Turn另有完整结果GET。创建请求包含operation_id。GET严格只读，404不能作为自动重POST授权。
- Memory 使用独立 GET /memory-operations/{op}，create/patch/delete独立operation；PATCH同样明确confirmed。删除回执只保留最小身份/状态，不保留旧正文。
- 财务事实选择为用户提供的查找键，不是信任凭证。FactSelection经服务端完整来源/披露版本/当前资格验证，提交事务再次recheck撤销状态；没有明确选择则needs_human_review。前端需提供真实发现选项/用户明确选择途径，不能把财务正向路径做成永远不可用。
- 只允许research_preference三个key及枚举值（backend-a0第3.4节），用中文展示。不存任意自由财务值/敏感资料/PDF指令。
- source_states=current_at_read仅指数据库读取时资格投影，不能宣传为已再次核验PDF字节；每次新Turn及打开原PDF仍做实际来源复验。历史数字仅表示完成时验证，不能显示当前已核准徽标。
- 所有来源身份冻结完整SelectedDocumentIdentity；选择hash复用原序列化。禁止只比较document/year或重算不兼容hash。
- 所有特权actions由服务端构造站内白名单路径；review_facts只导航既有核对/研究准备界面，不能进入即创建/接受/保存/继续。无精确任务身份时可导航 /research?mode=operating，显示来源需用户明确准备，不伪造已核对任务。

## 实施门禁

A1先仓储/API+fake，再A2真实只读工具；前端基础可并行，精确DTO以上述规范接线。A4为真实HTTP/SQLite+明确标记的替身浏览器测试；G另有限真实模型/真实年报证据。所有Green、skip、失败与人工待验分别保留。
