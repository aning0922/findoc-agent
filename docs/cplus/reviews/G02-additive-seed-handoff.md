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
