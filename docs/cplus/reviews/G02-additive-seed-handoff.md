# G02 additive seed builder — first delivery

Branch codex/cplus-additive-seed from root9f6bd3a (tracked clean). New app/cplus_seed + experiments/cplus/build_additive_seed.py only; no demo/seed/process/runtime_factory edits. CLI is offline-only and does not initialize app, auth, provider or budget. Before first build, root provides an explicit JSON list (max2) with exact fields path/sha256/source_url/security_code/exchange/report_year/official_name; no user-uploaded/private arbitrary files.

```
python -m experiments.cplus.build_additive_seed \
  /absolute/data/showcase-seed-v1 /absolute/data/showcase-cplus-seed-v2 \
  --input-manifest /absolute/root-approved-additions.json \
  --bundle /absolute/data/findoc-showcase-cplus-seed-v2.tar.gz
```

Base manifest must pin efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4. Base files must be known documents/parse-v2/finance-v2/research-memory/showcase-archive DBs, public PDF objects, Milvus files and old inventory. New output destination and bundle must never exist; symlink/active/base nesting forbidden. Inputs are plain absolute non-hardlinked files, bounded20MiB, actualSHA, static.cninfo.com.cn finalpage HTTPS URL and exact cover legal name/code/year/market. No downloading or guessed basis: new metadata basis=unknown.

Materialize exclusively into our TemporaryDirectory's new child, then explicit synchronous SourceService→DocumentProcessor fast PDF→existing offline BGE→Milvus IndexPublications, with metadata binding before processor. No fake stopped_source marker, no existing active runtime. Milvus opens after offline BGE warmup; context finally closes client even if construction/addition fails. No background workers. All writer contexts exit before sidecar/link inspection, grants rejection, vector probe (own client closes), SQLite backup/quickcheck/tables/indexes and readonly manifest. Original archive rows remain exact; original seed file+manifest SHA rechecked; original inherited operation table snapshots remain exact (no new operation rows or identity-bound research). Extra runtime files/control/keys/non-whitelisted DBs fail closed. Original approved notes/conversations/archive remain inherited; no new research or financial confirmation is created. LRU/GC not involved.

Final frozen seed gets demo-seed-v1 unchanged top-level manifest contract, preset_demo, new cplus-seed-inventory.json with actual added identities and owned closure proof, no input local paths. Base inventory retained separately. No reuse of stopped-source verifier against forged provenance. Production custom pipeline/index ports rejected; unit-only test_mode explicitly marks substitutions and complete_product_seed=false, CLI cannot enable it.

Unit tests2 passed (5 existing Swig deprecation warnings): actual SourceService/PDF parsing but fake embed/index in owned test temp; writer closes before probe, original seed unchanged, readonly seed/SQLite/tar manifest, overwrite rejection, URL/SHA/count rejection and unclosed-WAL sidecar prevents destination. CLI help and Ruff pass. This is mechanism evidence, NOT real BGE/READY new seed proof. Real root-approved Haier/Midea file paths are not yet supplied in this delivery; do not claim final seed or bundle generated. No model calls/human approvals/private config/ledger/original runtime DB read. Real-input build/inventory/bundle evidence will be a separate follow-up SHA after root supplies explicit source list.

## Real two-PDF build completed — 2026-11-03

此节替代上一轮“等待真实输入”的当前状态；保留先前机制证据。root提供`data/cplus-public-fixtures/seed-additions.json`，现在CLI同时接受原list或严格`{schema_version:'cplus-public-seed-additions-v1',files:[...]}`。真实运行新增显式参数：

```
--manual-existing-sha b17a9b9b84bca1d2a4e4a3cadc5dd5ba5c85e3f1fd2d758acd3315b5b040ecd9
```

该参数不是放宽controller：仅root明示批准的SHA可走既有企业手动上传回退，必须先在原seed registry匹配唯一code/exchange/法定name/country，再按原SourceService核对封面name/year/type。pipeline再次要求该既有主体存在，不能借manual路径创建新公司。Midea2024封面无代码，inventory明确`binding_mode=root_approved_existing_company_manual_upload_fallback,cover_code_verified=false,financial_authority=false`；code来自原registry，不声称cover-code验证或财务人审。Haier2025保持自动cover-code校验、新公司创建。两者basis均unknown。未改旧controller、自动gate或SourceService合同。

真实构建使用现有venv和离线cached BGE-M3、真实DocumentProcessor及Milvus IndexPublications，无模型provider或下载请求。所有writer实际退出后冻结，新增operation rows=0、原archive内容保持。最终另物化到全新owned temporary copy后验证5份READY的SourceService身份和vector publication current；原扫描件仍legacy failed，其OCR completed/current、68行54格、legacy_source_verified=false；5个archive条目current。新seed共6文档（5READY+1原扫描failed），包括Gree2024/2025、Midea2024/2025、Haier2025。

实际目标：`/Users/aipuli/.codex/worktrees/findoc-showcase-cplus-integration/findoc-agent/data/showcase-cplus-seed-v2`。
- manifest SHA **287d939e8d72aba2092a4fae00f10ecab0711258a86f11f453dd760febe49459**。
- bundle `data/findoc-showcase-cplus-seed-v2.tar.gz` SHA **8852d191adfe74b1f4700f499919dd3b05e0e92e840d53bc6a6eecaa015fed3b**。
- 41个manifest文件逐SHA验证，所有SQLite quick_check/表数/index通过；tar无link成员，文件集合与manifest完全一致且41个逐文件SHA匹配。
- 原v1 seed重新verify，manifest仍efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4，全部原文件SHA保持不变。没有向原seed或运行库写入。
- 结构化proof：`docs/cplus/reviews/G02-additive-seed-proof.json`。大PDF/DB/seed/bundle仍ignored且未提交。实际CLI运行日志`/tmp/findoc-cplus-additive-real-build.log`，仅本机engine进度及公开库存，不含配置/账本。

最终测试3 passed（5现有Swig warnings），包括“无封面代码默认拒绝；只有explicit SHA+唯一既有registry身份才能manual fallback”新增回归。Ruff通过。真实BGE/READY/新物化副本证据PASS；没有宣称C+ browser登录/接管/reset新seed E2E已通过，该主控验收仍独立。provider/human financial approvals均0。
