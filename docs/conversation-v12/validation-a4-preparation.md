# V1.2 A4 / G 验收工程准备交接

日期：2026-11-02（Asia/Taipei）。状态：**准备交接；A2未接通，不宣称A4通过；G未分派。**

唯一仓库为 findoc-agent 的独立 worktree `/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12`，分支 `codex/conversation-memory-v12-20261102`。主控负责集成和唯一提交。本轮按主控要求收敛文档，没有再次启动注定缺A2装配的完整套件。

合同权威为 `contracts.md` 与 `backend-a0.md` 第3节，A0覆盖设计及早期失败详见 `validation-a0.md`。本文中的将来命令不代表已经执行或通过。

## 当前文件及装配边界

| 文件 | 作用与限制 |
| --- | --- |
| `tests/support/conversation_app.py` | 在正式 `runtime_factory.create_runtime_app` 上替换model、retriever、indexer/BGE/Milvus重依赖；保留真实HTTP、业务服务、SQLite、PDF解析和来源复验。禁止outgoing socket及runtime外SQLite。不得把synthetic provider当真实模型。 |
| `scripts/run_conversation_v12_e2e.py` | 当前worktree四PDF SHA核验、全新runtime/输出、独立端口和进程、Node24检查、凭据移除、零重试、进程收口与运行manifest。支持专属spec选择及两类旧proof生成。 |
| `frontend/playwright.conversations.config.ts` | 显式匹配 `conversation*.spec.ts`，单worker、零retry、失败截图/trace、JSON结果。不能用默认`agent*.spec.ts`配置代替。 |
| `frontend/e2e/conversation-helpers.ts` | 真实HTTP创建企业、上传四PDF、等待ready、核对源SHA/报告年度；创建会话/发送/计数帮助函数。无整API响应mock。 |
| `conversation-api.spec.ts` | 10项：create/turn幂等与冲突、三轮/缺事实、歧义/越界、旧Run不变、并发、错误引用、provider失败、删除、严格请求、真实隔离绑定纠错。 |
| `conversation-browser.spec.ts` | 3项：390/1440历史/PDF/焦点/零写，真实POST提交后丢响应的UNKNOWN只读查证。仍需实际前后端联调，不应假定所有定位器与文案已运行验证。 |
| `conversation-memory.spec.ts` | 2项：明确候选/确认/编辑/删除/replay，以及四种非法载荷。输入对齐B1有限语法“记住：我更关注现金流。”，不是任意语言召回测试。 |
| `scripts/validate_conversation_v12_live.py` | G专用有限真实运行准备；显式execute开关、最多5新Turn/10物理provider请求、禁SDK重试、输出token上限、只读查证、无财务写路由。仅静态检查，未执行live。 |

普通E2E必须等正式factory挂载实际ConversationGraph、Memory及v11后运行；缺少Conversation路由默认明确失败。只有显式 `--a1-only` 会在缺正式路由时挂载真实ConversationRepository/Service/API与后端提供的 `fake_handler`；该模式仅运行两项创建/范围测试，不能证明多轮语义、工具或摘要。

## 精确命令

以下初始化适用于本机。Python由主仓库已安装环境提供，导入与文件源仍来自当前worktree；不安装依赖、不切换其他工作树。

```bash
cd /Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12
export PATH="/Users/aipuli/.nvm/versions/node/v24.19.0/bin:$PATH"
export FINDOC_VALIDATION_PYTHON="/Users/aipuli/Documents/AI应用学习/02_项目/findoc-agent/.venv/bin/python"
export PYTHONDONTWRITEBYTECODE=1
```

低成本静态检查，不启动HTTP服务或模型：

```bash
"$FINDOC_VALIDATION_PYTHON" -m ruff check tests/support/conversation_app.py scripts/run_conversation_v12_e2e.py scripts/validate_conversation_v12_live.py tests/test_d23_migrations.py
FINDOC_CONVERSATION_OUT=/tmp/findoc-conversation-v12-collect FINDOC_CONVERSATION_WEB_ORIGIN=http://127.0.0.1:14123 frontend/node_modules/.bin/playwright test --config frontend/playwright.conversations.config.ts --list
npm --prefix frontend run build
"$FINDOC_VALIDATION_PYTHON" scripts/validate_conversation_v12_live.py --help
```

