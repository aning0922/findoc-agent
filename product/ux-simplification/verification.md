# UX 简化改造交付与验收

日期：2026-11-02。工程实现与本轮自动化验收完成；真人财务核准、五人可用性测试和完整生产业务验收仍待人工完成。

## 实现结果

- 首页保留开始、待办、最近完成三个区域；五导航为首页、研究任务、企业与年报、年报问答、我的报告。企业筛选位于任务列表，顶部不再隐式改写研究范围。
- 新建研究按目标、准备年报、准备核对组织，资料缺失可原位上传。来源仍需明确采用；多披露版本不替用户猜测。
- 六项数据用三指标×两期/两企业矩阵展示。只读候选明确标为待核对，不进入计算；已保存数据须通过原有资格验证。桌面左侧矩阵与核对、右侧真实 PDF 同屏，移动端使用原文抽屉。
- 原位复用候选审阅、逐项勾选、明确接受、保存及只读恢复。保持 ACCEPT、SAVE、RESUME 分别显式操作；不是一键事务，也不在刷新或效果函数中自动继续。当前来源、财务年度、报告年度、原单位和会计口径仍可核验。
- 问答突出原文回答与证据，右侧原生模态 PDF 抽屉关闭后恢复焦点和滚动；不重写服务端 verified_excerpts 为未经校验的新答案。
- 报告库直出，列表与阅读分离；版本、指定版本导出、编辑为新版本集中呈现。旧版本只读、不可变历史和来源失效阻断保留。
- 修复报告保存前 GET 未完成时离开仍可能继续 POST 的所有权问题；已提交后的未知身份继续保留查证。
- 修复核验暂停时隐藏原生 modal 仍锁住页面以及移动 PDF 滚动锁残留的问题。暂停撤销本次同意、解除弹窗和滚动锁，恢复不自动同意或写入。

## 基线与提交

正式来源为 findoc-agent/main@cdbd081，本机和远端 HEAD 已核验。聊天初始目录 findoc-v1-product-design 是旧历史分支，未在其上修改。

工作区：`findoc-ux-implementation`；分支：`codex/ux-simplification-20261102`。

- `f032e69`：迁移映射、边界和分工计划。
- `902c523`：P0 首页/导航/原位六项核对与真实 PDF。
- `ae8ff91`：P1 问答/报告阅读、精确版本与保存导航保护。
- 后续验收提交：独立边界运行器、真实 QA smoke 运行器、失效专项与本记录。

原型里的金额、假 PDF、演示状态没有导入产品代码。未改后端 API 合同，未覆盖原数据库、原始 PDF 或历史验收快照。所有提交仅在本地独立分支，未推送或发布。

## 验收结果

| 检查 | 本轮结果 | 证据范围 |
| --- | --- | --- |
| 前端单测 | 184 PASS、25 SKIP、0 FAIL | 跳过项如实保留；独立审查22项包含在这些检查中，不重复相加 |
| lint / TypeScript / build | 通过 | lint有一处原有D14测试Fast Refresh警告；构建有大chunk提示 |
| 后端相关契约 | 161 PASS | 审阅、事实保存、任务、研究、报告草稿与不可变报告 |
| 新同页完整旅程 | 1 PASS | 四真实PDF上传、六项原位核对、明确接受/保存/继续、刷新0POST；同组勾选、SAVE丢响应、暂停modal与移动滚动锁 |
| 问答/首页/新增阅读 | 17 PASS | 原文及年度/单位、实际PDF身份、七宽度、来源失效、unknown查证、报告版本及保存前离开0POST |
| 报告既有回归 | 20 PASS | 精确v1字节SHA、历史不可变、脏编辑/Back守卫、对比、七宽度、八类导出拒绝、真实绑定纠错 |
| 独立财务边界 | 18 PASS | 四真实PDF、接受/保存响应丢失、GET损坏、409、双击、迟到、冲突、纠错 |
| 内嵌真实来源纠错 | 1 PASS | 独立派生PDF实际纠错后旧PDF409、候选撤下、写入口阻断、移动解锁、预算不变、原seed不变 |
| 实际检索与模型 | 1次QA answered | 实际BGE、Milvus、1次供应商调用；两次GET结果一致且调用数仍为1 |
| 实际运行前端 | 只读查看与刷新通过 | 正式main入口读取上述真实QA；0POST、0页面错误，无测试入口替换 |

