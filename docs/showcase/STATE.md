# FinDoc C 主控状态

更新：2026-11-03（Asia/Taipei）。当前为 **完整功能候选已集成、本地可体验**；不是全量验收或生产发布。M0→M5 研发及自动化核心走查完成，真人财务核准和完整评测仍保留待验证。

- 集成分支：`codex/findoc-showcase-c-integration`；工作树 `/Users/aipuli/.codex/worktrees/findoc-showcase-c-integration/findoc-agent`。
- 已重新 fetch，V1.2 远端／本地仍为 `c8be30808a3ac8c6d13daa5fd9d43c0ea1212c78`，main 为 `1f0a3d4131480ac0ea742772127afac3c892fc7c`；原 V1.2 工作区 tracked clean，原资料与私有数据保留。
- 业务集成实现检查点 `9f4993cf3463fa0d3c4520799435f3bf45eefeac`，最终 Astra 独立审查 `4ef39b5`（源 `90ac635`）；launcher TTL 跟进 `94ad7890321eda3f69034c977b8f32f54e32ecce`（源 `e51654c`）。最终交付 SHA 以本分支 `git rev-parse HEAD` 为准。
- [36 项任务表](task-board.csv)分别记录实现和验证状态，全部已集成；存在 human_pending、eval_partial 和旧 fixture 缺失，不把它们算完整 PASS。[F01–F18 地图](PRODUCT_MAP.md)与原工作包一致。
- 热点由主控唯一集成；3 个可见 worker chat／worktree 已完成实质任务，最后轻量交付核查采用 Terra medium。当前没有待并行开发批次，后续只按实际体验发现修演示 P0。

## 实际体验入口

主入口 **http://127.0.0.1:14530**。本机 launcher 已实跑登录／完整首页／退出复位和 Ctrl+C 清理；交付时由主控重新启动并保持未登录 ready。它依赖当前本机进程，不承诺应用关闭后持续无人运行。

本机固定演示账号与随机密码保存在 Git 忽略、600 权限的 `data/showcase-local.env`，本人本地查看。默认 wait_only、20 分钟，可选 30；独立 owner 密码的接管模式需明确启动参数。provider 密钥仅从原仓库 Git 忽略 `.env` 读取，不入前端、种子或证据。

## 里程碑结果

| 里程碑 | 用户可见结果与真实证据 |
|---|---|
| M0 | 真实读工作包／V1.2，独立 Astra 最高专项评审，两套 token 实际比较选择 Navy/Blue，可点击 React、六组最小 API 与分工冻结。 |
| M1 | 完整 React 首页／统一导航；登录、剩余时间、owner 二次确认接管、旧浏览器下线、独立代际恢复。最初机制 seed 验证后，M4 已用完整产品 seed 重新验证。 |
| M2 | 官方下载→219 页真实解析／BGE／Milvus；真实 Apple Vision OCR 68 行／54 格与原页；资产／负债四候选、真实财务日期及待核对界面。财务本人确认未执行。 |
| M3 | 单／双真实子代理受限交接、意图／计划／明确批准、事件、原文与解释、财务任务等待；版本报告及实际 PDF；跨会话真实 BGE 记忆与删除、偏好改变首页。 |
| M4 | 完整只读 seed 及可搬运 bundle；双独立 Chromium 真实 HTTP 复位恢复全部库存与 OCR SHA；历史报告与 OCR 只读浏览无模型调用。15 题只做 5 条 intent 层观察，其余保留 skipped。 |
| M5 | 实际 UI 单／多研究→报告 v1/v2→5 页 PDF→财务任务等待本人；三宽桌面手机、截图和真实录屏；launcher 实跑及停止验证；README 与独立分支交付资料。三脚本为自动化走查，未冒充真人财务验收。 |

最新主界面走查 `06nyuff2`：真实 Chromium／HTTP／官方 PDF／BGE／模型，单 4 次模型／2 次工具、双 7／4；另 1 次意图创建旧任务等待本人。最终独立审查 23 个离线检查通过，无复现 P0/P1，但不替代真实运行证据。主控较宽回归 141 PASS／57 fixture setup ERROR；build/lint 成功且 warning 保留。[证据](EVIDENCE.md) · [截图／录屏](evidence/M5) · [限制](KNOWN_ISSUES.md)。

## 种子与费用

- Manifest `efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4`，3 官方 READY PDF＋1 派生扫描、2 真实历史研究、2 报告／3 revision、2 示例笔记、1 会话、真实 OCR 68／54。无财务授权。
- `data/findoc-showcase-seed-v1.tar.gz`，29,355,026 bytes，SHA `3693670d2369e6bed5f4981108f00a62602686a6a72bc44a64dc997bc28a2afc`；已解包校验。不进 Git，另附本地交付，不含凭据／provider／预算账本。
- 用户授权本轮 runtime API 上限 5 元；root 唯一调用，共享 ledger 在 generation 外。最终快照 73 calls、保守预留 **1.354700 元**，UNKNOWN 0，实际账单未观测；不以演示 reset 补额度。不再为收尾重复付费调用。

未触及本人财务 ACCEPT／SAVE／RESUME、公开部署、main 合并或 force push。源码 feature 分支交付不代表上述授权。当前没有需要用户先授权才能继续的普通研发步骤。


远端交付：源码／资产6476ad03ce869d315f4b8174fcd0af233e3d4b5d已push；[草稿PR #2](https://github.com/aning0922/findoc-agent/pull/2)以独立V1.2为base。最终文档跟进以HEAD为准。实际本机14530 HTTP200、ready、20分钟、wait_only，未登录；自动Quality已触发，未预填通过。下批没有实质并行任务；仅跟进CI实际失败或用户体验P0。
