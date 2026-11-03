# M1 Demo 任务交接（M0冻结后派工）

任务：L01→L02→L03，之后与UI owner L04接力。模型计划Sol/high，竞态跨层必要时xhigh；主控独立审查。
Owner：`app/demo/*`、`tests/test_demo_*`、`scripts/showcase_demo*`、专属交接文档；禁止修改runtime_factory.py、migrations.py、DocumentService、AppShell/ResearchHome/Conversations、Dashboard worker文件。每项独立commit。

从集成分支冻结SHA建立codex/showcase-l01独立worktree。先读STATE/DECISIONS/API_MINIMUM与独立M0评审，按审核修订的真实合同实现，不照旧包猜函数。网关唯一公开入口、内部每代secret/loopback进程、固定gen目录、无active SQLite覆盖；default wait_only、配置密码hash，20/30绝对TTL。

接口路由Python无/api前缀（Vite去前缀），mutation UUID操作幂等/可查证，所有业务和PDF/SSE需lease。wrong password不泄露占用；认证后423可显示generation/余时。owner takeover CAS+显式确认；仅恢复/child健康成功才issue lease。重置失败degraded；旧请求/回包不得送进新代际；过期由服务器处理。

Seed：先提供可验证manifest的专属最小seed构建/复制机制，不读取或复制未知真实数据。真实完整资料/历史报告种子由E01/E03完善；M1机制测试样本明确fake，不能把空库称完整产品seed。接线必须能运行现有真实runtime factory，测试可注入fake manager，真实BGE/Milvus启动另有spike证据。

核心验证：正确/错误密码、并发winner、同cookie不续期、wait_only拒接管、owner二次确认接管、旧token读写拒绝、在途晚到只旧代、seed校验失败关门、退出/expiry复位。先逻辑unit、再真实HTTP双浏览器（与L04联调）。不要写海量mirror测试。保留fake/真实PDF/模型/真人区分。

财务写权限以独立审查最终合同为准。不能代理local_operator；共享密码不自动构成真人签核权限。无需新RBAC系统。

交付：各项SHA、真实启动命令/env变量名（无密码）、checks PASS/FAIL/SKIP、截图/HTTP证据、未验证/回退、有限费用。任何外部阻断记录后继续可独立部分。不得部署/合main/force push/触碰既有data。不要创建额外子会话或subagent，主控已安排有限并行。
