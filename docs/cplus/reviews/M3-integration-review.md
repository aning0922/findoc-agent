# M3 root assembly 独立审查

固定提交 **ee836e6**，分支codex/cplus-m3-integration-review。仅写本文与独立回归测试，未改业务或root热点。审查对象是本人未写的root装配、证据定位、segments路由及正式前端接线；peer/batch/checkup仅检查其被root注入的合同，不对本人算法作自我验收。未读私有配置/真实账本/原开发库，provider物理调用0。

结论：**未复现P0；发现4项可复现P1，固定基线的M3装配尚不能整体通过。** Root已有21条实际两Chromium/PDF/Vision/BGE断言及36fakePASS/3skip属于独立既有证据，本审查不改写其结果，也不以它们覆盖下列负向路径。检查规模与性能不是本轮阻断点。

## P1-1：root memory读栅栏内再次使用写事务检查代际，peer/checkup会自锁

定位：`app/cplus/runtime.py:79–84`取得原ResearchMemoryService的SHARED publication_guard；同文件`:227–229`与`:245–247`把同一原memory注入peer/checkup。`app/research_memory/service.py:104–106`的check_generation使用`:84–89`的BEGIN IMMEDIATE事务。

复现：用真实root register_cplus_runtime装配临时生成PDF/fake OCR/SQLite，进入app.state.cplus_publication_guard(identity, context)后调用实际app.state.cplus_peer_service.memory.check_generation(context.memory_generation)。check取得写事务，在COMMIT请求EXCLUSIVE时被当前外层SHARED读锁阻挡，抛sqlite3.OperationalError: database is locked；生产默认timeout5秒，测试缩至30ms。结果是已具备候选的比较/解释也会503，之前nullcontext叶子测试覆盖不到。

测试：`test_root_peer_nested_memory_generation_check_is_read_only`。Root本轮已报告相同真实HTTP失败并正在引入C+-only MemoryView；本审查固定ee836e6未包含该补丁，不能宣称补丁通过。建议只把嵌套check_generation改成readonly BEGIN/SELECT/rollback，原memory.publication_guard仍负责跨COMMIT阻写，并保持workspace/expected generation精确比较；修复后用本root装配测试去掉xfail复跑。StatementService(source=True)本身是BEGIN读事务，不能把此问题泛化成所有SQLite嵌套读都不可用。

## P1-2：正式fast引文的“收藏这条证据”始终提交不合法字段

定位：`frontend/src/product/cplus/research/DocumentResearchPanel.tsx:76–79`，不分fast/ocr都发送physical_page，fast时artifact_id=null。既有Memory合同`app/research_memory/service.py:167–179`明确无artifact时禁止physical_page/source_line_index。

复现：用真实临时SourceService READY PDF/evidence与真实memory router提交与UI一致的saved_evidence body（fast evidence_id、artifact_id:null、physical_page:1）→422 invalid_source_reference；同一合法引用仅将physical_page置null→200。这证明接口接合错误，不是缺来源/权限。UI随后留下UNKNOWN提示，用户要额外GET404/放弃线索才能恢复正常操作。

测试：`test_root_fast_favorite_payload_is_accepted`。建议UI按ref.kind构造body：fast只传真实evidence_id及必要source identity；OCR才传artifact/page/line。不要为了迁就UI放松backend的引用资格检查。

## P1-3：OCR active替换后新执行正确拒绝，但历史GET/恢复仍返回“current”且无历史标记

定位：`app/cplus/runtime.py:134–138`执行guard严格校验active artifact；root注册的`app/retrieval_v2/api.py:94–111`却直接返回已存read，`app/retrieval_v2/service.py:371–393`没有当前状态投影。`DocumentResearchPanel.tsx:64–65,91–93`恢复后直接展示保存的answer，不展示artifact已失效/历史。

复现：真实root HTTP路由完成fake OCR enrollment→build→context→无provider answer；同一owner/固定expiry重复GET200，过期身份GET403。再明确生成新artifact使active切换：用旧context POST answer→409 artifact_changed（这是正确行为）；GET旧answer仍200，findings.source_status仍为current，historical_snapshot和current_source_status均缺失。GET没有新增operations，也没发模型，但当前来源资格的呈现与执行gate不一致。

测试：`test_root_ocr_history_exposes_current_status_after_artifact_replaced`。建议root在answer/operation的读取adapter上增加“获准读取后的历史/当前源状态”投影及UI显示，不重写immutable原快照，也不把旧state=completed当当前资格；授权失败仍应拒绝，不能降级成历史可读。原文定位因active失效拒绝是安全行为，不要求绕过它。

## P1-4：图表选择的实际财务期间在进入研究助手时丢失

