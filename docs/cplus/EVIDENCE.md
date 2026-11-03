# C+ 实际证据

## 当前追加证据（优先于后文历史检查点）

- `M5-followup/provider-one-answer.json`、`three-business-explanations.json`、`annual-after-projection-fix.json`：新的真实来源问答、体检三规则解释、OCR待审解读、双年三主题解释。先前输入超预算失败及FTS五来源超过四上限的脚本失败均保留；修复后只用新操作，旧4 UNKNOWN不重放。
- `../eval/results/agent-paths-real-v2/result.json`：E01-06 deep evidence/risk_operations与E01-01 synthesis generalist，不同题，共11实际SDK调用。后者现金流检索不足如实保留。
- `../eval/results/agent-paired-e0115-v1/result.json`：最初同题实验因脚本写死角色在两次成功准备后停止，未派发job。`agent-paired-e0115-continued-v1/result.json`使用原有效会话与已保存成功plan继续，deep evidence/finance及synthesis generalist同题同源完成，再新增9次调用，总11；finance没有已核准输入，明确证据不足。原始断言失败未覆盖。
- `M5-followup/batch-pure-controls.json`：真实Chrome异步ack、运行中取消仅queued三格、当前代单个公开PDF暂不可读→1UNKNOWN+3完成、恢复原字节、GET不重放和历史可发现10检查PASS，纯工具provider0。
- `M5-followup/profile-native.json`与截图：真实两年候选、五KPI及Decimal比率、体检来源/公式/期间/下一问、不足状态和三宽。未知basis未有真实样本，不由合成单测替代。
- 最新隔离checks环境 `pytest -q tests/test_cplus_*.py`：114 PASS/3 SKIP/5 SWIG warnings。3个真实PDF opt-in没有在此命令设置，真实PDF/浏览器证据单列。依赖安装到独立ignored检查环境，原模型环境未sync。
- 当前ledger103 physical/保守预留1.976784元/原5元cap/旧UNKNOWN4/实际账单未观察（这是四模板新AI前的检查点，最终以更新后的STATE为准）。所有AI仍未人类语义接受，人工财务确认0。


M0基线见[evidence/M0-baseline.json](evidence/M0-baseline.json)：fetch SHA无漂移、原Cseed保留与独立备份校验、同一预算只读、工作包原文副本。现代码AST位置清单[evidence/M0-source-inventory.json](evidence/M0-source-inventory.json)。工作包verify_package实际PASS（35manifest文件/16features/42tasks）。此时C+业务尚未完成，不借用旧C CI作为新增验收。


M0冻结：Astra Ultra源129d8d4→集成3ae6b43，23离线PASS/1真实PDFdeselected，仅复用边界检查。root实读全文采纳八项合同修正，明确最小scope/score/cache/财务/报告版本/预算决定，见ADR及contracts；不是C+功能PASS。

D01源f413803→40ea97d：17实际外部请求，16HTTP200/robots404，最小间隔1.104848s；海尔A/H共享orgId不能混；600690中文全文245页/1,823,191bytes，SHA14186f9f9b47f687c527ba14825664f3b09e51759d581636cddcc248f26e3660，尚未入库READY。官方长期稳定/自动化授权未知，fallback保留。

B02源6ecb5ee→fc987a4：root在集成树独立启动14541/cplus.html，实际Chrome1440/1280/390八视图PASS、pageerror0/横溢出0；截图目视已看桌面。evidence/M0-ui/result.json是UI_MOCK，不是后端。root Node24 build/lint exit0，现有chunk/React提示保留。指标选择器暂只标签/曲线不变，正式业务重做真实DTO/数据映射。

B03：root从独立物化seed真实BGE/Milvus跑6题top5，evidence/M0-retrieval-before.json；无LLM，seed SHA不变。旧C真实结果的经营风险→物理70页委托理财表见M0-historical-risk-failure.json，此旧失败与本轮6题不同，不合并假称重现。三PDF实际SHA与三表标题候选页另存M0-statement-page-map.json，候选位置不是财务确认。

初次原包CSV CRLF触发diff whitespace告警，原字节保留并为immutable archive配置cr-at-eol；随后整baseline diff --check PASS。原包verify35files/16features/42tasks仍PASS，root42唯一任务及24题清单可读。M0付费call0、真人财务0、未动原Ccontroller14530/seed/ledger额度。


主控基础实现：tests/test_cplus_demo_namespace.py、test_cplus_retired_gc.py、test_cplus_shared_budget.py + existing demo_auth/demo_gateway/showcase_local_launcher/runtime_startup：25PASS/5SWIG warnings，3.96s；root改动ruffPASS。曾ruff发现root新test的unused import和同行semicolon，已修并复跑；没有把该失败写成通过。