当前已运行过的A1窄组入口，重跑时必须使用尚不存在的输出目录：

```bash
"$FINDOC_VALIDATION_PYTHON" -B scripts/run_conversation_v12_e2e.py --out data/conversation-v12-validation/a1-api-02 --a1-only
```

**以下为待A2/v11装配完成并经主控分派后的命令，现在不启动：**

```bash
"$FINDOC_VALIDATION_PYTHON" -B scripts/run_conversation_v12_e2e.py --out data/conversation-v12-validation/a2-api-01 --spec conversation-api.spec.ts
"$FINDOC_VALIDATION_PYTHON" -B scripts/run_conversation_v12_e2e.py --out data/conversation-v12-validation/a4-browser-01 --spec conversation-browser.spec.ts
"$FINDOC_VALIDATION_PYTHON" -B scripts/run_conversation_v12_e2e.py --out data/conversation-v12-validation/b2-memory-01 --spec conversation-memory.spec.ts
"$FINDOC_VALIDATION_PYTHON" -B scripts/run_conversation_v12_e2e.py --out data/conversation-v12-validation/a4-all-01
```

先跑有针对性的组修正真实缺陷；只有集成后需要统一证据时再跑全套，不能将这些重复运行的用例相加。各命令各自创建fresh runtime，前一命令的seed不会被自动继承。

旧报告与迁移proof已存在且来自本聊天独立运行，可用于精确旧组，无须再跑完整后端：

```bash
export FINDOC_REPORT_TEST_PROOF="/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12/data/conversation-v12-validation/legacy-proof-01/report-test-proof.json"
export FINDOC_MIGRATION_TEST_PROOF="/Users/aipuli/Documents/AI应用学习/02_项目/findoc-conversation-v12/data/conversation-v12-validation/migration-proof-01/migration-test-proof.json"
"$FINDOC_VALIDATION_PYTHON" -B -m pytest tests/test_d22_reports.py tests/test_d23_reports.py tests/test_d23_migrations.py tests/test_d24_exports.py -q -p no:cacheprovider
```

如临时seed已被系统清除，用未存在的输出目录重新生成；不能直接改proof指向任意旧库：

```bash
"$FINDOC_VALIDATION_PYTHON" -B scripts/run_conversation_v12_e2e.py --out data/conversation-v12-validation/legacy-proof-02 --legacy-proof-only
"$FINDOC_VALIDATION_PYTHON" -B scripts/run_conversation_v12_e2e.py --out data/conversation-v12-validation/migration-proof-02 --migration-proof-only
```

生成后将两个环境变量分别改为新输出的`report-test-proof.json`与`migration-test-proof.json`。两个生成选项分开执行，不组合模式。

G真实运行仅在主控另行明确分派后执行；下列是待分派命令，**本轮没有运行**：

```bash
"$FINDOC_VALIDATION_PYTHON" -B scripts/validate_conversation_v12_live.py --out data/conversation-v12-validation/g-live-01 --env-file /Users/aipuli/Documents/AI应用学习/02_项目/findoc-rag/.env --max-provider-attempts 10 --execute-live
```

旧findoc-rag仅用于已授权配置文件只读；不改其代码/数据，不复制凭据至证据。字段存在不证明供应商余额、可达性或能力。G脚本需先完成对最终A2实际接口/调用预算/异常分支的复核；execute参数是防误启动，不是新增授权。

## Fixture / runtime 与结果预期

