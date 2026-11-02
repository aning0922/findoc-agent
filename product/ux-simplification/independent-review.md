# FinDoc UX 简化改造：独立契约与边界审查

日期：2026-11-02。审查对象为 `findoc-ux-implementation` 工作树、`codex/ux-simplification-20261102` 分支上的当前迁移修改；起始基线 `cdbd081`。这是独立工程审查记录，不构成真人财务接受、生产发布或五人可用性验收。

## 当前结论

已复查六项矩阵、原位核对、ACCEPT/SAVE/RESUME、UNKNOWN 恢复、首页/任务列表导航、PDF portal 生命周期以及报告编辑保存前校验。此前发现的嵌入披露身份、历史记录写权限、同组重挂和暂停时隐藏模态锁问题，均已反馈实现者并逐项复查修正。当前静态复查没有保留的阻断性契约发现。

独立运行的既有财务边界 E2E 为 **18/18 PASS**；独立运行的四个前端契约测试文件为 **22/22 PASS**。最新 `paused` 生命周期断言已在最终 journey 通过；独立审查员已读取主控产物确认 journey 1/1、reading/dashboard/QA 合计 17/17，0 失败、0 跳过。该运行由主控执行，本审查员读取核验结果，不能描述为本人重复执行。P1 最终产物另确认报告套件 20/20 与其独立 seed journey 1/1；这些共同构成限定的工程证据，仍不是真人验收。新嵌入实际来源纠错补充测试也已通过，审查员已读取其运行结果和专项断言。当前本审查范围内无剩余工程阻断；真人财务核验与五人可用性测试仍待人工。

## 独立执行证据

### 财务接受与保存 E2E

- 测试文件：`frontend/e2e/financial-review-real.spec.ts`（10 项）、`frontend/e2e/financial-persistence-real.spec.ts`（8 项）。
- 结果：18 通过、0 失败、0 跳过、0 flaky、0 重试；浏览器耗时约 124.4 秒。
- 机器可读记录：`data/ux-financial-boundary-20261102/results.json`、`independent-validation.json`、`run-manifest.json`、`review-measurements.json`、`facts-measurements.json`；同目录 `screenshots/` 有 19 张截图。
- 复现脚本：`frontend/scripts/run-financial-boundary-e2e.py`。Node 24.19.0，本工作树 `.venv`，独立动态端口与临时 runtime；运行后拥有的 API/Vite 服务均停止。
- 四份实际年报 PDF 的 SHA 与 `product/validation/sources.json` 逐一匹配；实际使用 PDF、解析器、SQLite、HTTP、Chromium PDF 阅读器。embedding、向量索引与 chunk IDs 使用测试替身，没有模型执行。
- 只读数据库审计：15 条 `financial_acceptance_receipts` 和 7 组 `financial_fact_sets` 全部标记 `simulated_test`。没有真人接受记录。
- 覆盖：原值/单位/年度与证据；取消和修改零接受 POST；unsupported/conflict 阻断；审阅迟到响应；接受和保存双击仅一次 POST；跨企业迟到响应不能发布旧成功；接受/SAVE 响应丢失后刷新仅按原身份 GET；POST 成功而 GET 内容损坏不得宣告成功；确定保存失败不得将接受记录升格为事实；来源纠错撤下旧接受/事实界面。
- 保留限制：该次 `FINDOC_E2E_STAGE=ux-boundary`，最后来源纠错用例执行接受资格分支，没有在该条测试内先保存新的事实组。保存套件的 8 项独立通过，不把它们拼接成未实际运行的纠错流程。

测试改动仅添加独立 runtime/截图/measurement 路径环境覆盖，以及将旧显示文案“财务事实入库待完成”同步为“数据尚未保存”；没有降低身份、POST 次数、只读恢复、值/单位或准入断言。

### 前端契约单测

独立使用 Node 24.19.0 执行：

```text
node --test tests/researchCandidates.test.ts tests/financialReviewApi.test.ts \
  tests/financialFactsApi.test.ts tests/operatingResearch.test.ts
22 passed / 0 failed
```

覆盖候选预览的来源/披露歧义、审阅与接受身份、SAVE 读回、UNKNOWN 不重发、六项合格事实准入、revision 所有权、旧任务与语义待审边界。

