# Showcase 固定评测资料

题集是 15 条固定题的执行规范。当前最新真实执行为 **5 partial intent / 10 skipped / 完整层级 PASS 0**，不能报告质量通过率。原题目中的 not_run 为执行前模板；实际结果见 `docs/showcase/evidence/M4/bounded-eval/fixed-intent-eval.json`。案例覆盖提示注入、删除和预算故障时，必须使用独立隔离fixture，不污染真实seed。source_fixture是逻辑别名，执行者需映射为本代实际document_id/source_revision/content_sha256及会话scope，不能当作真实引用。四份目录仅美的/格力2024/2025；其导入、解析、事实资格分别核验。

每题先记录前置条件。程序契约和fake UI可验证请求形状、失败关闭、幂等；不能因此填入real_source_model、真实BGE或paired_real_model通过。controlled_race/fault需记录实际注入点、提交顺序/UNKNOWN和预算账本。真人财务确认必须由本人完成且保留独立回执，不能为跑题集自动生成local_operator。

推荐每次执行产出一份JSON：

```json
{
  "run_id": "唯一执行ID",
  "commit": "实际代码SHA",
  "runtime_instance_id": "服务端实例",
  "lease_generation": 0,
  "fixture_manifest_sha256": "实际映射清单hash",
  "cases_planned": 15,
  "results": [{
    "case_id": "E01-01",
    "status": "not_run",
    "evidence_tier_actual": "none",
    "mode": "quick",
    "job_ids": [],
    "source_refs": [],
    "invariants": [{"name": "引用精确匹配", "status": "not_run", "evidence_path": null}],
    "provider_attempts": null,
    "provider_outcome": "not_started",
    "tool_calls": null,
    "duration_ms": null,
    "cost_cny": null,
    "cost_status": "unknown",
    "failure_code": null,
    "limitations": []
  }]
}
```

结果状态使用 pass/fail/partial/unknown/skipped/not_run。只有证据层级满足题目要求且全部invariants通过，才是该层级pass；程序断言通过而真实模型未执行属于partial或not_run。UNKNOWN/失败不得排除出已尝试分母。报告固定15题覆盖率（满足层级的pass/15），并单列各层级尝试分母、pass/fail/partial/unknown/skipped/not_run数量；若报“已尝试通过率”，同时显示分母定义及排除项，不用它替代固定题覆盖率。配对题只有两臂都满足相同source/问题/事实/预算前提才可比，单臂失败仍保留。

模型费用由root预算proxy唯一执行与汇总，其他worker不调用付费API。本轮全局授权上限人民币5元不是单题额度。费用未知写null和unknown，不能当0；本地BGE、fake、GET也应记录实际0或无外部调用证据。调用次数按真实尝试计，UNKNOWN不退款；时延使用执行开始/结束，注明是否包括排队/用户等待。单/多比较列各自calls/tools/findings/source coverage/费用/时延/错误；coverage为实际核验的source identity数/冻结可用source数，不由findings数量推断。不能仅凭字数、角色数或一组样本宣布多Agent更优。

当前有 `frontend/e2e/showcase-eval-http.mjs` 的有限 intent 执行器，由 `experiments/showcase/integrated_http_check.py --flow eval` 启动隔离环境；付费配置仅主控统一提供，不在 README 自动运行。`eval/summarize_showcase_run.py` 只读已存 browser-result/research-progress JSON，绝不调用模型。单／双真实研究结果见 `docs/showcase/evidence/M5/browser-result.json`；它不替代固定题的完整层级验收。
