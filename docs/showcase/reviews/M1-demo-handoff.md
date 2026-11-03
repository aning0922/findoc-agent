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
