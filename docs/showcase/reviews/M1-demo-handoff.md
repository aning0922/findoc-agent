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
