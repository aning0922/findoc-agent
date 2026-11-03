# C 候选交付说明 · 2026-11-03

入口、依赖与命令以[仓库 README](../../README.md)为准。当前是独立 V1.2 衍生的求职演示候选，非公开部署。业务实现检查点 `9f4993c`，最终独立审查 `4ef39b5`，launcher TTL `94ad789`；最终文档提交可由分支 HEAD 定位。

## 本机继续

在集成工作树使用已安装环境：

```sh
PATH=/Users/aipuli/.nvm/versions/node/v24.19.0/bin:$PATH PYTHONPATH=. \
/Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python -u \
scripts/run_showcase_local.py --llm-config /Users/aipuli/Documents/Projects/findoc-agent/.env
```

入口 http://127.0.0.1:14530 。本机 `data/showcase-local.env` 已建立，不重复 init。登录凭据只在本人本机文件中查看，不发聊天；默认等待策略、20 分钟，配置仅接受 20／30。没有启用公共接管。launcher 的 `--owner-takeover` 只允许独立 owner 密码和二次确认。Ctrl+C 清理本次拥有进程，不影响原开发库。

模型配置为同 Git common-dir 下的私有、600 权限 `.env`；仅 backend 接收四项白名单。现存共享预算 `data/showcase-cost-control/provider-budget.db` 保持，不删除、不复制到 seed、不重置余额。即使省略模型配置，也可浏览种子和 OCR／报告历史；新模型研究会不可用。

## 可搬运资产

源码与文档在 feature 分支；单独的公开精选 seed bundle 在 `data/findoc-showcase-seed-v1.tar.gz`。该文件不由 Git 托管，需要随本地候选传递；不包括任何登录密钥、模型配置、账本、私有测试集或开发者真实 DB。manifest／bundle 全 SHA 与解包核验见[evidence/seed-bundle.json](evidence/seed-bundle.json)。新 checkout 安装依赖、预热 BGE 后，解包到尚不存在的 data/showcase-seed-v1，再运行 init/check/start。

当前 seed：美的／格力两企业，3 官方 READY 年报，2 真实历史研究，2 报告／3 revision，1 示例会话，2 演示笔记，派生扫描真实 OCR 68 行／54 格。库存齐全不代表财务签核；没有继承历史 lease 或财务 grants。重置已在两个独立 Chromium 进程、真实 HTTP 下验证，seed SHA 不变且新代移除脏新增。[M4 结果](evidence/M4/full-reset/browser-result.json)

## 展示与验证

实际截图／录屏／PDF在[evidence/M5](evidence/M5)。最新完整 UI 走查 `06nyuff2` 完成单／多研究、明确计划批准、事件与来源、两个版本、实际 5 页 PDF，以及旧任务等待真人；human_financial_approvals=0。历史只读 PDF／OCR 查看没有业务 POST 或模型调用。

最终费用快照 73 个物理 provider calls，保守预留 1.354700 元／5 元；实际扣费未观测。15 固定题只有 5 partial intent 观察、10 skipped，无完整层级 PASS。23 项最终独立离线检查 PASS；较宽旧回归 141 PASS／57 setup ERROR（缺旧 d21-real-research.json fixture），没有伪造替代证明。前端 build/lint 成功并保留 warning。

原始失败继续留存：早期工具多调用／不支持表页／JSON截断；ybr4pane 研究阶段完成但 runner 在额外 seed 上传缺 Origin 最终 FAIL，后补 seed 材料为真实 Vision／BGE 的 in-process ASGI，不冒充外部 HTTP UI；后来完整 UI runner 06nyuff2 单独 PASS。详见[EVIDENCE](EVIDENCE.md)。

仍待本人：逐项 PDF 核对、独立 ACCEPT／SAVE／RESUME；扩展财务核准图正向和完整固定题层级未获真实验收。OCR 是真实页派生单页而非完整原生扫描公告；目录限两企业两年。P2 与环境限制见[KNOWN_ISSUES](KNOWN_ISSUES.md)。没有公开部署、main 合并或代理代签。


## 远端与本机交付

源码及截图／录屏／PDF资产提交 `6476ad03ce869d315f4b8174fcd0af233e3d4b5d` 已正常 push 至 `codex/findoc-showcase-c-integration`，远端 SHA 一致。草稿 [PR #2](https://github.com/aning0922/findoc-agent/pull/2) 目标为 `codex/conversation-memory-v12-20261102`，不是 main。最终交付说明跟进提交以分支 HEAD 为准。没有合并或公开部署。

本机 launcher 已重新启动，HTTP200，`/api/demo/status` 为 ready／20分钟／wait_only，保持未登录供本人使用。费用账本不因重启而补充；原始V1.2工作区tracked clean。远端自动Quality正在执行，结果以Actions及最终汇报为准，不预填PASS。
