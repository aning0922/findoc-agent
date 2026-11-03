# F25 显式体检解释快照

独立CheckupExplanationService(runtime_root, *, statements, identity_validator, publication_guard, commit_check, provider_json=None, memory=None)，已从app.checkup最小导出。不改原三规则，不重写旧checkup。复用同根StatementService、peer Store与同步提交钩子；root唯一装配点。

create_checkup_explanation_router(service,identity_provider)：POST /cplus/checkup-explanations {operation_id,checkup_id,expected_payload_sha256,confirmed:true}，GET /cplus/checkup-explanations/{explanation_id}，GET /cplus/checkup-explanations/operations/{op}。新mutation/GET待root登记policy；返回operation_id/state/result。expected hash是statements.read(id,'checkup')整个原payload的canonical SHA，不是来源文件hash，也不猜旧checkup自带payload_sha字段。

schema_version=checkup-explanation-v1：explanation_id、原checkup_id/hash/snapshot、collection_refs、receipt_refs、candidate_view、memory_generation、explanations、provider_outcome、interpretation_review_status、financial_authority=false、created_at、payload_sha256、限制。hash是去掉payload_sha256字段后的创建快照canonical SHA；GET追加historical_snapshot/current_source_status，不改变原hash。原checkup不变。每条解释带rule_id/input_refs、ai_unreviewed，候选规则不升级确认；缺证据规则不送模型，全部insufficient直接not_called_insufficient。provider未配置返回unconfigured/not_generated，不伪造模型输出。

provider_json(snapshot,identity)同步/异步，由root适配已有guarded provider，不构造SDK/预算。snapshot含原规则及实际当前输入cells和receipt/候选状态，以及“仅解释规则观察，不重算数、不推断原因”的指令。根须限制总输入/输出token、timeout、共享5元guard；资料文本不能作为授权。只允许一轮JSON：`{"explanations":[{"rule_id":"cash_profit_divergence","text":"观察提示方向变化，建议对照原文核查。","input_refs":["原规则全部输入cell_id"]}]}`。只能解释eligible rule，不重复；input_refs必须与该规则全部输入一致。单条文字≤1500，数字（含中文数词）和显式因果断言/买卖建议词会拒绝；这会拒绝含“一方面”等普通措辞，root prompt需避免数词表述。文字过滤不是语义事实核验，输出仍AI待审。省略规则不补解释。

UNKNOWN先持久再物理callback；timeout/非法输出保留原op unknown，原UUID只读恢复，不重发。身份校验先于读取；owner hash含固定lease expiry。回调前无SQL锁，返回后重新selected/context检查和当前admitted receipt核验；与回调前cells/receipt不同拒发布。最终root publication_guard(identity,fence)持源/metadata/parent/context/memory/lease读栅栏跨COMMIT；fence含selected_sources、collection_refs、checkup id/hash、memory generation及receipt_refs。statement source/receipt事务再次核验并拒WAL，内库实际COMMIT前必需同步commit_check(identity,fence)，钩子前后expiry核验。缺hooks失败关闭，异步commit hook拒绝。

UNIT_FAKE 3组tests/test_cplus_checkup_explanations.py：provider时无SQL读锁、原snapshot不改/GET不调用/幂等；不足不调用、timeout不重放；receipt变化、非法数字因果文本、最终identity拒绝不发布。连旧statements测试5 passed/1 skipped，保留5既有Swig warnings；Ruff通过。没有本worker真实LLM/真人核准，root接同一体检UI与现有预算provider后另验。未读取.env/密码/账本/原开发DB。
