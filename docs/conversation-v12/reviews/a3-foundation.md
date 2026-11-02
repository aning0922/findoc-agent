# A3 前端基础轻量审查

日期：2026-11-02（Asia/Taipei）。范围：当前独立 worktree `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12` 内的新 Conversations 页面、conversationSources/state、productRoutes、FinancialProduct/AppShell 路由装配与 QADialog 差异；依据已冻结 `docs/conversation-v12/contracts.md`。只读审查，仅新增此报告，未改业务代码/测试/Git，未运行回归或浏览器。并发开发中的后续接线不在本次结论内。

## 结论与 findings

**当前受审基础代码没有足够证据支持的缺陷 finding。** 可继续按冻结 DTO 接线；这不是完整 A3 或浏览器验收通过。创建、历史和发送尚未接入的占位状态符合此阶段范围，没有将其报告为最终功能 bug。

## 静态证据

- **旧深链保留。** `frontend/src/product/productRoutes.ts:9–18` 仍解析 `/research`、mode/run/task；`qaPath` 仍生成 company/return_task，新增 conversation 参数重复校验。`FinancialProduct.tsx:127` 附近将新页面独立装配，旧 research 分支保留；`ResearchWorkbench.tsx` 的 return_task 读取、身份核验与返回链接未被替换。AppShell 仅把原问答导航入口指向 `/conversations`，旧页面有回到单次问答的链接。测试定义 `frontend/tests/conversationFoundation.test.ts` 覆盖了路由级深链，但本轮未执行。
- **没有从目录授予冻结来源权限。** `conversationSources.ts` 校验目录版本、唯一 document ID、字段类型；`selectableConversationScope` 限制1–4份、唯一且 selectable 的 annual。`Conversations.tsx:26–34,46–52` 在重新读取时清空 options，保留 draft IDs 并用新目录重新判断 ready；已失效/不在目录的选择不会满足 ready，也没有静默删除用户选择。`65–78` 允许移除已选失效项，并可从已选清单移除筛选之外的条目。正式创建/每轮冻结和字节复验由后端承担，不能以当前目录缓存替代。
- **路由归属已有卸载边界。** `FinancialProduct.tsx:64–69,101–103` 的 popstate 更新 historyEpoch，AppShell 的 key 包含 route.key/historyEpoch。因此 URL A→B 或 Back 会卸载其 children，不能只看 Conversations 未设置独立 key 就判定旧视图必然复用。`Conversations.tsx:26–34` 的目录请求在卸载时 abort，回调检查 aborted。后续发送响应还需要服务端 conversation/operation/turn 身份校验。
- **当前模态框具备基本清理。** `QADialog.tsx:9–18` 在 layout effect 保存 opener/overflow，打开 native modal；卸载 close、恢复旧 overflow，opener 仍连接才恢复焦点。此次差异加入 textarea，并过滤 hidden/inert/disabled。`Conversations.tsx:35–44` 在1099px断点变化关闭本地 panel；本地 panel 只有一个枚举值。native modal 会使背景导航不可交互，不能仅凭两处均保存 overflow 就断言当前必然发生双锁。程序化打开导航/关闭顺序仍需实测。
- **操作线索只是客户端提示。** `conversationState.ts:15–35` 对读失败明确报错；重复 operation 对应不同 kind/conversation 时拒绝；resolve 注释限定为已验证确定回执，不能由404/传输错误触发；ownership 同时比较 conversationId 与 epoch。当前页面尚未调用这些工具，不据此声称已实现 UNKNOWN 恢复，也不把尚未支持 delete 的 helper 判成最终合同违背。

## 完整 A3 接线时必须验证（非当前 finding）

1. **operation 存储与删除。** 接线明确使用 sessionStorage 还是 localStorage。当前 helper 对一个数组 key 做 read-modify-write：若用于共享 localStorage，多标签并发写入/resolve 可以覆盖另一标签的新线索；届时应采用每 operation 独立 key 或具备事务的存储，或者明确每标签隔离设计。未见生产调用选择前不把这写成当前已发生的 bug。存储失败应阻断首次 POST；UNKNOWN 保留原 op；create/delete/turn 回执按冻结接口查证；delete需补对应kind/流程或独立适配器。只投影允许的身份字段，避免结构兼容对象的额外正文被意外序列化。
2. **服务端身份与迟到响应。** conversation 参数做规范UUID/服务端身份验证；DTO同时核对路由会话、operation、turn、schema；旧epoch响应不能写入新视图。Abort仅撤销前端所有权，不能宣称服务器取消。已登记但响应丢失、GET404/503、损坏响应均不得自动重POST。
3. **冻结来源与失效。** 区分创建草稿 selected IDs 和历史 frozen documents；历史会话的“选择资料”只进入新会话，不修改旧 scope。创建服务端复验；来源失效撤下当前有效声明，历史内容按快照保留；source_states=current_at_read 不能宣传为重读PDF字节。目录刷新时同document的元数据变化属于草稿重新确认，不得覆盖已创建会话身份。
4. **深链实际回归。** `/research?mode=qa&run=...`、company/return_task、经营任务、精确报告版本与原PDF仍可读；导航到新页面不携带旧 task/run/report 或全局企业作为授权范围。route参数不能产生自动ACCEPT/SAVE/RESUME。
5. **焦点与锁实测。** 390/1440下来源开关、Esc、Tab/Shift+Tab（含textarea与折叠details）、来源失效、Back/路由卸载/断点切换之后 `:modal` 与overflow还原；导航与本地panel互斥。异步添加/移除最后焦点控件时，焦点仍回有效控件。新来源/PDF/偏好面板不得并行建立独立锁。
6. **页面布局及可访问性。** 长来源名/宽表无整页溢出；输入sticky不遮正文；键盘弹起/安全区需设备实测。GET状态刷新不抢输入焦点、不反复朗读完整消息。当前CSS审阅不能替代这些浏览器证据。

本次没有执行单测、构建、E2E或真实来源验证；没有新增PASS数量。G的全量独立审查由主控后续安排。
