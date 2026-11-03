# M1 DATA D02–D05 controller-side handoff

2026-11-03；`codex/cplus-discovery-cache` from frozen root `3c737327198a55b72d02490a981b5259cd164ffa`，起始tracked clean，保留source-spike。已读ADR/API_V1/PORTS_V1及独立review最小切片。仅新增本worker目录、两test文件、本文、D01下M1 proof；未修改root/runtime/demo/disclosures旧服务或root retrieval脚本。无付费模型、无.env/密码/原开发DB/账本访问，无新agent。

## Root可直接组装的接口

```python
from app.company_discovery import (
    CNInfoProvider, DiscoveryService, TrustedImportIdentity, create_discovery_router,
)
from app.public_pdf_cache import PublicPdfCacheBroker

provider = CNInfoProvider()  # 固定两个CNInfo HTTPS metadata端点
cache = PublicPdfCacheBroker(cplus_control_root, max_disk_bytes=256*1024*1024)
service = DiscoveryService(cplus_control_root, provider, cache, captured_binder, validate_current_identity)
router = create_discovery_router(service, identity_provider)
# root把router放在C+ controller authenticated /api透传；不要装到child。
# controller关闭时 cache.close() 释放唯一writer flock。
```

- `TrustedImportIdentity(generation:int, instance_id:str, principal:str, expires_at:float, fence:Callable[[], ContextManager])` 仅root构造。`validate_current_identity(identity)`同步校验当前捕获handle/登录人/代；`identity_provider(request)`可sync或async。浏览器body严禁上述identity、URL/path/任意SHA/公司名；Strict DTO拒绝额外字段，confirmed必须bool true，1不接受。
- `identity.guard(validate_current_identity)`在持久化、ticket读取、network前后、cache最终落盘、最后operation发布时检查。fence必须由root提供真实当前controller publication guard（与接管/reset互斥），不能生产接线nullcontext。binder必须捕获旧代的确切private child handle，不能在请求中重新挑当前新代。
- **CapturedGenerationBinder精确签名**：`async binder(identity, public_pdf_bytes, resolved_company_identity, announcement, *, on_phase)`。第五个keyword是为了准确保存已创建公司副作用：创建成功后`await on_phase('company_created', created_company_id=actual_id)`，上传前`await on_phase('uploading')`。返回`{'company_id':actual_id,'document_id':actual_id,'status':'queued|parsing|indexing|ready|failed'}`。这是必要的阶段回调，不能丢掉公司创建后上传失败的状态。
- resolved identity包括唯一封面`official_name,security_code,exchange,country,identity_status`和`company_id`请求选择、`create_company`明确同意。root binder先按本代workspace+exchange+code查询，已有名称冲突应raise DiscoveryError('needs_manual_review')、不patch；新建必须create consent，复用现CompanyService create/SourceService.upload。每次child读/写前后以及最终响应都必须检验捕获identity；company/upload使用同operation派生的幂等能力（若旧API不能实现幂等，不在UNKNOWN后重跑）。服务不会自动重试binder。
- 先封面检查再binder，首版只支持A股SSE/SZSE、中文年度全文；首物理页唯一法定全称、明确公司/证券/股票代码与报告年度匹配，代码规则与market一致；摘要/英文/缺码/多名字/加密/冲突均不创建公司、不上传，返回unsupported/needs_manual_review。封面匹配不是财务审核；会计准则等未知字段不要凭provider补PRC_GAAP，应由现SourceService保留manual/unknown。
- 同API_V1四路由：POST searches联网一次且持久化搜索snapshot；GET searches只读；POST imports `{operation_id,candidate_id,candidate_digest,company_id?,create_company:false,confirmed:true}`；GET imports只读本owner原receipt。不接受无选定证券快照直接拼orgId查询。POST也是同步有限执行，调用中断后以同UUID GET读unknown，不再次执行。
- Import receipt `schema_version=cplus-import-v1,operation_id,state,phase,error_code`，成功另有document_id/company_id/document_state/sha256/cache_hit；公司阶段已发生则保存created_company_id。**document_state是binder返回时快照**，完整READY轮询请root/UI走既有本代`GET /documents/{document_id}`，不能把queued标READY。GET receipt不会向provider/child发请求或触发解析。

## 隔离、持久化和缓存

`<control>/discovery-private.sqlite`：owner绑定的搜索候选、操作、ticket。candidate不可UPDATE；digest/expiry/owner、generation/instance/principal均校验。证券候选security_id先服务端存储，公告恢复其完整身份。import reservation UNKNOWN先于ticket/network/company/upload；相同UUID+body只读旧状态、不同body409、其他owner404。binder异常保留UNKNOWN和最后phase；过期调用fail closed。未挂接返回500的未知异常不会自动重试，用户GET恢复原op。

