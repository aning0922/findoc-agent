# M1 Demo backend handoff

2026-11-03，隔离工作树 `/Users/aipuli/.codex/worktrees/4eab/findoc-agent`，基线 `d6ccca07d46f5625bae8176166dc8b9f6e3b434a`，分支 `codex/showcase-l01`。范围仅 app/demo、test_demo、showcase_demo 脚本与本文件。未读写现有 data/PDF/密钥，未改旧 runtime/迁移/DocumentService/前端。

遵循 API_MINIMUM v1.0，以及主控集成树 `docs/showcase/contracts/M1_WIRE.md`（本树冻结基线尚不含该新增文件，已实际读取）。claim 请求为 `{operation_id:新UUID,attempt_operation_id:原login/takeover UUID}`。

## L01 — Cookie / credential / absolute lease

- 服务端 PBKDF2-SHA256 hash env、常数时间密码/用户名比较；20/30min 绝对 TTL；HttpOnly/SameSite=Strict/Secure 默认开启；当前 Cookie 登录不续期。
- 独立 `demo_control.db` 单 slot + 短 SQLite IMMEDIATE 事务；同控制目录单 controller 文件锁。operations 仅存 HMAC 请求摘要、token hash，不存明文密码/token。
- 202 pending Cookie → 受保护 operations/reset → claim 单次签票。UUID 不授予权限；丢失 active Cookie 不重复发票；原占用待到期/owner 接管。
- status 不泄露占用；Origin 精确 allowlist、JSON/content-type、基本凭据限频；422 不回显密码。重启撤销旧租约并先恢复/清理，不信任旧票。
- L01 暂以注入 manager 测试，所有业务默认关闭；真实 child/reset/gateway 属于 L02/L03，不能单独把 L01 用作完整 Demo。

Checks（UNIT_FAKE，真实 FastAPI TestClient + 临时 SQLite，fake manager，LLM=0、真实 PDF=0）：

- PASS: `python -m pytest tests/test_demo_auth.py -q`，3 passed。
- PASS: `python -m ruff check app/demo tests/test_demo_auth.py`。
- SKIP: 真实 child/BGE/Milvus、HTTP 双浏览器（后续 L03/L04）。

配置字段/未来入口：`DEMO_CONTROL_ROOT`、`DEMO_SEED_ROOT`、`DEMO_USERNAME`、`DEMO_PASSWORD_HASH`、`DEMO_ALLOWED_ORIGINS`、可选 `DEMO_OWNER_PASSWORD_HASH`、`DEMO_TTL_MINUTES`、`DEMO_CONFLICT_POLICY`、`DEMO_COOKIE_SECURE`。密码由部署者离线生成 hash；不在文档提供有效凭据。L03 将提供可运行入口与合成 seed 构建脚本。

回退：每任务独立提交，可 revert；控制目录和每代目录保留，不覆盖原 runtime；不自动合并 main/部署。

## L02 — exclusive slot / owner takeover / gateway

L01 commit: `a9284b4`。L02 在同一隔离分支接力，无主控热点文件变更。

- `takeover_enabled` + 独立 owner hash + `confirm:true` + `expected_generation` 在同一 IMMEDIATE 事务中 CAS；并发仅一个胜者，撤销在 reset 前完成；默认 wait_only 拒绝。
- owner-authorize 当前 lease + Origin + 明确确认，grant 到期为 min(lease, now+300s)，重复 operation 不续期；五条现存正式财务/RESUME 写均需 step-up。没有创建/伪造真人财务回执。
- `policy.py` 显式列出实际 V1.2 mutation 路由；未知 mutation（含评测/恢复、新 v2）默认拒绝，后续主控审查登记。全部业务 GET/HEAD/POST/PDF/SSE 经同一 lease 网关。内部路由不透传。
- 每请求捕获固定 handle/client/root；仅向固定 loopback 上游注入服务器 secret/generation/instance；剥离浏览器内部 header、Cookie、Authorization/Host，拒绝上游重定向。JSON/PDF 全体接收后和 ASGI 发送前复核；SSE 每事件与无数据等待期间复核，撤销断开不发送旧事件。
- 所有 gateway mutation 要 UUID。已有 operation_id 的新接口保持原 body；旧严格 DTO 由网关消费外层 operation_id（也支持 `X-Operation-ID`，multipart 必须此 header），不擅自改旧业务 schema。缺失返回422；**主控接旧 UI 客户端时需补此字段/header**。临时代际 `.demo-gateway.db` 先预留 UNKNOWN，再调用；同ID同请求复读缓存，冲突409，UNKNOWN禁止重放，GET `/demo/operations/{id}` 可查。缓存只留当前/历史隔离代际目录，不放控制库。

