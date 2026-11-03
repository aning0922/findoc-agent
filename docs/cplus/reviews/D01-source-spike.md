# C+ M0 / D01 官方来源 Spike

2026-11-03；分支 `codex/cplus-source-spike`，从冻结基线 `45d55d75662f01d9bc78da1a946d845a01a27480` 新建；起始 tracked clean，保留原 `codex/showcase-e03`。仅新增 experiments/cplus、本文和 docs/cplus/evidence/D01；没有实施业务 API、缓存或修改 runtime/服务热点。

已读工作包 README/00/02/03/10/11/12/13/14/15，以及现 DisclosureService、SafeDownloader、DocumentSourceService、公司 identity 模型。工作包建议为 M0 输入，尚不是冻结合同。

## 结论和证据层级

**OBSERVED_AVAILABLE_CONDITIONAL**：本机当次无登录、无代理、无 SDK 指纹/验证码处理的直接 HTTPS 请求，官方网页/JS及候选/公告端点可用。存在真实非旧catalog企业海尔智家600690的2025年报元数据与公开PDF。**未获得官方开放API、稳定性或自动化使用授权承诺**；robots.txt HTTP404不是授权依据。可以推进可关闭、低频、带回退的适配器设计审查；不能称“官方保证稳定API”，不能据此宣布F19/F20/F21已完成或正式导入READY。

真实请求只通过实验脚本发出，共17次：16 HTTP200、1 HTTP404（robots.txt）；共读取2,250,786 bytes，最小请求起始间隔1.104848秒，无重定向跟随、重试、登录、验证码、代理、付费调用或正式导入。每次URL/表单/UTC时间/耗时/状态/大小/响应SHA均在 `../evidence/D01/requests.json`。未保存PDF bytes，未写业务库。相关结果是公开元数据与有限官方JS上下文，不含私有配置。全部外部请求现已停止。

## 官方网页和真实请求

