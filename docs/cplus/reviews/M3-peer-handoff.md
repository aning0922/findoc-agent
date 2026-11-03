# 同行比较叶子模块

PeerComparisonService(runtime_root, *, statements, identity_validator, publication_guard, memory=None, commit_check=None)。复用StatementService.selected/guard/admitted，不写原财务事实。create_peer_comparison_router(service,identity_provider)提供POST /cplus/peer-comparisons、GET /{result_id}、GET /operations/{operation_id}，后两条待root登记policy。POST body=operation_id/company_ids(2–3)/collection_refs:[{collection_id,cell_ids}]/candidate_view:false；必须明确cell集合，不按最新版本猜选。返回operation_id/state/result。同行身份仅用户选择，不代表行业已认证。

按metric分组，每公司必须恰有一项；日期union/time、basis、scope、currency、normalized_unit全一致且数值有效才Decimal差额，否则明确incomparable和reason，缺值不补零。candidate_view显式开启才允许未确认值，结果candidate_observation；每个point带真实receipt_ref或null。默认无回执不计算。没有同比/行业优劣推断。

最终root publication_guard(identity,fence)必须同步持源/记忆/代际锁跨COMMIT。fence含selected_sources/collection_refs/memory_generation；StatementService事务再锁source与receipt状态并重验撤销，拒绝main WAL的receipt栅栏。必需同步commit_check(identity,fence)在peer DB实际COMMIT之前校验当前身份，expiry在钩子前后检查；异步钩子拒绝。缺钩子不发布。owner以完整TrustedIdentity hash绑定，expiry必须固定lease expiry。GET历史先授权，来源/回执变化单列stale_or_receipt_changed，不改快照。peer-compare.db存不可变snapshot及幂等操作。异常unknown不重发。

测试test_cplus_peer_compare.py为FAKE，验证候选Decimal差额20.20/幂等/期间不同比较拒绝。真实公开seed物化副本M3-peer-public-proof.json：格力2025-12-31提取7个候选，美的同期期末候选0，实际comparison=null，不冒充两家公司真实对比成功；root须补美的提取。源seed efc10a4...前后校验一致，LLM0/真人0。脚本M3-peer-public-proof.py使用当前公开seed与新temp，未读原DB/账本/配置。最终真实UI/owner回执正向与并发fence仍待root。

配套annual_diff P1修复SHA单独aedca75：新增相同同步commit_check钩子，外层guard退出不再被当成内库最终COMMIT检查；root须更新装配。此前A01原实现已有独立提交，不需重新cherry-pick本分支的基线重复A01。

真实美的扩展后复验：修复point投影的dict重复financial_review关键字（使用mapping positional后显式覆盖），fixture补入真实cell已有的financial_review，回归通过。真实同一seed两公司2025年末：格力7候选、美的2候选；资产差额217419766180.51元、负债差额130786823855.21元（美的减格力），均candidate_observation/human0/LLM0；其他只有格力的项明确missing_or_ambiguous_period_selection。公开M3-peer-public-proof.json已更新为实际service输出，nullcontext仍不代表root并发fence验收。