Checks（UNIT_FAKE，HTTPX MockTransport/fake manager，真实 lease SQLite 和 FastAPI ASGI，LLM=0）：

- PASS: `python -m pytest tests/test_demo_auth.py tests/test_demo_gateway.py -q`，6 passed。
- PASS: `python -m ruff check app/demo tests/test_demo_*.py`。
- 额外竞态覆盖：两个接管请求一个202一个409；旧token读写失败；故意允许旧 fake handler 在新lease激活后晚到写入，只落旧root，旧PDF响应不发浏览器；旧SSE事件丢弃。
- SKIP: 真实 OS child停止/完整seed恢复与真实HTTP SSE/PDF（L03）；真实双浏览器UI（L04）。这一级别不代表真实BGE/Milvus、LLM、PDF或真人签核。

L02已知限制：网关是受控同源 API，不提供公开静态预览；Vite `/api` 去前缀由主控接线。允许写清单需随新增模块登记；业务幂等UNKNOWN表示可能已执行，不能自动换UUID重试。L03前没有可部署的进程/seed manager。

## L03 — immutable seed / OS child / readiness / recovery

L02 commit: `5ea5abb`。L03 的完整 SHA 由最终交割回复给出；本提交连同前两项形成线性可 cherry-pick 序列，仍不合主分支。

实现与接线：

- `entrypoint.create_app` 是唯一公开控制器；`child.create_child_app` 包装真实 `create_runtime_app(root)`，默认 `DEMO_CHILD_MODE=real`，不改旧入口。每代子进程继承父进程预绑定 loopback socket，避免空闲端口竞态；每次请求都核验 secret/generation/instance，不公开内网 readiness。
- child 向支持的 factory 关键字传 `showcase_generation`、`showcase_seed_version`、`showcase_preset_task_ids=frozenset(manifest["preset_task_ids"])`。本树冻结 factory 没有这些参数，按真实签名兼容旧调用；主控注册后的 factory 自动接到固定 metadata。未 cherry-pick/修改主控 runtime_factory 或 Dashboard 文件。
- 控制库、密钥、进程注册在 `DEMO_CONTROL_ROOT/`，业务只在 `DEMO_CONTROL_ROOT/active/<generation>/`。每次 fresh mkdir，拒绝已存在代际目录，不覆盖或删除历史 SQLite/Milvus/PDF/对象。每个 child 的环境固定到该 root；旧请求不可能重新查全局 root。
- seed manifest pin SHA256；源种子必须只读、无 symlink/hardlink/未登记文件/WAL侧文件；复制后逐文件比对。SQLite 用只读连接验证完整性、指定表计数和必要索引；对象 SHA 再验。真实 child 另验证实际 Milvus collection 存在及 row_count。启动/预热不持控制事务。
- readiness 回报 instance/generation/manifest SHA/seed version、SQLite counts、object hashes、vector checks；父进程再次核对，不只信 `/health`。服务可在坏 seed 情况下返回 `degraded`，拒绝签 lease。新增服务可在代际内初始化自己的独立库；readiness 不把 runtime 限死为原 seed 文件列表。完整 E03 向量 seed 仍需提供其 collection/rows 清单并实测，不用本次空文档索引结果替代。
- 旧进程组 SIGTERM 后有界等待，必要时 SIGKILL，再确认整组退出；注册 PID + OS birth + PGID，重启不靠 PID 单独认领，不确认的 PID/孤儿组会 DEGRADED。进程 registry 不含可复用内部 secret。controller 重启先撤销旧票，再清理或关闭访问。
- runtime 连接失败使相同代际 degraded；旧 N 的迟到失败不能降级 N+1。UNKNOWN mutation 不自动重发。操作 ID 在控制/业务网关之间共用 namespace，不能同 UUID 跨动作静默复用。
- 主控后续授权的 `POST /disclosures/import` 已登记为普通 lease、native operation；财务 step-up 五路由不变，其他尚未注册的 v2 写仍默认拒绝。

审查修复：

1. **pending Cookie Path P0**：原 L01/L02 使用 `/demo` 无法匹配浏览器 `/api/demo`。本次设置与删除都改为 `/`，仍 HttpOnly / SameSite=Strict / Secure(默认)。已由真实 Chromium 经实际 Vite `/api` 代理验证 pending→operations→claim，不用内部 TestClient 结果替代。
2. **owner grant 读取 body 到期 P0**：body 读取完成后与实际转发前重新检查 owner grant + active lease/generation。`test_owner_grant_expiring_during_body_read_never_dispatches` 令时钟在流式 body 读取中前进 301 秒，断言403且上游调用0。重复授权 operation 也不会续期。
3. owner 口令若能用共享 password hash 验证，不允许作为独立 owner 口令；demo JSON body 有16KiB边界，validation 错误不回显密码；业务有24MiB边界。实际部署 Origin 必须包含浏览器同源 URL。

