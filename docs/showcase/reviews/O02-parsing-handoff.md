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

## O02 实现交接（最终）

基线 `7141ec8`；最初有限接口草案提交 `54d0863`，实现及本补充在其后独立提交。M2-next-batch 原文件在主控集成工作树读取，原 Git 基线中尚未跟踪；O01 文档/JSON/Swift、API_MINIMUM 及真实 DocumentSourceService/DocumentProcessor 已读取。

### 接线与实际端点

```python
from app.parsing import ParseV2Service, VisionEngine, create_parse_router

parse_service = ParseV2Service(
    runtime_root=runtime_root, documents=document_service,
    sources=source_service, engine=VisionEngine(timeout_seconds=30),
    max_pages=50, max_seconds=180,
)
app.include_router(create_parse_router(parse_service))
```

注入的 documents 必须与 sources.documents 同实例、同 generation 的 documents.db；服务端生成隔离 `parse-v2.db`（含 artifact/operation/active 和 FTS5 trigram 表）。主控在 runtime_factory 单点装配，POST `/documents/{id}/parse-retry` 登记 gateway 白名单、`native_operation=True`；所有 GET/POST 继续通过 generation gate，不能直接公开 child。不得把新索引当旧 Milvus 集合或旧财务事实。

- `GET /documents/{id}/parse-identity`：返回服务端计算的 `document_id,company_id,report_year,report_type,content_sha256,source_revision,attempt,parser_version,metadata_sha256,legacy_source_verified:false,identity_assessment:"manual_check"`。FAILED/queued 文档也能取得该身份；它只是当前记录的计算身份，**不证明旧 SourceService 已捕获或 READY**。OCR identity assessment 是 pending/manual，仅描述公司/年报身份，不签核财务。
- `POST /documents/{id}/parse-retry` body `{operation_id,expected_source_revision}`，严格禁止额外字段。返回 `{operation_id,state:completed|partial|failed|unknown,artifact_id}`。首个 POST 等待实际本机处理；处理中同 op 重放只返回 unknown，不再次启动；不同请求同 op 返回409，当前单 worker 已忙返回423。若客户端中断，worker退出前保持锁，操作可保留 unknown；GET 不重跑。
- `GET /documents/{id}/parse-operations/{operation_id}` 按文档与 operation 查询；`GET /documents/{id}/parse-quality?artifact_id=...` 精确读历史，不传 id 读最新完整指针；不存在404。返回 `schema_version,artifact_id,document_id,company_id,report_year,report_type,content_sha256,source_revision,attempt,parser_version,metadata_sha256,engine,adapter_version,config_hash,output_sha256,model_revision,state,pages_total,ocr_pages,created_at,pages,error_code,identity_assessment,legacy_source_verified,limitations,source_status`。`source_status=current` 仅指当前对象/元数据身份一致，**不代表旧研究准入或财务事实通过**。
- artifact engine `name/version/os_version`，Vision version 为实际 request revision，model revision 固定 unknown；config hash 含 DPI、页数/时间限制、引擎名/适配版本、Swift 文件 SHA 与单页超时。output SHA 是写入前完整 artifact（不含自身 output_sha256）的 canonical JSON SHA；读取时复验。SQLite trigger 拒绝更新/删除 artifact；仅 completed 能更改 active；partial/failed 保留可读取历史。
- `pages[]` 含 1 起物理页、`method:fast|ocr`、status、text、tables、warnings；OCR 还含 Vision 返回的未经核对 line/bbox/confidence。表格仅 `{quality:"needs_review",cells:[],warning}` 候选，没有虚构结构、金额或 verified geometry。页数超上限或个别 OCR 失败为 partial/failed，不更换 active；总时间在页边界检查，可能超过配置上限最多一页执行/渲染开销，不声称硬实时。
- `GET /documents/{id}/parse-artifacts/{artifact_id}/pages/{page}/image` 渲染 PNG；`GET .../{artifact_id}/file` 读取同 identity 原 PDF；当前源身份不一致拒绝409，不返回新 PDF 冒充旧 artifact。PNG渲染前与返回前复核对象身份，限制像素。旧 PDF 原文件有版本历史访问需求时仍需后续独立存储合同，目前不伪造可用。
- `GET /documents/{id}/parse-artifacts/{artifact_id}/search?q=...` 实际查询独立 SQLite FTS5 trigram；query 3–200 字、最多20页，结果 `{artifact_id,source_revision,status:"candidate_unreviewed",items:[{physical_page,text}]}`。查询前后重验当前 source，索引返回文字与不可变 artifact 对照；failed artifact 不可检索，partial 的成功页仅作候选。运行环境需 SQLite FTS5 trigram；当前实测 3.50.4。

