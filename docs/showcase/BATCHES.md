# 36任务批次与恢复策略

单一状态：STATE.md；实时36项：task-board.csv；实际会话/模型：orchestration.json。planned列不代表已调用。

| 批次 | 任务与依赖 | owner / 文件范围 | 测试预算与风险 |
|---|---|---|---|
| 0 M0 | B00→B01→B02；架构读审与UI原型并行准备，合同审定后验收 | 主控文档/合同；Astra独立review；Terra仅src/showcase与独立entry | 真实启动spike、两tokens三宽度截图、CTA和build；不冒充后端 |
| 1 M1三线 | L01→L02→L03→L04；H01→H02→H03；U01依赖H02 | Sol app/demo+tests；Dashboard app/dashboard单独owner；Terra UI新组件，主控AppShell/ResearchHome/runtime接线 | 每模块smoke，双浏览器实际HTTP、旧generation迟到、reset失败关闭；≤15min窄回归 |
| 2 M2三线 | D01→D02→D03；O01→O02→O03；F01→F02→F03 | Document/OCR共享DocumentService由主控统一接入；其他新模块各独占；三条实质线最多 | 2公司官方源证据、真实OCR页/表、2新增指标来源，财务真人未审不阻塞其余 |
| 3 M3三线 | C01→C02；F01+B02→S01→S02→S03；C01/S01→A01→A02→A03；M01→M02 | C/S/A同Agent owner阶段接力避免Graph竞争；Memory独立；Report/Trace UI接力 | 10–20 intent固定题；单/多真实例子和调用预算；跨会话语义删除；实际版本PDF |
| 4 M4 | E01(D03/O03/S02)→E02(A02/M02)；E03(E01/L03)→G01(E02/E03/A03/S03/F03) | QA/seed独立；主控集成；必要独立Astra复核 | 3面试路线、关键旧回归、来源/Decimal/报告；不以数量替代功能 |
| 5 M5 | G02真人走查→G03交付 | 主控/UX/QA；真人状态human_pending | P0清零、截图/录屏、README/限制；无main合并/公开部署 |

每个子任务从最近已集成精确SHA建独立codex/showcase-<task>工作树；完成含owner/独立commit/检查与失败、证据等级。不得在一个未交割任务中悄悄改热点；同一owner任务可串行接力，每项独立提交。保留原PDF/私有集/V1.2分支。

最多3条实质开发线，必要第4条只在文件owner完全分离；读审不扩大为业务开发。阶段变化由主控set_thread_title改当前任务名，再send_message指定实际模型/推理，不修改用户全局默认。

中断恢复：读取STATE/CSV/orchestration→git status/worktree/rev-parse核对→wait_threads(cursor)读取活会话→审查已提交SHA→依赖满足才派工。不得把旧工作树测试转移到新SHA或依赖。主控不承诺无人服务数天。

恢复：代码revert独立提交；新隔离runtime generation/保留失败目录证据；不删/覆盖真实库、不修改已应用迁移。官方源/OCR/model失败记录blocked_external但继续独立任务。

费用：未购买外部服务。调度按账户实际用量，无价格证据不编造金额。应用真实LLM只固定精选案例，默认先替身验证合同，真实证据另记；不擅自大量请求。
