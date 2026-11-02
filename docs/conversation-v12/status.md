# V1.2 主控状态

日期：2026-11-02，Asia/Taipei。代码实现与本地自动验证已完成，交付为本地候选，G人工语义/财务核准待用户，尚无发布/合并声明。最新精确结果见 [tests.md](tests.md)。

- 仓库为findoc-agent，基线main@1f0a3d4；隔离worktree `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`，分支 `codex/conversation-memory-v12-20261102`。旧findoc-rag及正式runtime未用于覆盖实验。
- A0合同、A1持久化、A2只读Graph、A3界面、B1明确偏好管理、B2有界结构摘要均已提交；迁移仅追加v10/v11/v12。解释模式关闭，原文与确定性财务不混同。
- 可见聊天为架构审查、后端、前端、测试、偏好五个；实际模型/推理调整及文件所有权见 [orchestration.md](orchestration.md)。root负责唯一Git提交与门禁。
- 独立A1与G原finding已修复并关闭，原记录保留。G后端c103ab3、前端337916f；表格CSS/真实物理检索观测10339fd。
- 完整后端1681PASS/1SKIP为8638b05启动快照；后续G相关284PASS为5e9fb1b。前端209PASS/25SKIP、lint/build/audit通过，旧报告83PASS。重叠测试不求和。
- 旧Agent2PASS、QA12PASS、阅读4PASS、报告20PASS、财务边界18PASS、来源失效1PASS及各自fresh模拟经营旅程通过。最终新21项在固定ad12570全PASS（0失败/跳过/重试），服务器停止，S4实际context观察链通过；早先19/1失败和dirty20PASS记录保留。
- 真实g-live-01有2个provider响应及2个source_quote，但Milvus挂钩错API计数0，保留insufficient。修正物理观测后新g-live-02已完成：2provider、4物理Milvus成功0失败、2source_quote、GET新增0、财务写0，observed_pending_human_review；真人语义及财务接受不由自动化代替。

## 待收口

最终新旧浏览器结果、实际live物理证据、README/交付文档、独立审查和本地PR说明已准备。用户需对真实原文语义和明确财务核准旅程作人工复核，见human-review.md。详见tests/release-notes/user-guide，不把未覆盖项称通过。

Codex侧栏项目根目录仍需用户在UI改为findoc-agent：现有API不能改项目路径，电脑控制访问Codex自身被拒。代码与所有工作聊天都已使用正确仓库的绝对路径，此UI归属问题不阻断实现。