experiments/cplus/gc_runtime_check.py实际OS+private HTTP synthetic fakechild三代PASS，evidence/M1-gc-runtime.json；无真实PDF/BGE/LLM/人签。清理仅新owned temp目录，原C14530/controller不动。新launcher--cplus --check与原.env/同一既有ledger只读准入PASS，20分钟/wait_only/14540，provider call0；模型配置只在backend，不印密钥。


## M1 root assembly / real HTTP

- Actual proof: `evidence/M1-official-import.json`; official Haier 2025 PDF245pages SHA14186f9f…: cold download then new-generation cache_hit true, current generation READY/source200/metadata200, GET operation recovery and logout. Real HTTP/PDF/BGE/Milvus; provider0/human0.
- Failure retained: initial script KeyError receipt after completed import; no original operation replay. Launcher restart409 resetting; no accepted operation; fixed read-only startup-status wait. Initial lazy FastAPI `_IncludedRouter.app` assembly failure corrected by final ASGI middleware, 2 boundary fake tests pass.
- Corrected selected suite: 10PASS/1SKIP, realPDFopt-in unset. Mistyped file path invocation exit4/0tests retained. Ruff PASS; Node24 build PASS with chunk warning.
- Independent AstraHigh review432824f: two P1 journal/COMMIT timing windows reproduced; assigned fixes. Real source/memory/parse/parent cross-store root guard still under review.


## M1/M2 native main path

`evidence/M1-M2-native/result.json`: 21 PASS assertions, two independent real Chromium processes with actual local HTTP/PDF/BGE/Milvus/Vision. Real UI extracted Gree two years 38 candidate cells each, generated real candidate trend, checked1440/1280/390. This generation reran Vision (68lines), legacy scan remainsFAILED; explicit OCR enrollment/build/context/answer (provider disabled) returned cited OCR lines, actual normalized bbox highlighted original PDF render, saved evidence memory. BrowserB423 conflict/remaining time, separateowner password+confirmation, generation16→17, oldbrowser actualHTTP401, new financialcollections0, logout. No financial human confirmation/provider call.

Four failed runs retained: selector accessible-name mismatch; literal question noOCRhit correctly insufficient; chartgroup label changed during integration; test omitted required re-entry of shared password so takeover remaineddisabled. Corrected run PASS, not hiding failures. Root visually inspected1440home/company360; Hero contrast and compact KPIs fixed; 390 screenshots retained.

After assembly changes: C+ suite36PASS/3SKIP (opt-inPDF tests); separate explicit realpublicseed Midea extractor1PASS proving original Gree2024/2025 payload equality. New generatedPDF highlight/fallback/expiredreader3PASS. Node24 buildPASS; lint exit0 warnings, Swig/chunk warnings retained.


## M3 controlled execution

- `evidence/M3-http/result.json`: first actualpaid-path matrix PARTIAL, generic503 failures and 3newUNKNOWN preserved. `diagnostic.json`: one additional12sec bounded SDK ReadTimeout with safe cause chain; no response/usage observed. Samecap5/77calls/1.441018 reserved/4UNKNOWN; billednotobserved.
- `corrected-no-provider.json`:19actualHTTP executionsPASS with realPDF/BGE/Milvus and rootreadonlymemoryadapter; all5 explanation/answer paths explicitly unconfigured, provider successes0. NaturalOCRquestion retrieved afterboundedFTS terms fix. Not a modelacceptance score. Full raw proof retainedignored with SHA in summary.
- Independentbd67e29 baseline review1PASS/3XFAIL, --runxfail3FAIL/1PASS retainedreport. Afterrootpatch review rerun3PASS/1FAIL because originalfastfavorite test hardcoded malformedfield; contracttest updated to require422for malformed and200corrected, then targeted8PASS inclmemoryview. Rootsource/parse/memory lock plus forgedquote-tail tests continuepassing. Comparative financialFocus typedserverlookup1PASS verifies report2031 point2030 and rejectsperiod/value/source tamper.


## M4 real saved candidate artifacts

`M4-native-exports/result.json` actual11checks, trueReact+gateway+twoactualPDFfinancialcandidates→5metricpeer snapshot→3formats downloads+printedPDF, allsameexplicitref/SHA. CSV exact391371999819.49. Independent86aaca4 confirms textprecision/formulafree/sourcepages/PPTX6renderedpages; provider0/human0. PubliccandidateCSV/XLSX/PPTX committed as deliverables; 21-page initialPDF remainsignoredproof and rootcompactprint adjustment awaitsfreshmeasurement. ActualPDF/sourcebinary/DB/seed/config remainignored.

