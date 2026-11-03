# S03 报告合同（2026-11-03）

分支 codex/showcase-s03 基于 2db02f8；保留 codex/showcase-m01。只新增 showcase_reports、测试及本交接/实验。主控 docs/showcase/handoffs/M3-agent.md 本分支不存在，已只读 4eab 的 reviews/M3-agent-handoff.md；尚未与未完成 Agent job 具体实现绑定。

## 冻结注入协议

`ShowcaseReportService(runtime_root: Path, *, workspace_id: str, verified_job_reader: VerifiedJobReader)`，独立 `showcase-reports.db`。`create_showcase_report_router(service)` 由主控装配与登记 gateway。

`async verified_job_reader(job_id: str) -> VerifiedJobSnapshot`，类型位于 `app/showcase_reports/models.py`。这是服务端受信适配器，绝不是 HTTP 客户端输入。必须只读、零模型调用，并校验当前身份/工作区/lease generation/job completed、来源归属和当前状态、已核准 financial refs 的资格与确定性财务文本。不可使用旧六事实 Task 拼装假 job。失败抛异常，报告历史显示 unavailable；不得自动启动模型。scope/lease/source 的授权必须由该 callback 与主控路由控制保证；报告模块不能独立证明外部数据库最终提交一致性。

DTO 必需字段：`job_id,workspace_id,state='completed',company_name,period_label,data_origin='live'|'seed'|'fake',findings`；默认 `schema_version='verified-report-job-v2'`，可选 `limitations:list[str]`。findings：`finding_id,kind,text,data_origin,source_status='current'|'stale'|'unavailable'`，`financial_refs:list[str]`（由适配器将服务端已核验引用投影为不可伪造的标识），`evidence_refs:list[dict]`（保留精确原文/来源身份；打印识别 document_id/source_revision/physical_page），`transcription_review_status,interpretation_review_status` 默认 unreviewed。kind 为 confirmed_financial/sourced_excerpt/model_interpretation/unresolved_question。前两类各自非空 refs；其真实性和数值不是靠此 shape 校验成立，必须 reader 验证。reader 在历史读取时返回相同 job finding identity 并重验 source_status，不改变已保存报告正文。

## HTTP

POST `/showcase-reports/drafts {operation_id,job_id}` 从 trusted reader 构建快照；POST `/showcase-reports {operation_id,draft_id,title,notes?}` 用户明确创建；POST `/{report_id}/revisions {operation_id,expected_revision,title,notes?}` 仅编辑标题备注、追加不可变 revision。HTTP extra fields forbid，不能上传 findings/金额/refs。GET 集合、GET `/{id}/revisions/{revision}`、GET 同路径 `/print` 均不调用模型。打印返回经过 HTML 转义的受控 HTML，固定同源 `/api/documents/{id}/file?source_revision=...#page=N`，离线需服务与权限。保存版本历史只读；当前来源状态另行显示，不自动更新结果。备注不是财务签核。主控需为所有入口提供 session/generation 授权；本模块没有独立登录系统。

## 验证与复跑

`.venv/bin/pytest -q tests/test_showcase_reports.py`：3 passed（版本CAS/幂等/不可变、HTTP禁客户端findings、HTML转义与历史来源无法复验）。Ruff新增文件通过。所有临时数据库和job是合成fixture，零LLM、无财务签核。

PDF：先运行 PDF skill 的 mark_artifact_operation_started create/count1/pdf；随后 `.venv/bin/python -m experiments.showcase.report_print_smoke` 生成 output/pdf/showcase-report-synthetic.html，再以 `NODE_PATH=<bundled node_modules> node experiments/showcase/report_print_smoke.cjs` 实际 page.pdf。bundled Playwright默认浏览器版本缺失，首次失败已保留此记录；改为已安装 Google Chrome executablePath 后成功，环境可用 REPORT_CHROME 覆盖路径。没有下载浏览器。最终5页A4，PyMuPDF渲染后逐页视觉检查：中文、页脚、引用、分页可读，无重叠截断；提取检查每页模拟声明和文本边界，PDF内5条同源引用链接。样本为明显标注fake的模拟企业/合成引用，非真实LLM结果，链接目标没有真实附件，不能当真实引用访问验收。

真实源/Agent DTO适配、session/generation接线、最终发布时跨库来源栅栏、真实AI报告与真实引用跳转均由主控另验。报告draft创建与来源变化可能并发：本模块只保存reader已验证快照，不声称跨库原子发布；历史读取重新调用零模型reader显示当前来源状态。版本创建仅title/notes改变，其余内容冻结。未push、部署或改其他worker文件。
