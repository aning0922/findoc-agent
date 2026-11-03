# D02 已验证演示目录 / 安全下载 / 导入交接

2026-11-03（Asia/Taipei）。分支 `codex/showcase-d02`，base `2f3223d`；旧评审/H01 分支未重写。派工 Sol/high，当前 developer 模型标识 gpt-6.1-sol；没有额外推理档位运行元数据。未创建子代理。

## 交付与接线

唯一业务新增范围 `app/disclosures/*`，另有 `tests/test_disclosures.py` 与本交接文档。未修改 DocumentService/source_service/runtime_factory/migrations、前端、主控状态、seed 或既有 data/PDF。

主控接线（当前 generation 的同一组对象）：

```python
from app.disclosures import DisclosureService, create_disclosure_router

service = DisclosureService(
    runtime_root=runtime_root,
    sources=source_service,       # DocumentSourceService
    companies=company_service,   # 与 sources.companies 相同实例
    # downloader=None            # 默认 SafeDownloader；仅测试时注入替身
)
app.include_router(create_disclosure_router(service))
```

constructor 要求现有 documents.db 和所有服务绑定相同 runtime_root，不创建业务数据库、不注册旧迁移。独立创建 `runtime_root/disclosure-imports.db`（0600）。其生命周期随 generation；主控必须将新模块三个路由纳入内部 child/router，并将 POST `/disclosures/import` 登记 gateway mutation 白名单，保留 native operation_id（`native_operation=True`）。不要公开 child 端口；lease/身份/旧代响应拦截由现有 gateway 执行。

## 路由与 DTO

1. `GET /disclosures/search?code=格力&report_year=2025`；code 可为证券代码或公司中文名片段，年度允许空。返回 `{schema_version:"disclosure-search-v1",source_scope:"verified_demo_catalog",items:[],limitations:[],fallback}`。空 code、范围外代码/年度为空 items，提示现有手动上传。重复/未知 query、非法年度为 422。
2. item 固定 `candidate_id,company_code,company_name,title,report_year,kind:"annual_full",publish_date:null,is_amendment:null,amendment_status:"not_verified",official_url,provider,sha256,checked_at:"2026-11-03",downloadable:true`。目录来自 D01 四份 URL/SHA；仅美的 000333、格力 000651，2024/2025 正文。没有实时全市场发现、最新公告或无更正保证。未证实发布日期和更正状态不从 URL 日期推造。
3. `POST /disclosures/import {operation_id,candidate_id,company_id}`，严格拒绝额外 URL/路径/版本/金额字段。服务端精确核对公司 code、全称、SZSE、CN；不会帮客户端创建公司。选择年份与全年期间、PRC_GAAP 元数据由目录恢复，不执行财务确认。
4. 返回 `{schema_version:"disclosure-import-v1",operation_id,state,phase,error_code,result}`。completed 为 HTTP 200，result 是原 source upload 的 document_id/duplicate/queued 状态/metadata/assessment/physical_pages/source_url，另附 `disclosure_import` 下载证明（candidate_id、官方 URL、实际 SHA、字节数、downloaded_at、目录检查日期）。completed 指上传/绑定结束，不是解析 READY；原 dispatcher 继续原处理流程。
5. `GET /disclosures/imports/{operation_id}` 只读查询同一账本 DTO，HTTP 200；未知 op 404，非法 UUID 422。unknown 时 POST 为 409，failed 为 502；客户端查 GET，不自动换 ID 重发。独立路由校验/错误使用脱敏 `{detail:{code,message}}`；有账本结果的 failed/unknown 保留完整操作状态 DTO。响应 no-store。

source_url_status 保留现有 `user_declared` 语义，不冒充改造了旧 SourceService 的来源合同；实际官方 HTTPS/SHA 校验证明在新模块 `disclosure_import` 与目录中。新增 `publish_date:null/is_amendment:null` 必须让 UI 显示未知，不按 false/无更正解释。

## 下载与幂等边界

