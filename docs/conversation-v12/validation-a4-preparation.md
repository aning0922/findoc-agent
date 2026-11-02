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

## A2/v11首轮实际集成运行（未完成全套）

主控授权后在HEAD `847b19c67a297b7c9f20490bec4e04bd6e732b2c`启动16项。`a4-integrated-01`在fixture直接遍历app.routes的存在性检查处误拒绝，未启动浏览器；已将fixture及live脚本相同检查改为实际OpenAPI paths，不改产品route或放宽G真执行门槛。

`a4-integrated-02`的API/Vite成功ready，无reload；实际后端是启动时A2/v11。浏览器日志显示前9项API检查完成未报失败，C09因测试使用不存在的`/source/file`而得到404（预期409）。C09又纠错了共享原seed，导致后续beforeAll等待该文档ready；为停止已知级联污染，对本次runner发SIGINT。服务均收口，未产生完整results.json，**不得将该轮称为9/16全套结果或完整通过**。原manifest保留当时记录，其`status=running`是旧runner未处理KeyboardInterrupt的缺陷，不是仍有进程；补充中断证据另存于同目录`interruption-note.json`。runner随后已补显式中断状态和exit130，后续不会以running结束。

修复限专属fixture/spec/helper：C09另上传尾部附加PDF注释的独立派生副本，记录原/派生SHA并验证原件不变；用完整注册企业名明确提问，并要求completed+source_quote+非空引用后才纠错。helper复用源必须匹配精确原始文件名及selectable，不能仅company/year命中派生或失效源。PDF真实GET统一使用现有`/api/documents/{id}/file`。浏览器原文展示按每条完整引用原文断言，而不要求卡片同时包含服务端纯文本信封标题；后端完整result/hash不变断言保留。

这些修订后完整build通过，尚未重新执行。准备重启时发现HEAD已前进至`f4eee49bf70be9b131412b8140c4e3cfff13f26a`且B2 context/graph/service有在途改动，故未加载不完整B2快照冒充A2。等待主控协调B2就绪后fresh runtime重跑；财务PDF正向、完整双标签及其他新浏览器项仍未获得通过证据。G真实请求0。

## v12新会话集成最终运行

主控完成B2并提交后，以HEAD `8638b057c3554066e0e97f646517da74dfc3af76`在fresh runtime运行全16项；后端本轮无reload，正式factory装配真实ConversationGraph/Memory/v12 summaries，model/BGE/vector重依赖仍为明确替身。

- `data/conversation-v12-validation/a4-v12-integrated-01`：**12 PASS / 4 FAIL / 0 SKIP / 0 flaky**，126.40秒。C09独立副本与两项Memory均通过。四个浏览器失败为两尺寸将Markdown表格原文与HTML单元格直接整串比较、UNKNOWN未等待route.fetch完成即检查submitted、双页误以全局provider计数代替当前会话登记屏障。均保留results/trace，不冒充首次即通过。
- 仅修专属浏览器规格：逐引用、逐表、逐行单元格严格对照原文结构，保留所有数值/单位/行列；UNKNOWN先等真实服务返回被捕获再执行查证；并发先等待当前会话真实active_turn_id，防止上一用例迟到计数误唤醒。没有改业务代码或减弱零重放、范围/身份、原文及不可变断言。
- `data/conversation-v12-validation/a4-v12-integrated-02`：**16 PASS / 0 FAIL / 0 SKIP / 0 flaky / 0 retry**，123.54秒，exit0、API/Vite均停止。manifest HEAD仍为上述v12提交，记录dirty测试代码；actual_llm/BGE/Milvus均false，human_acceptances=0。两轮为同组重复运行，不相加。

已核对final results与manifest及关键proof：

