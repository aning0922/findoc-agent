# FinDoc V1.2 本地开发候选交付

分支：`codex/conversation-memory-v12-20261102`，仓库findoc-agent，基线`main@1f0a3d4131480ac0ea742772127afac3c892fc7c`。实现与本地自动验证已完成，G的人工作业尚未通过。2026-11-03用户授权将已完成工作交付GitHub独立开发分支；当前阶段判定、复跑及交付记录见 [状态审计](delivery-audit-20261103.md)。没有远程PR、main合并、部署或发布。

## 可使用的能力

- “研究助手” `/conversations`：冻结1–4年报范围，保存多轮历史、结构化公司/年度/指标指代，范围外或模糊指代先澄清。旧单次原文问答及经营研究入口保留。
- 只读白名单工具：同版本年报原文、当前有效且明确选择的已确认事实、既有确定性比较。PDF链接恢复完整来源身份；无证据/未确认不能从原文心算同比。
- operation/hash/回执、数据库互斥与claim fencing：历史GET不重执行，UNKNOWN只读查原操作；重启不自动续跑。精确未登记的原POST拒绝保留草稿，禁止把通用GET404当作重发许可。
- 明确确认的研究偏好：原句候选不自动存储，可单独保存/编辑/删除；每轮新读偏好，revision/generation防旧值覆盖。来源授权和财务核准不受偏好改变。
- 追加v10会话、v11偏好、v12结构摘要，最近消息/摘要/偏好各自限额。摘要只存焦点、进度和澄清状态，不保存财务值或偏好正文。
- 手机/桌面单列消息、抽屉焦点与滚动锁清理，真实PDF阅读；宽表内部横向滚动、数值不拆行。

## 验证与演示

精确测试结果、失败历史、跳过原因和快照见 [tests.md](tests.md)。完整后端1681PASS/1SKIP为G前快照，G修复后相关284PASS；前端209PASS/25SKIP，lint/build/audit通过。旧报告后端83PASS。最终新会话21PASS（固定ad12570，0失败/跳过/重试）；旧Agent2、QA12、阅读4、报告20、财务边界18、来源失效1均通过，模拟旅程/接受明确标记。不将较早dirty快照或重复运行累计为通过。

真实 `g-live-02` 在独立runtime使用两份SHA核验年报：2次供应商请求/实际响应，5次BGE、4次物理Milvus成功、0搜索失败；两个原文摘录、两次未确认计算拒绝及一次范围澄清。每轮重读新增provider0，财务写0。配置请求模型deepseek-v4-flash，response.model实际deepseek-flash，未把别名当成同一个已验证版本声明。状态为observed_pending_human_review，尚无真人财务接受。

- 完整功能：按 [user-guide.md](user-guide.md) 启动，先准备可选来源，进入 `/conversations`。允许后续明确发送真实模型请求。
- 本轮实际只读案例： [demo/conversation-v12](../../demo/conversation-v12/README.md)，冻结真实已提交5轮、无API Key、无写接口，不能用旧静态演示冒充新功能。
- 本轮可见聊天、模型/推理变化、文件所有权与提交职责见 [orchestration.md](orchestration.md)。

## 人工复核与本版限制

自由自然语言解释关闭，interpretation_status=not_generated。本版没有多用户认证、OCR、无限工具循环、股票预测或对外发布的私有资料接口。当前是demo本地单人空间，不承诺生产级隔离或供应商计费exactly-once。

具体待办见 [人工复核工作单](human-review.md)。G仍需用户：核对只读案例中的原文语义、年度/单位/页码；在完整本地app明确核对并接受财务数据、单独保存、选择当前披露事实，再明确发送比较问题，验证结果与既有公式一致。自动化中的模拟接受不能代替这条真人旅程。S4 UI保存/新上下文召回/删除由自动化验证，真人可用性判断仍独立保留。

删除偏好只阻止后续Memory注入，不改写旧已提交聊天、不撤回供应商已收到内容或备份。删除会话保留幂等墓碑，不删除原PDF/旧ResearchRun/已确认事实。回退需停服务使用升级前完整备份或新runtime；不支持手动删migration降级，见 [migration.md](migration.md)。

2026-11-03已将V1.2工作树迁到 `/Users/aipuli/Documents/Projects/findoc-agent`，应用已识别该Git仓库，五个协作聊天归入findoc-agent项目。主控聊天侧栏归属API读回未生效，仓库操作显式使用新目录；该UI问题不改变代码、分支或验收状态。
