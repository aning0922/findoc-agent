# A07 有限工具批量研究

分支codex/cplus-peer-batch；依赖peer commit中的Store、现hybrid/annual模块。BatchResearchService(runtime_root, *, identity_validator, publication_guard, commit_check, prepare_cell, validate_prepared, execute_cell)。create_batch_router(service,identity_provider)由root注册，不改runtime。

API：POST /cplus/batch-plans {operation_id,cells:[{cell_key,company_id,template,sources:[SourceRef]}],preparation_confirmed:true}；GET /cplus/batch-plans/{id}；POST /cplus/batches {operation_id,batch_plan_id,batch_plan_revision,batch_plan_sha256,confirmed:true}；GET /cplus/batches/{id}；POST /cplus/batches/{id}/cancel {operation_id,expected_revision}；GET /cplus/batch-operations/{op}。新增GET待root登记policy。所有mutation返回operation_id/state/result，start在操作unknown时即持久batch_id供GET恢复。GET绝不dispatch。

MVP是**纯工具矩阵**，不是已实现的付费multi-Agent批次：最多12格/3公司、默认串行1，提供risk_excerpt（经营风险原文检索）与annual_changes（双年3主题原文对比）两个冻结模板。root可实例化ExistingToolAdapter(hybrid=...,annual_diff=...)并将其prepare_cell/validate_prepared/execute_cell分别注入。prepare只校验实际来源、捕获source hash与memory generation，不写业务、不调用模型；execute在明确批准后复用hybrid.mutate('search')与annual.create(generate_explanation=False)，保存下游真实operation返回，不造showcase job。任何未来付费意图/plan/job模板必须另按冻结ADR保存真实child plan triples和共享guard，不能靠本纯工具plan授权模型。

plan snapshot保存每格显式来源、template、问题、prepared、child_operation_id，带revision/hash。批准只接受完整相同triple，修改必须新plan；同plan只能创建一个batch。每格CAS queued→dispatching先COMMIT，之后仅一次调用；已存child UUID不更换。UNKNOWN/异常停在unknown，GET/重启不恢复执行，其他格独立继续；结果known completed/partial/failed保存不可变cell snapshot，下游unknown不伪完成。批次实时matrix可running/completed/partial；最终批次snapshot也不可变。取消与claim同事务CAS，只影响queued，不声称已dispatch调用退款。

identity_validator同步/异步，校验lease/instance/principal/generation；owner hash绑定完整TrustedIdentity，expiry应固定。prepare_cell(cell,identity)->prepared，至少selected_sources；validate_prepared(prepared,identity)须只读复验源/metadata/parent/context/memory，本具体adapter复验hybrid来源及memory。execute_cell(cell_with_prepared_and_frozen_question,child_operation_id,identity)->{domain:retrieval_v2|annual_diff|financial_statements_v3,state:completed|partial|failed|unknown,payload:dict}；真实业务只上述两个具体adapter，本层不创建provider/budget。

所有计划/批准/claim/结果/取消的业务COMMIT均在root publication_guard(identity,fence)内，fence含prepared_cells和去重selected_sources；root必须保持source/memory/context锁到本库COMMIT后。同步commit_check(identity,fence)在实际COMMIT前执行，钩子前后expiry检查，异步钩子拒绝。每次dispatch前与工具调用后再validate_prepared；root下游工具也必须在自己物理调用前校验身份。异常诊断可在过期后写unknown安全状态，但不得发布成功业务结果。batch-research.db不改旧jobs/预算，日志不包含密钥。

测试test_cplus_batch_research.py两组UNIT_FAKE：2公司×2模板批准前零调用、未批准拒执行、首格timeout后其余继续、同op不重发、GET无调用、运行中取消3queued不取消在途、commit_check=False不发布新plan。未发任何真实批量模型调用，不宣称真实2×2模型验收。真实hybrid/annual各自无模型样本已有proof，本批次跨两实际公司仍受美的候选与rootUI接线限制；真实矩阵、HTTP、取消竞态及最终source/lease guard由root另验。