AllC+current52PASS/3SKIP; standalonefullPDF testsalreadyseparatelyran (Midea1PASS) notmisreportedSKIPaspass. OriginalCcheckoutclean45d55d7. Rootverifiedoriginalv1/newv2/newv3filechecksums+SQLite; rootreadonlyv3candidatefirstscreen remainsassemblycandidateuntilnativeflow.

## M5 final integration evidence

- Cache query-identity defect independently reproduced and fixd7b4160; actual Chrome pinyin cold import/READY then newgeneration codequery cache_hit=true/READY to360, V3seed5READY/source-bound5series restored, earlier37/38ownedgenerations removed after OSexit; originalCmanifest unchanged. Evidence `evidence/M5-official-reset`.
- Actualpoint2025report/2024period -> explicitFTS/context -> fastquote favorite -> newcontext/BGE recall -> UIdelete and absence:8PASS, `evidence/M5-point-memory`.
- Root actualChrome C annual3topics/segmentsdonut/approvedfourcellmatrix5PASS; D two actualtemplate two-source toolfindings+no fabricatedAI/home3width7PASS. `evidence/M5-interview`. Initial selector/wait mistakes retained `M5-script-attempts`; no originalUNKNOWN replay.
- Worker realOS/socketHTTP fullbatch119.413s200/fourcellscompleted/GETno dispatch/34sourceexactquotes, old260sUNKNOWN retained. Pure tools, no paidMultiAgent. `eval/results/batch-v3-fixed` and reviewM5-batch-handoff.
- Actualtwo-year Gree collections+5metrics×2points+threecheckuprules+360/table1440/1280/39011PASS; full-page mobile capture artifacts supplemented with actualviewport390 screenshots. `evidence/M5-finance`.
- NewAstra P1: savedexport ignoredparentdisplayrevocation; root47e5d23 readerrevalidatesexactdomainversion readpermission, controlledHTTP403/regrant samebytes+ETag/opsunchanged, independent49330cf close. Native3formatdownload/print3width11PASSafterfix `M5-export-permission-native`. NewconcisePDFactual2pages inspected bothrenderedPNGs; former21page artifact preserved.
- FinalcommandselectedC+ +demo/runtime/launcher90PASS/3SKIP/5SWIGwarnings(20.49s), 3SKIPopt-inrealPDFnotset; Node24 build/lint exit0 butlargechunk/React-hookswarnings retained(40warninglineslatestlog). No modelaccuracy/humanacceptance inferred.
- Raw real-browser recordings3localwebm, exactbytes/SHA in `recordings.json`, 5–10minute pacedhuman guide `INTERVIEW_DEMOS.md`. Rawprivate/runtime/seeds remainGitignored; PDFs/examples here are publiccandidate artifacts, nofinancialsigning.
- Samecanonical77physicalcalls/1.441018reservedcap5/UNKNOWN4/actualbillnot_observed unchanged acrossgenerations. C+newrealLLMsuccess0, providerdiagnosticsstopped; finalrepair/rules/retrieval/export0provider.

## 最终候选追加（123-call检查点）

- `eval/results/template-numeric-policy-real-v1`：真正一次新SDK、non_numeric_review_v1解释实际returned且published，AI仍待审；同版10候选点/3规则/趋势/三格式和浏览器PDF。旧年份错配未覆盖，已知缺口Astra独立f657917闭合。
- `evidence/M5-followup/business-native-corrected.json`及`examples/manifest.json`：真实精确服务端ref/SHA；四示例文件可直接查看，CSV属性-text防Git换行变动。6页PPTX全部查看；6页浏览器PDF首末查看、全文无input_refs，不称全页目视通过。
- 同图点`point-memory-final.json`原生9检查PASS，location_mode=page_only/物理页7/零矩形，真实明确回退，不写成exactquads；收藏→新context→BGE召回→删除→不命中。CP24加入13required-tier executed，13不是准确答案数。
- 最终选择性后端命令 `PYTHONPATH=. FINDOC_EXPORT_PYTHON=<isolated-checks-python> <isolated-checks-python> -m pytest -q tests/test_cplus_*.py tests/test_showcase_local_launcher.py tests/test_demo*.py tests/test_runtime_startup.py`：155PASS/3SKIP/5warnings，48.49s。3opt-in真实PDF未设置，真实PDF/OCR/LLM/native另列。C+ env build exit0，大chunk warning保留。
- 原全局5元ledger123 physical guarded rows/保守预留2.468274元/原UNKNOWN4/账单未观察；新修正窗口1row returned，logout200/旧session401/controllerready。原seed manifest重验相同，原C tracked tree clean45d55d7，main/V1.2未改。
- readonly scoped child gate不允许把模板内部原answer作为独立report导出，raw answer仍可审阅；父模板仍可列出。初次新fixture缺无关legacy report state导致失败、补齐后9/9受控边界通过，失败不称应用真实权限失败。
