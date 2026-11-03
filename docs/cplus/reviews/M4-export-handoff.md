# M4 exports service handoff

`codex/cplus-exports`基于79456a4，保留b921ac1 partial历史；本文件当前内容取代此前仅CSV的功能状态。只改app/exports_v2、对应tests、M4-export文档。provider0/human0，无私有配置/原DB/账本访问。

Root组装：`ExportService(runtime_root, resolver=async_resolver, identity_validator=sync_check, publication_guard=guard, before_commit_sync=sync_check, authorize_read=read_permission, renderer_python=python_with_openpyxl_and_python_pptx)`，再`create_export_router(service,identity_provider)`。默认renderer_python=sys.executable；本机实际验证使用bundled Python `/Users/aipuli/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`，它有openpyxl/python-pptx，项目venv当前无openpyxl。不可假称clone已自动安装这些依赖；root应在部署运行Python安装并显式配置或注入renderer Python。用户明确授权openpyxl/python-pptx，优先于artifact-tool技能默认作者工具。

精确resolver签名：`async resolver(domain,id,revision,expected_sha,identity) -> {snapshot,selected_sources,memory_generation?,display_status}`。domain枚举`showcase_report_v2/annual_diff_v1/checkup_v1/peer_comparison_v1/research_answer_v1`；schema和ID字段逐domain严格匹配。非report不可变结果revision=1；showcase使用真实revision。expected SHA定义为**完整snapshot JSON**的UTF8、sort_keys、ensure_ascii=False、compact separators、allow_nan=False的SHA256（包含payload自身已有的payload_sha256字段，不把业务内部hash误当此export snapshot hash）。root resolver必须读服务端明确版本、校验权限及源状态；不能取latest或降级权限异常为历史正文。服务渲染前后各调用一次resolver，内容或display_status变化则UNKNOWN，不发布。

请求：POST `/cplus/exports` `{operation_id,report_ref:{domain,id,revision,payload_sha256},formats:[csv,xlsx],export_profile_version:'research-v1'}`；GET `/cplus/exports/operations/{operation_id}`；GET `/cplus/exports/{export_id}/files/{format}`。返回manifest含绑定ref、display_status、每文件SHA/size/href；不自动下载。精确同UUID/body读回旧state，冲突409；UNKNOWN不重跑resolver或renderer。

`identity_validator(identity)`与`before_commit_sync(identity)`必须同步、检查当前owner/generation/instance/expiry，False拒绝；后者位于实际SQLite COMMIT前，所有操作和工件完成写入均走此钩子。identity的model_dump或dict的hash作私有owner，因此根需提供稳定原lease标识。`publication_guard(identity,resolved)`持源/权限读取栅栏到inner export DB COMMIT；不要锁本export DB制造自锁。stale历史导出必须是resolver明确允许的展示权限：root guard对历史快照保护访问资格和固定snapshot版本，不能把“当前源已失效”悄悄升级current；权限错误必须直接拒绝。`authorize_read(identity,manifest)`每次GET工件执行，可sync/async，False/异常拒绝；不调用模型/生成文件，允许查询可信展示权限。GET不再调用resolver或渲染器，返回完全相同bytes/ETag。

工件以BLOB存放`<runtime>/exports-v2/exports.sqlite`（0600、目录0700），不暴露任意文件路径；格式文件不可UPDATE/DELETE。显式POST私有临时目录内渲染，90秒/30MB限制，完成后清理；超时/错误保留原UNKNOWN，不重放。无导出账户/财务核准能力。

CSV UTF8 BOM；XLSX三sheet：概览/财务数据/来源证据。财务行只来自已有typed Decimal字段，不从AI文本解析财务数值；所有数值原字符串作文本保留，unknown字段留空。domain/ref/status每数据行保留。用户文本前置公式字符含控制空白已转义，Excel全部数据单元格为字符串，无公式，JSON引用/期间信息保留。AI无解释则明确未生成；源stale明确历史，不升confirmed。

CSV/XLSX专项test为3 passed：真实文件保存+openpyxl重开、长Decimal、三sheet、无公式、GET/同op不重新resolve或渲染、权限撤销拒绝、错domain UNKNOWN不重放。PPTX属于下一独立commit；视觉render/完整root浏览器接线另记录后续结果，当前不冒充端到端验收。