1. [公司列表](https://www.cninfo.com.cn/new/snapshot/companyListCn) HTTP200，搜索框明确提示公司代码、简称或拼音缩写；[信息披露入口](https://www.cninfo.com.cn/new/commonUrl?url=disclosure%2Flist%2Fnotice) HTTP200。页面自身引用的 `common.js`、`new-notice.js`、`history-notice.js` 版本及SHA均留证。
2. [官方 common.js](https://static.cninfo.com.cn/new/assets/js/common.js?v=20260826101926) 包含 `/information/topSearch/query`；[官方 history-notice.js](https://www.cninfo.com.cn/new/js/app/disclosure/notice/history-notice.js?v=20260710082532) 包含 `/hisAnnouncement/query`、stock组合为code+orgId、年报分类`category_ndbg_szsh`、查询字段column/plate/stock/searchkey。仅使用网页公开业务请求，没有调用页面引用的安全SDK。
3. POST `https://www.cninfo.com.cn/new/information/topSearch/query`，form `{keyWord,maxNum:10}`：

| 输入 | 实际结果 | 设计含义 |
|---|---|---|
| `600690` | 1候选，A股海尔智家 | 代码精确也保留市场字段 |
| `海尔智家` | 600690 A股＋06690港股 | 同名跨市场不能静默选择 |
| `海尔` | 海尔智家A/H、海尔施601206、海尔生物688139 | 名称子串是候选，不是身份 |
| `hezj` | 海尔智家A/H | 实证拼音首字母可用，非任意拼音/别名保证 |
| `海尔智家股份有限公司` | 海尔智家A/H | 全称也不是证券唯一键 |

原始字段为 `code,pinyin,sjstsBond,category,type,delisted,orgId,zwjc`。600690返回`type=shj,category=A股,orgId=gssh0600690,delisted="false"`；港股06690 **同一个orgId**，因此不能以orgId单独作为证券身份，也不能直接把`shj`保存为现有exchange。是否退市仅为当次provider标志，不推定完整上市状态。候选端点没返回法定全称，全文封面/公告标题另有证据。

4. POST `https://www.cninfo.com.cn/new/hisAnnouncement/query`：`column=sse,plate=sh,stock=600690,gssh0600690,tabName=fulltext,category=category_ndbg_szsh;,searchkey=2025年年度报告,seDate=2026-01-01~2026-11-03,pageNum=1,pageSize=10`；其余原表单见ledger。HTTP200，totalAnnouncement=3、hasMore=false，但totalpages=0；不能硬用totalpages作完整性证明。查询日期是披露日期区间，**报告年度独立由标题推断再由PDF检查**，不是把2026披露年当作2026财年。

| 公告ID | 原标题类型 | provider披露日期（中国时区） | 版本 |
|---|---|---|---|
| 1225038336 | 海尔智家股份有限公司2025年年度报告 | 2026-03-27 | 中文全文候选；修订/替代状态unknown |
| 1225038309 | 海尔智家股份有限公司2025年年度报告_摘要 | 2026-03-27 | summary，不可当全文 |
| 1225215703 | 海尔智家股份有限公司2025年年度报告（英文版） | 2026-04-28 | English fulltext candidate，不与中文混为同版本 |

该查询仅覆盖一个标题条件/日期窗口/类别，**没有证明不存在更正、补充、后续替代或其他市场披露**。标题分类是确定性推断并保留raw title；`associateAnnouncement=null`不表示未修订。`adjunctSize`原值1781等的单位未从官方说明确认，保存raw值，真正体积用下载字节数。

5. 中文全文 [官方详情](https://www.cninfo.com.cn/new/disclosure/detail?stockCode=600690&announcementId=1225038336)（链接由观察字段构造，详情页未额外请求），[公开PDF](https://static.cninfo.com.cn/finalpage/2026-03-27/1225038336.PDF) 已真实GET HTTP200。Content-Length=实收1,823,191 bytes，PDF魔数正确，PyMuPDF内存打开245页，封面显示公司全称、600690、2025年度，SHA256 **`14186f9f9b47f687c527ba14825664f3b09e51759d581636cddcc248f26e3660`**。这是文档身份预检，不是财务事实核验、解析/BGE/Milvus READY或正式导入。没有运行模型、保存PDF或做财务确认。

## M0适配器建议（待审查冻结，尚未实现）

- **CompanyResolver**：受控长度查询、max10，固定provider HTTPS origin+form，不接收用户URL；原code/市场type/category/orgId/delisted均保留；显式映射`shj→SSE`、`hke→HKEX`需测试支持，未知市场保留unsupported，不能默认SZSE。证券候选键至少provider+market+code，orgId另存；选择后再绑定现有CompanyService workspace company_id。返回match_type（code_exact/name/pinyin/provider_candidate）和歧义标记；不制造概率confidence，也不宣称返回法定全称。跨市场/多候选由用户选定。
- **AnnouncementProvider**：以服务端已保存候选身份查询，拒绝前端替换orgId；保留announcementId、secCode/secName/orgId、title_raw、announcementTime原毫秒、当地日期/时区、adjunctUrl/Type/Size raw、source_url、checked_at、schema/parser版本、response SHA；分别提供report_year inference、kind全文/摘要、language、revision_kind和supersession unknown。不要用一个verified布尔值混合“provider返回/封面匹配/财务审核”。分页有硬上限，hasMore/页码异常返回partial并提示用户；不自行无限补抓。
- **URL/下载边界**：adjunctUrl必须是固定`finalpage/...`相对PDF路径，拒绝scheme/netloc、`..`、编码穿越等；只从固定`https://static.cninfo.com.cn/`构造URL。候选服务端固化为不可被浏览器篡改的candidate ID/metadata SHA；显式用户选定才发起导入。现SafeDownloader已做HTTPS allowlist、公共DNS绑定、每跳校验、20MiB、PDF魔数、expected SHA；**动态元数据没有可信预置SHA**，不能直接移除SHA校验或相信前端SHA。后续需审查“首次隔离下载→实际SHA注册→服务端候选绑定→DocumentSourceService.upload”的合同，或先以明确已预检SHA的候选受控导入。本Spike SHA仅对应本次已下载中文全文，不替所有新公告背书。
- **复用现有约束**：当前DisclosureService固定catalog及import对SZSE/name/code的检查不适用于海尔SSE，不能直接修改候选字段混入旧目录绕过；新增adapter/import coordinator应继续使用现有CompanyService和DocumentSourceService上传/封面评估，保留workspace/company/period/basis、operation_id幂等/unknown状态。本地候选discover ≠ 已绑定source，更不授予财务authority。
- **缓存/代际**：共享缓存只能存经固定官方路径与字节验证的公开PDF；不共享上传、会话、笔记、模型输出或身份。缓存命中仅复用bytes，仍须当前generation/owner fence和本代upload/解析/索引；本worker不实施publiccache。TTL和并发单飞、失败负缓存、空间上限由D02–D05合同冻结后实施。
- **限频/可用性**：建议单provider串行≤1次/秒、UI防抖/短TTL缓存、查询上限10、公告页上限、20s超时、0自动重试；403/429/验证码/非预期HTML200立即source_unavailable/external_blocked并停自动请求。禁止引入付费key、指纹SDK、代理或CAPTCHA处理来恢复。返回官网查询跳转与既有手动上传，旧精选catalog明确fallback而非dynamic。官方页面未提供接口SLA或自动化许可，本次仅技术可达；若后续官方条款不允许该访问方式，停用动态adapter并走合法回退。

## 复现及交付边界

`experiments/cplus/source_spike.py`仅接受显式JSON计划，固定两官方HTTPS host，trust_env=False、follow_redirects=False，无自动重试，跨计划ledger累计最多20请求；顺序按plan-pages→plan-js→plan-resolve→plan-history-js→plan-announcements→plan-final。本次ledger已17，不应直接重跑全部计划触发重复或超额；评审仅离线读取证据。第二次history JS请求用于补全首次只截45条的上下文，真实重复也记入13号请求，没有隐去。源文件Ruff通过；真实HTTP和PDF内存预检为主要验证，没有用mock代替。

入口未被封禁，故当前不是external_blocked；更长期合法授权/可靠性仍UNKNOWN。不承诺接口稳定、全市场/所有拼音别名覆盖、修订完整性、年度自动认定或M1导入READY。全部业务API、公用缓存和正式下载导入仍等M0独立审查冻结。无push/merge/deploy、无付费LLM、无新agent。