浏览器共57个不同用例通过；多个隔离套件重跑了同一个种子旅程，该重复种子不重复计数。最终浏览器没有skip、flaky或retry。

独立来源纠错文档是原始真实PDF尾部追加隔离测试注释的副本，原始与派生SHA均记录；它不冒充原始字节不变。自动化财务接受全部标为 simulated_test，模型和索引在浏览器套件中为替身；真实模型证据是独立的一次QA，不扩大为真人完成全部经营研究的证据。

## 失败记录与修正

保留了早期运行，没有用最后一次PASS覆盖历史：

1. 初轮新建测试未同步明确采用来源步骤；更新正确用户路径后通过。
2. 首页筛选器与portal canvas、问答两个summary、同名历史问题，以及报告小屏目录/封面范围的旧测试定位不精确；改为正确控件或精确run身份，未放宽身份、金额、不可变和零写断言。
3. 一次独立测试启动用了Node20，不能直接加载.ts；改为项目要求Node24后22项通过。
4. 直接运行报告后端测试缺少历史proof，随后误用已有报告的seed导致预期空库计数失败。未更改产品或测试断言：运行器改为旅程完成、报告生成前通过SQLite backup取得一致的干净seed，最终57项报告契约通过。尝试清理副本的报告行被不可变数据库触发器拒绝，未绕过触发器；该副本未用于通过验收。
5. 静态独立检查发现隐藏modal/滚动锁问题，修复paused传播并新增实际503故障注入验证，同意状态不得恢复成自动授权。

原始记录在本工作区 `data/ux-simplification-20261102/`，较早运行保存在其 `prior-runs/`。独立财务证据位于 `data/ux-financial-boundary-20261102/`；真实前端证据位于 `data/ux-preview-20261102/`。这些本地资料被Git忽略，未作为公开发布资产。

## 复现与本地查看

Node24在PATH且Python依赖就绪时，四份PDF须与 `product/validation/sources.json` 的SHA一致：

```bash
python scripts/run_ux_simplification.py --out /tmp/findoc-ux-new-run
python scripts/run_ux_simplification.py --out /tmp/findoc-ux-new-qa --extra qa-workspace.spec.ts
python scripts/run_ux_simplification.py --out /tmp/findoc-ux-new-reports --extra report-polish.spec.ts report-workspace.spec.ts
python scripts/run_ux_simplification.py --out /tmp/findoc-ux-new-invalidation --extra ux-simplification-invalidation.spec.ts
python frontend/scripts/run-financial-boundary-e2e.py
```

真实QA可用 `scripts/validate_ux_live.py --out <新目录> --env-file <模型配置> --source-root <PDF根目录>` 复现；它限制一次供应商调用，不产生任何财务接受。凭据不会写入验收材料。

本次本地入口为 http://127.0.0.1:14288 ，后端为127.0.0.1:18088。使用本轮新建的真实QA数据目录，已导入一份真实年报和保存一次真实问答；没有代替用户确认财务数据。进程和数据位置记录于 `data/ux-preview-20261102/preview.json`。重启机器后需重新启动服务。

## 仍须人工完成的范围

- 真人对六项财务事实逐项核准及完整真实模型经营研究验收。
- 附件建议的五名新用户任务测试、完整键盘/辅助技术可访问性审计。
- 上述是正式业务/可用性验收，不能由自动模拟接受、局部键盘断言或单次真实QA替代。
