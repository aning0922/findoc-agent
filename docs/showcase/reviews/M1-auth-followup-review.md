# M1 L01–L03 修复候选独立复核

2026-11-03（Asia/Taipei）。**结论：旧报告的两项已复现 P0 在固定候选 7f6f268 上可关闭；本轮合成 seed / FAKE engine 范围内的代际进程、接管、退出、到期和故障关闭检查通过，未发现新的已复现阻断。** 此结论支持主控继续集成；不等于真实产品种子、真实财务、真实模型或完整 L04 UI 验收通过。

## 固定对象与工作边界

- 被审 SHA：`7f6f268241e8c72fad0dfb13cb25d2231cd9cade`，包含 a9284b4、5ea5abb 的后续修复与 L03。主控随后明确确认此 SHA 为最终候选。
- review 分支 `codex/showcase-l03-review` 从集成 `4bf1befc562a7020ff91d00964733933b10e6d67` 建立，未重写 D02/H01/旧评审分支；本次只提交此文档。
- 等待期间仅查询源分支 log/status，未将未提交 WIP 当候选。候选出现后以 `git archive 7f6f268 app ...` 导出到 `/tmp/findoc-l03-fixed-QFBobI`；运行时 cwd、app、测试、child 代码均来自该固定快照，不是继续变化的 worker 工作树。
- 真实阅读 process.py、seed.py、child.py、tests/test_demo_reset.py、实际 HTTP/Chromium 脚本，以及 app/config/controller/gateway/policy 的提交增量。沿用冻结 API_MINIMUM/M1_WIRE 和原 M1-auth-review 的两个具体问题。
- 模型记录：developer 当前标识 gpt-6-astra；派工 high，未取得额外推理档位运行元数据。未创建子代理/会话。
- 全部使用新临时 control 库与合成 seed。FAKE engine 中无真实 provider、原 PDF 或财务接受；真实 OS 子进程与本地 HTTP 是实际运行。未改业务热点或 worker 文件。

## 两项 P0 的关闭证据

| 原问题 | 修复位置（7f6f268） | 独立实际复跑 | 判定 |
|---|---|---|---|
| pending Cookie Path=/demo 不匹配 /api | `app/demo/app.py:121–123` 设 Path=/；logout 删除同 Path=/ | 真实 Chromium 两个独立 context，经真实 Vite `/api` rewrite 到 controller 和真实 OS child：login 202，operation 200/ready，claim 200，session active；脚本直接检查 Cookie.path=/、HttpOnly、SameSite Strict；登出后两种 Cookie 均清除，旧业务请求401。 | CLOSED，仅此候选及已测路径。 |
| 慢 body 越过 owner 300秒期限仍转发 | `app/demo/gateway.py:148–150,172–174` 在读完 body 与上游发送前复查 owner；保持先前捕获的 handle | 复用旧独立复现：授权后，request body iterator 把受控时钟推进301秒；结果 **403，upstream calls=0，can_review=false**。原旧候选结果为200/upstream1，此次已翻转为安全期望。 | CLOSED。 |

第二项验证是 UNIT_FAKE/ASGI HTTP，用假上游计数，未真实执行财务确认。新增 capture 返回值没有替换原 handle；generation fence 继续检查原请求所属代际，因此复查 owner 不引入重新路由到新代。

## L03 实际证据与结果

### 已提交测试与独立探针

在固定快照 cwd 用本评审已有 checks Python 执行：

```sh
/Users/aipuli/.codex/worktrees/ce18/findoc-agent/.venv/bin/python -m pytest -q -s \
  tests/test_demo_auth.py tests/test_demo_gateway.py tests/test_demo_reset.py \
  tests/test_independent.py
```

结果 **12 PASS / 2.21s**。前三文件来自候选，最后文件为上轮独立两条探针（owner断言改为403/upstream0，以及 reset 失败关闭）。不能把这12条全称为真实进程测试；其中 reset 文件实际启动 OS children，其余多数为控制 SQLite/ASGI/假上游。

覆盖：wrong password 无占用信息、pending/claim 丢票不换发原 token、同 operation/CAS、五路由 owner gate、旧响应丢弃、internal secret/generation/instance 防绕行、真实旧 PGID 退出、新目录独立、seed 文件只读与复制非 hardlink、manifest checksum/路径校验、错误 PID birth 不误杀、损坏 seed 后 DEGRADED/不签新 lease。

### 真实 Vite / Chromium / 双会话 / OS child

执行候选脚本：

