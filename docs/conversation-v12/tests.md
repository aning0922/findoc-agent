# V1.2 验证证据

日期：2026-11-02，Asia/Taipei。环境：macOS arm64、Python3.12.13、Node24.19.0。独立 worktree `findoc-conversation-v12`，基线 `main@1f0a3d4131480ac0ea742772127afac3c892fc7c`。本文件区分测试层次，不将重跑、交叠组或模拟财务接受相加为通过总数。原始本机记录位于 Git 忽略的 `data/conversation-v12-validation/`；公开仓库不包含私有 PDF、runtime 数据库或凭据。

## 代码与质量检查

| 检查 | 实际结果 | 快照 / 证据 |
| --- | --- | --- |
| 完整后端 pytest | **1681 PASS / 1 SKIP / 0 FAIL**，1066.17秒，5条既有 SWIG warning | 启动HEAD8638b05；`final-quality/backend-full.txt`。运行期间共享树有后续G提交，这是集成回归记录，不称clean固定SHA全量结果 |
| G修复后后端受控CI与会话/Memory相关组 | **284 PASS / 0 FAIL**，30.57秒 | 5e9fb1b；`final-quality/backend-after-g.txt`，与完整组重叠 |
| 旧报告全组 | **83 PASS / 0 FAIL**，100.95秒 | `final-quality/backend-reports.txt`；使用本轮fresh报告/迁移proof，非借用历史确认 |
| 前端完整单测 | **209 PASS / 25 SKIP / 0 FAIL**，234总数 | 5e9fb1b；`final-quality/frontend-tests.txt` |
| 前端lint/build/audit | 全部exit0；audit **0漏洞** | 5e9fb1b；`final-quality/frontend-manifest.json`；CSS补丁后ad12570完整build也exit0（`frontend-build-after-css.txt`），保留既有Fast Refresh warning和大chunk提示 |
| Ruff | 会话/Memory/相关原CI文件通过 | `final-quality/backend-ruff.txt`及`backend-ruff-after-g.txt`均exit0 |

后端1项跳过涉及未提供的本地冻结评估数据，不将其视为通过。前端25项为私有D28历史精确Run/Report载荷缺失时既有显式skip；未伪造公开fixture或删除断言。真实原始年报按 `product/validation/sources.json` SHA核验复制，四份原件未纠错或改写。v1–v9 migration DDL/checksum保持不变，新增v10/v11/v12逐项验证；旧D23只更新过期版本上限假设。

## HTTP与浏览器（明确替身）

运行器使用真实HTTP、SQLite、正式ConversationGraph/Memory/摘要实现、真实年报PDF及PDF.js；model/BGE/vector为显式确定性替身，所有模拟财务接受标记 `simulated_test`，真人接受计数0。Chromium、Node24.19.0，单worker、无retry。

| 组 | 当前实际证据 |
| --- | --- |
| 新会话基础16项 | `a4-v12-integrated-02` **16 PASS**；含来源失效、UNKNOWN、真实两page并发、记忆CRUD、390/1440及PDF |
| 扩展恢复20项 | `a4-v12-expanded-01` **20 PASS**，但启动时HEAD8638b05+dirty修订，不能作为最终固定SHA证据 |
| 最终固定快照21项 | `a4-v12-final-21-01` **21 PASS / 0 FAIL / 0 SKIP / 0 flaky / 0 retry**，151.52秒，HEADad12570c3da7c5fd3b201a2d22687191a4984954；exit0、servers_stopped=true。新增S4原句完整UI链，保留此前19/1失败记录 |
| 原默认Agent浏览器 | `default-agent-01` **2 PASS**，4.4秒，服务器已停止 |
| 旧QA阅读 | `legacy-qa-01` fresh经营旅程 **1 PASS** + QA规格 **12 PASS**，非真实模型/真人接受 |
| 旧阅读交互 | `legacy-reading-01` fresh旅程 **1 PASS** + reading规格 **4 PASS**，19.2秒，服务已停止 |
| 旧报告浏览器 | `legacy-reports-01` fresh旅程 **1 PASS** + report-polish/report-workspace **20 PASS**，121.87秒，服务器已停止 |
| 旧财务边界 | **18 PASS**，123.13秒；`data/ux-financial-boundary-20261102-232723`，原规格/断言未改，模拟接受明确标记，进程退出 |
| 旧来源失效 | `legacy-invalidation-01` fresh旅程 **1 PASS** + invalidation规格 **1 PASS**，34.44秒，固定ad12570，服务停止 |

最终21项的`s4-original-ui-preference-proof.json`记录真实Graph load_context返回值（隔离fixture观察、非重建/非猜回答）：未保存preferences=[]/generation3；独立UI保存后新会话cash_flow/generation4；明确UI删除后新会话及原历史会话后续preferences=[]/generation5。写请求严格一次POST和一次DELETE，财务表计数不变。该观察接口仅在tests/support装配，未进入正式app。

C01–C20由不同层次组合覆盖：后端负责严格DTO、事务/claim、预算、校验失败、启动恢复、真实事实资格、摘要及generation竞态；浏览器负责真实请求归属、用户动作、PDF/视口、原接口往返与零重放。最终21是规格项数，不等于每个C编号均有独立真实模型/真人验收。新助手独立C12已确认财务Action的正向PDF UI、20+轮摘要的浏览器专项、真实进程重启的浏览器专项及完整读屏/触屏软键盘尚未覆盖；对应事务/事实资格/摘要/启动恢复有后端回归，不能扩大为全部浏览器或真人验收通过。真人C12正向旅程见human-review.md。