定位：`frontend/src/product/cplus/profile/CPlusCompany360.tsx:32`发出draft含metricKey、point.time及source revision；`CPlusCompanyEntry.tsx:20`将其存入sessionStorage；`DocumentResearchPanel.tsx:35–37,69,89–90`只消费doc/revision与URL泛化question，创建context和answer都不携带point.time。模板双源的doc/revision在该路径会保留，不应把问题表述成全部scope丢失。

实际React复现：构造与chart点击相同的draft，选的是2025年报中的2024-01-01至2024-12-31营业收入点；加载真实DocumentResearchPanel组件（API仅mock），点击读取身份→固定范围→提交研究。抓取两次POST：文档及revision保留，但context和answer body都完全没有2024期间；问题只剩“请结合所选年报原文，说明营业收入的相关披露。”。系统无法区分用户点击的2024比较列与同报告的2025本期列。

复现脚本：`tests/cplus_m3_draft_review.cjs`；公开合成请求抓取`/tmp/cplus-m3-draft-review.json`。建议增加server-resolved point/cell+period reference到typedcontext，或至少在用户可核查草稿中明确财务期间并通过服务端引用恢复；不能把浏览器value_decimal直接提升成核准金额。修复应从2025报告里点击2024比较点验证，不能只测报告年度等于财务年度的样例。

## 正向检查及未覆盖范围

- 实际root guard，临时真实SQLite：在inner cplus-research事务提交钩子中分别启动独立writer更新documents公司行、parse active行、memory generation；三者均被SHARED锁阻挡，证明这些读锁保持到内库COMMIT。此测试不等于全部parent/receipt竞态已穷尽。
- root evidence location接上真实typed verifier：把已存OCR引文测试投影的尾部追加不存在文字，GET location返回409 exact_evidence_unverified；未出现只验证前缀却接受完整伪造引文。没有编辑真实业务记录。
- 同owner/固定expiry的HTTP恢复成功，过期读取403。首次测试因将小写已有header与大写替换header合并导致重复header而未正确覆盖expiry；纠正测试为相同小写key后验证403。该测试脚本失误不列为root鉴权缺陷。
- `runtime_factory.py:238–250`代码确认C+启用且模型非disabled时要求既有预算路径，经existing_shared_budget验证后包BudgetedSDK；root BoundedSDK继续包同一个llm_client.client，没有看到root另建无预算SDK。仅代码检查，没有打开账本或执行真实provider。
- `runtime.py:148–149`在documents读事务内检查linked parent；`segments.py:26–31`在源guard内执行statement公司快照核验和提交前validate。未运行真实parent删除/UI并发全集，未把静态路径阅读写成全面竞态PASS。peer/batch/checkup算法正确性不在本独立root审查结论内。

## 执行记录与复跑

```
.venv/bin/pytest -q -rx tests/test_cplus_m3_integration_review.py
# 1 passed, 3 xfailed, 5既有Swig warnings
.venv/bin/pytest -q --runxfail tests/test_cplus_m3_integration_review.py
# 3 failed, 1 passed：三个失败分别落到缺历史字段、fast收藏422、memory自锁；这是保留的缺陷，不是验收PASS
node tests/cplus_m3_draft_review.cjs
# UI_MOCK实际React复现period丢失，0真实API/provider
```

Python测试使用新temp下生成PDF、fake OCR和真实SQLite+root路由，没有读取seed/原开发库。JS脚本自启loopback Vite、禁envDir、拦截全部/api、结束只关闭自身browser/Vite；不是已登录真实产品验收。`/tmp/cplus-m3-review-failures.log`保留原失败输出。测试中strict xfail是已知缺陷标记，修复后应移除而非放宽断言。Ruff检查独立Python测试通过。未启动新agent/线程、未push/部署或更改业务实现。

### Root后续进展（固定基线之后，未纳入本轮代码复验）

Root已报告正在/已经新增C+-only readonly MemoryView，并为GET context/answer增加current_source_status/historical_snapshot投影；另补中文查询的有界主题词与trigram。上述均发生于ee836e6之后，本报告保留基线复现，待对修复提交去掉xfail重验后再关闭P1-1/P1-3，不把“已报告修复”写成独立验收通过。

Root另报告真实provider首轮三次物理调用UNKNOWN、未看到usage，正在执行单次有界诊断并保留5元cap。此为root执行记录，审查者未读取账本/凭证或调用模型。UNKNOWN只能说明响应/费用证据未完整取得，根因尚未在此独立判定；不能直接归于本报告四项装配缺陷，也不能据此断言供应商故障。不得自动重试、退款预留或补写真实模型PASS。
