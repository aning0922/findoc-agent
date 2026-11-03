# V1.2 主控状态

更新：2026-11-03（Asia/Taipei）。代码已形成独立开发候选，本轮只做交付与状态审计。最新结果与真实/替身边界见 [交付审计](delivery-audit-20261103.md)，历史验证见 [tests.md](tests.md)。

## 仓库与实现

- 当前根目录：`/Users/aipuli/Documents/Projects/findoc-agent`；分支`codex/conversation-memory-v12-20261102`；审计/复跑产品HEAD`77a2e18ff42173d7e555a594a092439c51b116ac`。原17提交全部保留，未合并main或重写历史。
- A0/A1/A2/A3/B1/B2在冻结合同及本版保守范围内已实现接通；A4和G为**部分完成**。不是所有人工/端到端质量闸口通过。
- 正式runtime注入ConversationGraph、只读RAG/确认事实/确定性比较、MemoryService及结构摘要。GET不重执行，中断轮不自动续跑；无saver调整有明确合同依据。
- 长期Memory是明确确认的有限研究偏好，跨会话fresh recall，revision/generation/墓碑及旧候选排除实际生效。删除不改旧回答或撤回已发送供应商内容；会话删除与偏好删除独立。
- 本版自由解释关闭；不是多用户生产认证或任意自主规划器。v10/v11/v12仅追加，旧ResearchRun原文及财务公式合同保留。

## 验证与交付边界

本轮固定77a2e18复跑前端209PASS/25SKIP、lint/build/audit exit0；新会话浏览器21PASS、原controlled Agent2PASS，均为真实HTTP/SQLite/PDF配合明确provider/BGE/vector替身。完整后端1690PASS/1SKIP/0FAIL（1050.08秒），CI范围两组Ruff均exit0；命令、跳过原因及原始记录SHA由交付审计记录，不将历史重跑/交叠组相加。

历史g-live-02使用真实provider/BGE/Milvus，有2实际模型响应、4物理检索成功，状态observed_pending_human_review；本轮不重跑provider或真实业务。当前预览runtime只读观察财务接受和已确认事实均0，不能宣布真人财务核准通过。

本轮用户已授权向GitHub同名独立开发分支提交推送；代码交付与A4/G真人验收分开。远程HEAD/CI以实际GitHub记录及交付会话为准，未创建远程PR、未合并main、未部署发布。

## 当前未完成

真人原文语义和接受/保存事实后再提问旅程；新助手C12正向PDF、长会话及真实重启浏览器专项；完整读屏/软键盘；缺私有冻结资料的skip。详见 [人工复核工作单](human-review.md)。这些不因代码推送自动转为通过。

工作树已迁到新主目录，五个协作聊天归入findoc-agent；主控聊天侧栏归属API读回未生效，但所有仓库命令显式使用新根目录，不阻断代码交付。
