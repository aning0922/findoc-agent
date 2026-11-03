# 03｜巨潮模糊搜索 / 下载 / 本地缓存 / 演示复位

## 当前限制

`DisclosureService.search(code, report_year)` 仅遍历 `catalog.json` 四个候选。`import_candidate` 通过已有 SafeDownloader 按预置 SHA 下载。其下游 `DocumentSourceService.upload` 已有绑定/解析/索引能力。**C+ 仅扩展 discovery adapter 与下载缓存，不能复制另一套 PDF 处理系统。**

## 数据来源与合规

- 官方首选：`https://www.cninfo.com.cn/new/snapshot/companyListCn` 公司列表和 `https://www.cninfo.com.cn/new/commonUrl?url=disclosure%2Flist%2Fnotice` 信息披露页面，公开网页支持代码、简称/拼音和公告分类搜索。
- 网页有检索入口不代表开放、稳定、允许无限自动访问的 API。第三方对历史 AJAX 的分析仅供 spike，**不能直接当作经官方保证的长期接口合同**。
- 开发先做 D-SPK：确认访问条件、HTTPS、返回字段/频率、是否需合法 token、是否有限流/验证码；无法确认则实现前端跳转官方查询及手动上传回退。
- 严禁突破 CAPTCHA、账号认证、访问限制或大规模爬取；请求有实际限流、缓存和超时，用户主动选定才下载。

## 两级检索

1. `CompanyResolver`: 匹配证券代码、标准简称、名称子串、拼音首字母、企业别名；返回 `company_candidate` `{security_code,market,display_name,official_name,source,match_type,confidence}`。默认候选上限 10，按代码精确→名称→拼音排。歧义不自动选。
2. `AnnouncementProvider`: 已选公司 + 年报年度 + 分类(全文/摘要/更正) → 公告列表 `{announcement_id, publish_at?, title, report_year, kind, revision_kind, official_page_url, pdf_url?, source_provider, checked_at, verification_state}`。发布日期/更正状态不能猜；正文优先但用户仍明确选择。
3. `ImportCoordinator`: 创建 `operation_id`，验证 candidate、公司身份、域名、PDF 页眉/封面、大小、文档 SHA、已存版本；调用原 `DocumentSourceService.upload()`，返回 operation receipt 和 `document_id`，直至 `ready`。

## 下载与本地文件

**推荐结构（均为草案，由 M0 冻结）**

```
control_root/
  public-pdf-cache/sha256/<2prefix>/<sha>.pdf    # 只存已验证官方公开PDF；缓存跨 generation
  public-pdf-cache/metadata.sqlite               # 来源、原URL、下载日期、大小、sha、访问策略
  active/<generation>/objects/documents/<id>.pdf # 已绑定的本代业务对象
  active/<generation>/documents.db                # 业务身份/解析状态
  active/<generation>/milvus.db                   # 本代向量索引
  active/<generation>/parse-v2.db                 # 本代OCR独立产物
```

- 未知 SHA 时在隔离下载 tmp 写入，验证 PDF 魔数、大小、实际 SHA 后以原子 rename 注册 `sha256` 缓存对象；缓存条目不可从浏览器指定绝对路径。
- 缓存只允许“经过发现适配器验证的公开官方 PDF”。不能把用户上传 PDF 或模型输出共享到跨代缓存。
- 对同 SHA 同解析器版本且已存衍生索引的情况，可做只读工件缓存；**首版先只共享 PDF bytes**，本代索引继续由现有 DocumentProcessor 创建，避免 Milvus workspace 污染。
- SHA 相同且同工作空间时原 `DocumentService` 已可去重，但重置后的新 generation 是新工作空间数据根，需绑定当前代 document 记录。
- 所有网络下载由后端完成并明确拒绝内网/环回/重定向越权，禁止前端直接传任意 URL 让服务器变代理（SSRF）。

## 下载状态机

`discovered → selected → validating → downloading/cache_hit → stored → queued → parsing → indexing → ready`，异常 `failed/unknown/needs_manual_upload`。每个阶段的显示由真实操作状态驱动，前端 GET 不发起新网络或付费模型调用。

## demo 重置与过期清理

- 20 分钟时限从**登录后**起算，不把一次 PDF 下载延长当前 lease；到期/强制接管时旧 runtime generation 取消发布权限。
- 下载与索引过程每个外部 side effect/最终发布须校验 lease_generation；旧进程被收回后不能发布到新代。
- public cache 在 generation 之外，由控制层约束写权限；单独设置大小和淘汰规则；不依赖登录退出重置 cache。
- `ProcessRuntimeManager` 停止旧进程、生成新目录后建议增加 `safe_gc_old_generations`；只清控制目录内、确认已停止且非当前/非 seed 的旧目录，不删除任何开发者原始库/seed；首次以 dry-run 报告证明。

## 限额与回退

当前 downloader/document limit 为 20MiB。C+ 设计可配置 `MAX_PDF_BYTES`（例如 40/60MiB，实际用样本验证内存/磁盘），统一网络、上传、解析三端校验。大文件建议先临时落盘，不在 HTTP 层无限堆内存。没有高可靠后台队列的要求，但用户应该能看到失败并手动重试。

## 必测异常

同名公司/拼音歧义；全文与摘要混淆；同年修订两个版本；非 PDF/HTML 200；SHA 不符；过大文件；重定向内网；重复导入；登录到期中途下载；缓存命中再次入库；新代重置后原用户文档不可见；官方来源不可用→手工上传。
