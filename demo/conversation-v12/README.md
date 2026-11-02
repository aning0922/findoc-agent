# FinDoc V1.2 真实模型历史只读页

这是独立的本地静态阅读页，展示本轮实际模型已经提交的五轮 Conversation 历史。它不替代完整 app，不包含可写聊天、财务接受、事实保存或恢复执行功能；不会调用模型、检索或业务 API。人工语义审核仍待完成，没有真人财务接受证据。

在 findoc-agent 仓库根目录运行：

```bash
python3 -m http.server 14407 --bind 127.0.0.1 --directory demo/conversation-v12
```

然后打开 [本地阅读页](http://127.0.0.1:14407/)。关闭该命令可停止这份静态服务；不需要启动后端或配置模型凭据。请勿直接以 `file://` 打开，浏览器通常会阻止同目录 JSON 的 fetch。这里的“离线”指无需互联网或模型服务；需要本机 HTTP 服务读取静态文件。

## 数据由主控导出

页面只使用同目录 `real-model-history.json`，由主控在 g-live-02 完成后导出；本次页面开发不生成或覆盖真实 JSON。数据未就绪时页面显示无法读取，不填充模拟对话或宣称真实验收成功。可以点击“重新读取本地快照”重新 GET 同一个文件。

约定外层结构：

```text
schema: findoc-conversation-v12-readonly-v1
observation:
  status, head, configured_model, provider_response_models,
  physical_provider_attempts, bge_calls, milvus_search_calls,
  human_semantic_review, financial_write_counts
conversation:
  conversation_id, selected_documents?（主控导出的所选资料 document_id / id / sha256）
turns:
  原 ConversationTurnDTO 数组，保持已提交顺序与原始字段
```

页面展示实际轮数，不补造缺失消息。`observation.status`、配置模型与供应商返回的模型名、物理调用次数、BGE/Milvus 次数和财务写计数分别呈现，不将 UNKNOWN、失败、零调用或未记录状态改写为通过。运行状态包含 synthetic/sample 时会显著标注“合成样例，仅用于布局自查”。合成 JSON 仅可在临时隔离目录中用于验证，不能作为本目录的真实模型资产提交。

## 模型与来源边界

- “真实模型已提交历史”说明这份快照的来历，不证明模型解释或全部金融语义已经人工核准。单独的供应商响应不能替代 BGE、Milvus、受控工具及业务全链路验收；以 observation 记录为准。
- `configured_model` 与 `provider_response_models` 可能不同，页面分别保留，不将配置名当成供应商实际返回名。
- 解析焦点、结果种类、原始 answer_text 和引用文本按数据展示。正文仅通过 DOM `textContent` 渲染，不执行文本中的 HTML、脚本或 Markdown 链接。复杂表格标记可能以原始文字显示；不重新改写模型/引用内容。
- 所选资料中的 `id` 是导出标签（例如 midea-2025），不是完整来源身份 DTO；该列表的 document_id / sha256 只作标识。完整引用来源字段以每轮 evidence_refs 为准，不伪称另有完整 scope 字段。
- 来源报告年度与财务年度不同。引用保留报告年度、物理页、source_revision 与 content_sha256 等技术身份；SHA 只是身份线索，本页不读取 PDF 字节或重新核准来源资格。
- 原 PDF 不随本页打包，不生成占位 PDF，也不提供 app API 的失效深链。请回到完整本地 app，根据原记录的来源身份、年度与物理页核对真实文件；不能自动替换为同名新版本。
- 偏好候选和历史财务事实只是保存内容，本页不确认偏好、不执行 ACCEPT/SAVE/RESUME、不重新计算。仅靠历史页面不能证明真人接受事实或删除偏好后的运行行为。

所有样式与脚本均在 index.html 内，无额外依赖、外部字体或第三方脚本。fetch 使用固定的 `./real-model-history.json` 路径、GET 和禁止重定向，不读取 .env 或供应商配置。无需公开部署；只监听 127.0.0.1。导出 JSON 前应另行检查聊天内容及来源资料是否适合分享。

## 核对方式

临时合成快照只能证明加载、转义、390/1440 布局和 GET-only 行为；真实 JSON 由主控写入后，仍需重新核对实际五轮内容、来源身份及截图。开发时的合成自查不是实际模型运行证据，也不改写既有 live 记录的状态。

本轮真实 JSON 写入后已完成实际浏览器核对：390/1440均显示五轮、无整页横溢，回答及引用文本逐项等于导出DTO；只有静态页与同目录JSON的GET，0页面错误。原始导出SHA256为 `5992798ab7a5fc0e13c0f083573176ee43a6358a7756e4a6aaf14a7d35e4105f`。截图与检查记录保存于本机忽略目录 `data/conversation-v12-validation/g-live-02/readonly-demo/`，不作为真人金融语义通过。