| 证据 | 本轮实际结论 |
| --- | --- |
| `c09-invalidation-proof.json` | 独立派生源先产生source_quote与真实引用；实际绑定纠错后旧PDF409、新Turn阻断、旧result/hash不变，原PDF SHA不变 |
| `conversation-390-proof.json` / `conversation-1440-proof.json` | 真实浏览器/真实PDF canvas及字节SHA，dialog键盘/焦点归还，body锁释放、无页面横溢出，重读0业务写/模型新增 |
| `conversation-unknown-proof.json` | 实际POST仅1次，提交后丢响应，GET查证/刷新后模型计数与提交后相同，Turn身份/hash一致 |
| `conversation-two-tabs-busy-proof.json` | 两真实page；第一tab POST1次，第二tab POST2次（首个真实409未登记、人工再次点击后新operation成功）；失败op服务端404，最终仅登记2条Turn，0自动重试 |
| Memory实际HTTP测试 | 有限语法候选未确认零写、明确确认/编辑revision冲突/删除/replay410及新会话store仍空；不将此扩大为全部Prompt/摘要删除竞态已浏览器覆盖 |

已查看390px历史截图：金额/单位和表格均保留，宽表可局部横向阅读；首列中文较窄、长引用使页面很长，这仍是可读性限制，自动布局断言通过不等于真人可用性验收。截图位于final目录`conversation-390-history.png`等。

本16项不包含独立C12已确认财务Action PDF正向浏览器、20+轮摘要浏览器专项、真实进程重启或真实模型/真人语义核准；不能称完整C01–C20或G通过。主控报告的后端CI139、新会话/记忆136与本组有不同层次/重叠，不相加。旧controlled agent及旧UX/报告/经营旅程待主控后续分派，本聊天未同时启动它们；G真实provider请求仍0。

## G02/G03扩展与旧入口回归

主控依Astra `reviews/g-final-audit.md`分派产品修复及专属回归。新增`conversation-recovery.spec.ts`四项真实浏览器：

1. G02目录读后来源失效→create真实409未登记；草稿保留、仅解除本op、原op GET404，读取最新目录后用户明确选择有效源、新operation创建成功。失效仅作用于带原/派生SHA的独立派生PDF，通过改绑不匹配封面年份确定资格失效，不污染原seed。
2. G02双真实page，writer真实running时另一page删除真实409 conversation_busy；草稿与失败方写入口安全恢复、原op404、只读刷新0重放、用户明确第二次DELETE以新op成功。
3. G03实际偏好create已提交但响应丢失，另一真实page明确删除后，原create op的合法deleted墓碑可查证、清pending、当前列表为空、CRUD解锁，0重POST且不还原旧value。
4. 同上但原操作为update；两项均保存墓碑/HTTP写次数/表与模型计数。原网络UNKNOWN用例仍保留，不把GET404当作重POST授权。

扩展后20项收集与完整build通过。`a4-v12-expanded-01`全20项通过、0FAIL/SKIP/retry、约2.5分钟、exit0且servers_stopped=true。该轮启动时产品修复尚未提交，manifest为旧HEAD `8638b05`及相应dirty列表；不冒充新提交的固定证据。随后产品已提交为`337916f015289791c7e89ecdfe235e4c739da3d3`，本聊天再次以fresh `a4-v12-final-01`启动最终全20项，结果另记，重复用例不累计。

旧入口独立回归：

- 原默认`npm run test:e2e`（Node24，Python通过ASCII路径launcher调用已安装venv，符合旧配置简单路径约束）：**2 PASS / 0 FAIL / 0 SKIP**，4.4秒，原临时runtime由脚本精确清理，服务退出。HTML报告与last-run及运行说明已复制至`data/conversation-v12-validation/default-agent-01`；没有改旧Agent规格或controlled app。
- `--legacy-proof-only --legacy-extra qa-workspace.spec.ts --out data/conversation-v12-validation/legacy-qa-01`：原经营旅程 **1 PASS**、约2.2分钟；后续旧QA阅读 **12 PASS / 0 FAIL / 0 SKIP**、34.2秒；最终exit0、servers_stopped=true。四PDF来自当前worktree SHA校验；旧测试未改断言。模拟接受/替身模型明确，与G真人核准无关。
- 运行器新增`--legacy-extra`，在fresh旅程之后先backup干净report seed再顺序跑指定旧规格，输出独立`legacy-extra-results.json`和日志；不通过公司/年份任意复用历史数据库。旧报告/invalidation浏览器结果后续单列。