- 四份原始PDF必须存在于当前worktree `data/30d-foundation/`，与 `product/validation/sources.json` SHA一致。启动器在任何测试前校验，不从历史工作树取文件，不改原件。
- 普通runtime由 `tempfile.mkdtemp` 生成绝对路径，前缀 `findoc-d11-conversation-v12-`，位于系统临时目录；fixture拒绝默认runtime、相对路径及非此模式路径。API只绑定127.0.0.1，端口由运行器分配，Vite strictPort且不复用其他服务。
- 上传/解析为真实服务；embedding、检索选择、vector索引和model为受控替身。截断响应使用真实POST到达服务端后的传输故障，不能直接返回预制Turn冒充落库。
- `run-manifest.json`记录HEAD/dirty状态、环境版本、源SHA、实际/替身、命令/退出码、runtime和进程收口；`results.json`为Playwright结果，另有API/web/browser日志及trace。manifest中的预期stage标签不能单独证明已走过Graph，仍须审查实际装配和结果。
- 每次out必须不存在，不覆盖早期失败。脚本结束停止本次进程，保留本次runtime和证据供复核；不递归清理其他目录。旧proof临时根路径保存在各proof中。
- `--legacy-proof-only`跑原旧经营旅程，使用原独立前端测试入口、模拟接受；在报告生成前通过SQLite backup取得一致seed，复制对应objects。不是新助手前端整体验收，也不是G真人接受。
- `--migration-proof-only`从空目录按前8条旧迁移构造v8源记录，不降级已有库、不DROP新表。它只用于v8→当前迁移回归；不代表产品使用截断迁移。
- 原D23测试修订保留对v9的DDL/log失败注入、回滚、旧表行及checksum；验证log[8]精确v9记录及全量迁移log，不用宽松`>=9`。unknown记录插入当前max版本+1，missing8/modified9不变。

## 已有证据与失败保留

| 检查 | 结果 | 限定范围 |
| --- | --- | --- |
| 本聊天旧经营E2E | 1 PASS | 四真实PDF/HTTP/SQLite、模拟接受、provider/检索替身；`legacy-proof-01` |
| 本聊天旧报告组首轮 | 80 PASS / 3 FAIL | 3 FAIL为D23缺单独v8 proof；不能称全组通过 |
| 本聊天补v8 proof后旧D23 | 2 PASS / 4 FAIL | migration10追加后旧测试硬编码9/未知10冲突，失败保留 |
| 主控授权D23测试修订后 | 6 PASS / 0 FAIL | 0.72秒，当时迁移1–10；v11集成后可精确复跑 |
| 本聊天A1创建/范围HTTP | 2 PASS / 0 FAIL | `a1-api-01`；真实服务+明确fake_handler；非A2 |
| 本聊天静态准备 | 15项可收集；Python AST/ruff通过 | 收集不等于15项功能通过 |
| 前端最终build | PASS | 本聊天Node24 / Vite8.2.4，tsc-b+Vite；保留大chunk提示 |
| B1模块 | 主控报告31 PASS | Memory单元/契约，不是runtime/browser已接通 |
| A1后端 | 主控报告48 PASS、已提交 | 实际A1契约；不是本聊天A2/browser结果 |
| 旧联合组 | 主控报告241结果 | 保留主控原始明细；不与48项、196项或本聊天结果相加 |
| 前端单测 | 主控/前端报告199 PASS / 25 SKIP | 跳过项保留，本聊天未重复运行 |
| 新助手A2/B2浏览器 / G | NOT_RUN | 等A2/v11装配与主控分派；真实模型请求0 |

TS2783曾由测试载荷重复value构造触发：已改为四个完整非法字段场景，保留具体非法value及422断言；修复后完整build通过。主控完整后端基线的缺PDF/缺proof失败、645PASS/20deselected/3ERROR提前停止，以及相关196PASS均见原记录；不与本聊天结果机械求和或覆盖。

## 待A2及后续明确工作

1. 正式factory注入真实Graph、只读工具和MemoryService，注册v11，检查history-only路由与启动恢复。默认fixture应从该装配获取实际新服务，不静默降级fake_handler。
2. 先跑实际API组，核实C01解析/年份、缺事实、C09失效、C13伪引用以及回执/删除枚举。provider/fault hook只操纵边界，不能绕过服务端终态提交。
3. 前端已接财务`open_source`正向PDF按钮；需对最终后端Action URL与前端校验确认一致，再加实际财务正向浏览器用例。此前发现的路径静态差异尚不能凭build证明已运行解决。
4. 补C12明确事实版本选择与既有Decimal服务的正向HTTP/浏览器证据；不得因为已有摘录PDF测试就宣称财务Action按钮已验收。
5. 补C16上下文/摘要/缓存不复活、generation并发fencing；当前Memory CRUD/GET为空不证明模型Prompt未召回旧偏好。B1候选仅支持有限明确表达，Graph须传当前持久用户原话。
6. 补C17的20+轮/token预算/摘要游标与污染防护，以及真实进程停止重启、active turn interrupted/GET零执行。当前刷新测试不能代替进程重启。
7. 在390/1440真实页面检查原文展示选择器、modal焦点/滚动锁、失效缓存像素撤回、UNKNOWN按原operation只读查证。不得削弱金额、身份、不可变、零重放断言使套件变绿。