```sh
PYTHONPATH=. /Users/aipuli/.codex/worktrees/ce18/findoc-agent/.venv/bin/python \
  scripts/showcase_demo_http_check.py --engine fake \
  --frontend-root /tmp/findoc-l03-fixed-QFBobI/frontend
```

临时 frontend 只有同源空页面、与产品一致的 `/api` proxy rewrite，使用现有 Vite/Playwright 依赖；未把协议检查描述为产品页面 UI 验收。结果 **BROWSER_FAKE PASS**：

- 两个独立浏览器 context：A 获 lease，B 错密码401且无占用信息，正确密码423；A 刷新不延长 expires_at。
- A 实际通过 gateway 在 generation SQLite 新增合成企业，数量1→2；同 operation重放仍2；未 step-up 的正式财务写403。
- A 开始延迟 PDF 和慢 SSE 后，B owner 接管；新 generation 数量恢复1；A PDF迟到响应不含旧PDF内容，SSE没有 late事件，A旧GET401。
- B logout 清两种 Cookie，旧业务401；恢复后下一 lease generation递增、企业数仍1。
- 脚本最后重新校验 seed manifest/SHA，通过。

证据目录：`/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-showcase-demo-check-tt4ju7fv/result.json`。这是本复核实际执行产生的独立结果，未借用主控或 worker 的既有运行结果。

### 真实 HTTP 到期 / 进程退出 / 原 seed 不变

独立临时测试 `tests/test_independent_http_expiry.py`（固定快照目录）使用真实监听 localhost 的 Uvicorn、两个真实 HTTP client、ProcessRuntimeManager fake child。仅 controller 的服务器时钟受控，未等待真实20分钟；没有向公开 API 增加调时入口。

实际结果 **1 PASS / 1.66s**：A lease中把合成企业数改为2；服务器时钟推进1201秒后 A session401、A旧POST401；旧 PGID 消失；B取得新 lease后企业数1；old_root仍保留且与新root不同；manifest每个 seed 文件 SHA 前后一致；新代文件 nlink=1；关闭后 manager.handle=None。stdout：

```text
REAL_HTTP_EXPIRY_PASS old_pgid_gone=True old_write=401 new_companies=1 seed_sha_unchanged=True
```

### 控制器真实 SIGKILL / 重启恢复

执行 `scripts/showcase_demo_http_check.py --engine fake --restart-check`，结果 **HTTP_FAKE PASS**。先实际启动controller+child并获取lease，再只SIGKILL controller留下独立child；新controller验证身份并终止旧进程组，旧cookie401，cleanup后可取得更高generation的新lease，企业数恢复1。证据目录：`/private/var/folders/hs/czlwyhb553l9_ghpn6byp6v00000gn/T/findoc-showcase-demo-check-s72_dv6c/result.json`。

脚本与独立HTTP测试均在 finally 关闭服务，manager检查退出；没有遗留用于本复核的监听进程。临时数据仅用于 QA，无原开发库拷贝、无原 PDF 读取。

## 有限源码判断与未验证范围

- `process.py` 在新代复制前先停止旧manager，核对PID birth/PGID，再有界TERM/KILL并确认group退出；新代使用新目录与继承的loopback socket。child环境去掉DEMO配置，内部secret不在命令行；fake模式不调用provider。`child.py` 在所有HTTP路由前检查loopback+secret+generation+instance。
- `seed.py` 对manifest路径、readonly、SHA、链接、SQLite quick_check/表计数/索引检查，materialize不覆盖既有目录且逐文件复制校验。此次证明合成seed保持不变；没有把任意外部真实DB放入测试。
- readiness不只检查health，还匹配实例/代际/manifest/seed和表/对象；代码有real模式向量检查，但本轮**未执行真实BGE/Milvus readiness**，也未执行真实模型。
- 合成 manifest 明确 `complete_product_seed=false`，只有机制测试企业/对象，无真实年报、已核准事实、产品报告和完整索引；完整产品seed恢复与成本仍需单独验收。
- 未强制制造磁盘写满/OS拒绝SIGKILL/任意崩溃时点；已测损坏seed与恢复错误，其他故障的分支主要来自静态阅读，不能写全部故障通过。
- 本轮没有新增 FAIL 或 SKIP；先等待最终提交再执行，所有正式证据都绑定7f6f268。原报告对旧SHA的两个FAIL保留历史，仅新候选的对应两项关闭。主控对最终集成SHA与真实产品UI的验收仍独立进行；本报告不自动授权部署/main合并。