- 只接受服务端四个 candidate 对应 URL；没有任意 URL 代理入口。精确 HTTPS 主机 allowlist 为 www.midea.com.cn、static.cninfo.com.cn、disc.static.szse.cn，拒绝用户信息、非443端口、fragment。
- 每跳解析 DNS，所有返回地址都须 ipaddress.is_global；拒绝混合公网/内网、loopback/linklocal/IPv6 loopback。连接固定到这次校验的 IP，不让连接阶段重新解析同一域名；Host 与 `sni_hostname` 保留原官方主机，TLS 证书校验不关闭。已读锁定环境 httpcore 对 sni_hostname 扩展的实现并以真实下载验证。
- trust_env=False、follow_redirects=False；最多3跳且每跳重新校验 host/DNS/IP。全下载总60秒，单阶段20秒、无自动重试；20MiB 硬上限（声明与流式实际双检查）、禁压缩响应、PDF magic、固定目录 SHA。验证全部结束后才调用上传服务。
- operation UUID + candidate/company request hash；短 SQLite IMMEDIATE 事务 reserve 后释放，再进行 HTTP/上传；同 op 同请求复读结果，不重复下载/上传，同 op 异内容409。不同 op 同 PDF 复用现有 DocumentService 的 SHA 身份/去重。
- reserve 初始为 unknown/downloading；可明确证明无上传的下载失败记 failed。进入上传阶段后可能存在部分提交，异常保持 unknown/uploading，不伪称安全重试；崩溃、取消或提交读回不确定也不自动续跑。查询不触发下载或恢复。没有跨业务库的虚构原子事务，UNKNOWN 需操作者核查原文档/来源后另行决定。
- API 成功没有财务 receipt，不将封面程序匹配当真人财务确认；真实未知/失败不悄悄回落示例。

## 实际验证

命令：

```sh
uv run --frozen --group checks ruff check app/disclosures tests/test_disclosures.py
uv run --frozen --group checks pytest -q tests/test_disclosures.py
```

结果：ruff PASS；pytest 3 PASS（约1秒），5条 PyMuPDF SWIG DeprecationWarning 保留。UNIT_FAKE 测试使用全新临时 SQLite、合成中文 PDF、假 HTTP：公司错配前置拒绝、实际 source upload/fast parse、同op恢复/冲突、不同op SHA 去重、上传未知不重放、DNS/IP固定与混合/内网拒绝、跳转每跳验证、超时、magic/SHA/大小拒绝、范围外空态、严格 DTO 与操作查询。初次 ruff 检查发现测试中的分号/unused import，已修正；首次业务 pytest 已通过，未删除断言。没有全量回归或浏览器验证。

真实验证命令：`PYTHONPATH=. .venv/bin/python /tmp/findoc-d02-real.py`（该临时脚本本次已执行；下方列足够复现的机制，不把临时路径当永久构建依赖）。脚本新建 tempfile runtime，用现有 `tests.test_document_sources.Harness` 装配真实 SQLite/ObjectStore/DocumentSourceService/fast parser，仅 embed/index 为替身，创建准确公司元数据，调用默认 SafeDownloader 的 service.import_candidate，然后 `h.processor.process(document_id)` 与 `h.service.source(document_id)`。

真实下载/解析证据：

- 官方 URL：`https://static.cninfo.com.cn/finalpage/2026-04-29/1225250396.PDF`
- SHA256：`7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c`，与 D01 一致；2,350,012 bytes；219物理页。
- 上传返回 completed、原文档 queued；真实 fast parser 后 READY。公司/报告年/类型均 matches_cover；basis/period 仍 manual_check，financial_facts=not_verified。
- 整个 HTTP→校验→真实上传→fast parse→source 读回约12.084秒。LLM/OCR调用0，财务接受0；并非部署性能保证。
- 新临时目录 `/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-d02-real-vcpcrdxb`，proof 在 evidence.json；PDF 仅落新临时对象仓库，没有重下其他三份或更改 D01/原始 PDF。等级 `REAL_OFFICIAL_HTTP_REAL_FAST_PARSE_FAKE_EMBED_INDEX_NO_LLM`，不声称真实 embedding/Milvus、OCR 或财务人工核准。
- 本次真实执行在追加下载证明字段与局部 API 校验错误格式前完成，下载器/上传/解析代码未再改动；这些后续局部字段变化由最终 UNIT_FAKE 覆盖，未为字段改动重复下载。

## 限制与主控下一步

集成 owner 接 runtime/router 和 gateway 白名单，再由 D03 消费 search.items / import result / GET operation；新库需随 generation 复制/恢复策略处理。旧手动上传保留现有入口。本任务不提供 UI，不变更全市场官方 API、不自行纠正公司元数据、不自动重试 UNKNOWN。仅真实验证四份目录中的格力2025这一份，本任务不扩大 D01 其余三份下载证据为解析通过。

目录标题为已知公司年度正文的规范展示名；publish_date/amendment 为空是有意保留的未知。DNS多IP目前使用首个已验证地址、失败不自动换IP重试，现场不可达时可用手动上传；同一进程库与source写入之间无法原子提交，因此UNKNOWN是必须保留的结果。HTTP服务长期权限/多租户/部署均不属于本提交。提交前执行 git diff --check；不部署、不合 main、不 force push。
