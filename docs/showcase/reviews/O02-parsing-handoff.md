# O02 有限接口与接线草案（实现进行中）

基线 `7141ec8`；接口先供主控审阅，非完成声明。主控拥有 runtime/gateway/前端接线；本任务只新增 app/parsing、对应测试及本文。

推荐 `ParseV2Service(runtime_root=Path, documents=DocumentService, sources=DocumentSourceService, engine=VisionEngine(...))`，`create_parse_router(service)`。runtime_root 是服务端当前 generation，独立 `parse-v2.db` + `parse-v2/`，不碰旧迁移、旧 parser/Milvus。工厂只接收服务端可信依赖和根目录。

- `POST /documents/{id}/parse-retry`：`{operation_id,expected_source_revision}`；同 op 同请求复读，不重复 OCR，冲突409。为 failed 文档也可服务端基于 document_id/PDF SHA/attempt/旧 parser_version 算当前来源身份（该 identity 不声称旧来源已捕获或 ready）；上传来源 PDF 和绑定元数据须存在。操作执行中状态 `unknown` 可 GET 查询；失败/partial 不覆盖 active 完整指针。
- `GET /documents/{id}/parse-operations/{operation_id}`：只读操作与 artifact 状态，不重试。`GET /documents/{id}/parse-quality?artifact_id=...` 精确读取历史；缺 artifact_id 时仅读当前完成指针。每页物理页号从1起，method fast/ocr，候选转录 `ocr_transcription_unreviewed`，表格只提供 needs_review 预览，不提供未经验证的格子或财务数值。
- `GET /documents/{id}/parse-artifacts/{artifact_id}/pages/{page}/image`：仅服务器解析对应文档对象，生成 PNG；不能接收路径。历史 source identity 非当前时拒绝返回误绑定的新 PDF。可另复用既有受控 PDF 路由。
- `GET /documents/{id}/parse-artifacts/{artifact_id}/search?q=...`：独立 SQLite FTS 候选，仅当前身份匹配时可调用；返回文本、页码、artifact/source identity 与未核对标签，不接入旧证据/财务工具。
- immutable artifact 包含 document_id、content_sha256、old_source_revision、attempt、旧 parser_version、metadata_hash、artifact_id、engine/version、adapter_version、config_hash、output_sha256、model_revision=unknown、state、逐页数据；保留历史，当前 source 变化必须标 stale 且不可当当前证据。扫描身份独立 pending，不将 manual_check 变为 matches_cover。
- OCR 在 macOS 以固定 Swift Apple Vision 脚本、受限页数/图像/单页子进程超时执行，子进程留在 generation 进程组；嵌入文本走 fast。重任务有界，禁止从 GET 触发。扫描页错误只生成 partial/failed，不悄悄补值或更新完整指针。页号、原始源 SHA 与 OCR 身份分开。

待实现验证：真实公开年报派生栅格页（非原生扫描报告）的真实 Vision + 同 op 幂等；合成测试验证旧源变动拒绝/历史 stale、partial 不换 active、独立检索、旧 fast 无修改。无人工签核、模型/API或旧库覆盖。