必须保留的环境失败：首次直接调用默认 `node` 命中 **v20.20.1**，四个 `.ts` 测试文件均因 `ERR_UNKNOWN_FILE_EXTENSION` 无法启动；当时没有进入业务断言。改用仓库要求的 Node 24 后取得上述 22/22。该失败没有被改写为首次通过。原始命令与输出位于本次独立审查聊天工具记录；未另存原始 TAP 日志。

## 已核对的实现边界

| 领域 | 当前实现及审查结论 |
| --- | --- |
| 六项矩阵 | `OperatingTaskPanel` 保留原有 guard、slotFacts、resumeFacts；候选值显式标记待核对，不能作为已保存事实计算。多合格事实保留用户选择。 |
| 候选预览 | `researchCandidates.ts` 全程 GET；验证 source/revision/SHA/parser/metric/year；候选接口不可按披露版本查询，因此多披露版本时拒绝自动归属。 |
| 冻结嵌入身份 | `EmbeddedTaskReview` 重新 GET task 并验证 scope/revision；`expectedDisclosure` 从已验证局部上下文传入，避免读取外层研究 URL 的缺失字段。 |
| 历史记录 | 非 waiting 任务的已保存记录可只读查看；`allowWrites=false` 隐藏写入口，模式切换处理器也拒绝 new/save。 |
| 同组切格 | 会话 key 使用 task/revision/side/document/disclosure/fact_set，metric 仅改变本地定位；不因同组切格丢失勾选。 |
| ACCEPT/SAVE/RESUME | 三个独立动作保留。ACCEPT 验证快照；SAVE 执行 POST 后按 receipt GET 并比较；RESUME 重新读取 task revision/checkpoint/idle 和六项当前合格事实。没有 effect 自动执行。 |
| UNKNOWN | ACCEPT 按 request/snapshot/scope GET，SAVE 按 receipt GET，研究按 operation GET；重开嵌入仅恢复查询身份，不恢复写授权。 |
| 首页/任务列表 | 新 `useResearchTasks` 全程 GET+validateTask；分页游标严格递减，清理后不发布旧响应。列表筛选不改任务冻结范围。 |
| 导航 | 五导航仍为 `a[href]`，原 ReportNavigation 捕获式点击/历史遍历守卫可先于导航处理器保护未保存编辑；不因导航自动执行研究。 |

当前交付是**同页指导流程**，不是一键顺序写事务：ACCEPT 与 SAVE 仍各需一次明确点击，六项齐全后再明确继续研究。界面简化不能被描述为已实现自动完整财务接受。

## 最后发现并修复的暂停生命周期问题

初始 portal 实现只对父会话和右侧容器使用 `hidden={!safe}`。独立最小 Chromium 探针证明：祖先 hidden 后，原 `showModal()` dialog 的尺寸为零，但仍 `open=true` 且匹配 `:modal`；页面可能被不可见模态锁住。移动 `EvidenceViewer` 同样会因 `narrow && active` 未改变而保留 `body.style.overflow='hidden'`。

实现者修正后，本审查重新核对了代码：

1. `paused` 从 TaskPanel 经 EmbeddedTaskReview、DocumentSession 传入 FinancialSession。
2. 暂停立即停止渲染同意弹窗，并清除 modal 状态；弹窗 cleanup 执行 close，恢复时不会自动重开，也不会保留弹窗内最终同意勾选。
3. Viewer 的有效 active 为 `open && !paused`，因此移动焦点/滚动锁 effect 执行 cleanup；父会话和 portal 容器仍同时隐藏旧内容。
4. generate/accept/save 的函数入口拒绝 paused；普通资格核验保留 FinancialSession 实例、本地逐项勾选与定位，不靠重挂会话恢复。
5. 父组件在隐藏区域焦点失去可用性时尝试转移至资格状态；明确 invalidated 时不再恢复旧焦点。
6. 桌面/移动切换改变 portal 目标，可能重建 **EvidenceViewer** 的阅读器局部状态并重新 GET 证据；不会重建财务确认会话或执行写操作。不能把“会话保留”扩张为“每个 PDF 子组件永不重挂”。

最新 journey 已加入以下两个真实浏览器场景，并在 `/tmp/findoc-ux-20261102-final/journey-results.json` 的 1/1 PASS 中通过；对应 `journey-proof.json` 标记均为 true：