### C12自动化资格路径与真人核准边界

`local_operator` 是后端资格字段，**不能单凭该字段证明独立真人核准**。若未来隔离fixture为覆盖C12正向资格路径自动生成含`local_operator`的测试记录，必须在manifest、proof、测试说明与最终报告明确写：`automated_fixture=true`、`human_acceptances=0`、字段由自动化fixture构造，非独立真人核准。应另列自动创建的资格记录数；不要错误声称“没有任何接受记录”。

这种fixture只能证明：受控测试来源/版本/资格通过实际服务校验时，工具选择、Decimal结果、出处与PDF导航符合合同。它不能证明真人阅读PDF、核实金额/单位/期间，不能升级为G真人接受或真实金融业务完成。若构造不符合生产资格，应保持拒绝，不放宽生产校验或将simulated_test冒充local_operator。

G仍需独立记录实际源SHA、真实provider尝试、实际检索、输出与人工语义待审；真实模型不能替用户执行ACCEPT/SAVE/RESUME或记忆确认。真人接受只有用户实际完成核准并有独立证据时才计入，自动化fixture与真实模型证据分别保留。

本轮准备到此交接。后续由主控在A2接好后以high推理分派实际整套运行；不提前宣称P0/P1、完整C01–C20或发布通过。

## Fixture audit静态复核

本轮只读复核未另启服务。audit hook在正式factory装配前安装：`socket.connect`全部拒绝，SQLite连接只允许`:memory:`或本次绝对临时root内路径，`file:`URI经URL解析/解码后再检查。model.from_env、BGE预热、embed/indexer及RAG资源构造在调用factory前被当前测试进程的确定替身替换；原SQLite/对象存储/解析服务仍真实装配。已有A1两项HTTP通过可证明该旧阶段mock装配能在这些限制下启动，不能证明尚未完成的A2模型接口兼容。

hook不修改应用代码，不解除外网限制，也不为模型安装网络例外。若A2新增模型方法未被替身实现或绕过注入创建真实client，套件应明确失败并在专属fixture补齐严格接口，不关闭hook或从环境恢复凭据。A2是否使用与fake Model兼容的调用方法、是否所有Memory/Conversation数据库都位于同root，仍在主控A2完成后通过首次实际运行核实。

## 新增C04双浏览器标签页回归（待A2运行）

主控补充分派：两个真实page同会话发送，失败方收到服务端真实409 `conversation_busy` 且未登记operation时，不得永久保留pending后反复GET404锁死。

已在`conversation-browser.spec.ts`新增该case：两个同context独立page先读同一会话，fixture在真实provider调用边界用Event临时保持首轮（最多20秒，finally释放），第二page实际POST竞争。校验409机器code、失败operation服务端404、失败tab草稿保留且sessionStorage仅清除自己的pending、首tab待处理operation仍保留；不伪造409响应。首轮结束后失败tab只读刷新，不能自动POST或查证已明确未登记的op；只有用户点击发送才发新的operation，最终仅两条已登记Turn。记录POST操作身份、读请求、模型/表计数及`conversation-two-tabs-busy-proof.json`。

该case不改变网络错误/5xx/坏JSON/普通GET404的UNKNOWN保留规则，原响应丢失case仍保留。当前总数为16项可收集测试；新增case未执行。首次静态收集发现新增断言括号错误，修正后收集16项通过；这不是后端运行失败。未启动缺A2的完整套件。

并行编辑结束后的最终静态检查：Node24/Vite8.2.4完整`npm run build`通过；完整`npm run lint`通过（退出码0，保留既有`tests/support/d14-chart-boundaries.tsx` Fast Refresh warning）；fixture ruff通过。第157行编辑中语法错误已经修正，不留待下一轮修复。主控另报告前端更新后203PASS/25SKIP，本聊天未重复运行该单测组。