`<control>/public-pdf-cache/{objects/<sha>.pdf,public.sqlite,writer.lock}`：controller唯一writer flock；无child path端口，broker.prepare/read_ready只接不透明ticket ID和trusted identity，通过注入私有ticket reader从controller恢复原候选URL和同意，不接受自由URL。公有provenance不存principal、generation、业务company ID、请求op、搜索token。文件copy/write不hardlink；读命中重新hash和封面验证，symlink/hardlink拒绝。版本digest排除私有snapshot时间/ID，因此新代新ticket在相同公告版本上可复用；内容SHA不覆盖。全controller串行flight覆盖相同版本且防磁盘容量竞争；开始冷下载前为20MiB最大文件预留空间，默认256MiB对象容量满则507，**未实现自动LRU/GC**。D06旧代GC仍root owns，不碰本cache或seed。

新UnknownShaDownloader保持旧downloader不动：仅`https://static.cninfo.com.cn/finalpage/YYYY-MM-DD/id.PDF`；每跳重新检查固定host/path/公网DNS、连接已检查IP、Host/TLS SNI原域名；最多3跳、60s总时限、20MiB、identity编码、长度/魔数和完整实际SHA，无假expected SHA。封面验证后才注册cache。provider和downloader共享RequestPacer≥1.1s；provider 403/429冷却5分钟、无自动重试，返回external_blocked/官网或上传fallback。官方接口是观察可用的网页adapter，不提供长期API许可/SLA。

## 真实发现、修正与验证边界

**重要字段修正：CNInfo `type=shj`不是SSE market。** 本次真实请求表明000333/000651也type=shj；代码现保留provider_security_type，结合category=A股及证券代码命名空间6xxxxx→SSE、0xxxxx/3xxxxx→SZSE，其余unsupported。D01旧建议的shj→SSE不再适用。A/H股同orgId，security_id区分归一market+code，HK只显示候选且supported=false。没有provider法定全称则official_name=null。

- `M1-real-provider-cache-initial.json`保留首轮错误映射状态 `PARTIAL_INITIAL_EXCHANGE_MAPPING_FAILED_FOR_SZSE`。该轮海尔官方metadata/已pin未知SHA冷下载/第二次缓存命中成功，但美的格力market错不能算PASS。
- 修正后`M1-real-company-corrected.json`用4次真实查询确认代码600690、简称美的、拼音gldq、模糊海尔，至少海尔/美的/格力三主体。保留跨市场/债券/退市候选，支持资格不混淆。无额外PDF下载。
- 本轮新增真实外部请求**10**＝首轮5 metadata+1 PDF、纠正4 metadata；各轮间隔≥1.1009s，轮次间无重叠且相隔更久。原D01 17次为先前Spike，不算本轮新增额度。新模型调用0。真实冷下载只一次1,823,191 bytes，SHA `14186f9f9b47f687c527ba14825664f3b09e51759d581636cddcc248f26e3660`与D01一致。缓存第二次导入和原op GET/重放新增请求0。
- 真实cache proof binder刻意为SIMULATED_PHASES_NO_COMPANY_OR_DOCUMENT_WRITES，返回SIMULATED IDs和queued：**没有真实本代公司创建、upload/processor/BGE/Milvus READY或browser验收**。这些必须由root真实binder/浏览器补验，D04完整READY仍pending。
- 两专项文件共3个代表性test覆盖：GET/replay不联网、额外字段/confirmed1拒绝、跨代新票+缓存命中/旧票拒绝、op冲突、公司已创建后UNKNOWN不重放、冷下载中代际失效不落盘/不bind、错误封面不bind、DNS内网/跳转越权/过大/HTML非PDF、TLS SNI/IP pin；加入真实发现的SZSE类型回归。Ruff通过。Swig弃用warning保留；最终pytest结果见交付。

## Root下一步实际验收

组装C+ controller router、真实认证/fence和上述binder callback；同company_id名称冲突和公司create后upload断线真实状态检查；新公司海尔真实upload→processor→BGE/Milvus READY；轮询原document状态；新代需要重新候选/ticket且缓存命中仍独立upload/索引；确认旧代最后发布被拒绝。工作树不得按本helper已完成就写“D04 READY PASS”。provider公告revision缺信息为null，明确title含修订/更正/更新版才标revised，仍不推断完整替代关系。
