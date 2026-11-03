# A01 跨年经营文本对比合同

分支codex/cplus-annual-diff，基线132fd7d8a8efd171fef4136c4ccdc1fd7da725ea。独立annual-diff.db，不改旧报告/研究/检索/前端或runtime。正式接入同一个公司详情经营变化页与报告由root完成，无独立研究平台。仅fast合法源，OCR支持不扩入本任务。

## 装配

`AnnualDiffService(runtime_root, *, hybrid, sources, identity_validator, publication_guard, provider_json=None, memory=None)`。hybrid必须同runtime_root且sources为同实例；默认memory取hybrid.memory。直接接口 `await create(AnnualDiffRequest, TrustedIdentity)`、`await read(result_id, identity)`、`await operation(operation_id, identity)`。请求模型见app/annual_diff/models.py，复用retrieval_v2 SourceRef/TrustedIdentity。

`create_annual_diff_router(service, identity_provider)`：

- POST `/cplus/annual-diffs {operation_id,left_source,right_source,topics,generate_explanation:false}`。
- GET `/cplus/annual-diffs/{result_id}`。
- GET `/cplus/annual-diffs/operations/{operation_id}`（恢复端点，待root policy登记）。

POST/operations返回 `{operation_id,state,result_id,error_code,result}`；GET result返回不可变payload加current_source_status和historical_snapshot。业务结果schema_version=annual-diff-v1；result_id/payload_sha256/request_sha256、left/right完整SourceRef、topics、memory_generation、provider_outcome、创建时间、来源/转录状态和限制。保存的source_status作用域为validated_at_creation；历史读取source变化单独显示stale_or_unavailable，不重跑模型。调用身份先校验，不能把身份拒绝降级成历史可读。

两个source必须fast、相同当前workspace/company、不同报告年度/document/revision，完整source身份由hybrid.records校验；左右不强行按年度排序，保留用户明选版本。topics只能`经营风险`、`主要业务`、`研发`，最多3个不重复。每侧每主题独立检索top5，保留最多2个带主题词、满足versioned候选门槛、逐条exact验证的引用；fast摘录最多1600字，保留精确子串。没有隐式build：FTS未建时按hybrid诊断保留degraded状态，root应在显式资料阶段build。

## 标签与模型

两侧摘录文本数组完全相同才确定性program_label=continued（仅表示所选摘录同文，不表示整个业务一致）；缺任侧→insufficient，label_basis=missing_in_retrieval；其他→comparison_required。不会用字符串diff自动宣布新增业务、减少/取消或未披露。主题词匹配与排序不等于语义对齐，人审状态始终human_pending。

可选 `provider_json(eligible_pairs, identity)->dict` 同步/异步，由root适配现有guarded provider；只在generate_explanation=true且有comparison_required时最多调用一次（全部主题合并一轮）。文档是资料而非指令，root应提供隔离system prompt、token/总输入字节/时间上限和共享预算guard；输入最多3主题×2侧×2段×1600字，真实费用只root执行。没有provider时provider_outcome=unconfigured且解释not_generated；没有可解释主题则不调用。

唯一允许模型输出：`{"topics":[{"topic":"经营风险","label":"wording_changed|new_disclosure_candidate|continued|insufficient","explanation":"...","evidence_ids":["左侧已有ID","右侧已有ID"]}]}`。每个输出topic必须来自eligible且不重复，引用ID必须全来自对应主题并两侧各至少1条；解释≤2000字。遗漏主题仍not_generated。模型标签单列ai_label并ai_unreviewed，不升级program_label或财务authority；新披露仅candidate。所有解释/数字未构成财务确认。

## 身份、原子性和恢复

identity_validator(identity)同步/异步、抛错或False拒绝；owner以完整TrustedIdentity hash绑定，expiry应固定为lease expiry，不能每请求滚动。过期/跨workspace拒绝。generation来自注入ResearchMemoryService现有tx/_generation；在模型前/提交前check_generation。

**必需root publication_guard(identity,fence_payload)** 同步contextmanager；payload含selected_sources、memory_generation、operation_id、request_sha256。root负责源documents/revision/metadata、当前lease/instance/principal、memory真正共享读锁到annual DB结果COMMIT后退出。worker异步前后校验不能代替跨库原子guard；缺guard直接拒绝。模型前短暂guard验证，然后释放，不跨模型调用持锁；模型后重验双侧scope和所有引用，再进入最终guard发布。只读对象有SQLite不可更新/删除trigger。

操作先登记unknown，再做检索/可选一次模型。相同UUID+body只读回原记录；不同body/owner409。异常保留unknown及安全error_code，不自动重试付费。状态unknown并不表示可重新POST；恢复仅GET同operation，未登记/未知不可捏造成功。

## 验证

`pytest -q tests/test_cplus_annual_diff.py`：3 passed。fake覆盖同文continued/缺侧insufficient、幂等及不可变、历史源变化状态、跨公司拒绝、最终guard拒发布、provider timeout UNKNOWN不重放；无真实模型/财务确认。Ruff通过。nullcontext fixture不证明root真实跨库fence。

真实公开seed只读物化到全新临时root，脚本docs/cplus/evidence/M3-annual-diff-real.py：选公司服务的证券代码000651，来源身份从当前SourceService读取，不由文件名或硬编码页码决定。真实本地BGE/Milvus检索两格力年报及三主题；公开JSON仅身份/hash/页码/状态，无全文/PDF/DB/key。首轮脚本因source响应未带workspace_id而KeyError停止（模型0），改用DocumentService服务端workspace后重跑。最终JSON记录实际左右页与不足；不作为人工语义准确率。未读.env/密码/原DB/账本，未发付费模型。

最终真实检索输出：经营风险2024物理44/43、2025物理39/38；主要业务2024物理13/44、2025物理6/6；研发2024物理20/31、2025物理40/11。3维左右均取得候选，但program_label全部comparison_required、provider_outcome=not_requested、解释not_generated；主要业务页6等候选仍需人工检查主题贴合，不能据此宣称准确对齐。seed manifest校验前后相同。公开JSON的implementation_sha256与最终service源码相符。

哈希说明：payload_sha256是创建时完整持久payload去掉payload_sha256本字段后的canonical SHA；read追加的current_source_status不计入旧payload hash。报告adapter应按持久快照范围验证，不因只读freshness投影而改写原hash。

P1提交时序修订：构造器新增必需同步 `commit_check(identity,fence)`（不传则写拒绝），在自己的annual-diff.db事务实际COMMIT之前调用，并在钩子前后检查expiry。异步钩子拒绝，不能把外层contextmanager的退出检查当成内层已提交结果的最终检查。外层source/memory guard继续持锁跨此COMMIT；测试证明外层guard可进入但内层commit_check返回False仍不保存结果。既有真实公开检索proof来自此hook修订前的无模型检索阶段，不冒充最终生产fence已验收。
