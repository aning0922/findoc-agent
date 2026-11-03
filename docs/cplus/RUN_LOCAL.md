# C+ 本机运行（开发中）

当前M0已冻结，M1/M2正在集成，不能将旧C首页和历史截图当作C+新增业务完成。可点击React UI_MOCK预览 http://127.0.0.1:14541/cplus.html 。

root组装的C+主入口使用14540；保留旧C14530。新私有账号文件在本C+工作树data/showcase-local.env，600/Git忽略，仅本人本机查看。独立C+cookie避免同host端口互相覆盖。种子已独立备份/解包，不覆盖旧C。

```sh
PATH=/Users/aipuli/.nvm/versions/node/v24.19.0/bin:$PATH PYTHONPATH=. \
/Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python scripts/run_showcase_local.py \
--cplus --check --llm-config /Users/aipuli/Documents/Projects/findoc-agent/.env \
--provider-budget-db /Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent/data/showcase-cost-control/provider-budget.db
```

--check不启动/调用模型。接线后去掉--check才启动真实服务；不要在C+目录执行旧README的ProviderBudget初始化命令，不复制账本！同一5元cap，缺既有文件/权限/schema/common-dir不匹配拒绝启动。现在只读快照73calls/保守1.354700元，实际账单未知。
