# C+ 实际证据

M0基线见[evidence/M0-baseline.json](evidence/M0-baseline.json)：fetch SHA无漂移、原Cseed保留与独立备份校验、同一预算只读、工作包原文副本。现代码AST位置清单[evidence/M0-source-inventory.json](evidence/M0-source-inventory.json)。工作包verify_package实际PASS（35manifest文件/16features/42tasks）。此时C+业务尚未完成，不借用旧C CI作为新增验收。


M0冻结：Astra Ultra源129d8d4→集成3ae6b43，23离线PASS/1真实PDFdeselected，仅复用边界检查。root实读全文采纳八项合同修正，明确最小scope/score/cache/财务/报告版本/预算决定，见ADR及contracts；不是C+功能PASS。

D01源f413803→40ea97d：17实际外部请求，16HTTP200/robots404，最小间隔1.104848s；海尔A/H共享orgId不能混；600690中文全文245页/1,823,191bytes，SHA14186f9f9b47f687c527ba14825664f3b09e51759d581636cddcc248f26e3660，尚未入库READY。官方长期稳定/自动化授权未知，fallback保留。

B02源6ecb5ee→fc987a4：root在集成树独立启动14541/cplus.html，实际Chrome1440/1280/390八视图PASS、pageerror0/横溢出0；截图目视已看桌面。evidence/M0-ui/result.json是UI_MOCK，不是后端。root Node24 build/lint exit0，现有chunk/React提示保留。指标选择器暂只标签/曲线不变，正式业务重做真实DTO/数据映射。

B03：root从独立物化seed真实BGE/Milvus跑6题top5，evidence/M0-retrieval-before.json；无LLM，seed SHA不变。旧C真实结果的经营风险→物理70页委托理财表见M0-historical-risk-failure.json，此旧失败与本轮6题不同，不合并假称重现。三PDF实际SHA与三表标题候选页另存M0-statement-page-map.json，候选位置不是财务确认。

初次原包CSV CRLF触发diff whitespace告警，原字节保留并为immutable archive配置cr-at-eol；随后整baseline diff --check PASS。原包verify35files/16features/42tasks仍PASS，root42唯一任务及24题清单可读。M0付费call0、真人财务0、未动原Ccontroller14530/seed/ledger额度。


主控基础实现：tests/test_cplus_demo_namespace.py、test_cplus_retired_gc.py、test_cplus_shared_budget.py + existing demo_auth/demo_gateway/showcase_local_launcher/runtime_startup：25PASS/5SWIG warnings，3.96s；root改动ruffPASS。曾ruff发现root新test的unused import和同行semicolon，已修并复跑；没有把该失败写成通过。

experiments/cplus/gc_runtime_check.py实际OS+private HTTP synthetic fakechild三代PASS，evidence/M1-gc-runtime.json；无真实PDF/BGE/LLM/人签。清理仅新owned temp目录，原C14530/controller不动。新launcher--cplus --check与原.env/同一既有ledger只读准入PASS，20分钟/wait_only/14540，provider call0；模型配置只在backend，不印密钥。
