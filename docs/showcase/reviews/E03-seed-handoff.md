# E03 preset archive / full-seed helper wire

2026-11-03；分支codex/showcase-e03从集成6bcb386建立，保留c01/f01/l01。仅新增app/showcase_seed、experiments/showcase/build_full_seed.py、对应tests、本交接；不改runtime/dashboard/Conversations/Agent/gateway。已读frozen demo-seed-v1、真实job/report/parse/memory schema及旧partial builder。

接口先冻结：

- `ShowcaseArchiveService(runtime_root: Path, *, sources, workspace_id="demo", parse_service=None)`：只读 `showcase-archive.db`，不创建live job，不读取旧lease作为当前授权；missing archive返回空列表/明确not_installed。source service必须同root。根owner装配 `create_showcase_archive_router(service)`，所有GET继续由当前demo gateway lease保护，不额外开匿名业务口。
- GET `/showcase-archive/items?kind=job|report&limit=20` → `{schema_version:"showcase-archive-list-v1",data_origin:"preset_demo",items:[summary...]}`。
- GET `/showcase-archive/jobs/{archive_id}`；GET `/showcase-archive/reports/{archive_id}/revisions/{revision}` → `showcase-archive-item-v1`。统一 `data_origin=preset_demo,historical_snapshot=true,label="预置演示案例",original_data_origin,saved_at,current_source_status:current|stale|unavailable,source_checked_at,current_sources,snapshot,provenance,capabilities`。capabilities全部false（plan/handoff/resume/regenerate）；无POST/PATCH/DELETE。
- snapshot为原已保存结果/报告，原文不重写；provenance保存original_scope_json及SHA、original_result_json及SHA、应用原result SHA、原job/report ID/时间/原模型标记；旧scope只是历史来源。当前状态单独复验固定document/company/SHA/revision/parser/period与精确引文，不修改保存时状态。缺身份/未知artifact/查证失败标unavailable，不猜current。
- `build_full_seed(source_runtime, destination, *, public_allowlist, job_ids, report_ids, conversation_ids=(), memory_ids=(), preference_keys=(), seed_version, complete_product_seed=False, index_probe=None, test_mode=False)`。CLI路径仅新脚本。默认只接受tmp下 `findoc-integrated-http-*/control/active/<gen>`，controller/runtime lock需可独占持有且child.json不存在；拒绝真实开发runtime、symlink/hardlink、覆盖目标、未允许PDF SHA与财务acceptance/receipt/factset。
- public_allowlist为以SHA256为键的dict，每项origin=`public_official|derived_public`，derived需derived_from_sha256指向允许的公开原件；可含id/url说明。单元test_mode只允许显式测试临时路径与synthetic_test，不能标完整。
- 仅复制documents/objects/Milvus、parse-v2（如有）、显式选定的示例conversation/笔记；拒绝未选私有会话/笔记，不复制原live showcase-research.db/showcase-reports.db/控制库/日志/key。选定completed job/report提取到独立archive；原scope/result SHA不变，不赋予新generation运行权限。
- manifest仍严格demo-seed-v1现有字段，不加top-level字段；`data_origin=preset_demo`，archive DB作为另一个sqlite spec，逐文件hash/表计数/index校验。`preset_task_ids=[]`不冒充live Task。默认complete_product_seed=false；仅真实完整库存条件满足且调用者显式要求时可标true，仍不等于完整reset/UI验收。

根将提供真正闭停的3官方PDF+派生OCR+真实completed job/2报告环境。目前先做UNIT_FAKE/合成source与archive机制，不借真实provider、不伪造完整seed成功。实际SHA/checks/限制后续追加。


实现及验证（2026-11-03）：

- 新namespace仅 `app/showcase_seed/{archive,api,build}.py`，CLI `python -m experiments.showcase.build_full_seed --help`；DTO只包含历史快照和来源复验，不接入旧scope授权。root接线时使用 `from app.showcase_seed.archive import ShowcaseArchiveService` 与 `from app.showcase_seed.api import create_showcase_archive_router`。新generation必须由既有gateway保护这些GET，不能注册到匿名例外。
- helper要求显式偏好keys/对话ID/笔记ID覆盖curated source现存内容；未选、撤销、未知PDF均拒绝。复制后重置documents内分页cursor签名随机材料，原source不改；不复制control identity/gateway key。source financial acceptance/receipt/factset即使模拟也拒绝。
- 报告findings使用既有report adapter的确定性映射比较（job finding origin→job execution origin；current_valid→current），不重写原job或原report。两套原始JSON及其SHA都保留；review axes不得升级，精确引文不得改写。
- UNIT_FAKE：`pytest tests/test_showcase_seed.py tests/test_showcase_reports.py tests/test_showcase_research.py -q` → **9 passed / 5 existing Swig deprecation warnings**。含readonly seed→新root、原lease已过期仍可读历史、GET-only/POST405、源修改stale/丢失unavailable、原snapshot/SHA不变、禁止覆盖/owned source/未允许PDF/未选conversation/模拟receipt、fake/custom probe不能标完整。Ruff check通过，CLI help通过。未调用provider。
- 真实read-only样本由root明确提供：`/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-integrated-http-5zk9mqeo/control/active/1`。Gree2025 SHA `7cc972f2d199e2ec3797cc5da479e8268afa59b77875770de3bcd3648242fb8c`；selected jobs `0c3056bb-f8c2-4d2c-91ea-26534a0b0bd4` / `64a7071f-3fb4-49e5-b126-130ccc143672`；report `57fd3e3a-a83d-401f-ad3a-51f451fd9bc9` revisions1/2；conversation `148a582d-9e5d-402c-82db-05b34d92819c`。无笔记、无财务授权。只读真实Milvus副本probe；**新模型调用0**。
- 当前代码生成partial seed：`/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-e03-real-history-dtafysfj/seed`；manifest SHA `1dc263ad8fc2360eb3d38f0eec35e4b81b6ae2ccb3221cdfe792a546b1aaf4e0`，`complete_product_seed=false`；验证详情在同级 `verification.json`。materialize后2job+2report revision均current；没有live showcase-research.db；原scope/result/report payload保留。构建前后源21个文件SHA相等。
- **完整3官方PDF+派生OCR+至少2份独立报告库存：SKIP / root尚未交付关闭源。** 当前真实样本只有1PDF/1报告2revision，不作为完整seed成功；新root reset/browser/UI/live-authority拒绝回归由root集成验收。本commit没有改runtime_factory/dashboard/Conversations/Agent/gateway，未push/merge/deploy。