- 已勾选最终同意的弹窗打开 → 只对 `financial-facts` 资格 GET 注入 503 → focus 触发重新核验 → 不留 modal、零新增 POST → 恢复 GET 后逐项勾选仍在，重新打开的同意勾选为空。
- 360px PDF 打开且滚动锁生效 → 同样仅对资格 GET 注入 503 → PDF 隐藏、滚动锁释放、零新增 POST → 恢复资格后可继续阅读 → 切回 1440px 解除移动滚动锁。

故障注入只控制资格 GET 的可用性，不伪造金额、PDF 或已接受事实。恢复允许重新显示阅读器，不允许自动接受、保存或继续研究。

## ReportEditor 保存前校验中止

`ReportEditor.save()` 在已有版本保存前持有 preflight AbortController；组件卸载会 abort。await 返回后先 `throwIfAborted()`，再检查 `alive` 与最新版本资格，在这些条件通过后才生成 operation ID、记入存储并 POST。

因此离开页面时尚未开始的写操作不会由迟到 preflight 继续发出。POST 开始后不伪称撤销，仍保留 operation 身份并执行验证读回；UNKNOWN 不会重新 POST。独立静态复查没有发现阻断性问题；报告最终 E2E 由 P1 执行，审查员随后读取其结果，确认报告套件 20/20 通过。

## 已读取的其他证据与待完成项

- 已读取 `/tmp/findoc-ux-20261102-qa-regression/journey-proof.json`：旧版 journey 的四 PDF、同页两次接受/两次保存/一次 resume、模拟 completed 结果、刷新零写入、同组勾选保留、保存响应丢失后 GET 恢复；`human_acceptances=0`、模型和索引为替身。该运行早于最新 paused 断言，不证明暂停修复已浏览器通过。
- 已读取 `/tmp/findoc-ux-20261102-live/proof.json`：实际 BGE/Milvus/模型的独立单次 QA 为 answered，provider attempts=1，重新读取后仍为 1，持久结果未变化；没有财务接受。它不是完整真人财务链，也不替代模型解释的人工语义审阅。
- 已独立读取主控最终产物 `/tmp/findoc-ux-20261102-final/{record.json,journey-results.json,reading-results.json,journey-proof.json}`：journey 1/1、reading/dashboard/QA 17/17；0 unexpected、0 skipped、0 flaky、errors 为空。`record.json` 为 exit_code=0、servers_stopped=true。最新 mobile GET503 滚动锁释放、modal 暂停同意重置、同组勾选保留、UNKNOWN 保存只读恢复、刷新零写入均为 true；准确写次数为 ACCEPT=2、SAVE=2、RESUME=1。运行仍是模拟接受、模型/索引替身、human_acceptances=0。
- 已独立读取 P1 最终产物 `/tmp/findoc-ux-20261102-report-final/{record.json,journey-results.json,reading-results.json}`：独立 seed journey 1/1、`report-polish.spec.ts` 与 `report-workspace.spec.ts` 合计 20/20，0 unexpected、0 skipped、0 flaky、errors 为空，exit_code=0，servers_stopped=true。仍为真实 PDF/HTTP/SQLite 与模拟接受/替身模型，不提升为生产或真人报告审核。
- 已独立读取 `/tmp/findoc-ux-20261102-invalidation-final/{record.json,journey-results.json,reading-results.json,embedded-invalidation-proof.json}`，并复查 `frontend/e2e/ux-simplification-invalidation.spec.ts`：独立 seed journey 1/1、实际来源纠错专项 1/1，0 unexpected/skipped/flaky、errors 为空、exit_code=0、服务停止。测试在真实原 PDF 尾部追加隔离注释，生成 **SHA 不同的派生测试文档**（不是原封不动的原始 PDF 字节），通过真实上传/解析/绑定纠错 API 执行；原 seed 来源 GET 前后完全相同。纠错后旧派生 PDF 请求返回 409、矩阵候选与 PDF/canvas 撤下、确认/保存/继续入口不可用、360px 滚动锁解除；没有额外浏览器写操作，task budget 不变。显式测试设置的绑定纠错 POST 本身不属于“额外浏览器写操作为零”的计数。全程仍为 simulated_test/替身模型与索引，human_acceptances=0。

未验证或不能从以上证据推出：真人逐项财务接受、五人可用性测试、生产完整研究与报告链、真实模型语义已经人工核准、生产部署/发布。最终测试若失败或跳过，应保留原记录并说明原因，不以静态代码或截图覆盖失败结果。
