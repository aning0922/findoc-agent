# M1 独立认证 / 网关窄审

2026-11-03（Asia/Taipei）。结论：**发现两项已复现的 P0，当前 L01/L02 不应标为可写演示认证验收通过。** 可继续 L03；修复后只需定点复核，不要求生产权限平台。

## 固定审查对象与范围

- 本评审分支：`codex/showcase-m1-auth-review`，从集成 `b5768ee01e69c791c47798f5b98b1a563e1479e4` 新建；旧 H01/review 提交未重写。
- L01：`a9284b412cc62c3ef2f5ff172b462b7cacae3350`，真实读取 app/demo 的 config、store、controller、app 以及 test_demo_auth.py。
- 本轮开始时 L02 已提交，故补审固定 `5ea5abbb509771016d4c6ea215f017dce3577062` 的完整 diff、gateway.py、policy.py、controller/app 增量与 test_demo_gateway.py。未把源工作树的未提交修改作为证据。
- 合同：集成基线的 `docs/showcase/contracts/API_MINIMUM.md`、`M1_WIRE.md`；明确浏览器 `/api/demo/*`、owner 五分钟/五路由、pending claim 和全部业务代际限制。
- 当前 developer 模型标识为 `gpt-6-astra`；派工要求 high，无独立推理档位元数据。未再创建子代理或会话。
- 所有运行代码均从上述 SHA 用 `git archive` 导出到临时目录；没有改源实现或本分支业务。使用新临时 control SQLite、FakeManager/HTTPManager、虚构密码、假 HTTP 上游，无模型、真实数据库、原 PDF 或真实财务签核。

## P0-1：pending Cookie 路径使公开 /api 登录无法领取租约（OPEN）

**位置：** L01 `app/demo/app.py:103–105` 设置 `findoc_demo_pending` 为 `Path=/demo`；`:133` 删除也固定 `/demo`。L02 未改这部分。主控随后发来的同项发现与本次独立复现一致。

浏览器实际请求 `/api/demo/login`，Vite 只在转发给后端时剥去 `/api`。浏览器 Cookie 匹配仍根据公开 URL，所以不会向 `/api/demo/operations/...` 或 `/api/demo/claim` 携带 `/demo` Cookie。内部 TestClient 对 `/demo/*` 的测试无法发现这个接线问题。

**实际复现（BROWSER_FAKE）：** 固定 L01 Uvicorn 监听 127.0.0.1:14691，真实 Vite 8.2.4 监听 14692，Chromium 在 Vite 同源页面 fetch。临时 Vite 配置仅复用项目的 `/api` rewrite 规则；没有使用正式前端 UI 或实际 runtime。

```js
// 临时 vite.config.mjs 的实际 proxy 规则
proxy: {'/api': {
  target: 'http://127.0.0.1:14691',
  changeOrigin: true,
  rewrite: path => path.replace(/^\/api/, '')
}}
```

观察结果：

```text
POST /api/demo/login                 202
GET  /api/demo/operations/{login-op}  401 unauthenticated
POST /api/demo/claim                  401 attempt_cookie_required
浏览器 Cookie metadata:
  name=findoc_demo_pending, path=/demo, httpOnly=true, sameSite=Strict
```

未输出原始 Cookie 值。安全/产品判定：**FAIL**，正常公开入口无法完成 pending→claim，需阻断 M1 登录交付；这不是断言攻击者已获得未经授权的会话。

**最小修正：** pending 的 Set-Cookie 与 Delete-Cookie 使用一致的 `Path=/`，保留 HttpOnly、SameSite Strict、HTTPS Secure；或明确支持外部 prefix 的配置，但本版无需增加复杂配置。已有旧 `/demo` Cookie 可按需要同时清理，避免升级残留。

**关闭证据：** 在修复 SHA 上重跑真实 Vite + Chromium 的 `/api` 流程，要求 login 202、progress 可读且 ready、claim 200、session active，登出后 Cookie 清理且业务拒绝；只更新内部 TestClient 不能关闭。当前审查未读取或执行任何后续修复 SHA，保持 OPEN。

## P0-2：owner grant 在请求体读取期间到期，敏感写仍被转发（OPEN）

**位置：** L02 `app/demo/gateway.py:142` 在读取请求体前 `capture(..., owner=True)`；`:146` await bounded_body 后仅 `fence(token,generation)`；`:168` 调用上游。`app/demo/controller.py:200–212` 中 capture 检查 owner，但 fence 只检查会话与 generation，不检查 owner_until。

**触发：** 已合法获得 owner step-up 的会话在授权期内发起敏感请求头，延迟发送请求体，超过 300 秒但仍在 20 分钟 lease 内。body 结束后 lease/generation 检查通过，因此已过期的 owner 能力仍发起新的上游财务写。此发现针对“上游执行尚未开始而 grant 已到期”，不要求回滚授权期内已送达的合法写。

**实际复现（UNIT_FAKE / ASGI HTTP）：** 使用固定 L02 的 HTTPManager，controller clock 可控，敏感上游仅记录调用并返回假 200。请求体迭代发生时把时钟推进 301 秒：