Apple Vision 脚本固定为 `app/parsing/vision_ocr.swift`，准确模式 zh-Hans/en-US；真实运行环境 macOS Vision request revision 3，模型版本框架未暴露。每页先检测文本层，短页渲染180DPI调用 `swift` 子进程，默认单页30秒 timeout；Swift继承 generation 进程组，未建立独立 session。进程重启遗留 unknown 不自动重跑。页数上限、预渲染像素限制及单 worker 限制在模块实现；max_seconds 为页间检查，不能解释成杀死任意卡住的 PyMuPDF 解析线程的硬 deadline。Linux 无 Apple Vision 时如实 failed，需后续平台引擎或预置产物。

### 测试与真实引擎证据

```sh
uv run --frozen --group checks ruff check app/parsing tests/test_parse_v2.py
uv run --frozen --group checks pytest -q tests/test_parse_v2.py
PYTHONPATH=. .venv/bin/python /tmp/findoc-o02-real.py
```

最终 ruff PASS，pytest **3 PASS / 1.09s**，5条 PyMuPDF SWIG DeprecationWarning 保留。UNIT_FAKE 测试：旧文档 FAILED 状态下新 OCR、同 op 不重复、FTS/PNG/PDF、同 op 不同请求冲突、跨文档 operation 拒绝、partial 不替换 active、处理途中原对象变化后 failed/旧 artifact stale/图片拒绝、恢复后原指针未变、旧文本层 fast 与 HTTP 合同。期间曾因 fixture 试图从 QUEUED 直接以 PARSING 阶段标失败，得到2 FAIL；已改为旧状态机允许的 QUEUED→PARSING→FAILED，最终3 PASS。未删断言。

真实引擎最终执行：公开美的2025年报物理第9页栅格化后得到的**单页派生扫描 PDF**（非原生扫描年报），读取集成工作树 `data/showcase-ocr-spike-20261103/derived-scan-page-9.pdf`，原文 PDF 未修改；源年报 SHA `c413ed1b993290ec98b254af4bf6ad69edb5a2230bbaec1b15702119b24d4f5c`（O01记录），派生输入 SHA `175235d1122aec489a6c943ec8c1f8f9fcb5ffdd0e75f938f5ce6080c8ed163a`。临时 runtime 实际 Apple Vision 输出68行、artifact物理页1、`ocr_pages=1`、`needs_review`，输出图片与一条 FTS 搜索可读，重复 op 无新 OCR；最终执行约1.15秒，model_revision unknown。完整结果只在 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-o02-real-vwcc_82n/proof.json`，未纳入 Git。

该次实际 artifact ID `dd77d445-2f66-4c51-9450-860b73c12f3e`、computed legacy revision `a2b80d07da80d874ef056c76cbaa279742e77de1b95bee2c2c6aad109a59ac84`、output SHA `042119e30130f8e315f94a047e07f271db8adec94ea75a6f4e7e0422cde2aa70`；随机生成的元数据/ID使不同运行 SHA可不同。扫描 PDF 的原文档为 queued 而非旧 READY，computed revision 不代表旧来源已捕获。无旧源身份放行、无金额确认、无 LLM/付费模型调用；真实测试是 `REAL_APPLE_VISION_DERIVED_SCAN_LOCAL_ONLY`，表格结构与数字仍未验收。

真实脚本在 `/tmp/findoc-o02-real.py`；复现可用 `tests.test_document_sources.Harness` 在新 tempfile 创建 documents/service/company，调用 source_service.upload 派生 PDF，再按上述工厂创建服务并 `retry`、`quality`、`search`、`image`，原样本必须存在上述本地路径。临时测试不调用 embedding/Milvus；新索引是独立 FTS，不声称旧 ResearchRun 可检索该 OCR。主控应审阅接线、generation 停止语义、状态/DTO 与视觉标签，再以最终集成 SHA 进行 O03 浏览器验证；本任务未实施人工身份接受接口、不部署、不合 main、不 push。