### 可运行命令 / env（仅变量名，不含部署秘密）

在仓库根目录，用项目 Python 或获准复用的 `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python`：

```sh
python -m scripts.showcase_demo_seed /absolute/new/synthetic-seed
python -m scripts.showcase_demo_password
python -m uvicorn app.demo.entrypoint:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

必需：`DEMO_CONTROL_ROOT`、`DEMO_SEED_ROOT`（彼此分离的绝对路径）、`DEMO_USERNAME`、`DEMO_PASSWORD_HASH`（PBKDF2 SHA256 versioned hash，helper 默认600000轮）、`DEMO_ALLOWED_ORIGINS`（逗号分隔的精确 Origin，无末尾斜线）。

可选：`DEMO_OWNER_PASSWORD_HASH`、`DEMO_TTL_MINUTES`（20默认或30）、`DEMO_CONFLICT_POLICY`（wait_only默认 / takeover_enabled需owner hash）、`DEMO_COOKIE_SECURE`（true默认；本机HTTP显式false）、`DEMO_CHILD_MODE`（real默认 / fake为明确机制测试）、`DEMO_CHILD_PYTHON`、`DEMO_CHILD_STARTUP_TIMEOUT`（90秒默认）。单 controller / 单 Uvicorn worker，不使用 reload 同时持有控制目录。

真实 child 继续使用现有 runtime 的 `LLM_API_KEY`、`LLM_MODEL`、`LLM_BASE_URL`、`LLM_TIMEOUT_SECONDS` 等配置，但 readiness 不生成 LLM。内部 `FINDOC_RUNTIME_ROOT`、`DEMO_INTERNAL_GENERATION/INSTANCE/SECRET/MANIFEST_SHA` 由 manager 每代产生，不从浏览器接收，不应由前端设置。

前端联调可运行 `DEMO_CHILD_MODE=fake`，须标 FAKE / synthetic mechanism；它提供企业读写、运输测试 PDF 字节和 SSE fixture，不声称真实财报/LLM/导出能力。Vite 使用原有 `FINDOC_API_ORIGIN` 指向公开控制器，保持 `/api` rewrite；不要指向 child。

### 响应示例（UUID/日期为说明占位，不是票据）

```json
{"schema_version":"demo-attempt-v1","operation_id":"<login UUID>","state":"pending","reset_id":"<reset UUID>","claimable":false}
```

以上为 POST login/takeover 202，附 pending HttpOnly Cookie；GET operations 同绑定返回 ready/claimable=true 后：

```json
{"operation_id":"<new claim UUID>","attempt_operation_id":"<login UUID>"}
```

POST claim 200（active Cookie 只签发一次；丢票返回 lease_cookie_lost，UUID不换票）：

```json
{"schema_version":"demo-session-v1","state":"active","expires_at":"2026-11-03T05:20:00+00:00","server_now":"2026-11-03T05:00:00+00:00","remaining_seconds":1200,"lease_generation":1,"seed_version":"synthetic-mechanism-v1","can_review":false,"owner_elevated_until":null}
```

正确凭据的其他浏览器 login 423：

```json
{"detail":{"code":"occupied","message":"occupied","remaining_seconds":1190,"expires_at":"2026-11-03T05:20:00+00:00","takeover_available":true,"lease_generation":1}}
```

无权或过期例：`401 {"detail":{"code":"taken_over","message":"taken over"}}`、`403 {"detail":{"code":"owner_authorization_required","message":"owner authorization required"}}`。`GET /demo/status` 只有schema_version/service_state/ttl_minutes/conflict_policy。不得从示例推定当前部署启用了接管。

### 实际 checks 与证据边界

2026-11-03 在本隔离树执行；所有 provider LLM 调用0，原真实数据/PDF/密钥读写0。

| 检查 | 结果 / 证据 |
|---|---|
| Auth / CAS / owner / fixed handle / late write / seed / process tests | PASS：`python -m pytest tests/test_demo_auth.py tests/test_demo_gateway.py tests/test_demo_reset.py -q`，10 passed；UNIT_FAKE + 真实临时 SQLite + OS fake-engine child。|
| 静态检查 | PASS：`python -m ruff check app/demo scripts/showcase_demo_*.py tests/test_demo_*.py`；`node --check scripts/showcase_demo_browser.mjs`。|
| Chromium两个context，真实Vite `/api`，公开controller，真实OS fake child | PASS：pending Cookie path=/、HttpOnly/SameSite、claim、错误凭据、占用、同Cookie不续期、幂等、owner门、owner接管、旧PDF响应丢弃、SSE无晚到事件、seed企业计数恢复、logout清Cookie、再登录新代。脚本 `python -m scripts.showcase_demo_http_check --frontend-root /path/to/frontend-with-installed-deps`。级别 BROWSER_FAKE，只验证协议，不代替L04页面点击/三宽截图。|
| 真实HTTP controller SIGKILL/替代进程恢复 | PASS：`python -m scripts.showcase_demo_http_check --engine fake --restart-check`；旧child按birth/PGID核验退出，旧Cookie401，清理后新lease+seed计数1。证据 `/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-showcase-demo-check-l2_03m6x/result.json`。|
| 真实缓存BGE/Milvus + 合成非空企业seed | PASS：`python -m scripts.showcase_demo_http_check --engine real`；pending→readiness→claim→companies200，约8.645s，generation1，companies1。LLM固定禁用loopback endpoint，0调用；HF/Transformers离线缓存。证据 `/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-showcase-demo-check-eluwqz29/result.json`。只证明此配置启动与探针，不是完整PDF/向量seed耗时。|
| 完整E03 seed / 真实PDF/OCR/LLM / 真人财务签核 | SKIP：不在本任务伪造，仍由对应owner/真人提供。|
| L04实际页面交互/响应式截图 | SKIP：本次只真实浏览器协议，UI验收由L04联调。|

历史失败保留：首轮真实进程测试8PASS/2FAIL（claim轮询过早，并观察到提前清理时的退出竞态）；增加真实等待、回收与PGID复核后10PASS。首轮实际env浏览器检查暴露 fake env 同一key重复删除导致reset_failed，修为安全pop并复跑PASS；初次脚本在macOS `/var` alias路径校验失败，修正只检查seed边界内symlink、使用canonical临时根路径。曾错误把 `.mjs` 交给 Python Ruff glob，工具报语法错误，改为 `*_*.py` 并由Node单独检查；不是JS运行通过的替代。失败日志保留在对应临时检查目录，没有以旧/空runtime证据冒充本实现通过。

### 已知限制 / 回退

- synthetic seed明确 `complete_product_seed=false`：1家合成企业，documents/reports/真实财务事实/PDF/真实历史研究均0，只有机制对象文本；不能称完整最终seed。E03需真实来源/合法资料、必要索引、历史/真人状态和完整reset验证。
- 本树真实factory尚无Dashboard showcase关键字，child兼容旧签名；主控集成后的factory必须再验证metadata贯穿。新增v2 mutation在policy显式登记后才开放；本次只加主控授权的disclosures/import。
- Cookie丢失不凭UUID补发active票，原lease保持占用到绝对到期或owner接管；未claim申请5min失效，reset完成后回AVAILABLE。没有自动公开排队/公开接管/复杂管理员控制台。
- 老DTO由gateway消费operation_id或X-Operation-ID；multipart使用X-Operation-ID并以实际编码body比对，重建不同multipart边界会409，不能假称重放成功。主控旧前端客户端仍需补operation字段/header。
- 已发响应头之后撤销可能表现为连接终止/空尾，而非改写已发送HTTP状态；保证不发送后续旧数据，前端需以session轮询/401清理可编辑态。慢重置显示pending，不保证秒级恢复。
- 24MiB网关传输边界、5min pending/step-up、单进程控制器为当前求职Demo范围。历史代际目录故意保留，无自动删除策略。
- 回退用独立commit的revert；停控制器/确认child退出，修复或替换只读seed后重启，使用持久control库的新generation。不要删除控制库使generation归零、不要覆盖活库、不要复用旧PID或把旧目录映射为新代。无部署、push、main合并或外部费用。

最终浏览器回归证据（包含两个P0修复与最终控制/网关代码）：`/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-showcase-demo-check-s6dnk8uc/result.json`，四组PASS，FAKE引擎；并非L04 UI视觉验收。

真实BGE/Milvus启动警告保留：child.log包含 XLMRobertaTokenizerFast 性能提示，以及退出时 `resource_tracker` 报告1个 leaked semaphore 待清理的 UserWarning；未屏蔽，未将此条标为已修复。该次启动/claim/企业读取PASS，进程管理走有界停止/整组核验，警告不能用于推断完整seed恢复已通过。日志位于上述 `eluwqz29/control/active/1/child.log`。