```python
# 已通过 async_login，并 POST /demo/owner-authorize 成功。
async def slow_body():
    clock[0] += 301
    yield b'{}'

response = await client.post(
    '/financial-facts/confirmations', content=slow_body(),
    headers={**HEADERS, 'content-type': 'application/json',
             'x-operation-id': op()['operation_id']},
)
# 实际：response.status_code == 200；manager.calls 数量 == 1。
# 随后 GET /demo/session：can_review == False，lease 仍 active。
```

安全判定：**FAIL**。脚本的断言故意确认“缺陷存在”，pytest 显示 PASS 不代表授权安全通过。没有向真实 FinancialService 发确认请求，也没有写 local_operator。

**最小修正：** 在 body 完成后、ledger 命中返回/新调用预留及上游 dispatch 前，对 owner-only 规则复查同一 session 的 owner grant。可给 fence 增加 owner 参数，检查 `can_review` 并保持已捕获 generation/handle 不变；不能通过重新查询 current 把请求改投新 runtime。正常 lease 与代际复查继续保留。

**关闭证据：** 同一复现应改为 403、上游调用数 0；五条 owner-only 路由都经过该通用检查；对照有效 grant 的请求仍成功。无需扩大为任意网络组合或生产 RBAC。

## 已检查的有效边界与有限测试

| 检查 | 实际结果 / 能证明的范围 |
|---|---|
| 固定 L01 原测试 | `pytest -q tests/test_demo_auth.py`：3 PASS，0.28s；覆盖错误凭据、绝对 expiry、pending/op 不授予 token、claim 重放/丢 Cookie、重启撤销和基本 Origin/秘密不回显。 |
| 固定 L02 原测试 | 与 L01 合计 6 PASS；与 owner 复现探针同次运行共 7 PASS，0.70s。原测试覆盖双请求 takeover CAS、无 owner/未确认拒绝、五路由、未知写拒绝、固定 header、业务 operation 幂等、旧响应丢弃与旧目录隔离的假 manager 行为。 |
| owner 到期独立探针 | 复现上述 P0-2；测试程序成功确认缺陷，安全期望 FAIL。不能算 owner 有效期通过。 |
| reset 失败独立探针 | FakeManager.reset 抛 OSError 后 operation=failed、claim 503、业务 GET 401、public status=degraded；PASS。与 owner 探针两条合计 0.18s。仅证明 controller 对 manager 失败的关闭行为。 |
| Vite + Chromium /api | 复现上述 P0-1；真实浏览器/真实本地代理，假 runtime manager；公开登录主路径 FAIL。 |
| 纯静态秘密检查 | config/store/controller 代码使用密码哈希、随机 Cookie，控制表存 token hash，operation fingerprint 为带私有 key 的 HMAC；validation handler 不回显密码。没有读取真实 env/key，也没有对部署密钥做验证。 |

复现工作目录：L01 `/tmp/findoc-auth-review-Od1JWV`；L02 `/tmp/findoc-auth-review-l02-5fdRak`，仅临时 QA 资料。L02 独立探针为 `tests/test_independent.py`；使用本评审工作树 `.venv/bin/python`，从各临时快照目录运行 pytest，防止错误导入本分支代码。首次从本工作树执行临时 L01 测试曾因导入路径失败（ModuleNotFoundError），改为快照 cwd 后成功；该收集错误不算业务测试结果。

为了复跑可重新 `git archive <被审SHA> app/demo tests/test_demo_auth.py [tests/test_demo_gateway.py]` 导出，补空的 app/tests `__init__.py`，再用已安装 checks 依赖的 Python 运行。浏览器复现用虚构测试密码和隔离 control/seed 目录，Origin 为 Vite 本地同源。临时 Vite/Uvicorn 已停止；未遗留公开服务。提交只包含此文档。

## L03 后续必须验收，当前未当成 L01 缺陷

本轮最后查询 `codex/showcase-l01` 仍为 `5ea5abb`，没有可固定审查的 L03 提交。本轮不等待其长任务，也不依据其未提交代码作结论。

1. 真实子进程的 internal secret/generation/instance 校验、端口仅 loopback、浏览器不能直达或伪造内部 header；现有 HTTPManager 不能证明 child 防绕过。
2. 停止并确认旧进程组退出后才能发布新代；旧目录永不复用，旧线程/延迟请求不写新代，控制进程重启/停止超时保持关闭。
3. seed/path allowlist、symlink/hardlink 防逃逸、SQLite 一致快照、manifest/对象/索引 readiness；无真实种子或子进程证据不能宣称 reset 合格。
4. 磁盘/校验/child 启动失败，以及 pending 超时/申请消失，都按冻结状态机收口。控制层假失败测试不替代实际进程/文件故障。

本次未发现可据有限证据进一步确认的错误密码占用泄露、operation UUID 换取明文 token 或重复 claim 双 lease；这不是穷尽证明。建议先修复两条已复现 P0，再对固定修复 SHA 做定点回归，L03 来后另做一次有限复核。