## 有限真实模型

`g-live-01`：实际源为美的2024/2025原始年报，fresh隔离runtime，HEAD5e9fb1b；真实BGE、版本化Milvus运行时和已配置供应商。配置请求模型 `deepseek-v4-flash`，供应商response.model实际返回 `deepseek-flash`，分别记录；密钥不输出或提交。

实际2次物理供应商请求、2个模型响应、5次BGE调用；5个新Turn：收入原文与主要业务原文分别completed/source_quote、物理页9和13；同比和现金流均因没有明确已确认事实refused/needs_human_review；格力不在本会话范围，completed/clarification。每轮重复GET/重读新增供应商请求0，财务事实/接受回执新增0。

该轮脚本错误地挂钩legacy `MilvusSearchStore.search`；正式版本化路径使用 `scoped_search → IndexPublications.search → MilvusClient.search`，因此记录Milvus调用0并以 `insufficient_live_execution`、exit1结束。独立后端只读审查确认两份active publication、manifest SHA及已提交引用chunk身份匹配，但没有物理搜索轨迹，**不事后推算/改写计数或将该轮改为通过**。修订观测挂钩并在新目录有限重跑后单独记录。

修正观测后 `g-live-02`（代码HEAD10339fd）以新runtime和新operation执行相同5轮，**observed_pending_human_review / exit0**：2次物理provider请求，response.model均deepseek-flash；BGE5次（含预热/索引/查询，不等同5次查询），物理Milvus **4 attempts / 4 success / 0 failure**。两原文摘录分别返回2025报告物理页9/13；同比/现金流仍因无明确已确认事实安全拒绝；格力仍澄清。每轮历史重读不新增provider，财务接受回执/已确认事实均0。原g-live-01失败不覆盖。

本次导出 `demo/conversation-v12/real-model-history.json` 为只读种子，来自实际已提交Turn DTO及经过挑选的执行proof字段，无凭据或本机runtime路径。它包含公开测试年报的引用摘录，不附PDF；完整本地app可核对同版PDF。静态只读页不会调用模型或财务业务接口。实际390/1440检查五轮及每项回答/引用与JSON一致，无整页横溢或页面错误，仅GET静态资产，记录于g-live-02/readonly-demo。手机表格修订后的实际历史截图位于g-live-01/visual-after-css，390首列210px、内部宽表滚动，整页390px无横溢；只读请求均GET。两轮内容相同不表示模型固定确定性。

真实模型回答仍待人工语义复核；返回原文、引用身份校验、模拟财务正向和真人财务核准是四种不同证据。自由解释本版关闭。真人确认已接受财务数据再明确发送的端到端G旅程仍待用户，自动测试不替代该动作。

## 保留的失败与中断

- 初始全后端328PASS/3FAIL：本地原PDF缺失；核验原件SHA后准备隔离资料，没有把该次失败抹去。后续645PASS/20deselected/3ERROR：缺新鲜报告proof；之后由本轮明确模拟旅程生成proof并重测。
- 旧报告最初80PASS/3FAIL、迁移专项2PASS/4FAIL：v9上限硬编码，保留v9原校验并改当前迁移列表后6PASS，最终报告83PASS。
- A4早期route存在性检查误判、错误PDF路径、共享seed污染导致中断，记录保留于validation-a4-preparation.md。后续独立派生副本和真实PDF路由修正；原始四PDF不变。
- `a4-v12-integrated-01` 12PASS/4FAIL：浏览器定位/事件同步，修订后同组16PASS，不累计。
- `a4-v12-final-01` 因启动后测试提交前进，为保持固定快照主动中断，exit130；不计全套通过。`final-02` 19/1为真实失败，其测试前置已改为合法basis纠错并验证来源失效状态。
- G独立审查原3条P2均由c103ab3/337916f修复、Astra窄复核关闭。原finding与关闭依据保存在reviews/g-final-audit.md，不删除历史。

## 复现

先准备依赖（Node24、已安装Python环境）与四PDF的正确SHA，参考 [validation-a4-preparation.md](validation-a4-preparation.md)。新套件不直接借用已有服务器或正式runtime：

```bash
python -B scripts/run_conversation_v12_e2e.py --out /absolute/path/to/new-conversation-e2e
# 旧规格：每个输出新目录；先新建模拟旅程，再顺序运行目标旧规格。
python -B scripts/run_conversation_v12_e2e.py --legacy-proof-only \
  --legacy-extra qa-workspace.spec.ts --out /absolute/path/to/new-legacy-qa
# 后端新功能与原受控CI组见.github/workflows/quality.yml。
python -m pytest tests/test_conversation*.py tests/test_memory*.py -q
```

完整后端另需本轮fresh `FINDOC_REPORT_TEST_PROOF` 和 `FINDOC_MIGRATION_TEST_PROOF`；生成方式见准备说明。真实验证使用独立 `validate_conversation_v12_live.py --execute-live`，受物理provider总预算/每Turn预算/无SDK retry/允许写路由限制；每次新out，不能为了绿灯覆盖失败或自动重放旧operation。

全部本轮隔离验收服务已停止；root另外保留完整功能preview及静态案例供用户复核，不属于仍在运行的测试。

本地质量检查不等于GitHub CI已运行；本分支尚未push、PR创建、合并、部署或发布。