## Full seed实际构建（后续库存验证，2026-11-03）

本节替代上一轮“完整库存SKIP”的当前库存结论，保留该历史记录。源由root明确授权，整个源只读，未重新生成模型/embedding/OCR，未改immutable记录。

- 源：`/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-integrated-http-ybr4pane/control/active/1`。显式job/conversation从祖目录`research-progress.json`读取，显式report/memory从`completed-seed-material.json`读取；不是扫描所有记录后自动授权。
- 目标（位于root集成工作树，已生成且只读、受data/*忽略）：`/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-seed-v1`。manifest SHA **`efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4`**，`demo-seed-v1`原有top字段，`data_origin=preset_demo`，**`complete_product_seed=true`仅表示静态完整库存满足**。
- 库存：3官方READY PDF（Gree2025/Gree2024/Midea2025）+Midea2025物理第9页派生scan；2公司；2真实completed job；2独立报告、共3revision；1示例conversation；2显式演示note（向量已存在）；1 completed v2 OCR artifact（68行/54格，output SHA见JSON）。派生scan仍legacy failed / `legacy_source_verified=false`，未升为READY或financial authority。
- seed有28个manifest文件，约65.7MB；3个非空Milvus collection分别1122/1300/1003 rows，加1个原有空collection；5个SQLite spec均quick_check/表计数/index验证通过，archive_items=5。receipt/acceptance/factset为0；新模型调用0、真人financial approval0。
- 构建前后**源34个文件SHA全部相等**；已记录聚合source_tree SHA。实际materialize副本的3官方source均可读，derived对象SHA保持；OCR quality completed/current且legacy_source_verified=false；5个archive item均来源current，原scope/result/report payload逐字比对源数据库一致，capabilities全部false；未复制live showcase job/report DB。只进行了本地副本service读取，**不等于browser/reset/full runner验收**。
- 原runner证据仍为 `REAL_CHROMIUM_HTTP_REAL_PDF_BGE_LLM`、`completed=false`、`failure="Error: derived scan binding only"`（root已说明该seed helper失败与missing Origin有关）。之后补材料属于`REAL_LOCAL_VISION_BGE_IN_PROCESS_ASGI`，不能改写为原runner整体PASS。
- 完整结构化证据：`docs/showcase/evidence/E03-full-seed-verification.json`（仅库存/IDs/hash/状态，无PDF/DB/key或模型原文）。`docs/showcase/PUBLIC_SEED_ALLOWLIST.json`由集成D01预检的SHA/URL建立，仅含本次4个公开对象；派生SHA `175235d1122aec489a6c943ec8c1f8f9fcb5ffdd0e75f938f5ce6080c8ed163a`明确指向Midea2025 `c413ed1b993290ec98b254af4bf6ad69edb5a2230bbaec1b15702119b24d4f5c`。
- 所有构建/核验由新`experiments/showcase/build_curated_seed.py`复现；Ruff通过，实际构建+manifest+两次物化服务读取成功。既有helper无schema修补。archive print endpoint、root接线、reset/UI/live-authority回归仍由root验收。没有修改root热点，没有push/merge/deploy。

可复跑命令（从集成repo执行，先集成本commit；`NEW_DEST`必须从未存在，不能覆盖已生成正式seed）：

```sh
python -m experiments.showcase.build_curated_seed \
  /private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-integrated-http-ybr4pane/control/active/1 \
  NEW_DEST \
  --allowlist docs/showcase/PUBLIC_SEED_ALLOWLIST.json \
  --verification-output NEW_VERIFICATION_JSON
```

本次实际destination为上述集成`data/showcase-seed-v1`；分页cursor签名材料每次在目标副本重新生成，因此重建manifest SHA可不同，以对应生成证据为准。PDF/DB/密钥不会提交。本次授权写入集成工作树的allowlist为同内容新文件；root cherry-pick若提示未跟踪文件阻挡，可确认与本commit内容相同后先处理该未跟踪allowlist。