主控完整后端及报告组由主控运行，本聊天没有重复其全套。G真实provider请求仍0。

固定提交重跑记录：`a4-v12-final-01`在主控提交测试前启动，随后因same-SHA要求SIGINT收口（interrupted/exit130），不计功能失败或通过。`a4-v12-final-02`以产品+测试固定HEAD `5e9fb1bd6185925fedf11849297acf1e5a2b97f8`运行得到**19PASS/1FAIL**，约2.6分钟、exit1且服务收口。失败仅G02前置造数将2024 PDF改绑2023，产品按既有规则正确返回`report_identity_conflict`，未进入create恢复断言。修订为合法basis纠错，并明确断言副本文档`failed/SOURCE_BINDING_CORRECTED`（实际纠错事务会使旧资料等待显式重试），无需伪造错封面绑定或放宽产品验证。该测试修订需主控统一提交后再最终全套；旧19/1保留，不以先前dirty快照20PASS覆盖。

`legacy-reading-01`已完成：fresh原经营旅程1PASS（约2分钟）、`ux-simplification-reading.spec.ts`实际收集**4PASS/0FAIL/0SKIP**（19.2秒），不是初步估计的5项；manifest exit0且服务停止。旧测试未修改。随后独立`legacy-reports-01`顺序运行fresh种子+report-polish/report-workspace；不与新会话Chrome或财务边界套件并跑。

截至本记录，`conversation-recovery.spec.ts`的G02造数修订已完成、build通过，可由主控立即提交；最终same-SHA20仍需提交后运行。390宽表首列过窄的可读性问题已由主控另行确认，自动横溢出断言通过不能替代CSS可用性修复；本聊天不改产品样式。主控G-live与实际provider观察由主控处理，本聊天未发真实模型请求，也未修改其观测挂钩。

后续主控分派S4原句旅程：现有HTTP候选输入已改为“以后研究先关注现金流”，保留完整候选及未确认零写断言；另新增1项UI旅程（总数21）。真实UI发送原句→未保存时新会话实际context无偏好→点击候选的独立保存→新会话UI发送且实际Graph context含cash_flow→明确UI删除→新会话及原历史会话后续context均无偏好，原候选source turn不重新注入。fixture只包装实际Graph全局load_context返回值，保存有限偏好枚举、generation和prior turn IDs；只读test GET返回已观察快照，不重新加载上下文、生成摘要或保存raw prompt。测试不是根据答复顺序推断召回。fixture ruff、完整build和21项收集已通过，新增旅程尚未执行；这几份测试/fixture编辑可供主控统一提交。

表格可读性回归补充到原两尺寸用例：严格逐单元格原文比较不变；要求首列宽度至少150px、数值nowrap，390px宽表在局部容器可键盘横向滚动，并保存实际测量。用于防止此前逐字竖排回退，不新增用例计数。产品CSS由前端聊天修改，本聊天未改src。

`legacy-reports-01`已完成：fresh原经营旅程1PASS（约2分钟）、report-polish+report-workspace **20PASS/0FAIL/0SKIP**（约2分钟），exit0且服务收口，旧规格未改断言。随后启动原financial-boundary十八项，使用`work/run_financial_boundary.py`解释器适配器：仅在内存把旧runner唯一的硬编码`.venv/bin/python`替换为调用本适配器的已安装Python；源runner/测试/HTTP服务及财务断言均不变，不创建或修改产品venv。结果与模拟接受边界后续单列。

## 最终固定提交与本聊天验收收口

主控将G02合法纠错造数、S4原句UI/context观察、表格可读性与其他测试统一提交后，最终以 **`ad12570c3da7c5fd3b201a2d22687191a4984954`** 启动全套。启动前产品/前端/fixture范围无未提交改动；本轮没有reload，结果不借用旧进程。`data/conversation-v12-validation/a4-v12-final-21-01`为最终新会话证据：

**21 PASS / 0 FAIL / 0 SKIP / 0 flaky / 0 retry，151.52秒，exit0，servers_stopped=true。** manifest与results.json已核对；actual_llm、actual_bge、actual_milvus均false，human_acceptances=0。运行真实HTTP、SQLite、原始PDF/parser和正式ConversationGraph/Memory/v12装配，重依赖为明确替身。早期16、20、19/1、12/4及中断记录全部保留，不相加或覆盖；这轮后无新缺陷，不再重复。

