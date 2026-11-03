# M02 研究记忆面板交接

分支 `codex/showcase-m02-ui` 从集成分支建立，保留 `codex/showcase-s03`。导出 `ResearchMemoryPanel({ companyId?: string, conversationId?: string })`，默认折叠；root 可在 AI 工作区挂载。组件仅对有 companyId 的记忆按企业筛选和绑定；无来源 turn 时不传 conversationId。旧 ResearchPreferences 按其真实导出直接复用；其内部写成功回调尚未提供，root 需要在偏好保存确认后补发 `CustomEvent('findoc-preferences-updated')`。

新增 sessionStorage key `findoc:research-memory-operation:v1`，在已有 demoHintBoundary 按前缀跨代清理；同代刷新保留 UUID。写返回未知后仅查询 operations 原 UUID，不自动重放。对所有失败均保留查证状态（包括确定性冲突），需主控后续设计可安全放弃未登记冲突的交互。删除经二次确认及 revision；笔记写需勾选确认。来源收藏只展示和删除，编辑关闭。GET异常清空结果，不伪造召回。

验证：`npm run build` 成功；`npm run lint` exit 0，存在既有告警及本组件 effect 告警。`frontend/tests/research-memory/smoke.cjs` 使用本机 Chrome 与 fake API，在 1440/1280/390 覆盖 create、写结果 UNKNOWN、硬刷新同代查证、搜索和删除；截图 `/tmp/research-memory-{1440,1280,390}.png`，390 已目视检查。测试环境的旧偏好 API fixture 不符合旧偏好 DTO，截图显示偏好不可读取；不能视为偏好集成成功。编辑、搜索失败、跨代清理浏览器实际验证、真实 BGE/两会话和真实 API 尚未验证；请求并发时公司切换/旧查询返回次序仍需主控验收。运行：在 frontend 启动 `vite --host 127.0.0.1 --port 5198`，再 `node tests/research-memory/smoke.cjs`。

## Follow-up：作用域与测试

公司和会话组合切换时重新挂载隔离面板、清除旧显示，pending key 含编码后的完整 scope；卸载后的迟到写回执不能改变新面板或清理同范围后来生成的线索。每次列表请求递增 epoch，旧响应不能覆盖新读取。原有旧格式 pending key 不再在新面板恢复；跨代由同一 prefix 边界清理。复用偏好的 fixture 已改为真实 `memory-list-v1`/generation/items；未修改旧偏好组件，更新事件仍由主控补发。

假 API 在 1440/1280/390 跑通 create、断线刷新和同 UUID 查证、PATCH 编辑、搜索、搜索失败清空、删除、代次清除、切换上下文及旧范围延迟查询响应不显示。三宽截图在 `/tmp/research-memory-{1440,1280,390}.png`；构建和 lint 命令通过，lint 仍有告警。测试未覆盖真实 BGE/会话、真实旧偏好写成功事件，亦未覆盖同 scope 并发请求的网络反序以及切换进行中的未知写回执；这些仍需集成验证。未使用付费模型。
