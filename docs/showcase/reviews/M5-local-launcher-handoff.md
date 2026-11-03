# M5 本地交付入口

新增 `scripts/run_showcase_local.py`。基于实际 DemoConfig、ProcessRuntimeManager、provider_budget 和 integrated_http_check 的参数；不改runtime/README。默认 loopback Vite `http://127.0.0.1:14530`，gateway空闲端口，real main而非showcase静态预览；真实child在登录恢复时由已有控制器创建，使用本机缓存BGE与offline环境，不自动安装依赖。首页示意功能flag开启，数据与水印语义沿用现有UI。

在root集成工作树运行（使用已安装依赖的Python）：

```sh
.venv/bin/python scripts/run_showcase_local.py --help
.venv/bin/python scripts/run_showcase_local.py --init-config
.venv/bin/python scripts/run_showcase_local.py --check
.venv/bin/python scripts/run_showcase_local.py
```

init只创建 `data/showcase-local.env`（必须git check-ignore成功），600、O_EXCL/O_NOFOLLOW，固定本地用户名+两个独立随机密码；本人在本地查看该文件，CLI不打印密码，不覆盖已有文件。路径及祖先拒绝symlink。配置只用于后端慢hash，不进入前端环境。若init与check同时给出，仅执行init，随后单独check。

默认模型关闭；root若明确提供真实模型配置，可附 `--llm-config /本集成树/.env`。该文件必须600、Git忽略、非symlink且非hardlink。只读取LLM_API_KEY/LLM_MODEL/LLM_BASE_URL/LLM_TIMEOUT_SECONDS，dotenv interpolate=False，不展开变量、不执行shell。只支持HTTPS api.deepseek.com（无query/credentials、根或/v1路径）+deepseek-flash。现存 `data/showcase-cost-control/provider-budget.db` 必须有5元cap；入口不删除/重建/重置额度，使用原BudgetedSDKClient保护，预算耗尽失败。模型配置不可附在CLI参数或写到前端。

默认seed `data/showcase-seed-v1` 必须通过完整verify_seed；缺失/可写/校验不符就失败，不切回开发者DB。control默认且basename必须 `showcase-local-controller-v1`，位于本checkout data下，需与seed和budget路径分离。可选 `--seed`、`--control`、`--port`、`--gateway-port`、`--python`、`--node`。默认wait_only，只有 `--owner-takeover` 显式启用已有“共享密码+独立owner密码”接管；不是公开访客任意接管。

前端子进程只允许基础OS环境和明确Vite/proxy flags，禁止继承任意LLM/DEMO/password/provider变量并关闭envDir。网关和Vite日志放600的control/launcher.log，控制台仅输出无secret摘要。端口占用失败不杀进程；同control launcher.lock防双启动；Ctrl+C/TERM按逆序终止本次Popen自建进程组并等待，gateway正常lifespan负责独立child退出。若需要强杀gateway，子代可能需已有registry恢复机制处理；本脚本不扫描或杀未知进程。loopback限制是本地使用，不构成生产部署或RBAC验收。

证据：`--help`通过；`pytest -q tests/test_showcase_local_launcher.py` 4 passed：临时Git忽略配置权限/拒绝覆盖和symlink、dotenv及前端环境隔离、占用端口、临时合成seed --check。Ruff通过。本worker未读取真实.env、未init真实配置、未启动真实预览或付费请求。正式本地启动/退出/已有seed与共享账本路径由root另验。