最终关键proof：

- `conversation-unknown-proof.json`：实际POST1次，丢响应后按同op GET，provider/表计数无额外重放。
- `conversation-two-tabs-busy-proof.json`：真实双page竞争，失败send op未登记；草稿与pending按合同恢复，用户再次点击新op成功。
- `g02-stale-create-proof.json`、`g02-busy-delete-proof.json`：stale来源create409与另一tab运行中delete409，未登记op404，明确拒绝安全解锁，之后用户新op成功。
- `g03-create_memory-deleted-proof.json`、`g03-update_memory-deleted-proof.json`：原写已提交、丢响应、其他真实tab删除、原op合法墓碑查证，原tab解锁，不重POST、不复活旧值。
- `s4-original-ui-preference-proof.json`：原句“以后研究先关注现金流”→未保存新会话实际context为空→独立UI保存→新会话实际context为`[{key:analysis_focus,value:cash_flow}]`→明确删除后新会话和原历史会话均为空。generation实测3→4→5，UI写仅POST、DELETE各1次；原候选source turn不重入上下文。context为实际Graph返回对象观察，不是独立重构或按回答顺序推断。
- `conversation-390-proof.json`、`conversation-1440-proof.json`：全量原文单元格严格相等、实际PDF SHA/canvas/焦点及锁清理、只读恢复。390px下三表首列均210px，容器宽322px、内容宽740/562/840px，局部键盘横向滚动通过。已查看修复后390截图，首列不再逐字竖排；仍不替代真人软键盘/读屏/可用性验收。
- `c09-invalidation-proof.json`：实际原文quote先成功，独立派生源纠错后旧PDF409及新请求拒绝，历史结果/hash与原PDF SHA保持不变。

旧入口必要组已全部完成，均顺序运行、原规格未改财务/身份/零POST断言：

| 组 | 本聊天实际结果 | 证据目录 |
| --- | --- | --- |
| 默认controlled Agent | 2PASS、4.4秒 | `data/conversation-v12-validation/default-agent-01` |
| 原QA阅读 | 12PASS、34.2秒 | `data/conversation-v12-validation/legacy-qa-01` |
| ux-simplification-reading | 实际4PASS、19.2秒（不是预计5项） | `data/conversation-v12-validation/legacy-reading-01` |
| report-polish + report-workspace | 20PASS、约2分钟 | `data/conversation-v12-validation/legacy-reports-01` |
| financial-boundary原两规格 | 18PASS、123.13秒，0FAIL/SKIP/flaky | `data/ux-financial-boundary-20261102-232723` |
| 独立来源invalidation | 1PASS、34.4秒 | `data/conversation-v12-validation/legacy-invalidation-01` |
| 原经营旅程 | 各UX组fresh种子均1PASS | 各legacy目录的`results.json`；同旅程只算一个不同用例 |

各legacy运行manifest均exit0且servers_stopped=true；financial-boundary原runner exit0，API日志确认shutdown完成，原finally结束所启动进程。原financial runner使用解释器适配器的说明与源测试不变边界见前文。财务接受均simulated_test，模型/向量替身，不记为独立真人核准；本聊天没有构造local_operator真人接受记录，也不把旧财务正向测试当作新助手C12 Action PDF完整浏览器证据。

最终21项前完成的完整build/ruff检查通过；没有为这些旧组重复主控139/136/83或完整后端1681等结果。所有后端数字仅由主控汇总，不与浏览器层机械相加。仍未覆盖：新助手独立C12已确认财务Action PDF正向UI、20+轮摘要浏览器专项、真实进程重启、完整辅助技术/触屏软键盘及真人财务/语义核准。

真实provider运行由主控另存`g-live-*`证据，不混入本聊天fake报告。本聊天真实provider请求0、Git提交0；不据21项与旧回归宣布完整C01–C20、真人业务接受、合并、部署或发布。最终本聊天仅补此收口记录，产品/测试冻结不再修改。
