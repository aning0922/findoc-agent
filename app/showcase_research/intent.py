"""Finite fallback + program-validated model proposals. No model output grants authority."""
import re

from app.showcase_research.models import IntentProposal, ResearchError

METRICS = {"revenue": ("营业收入", "营收"), "net_profit_parent": ("归母净利润", "净利润"),
           "operating_cash_flow": ("经营现金流", "现金流"), "total_assets": ("总资产", "资产总计"),
           "total_liabilities": ("总负债", "负债合计"), "debt_asset_ratio": ("资产负债率",)}
FINANCIAL = ("比较", "同比", "增长", "差额", "金额", "比例", "财务", "计算", "财务研究")


def years(text):
    return sorted(set(int(v) for v in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)), reverse=True)


def resolve_scope(text, scope):
    allowed = {doc["company_id"] for doc in scope["sources"]}
    found, outside = set(), False
    for company in scope["companies"]:
        names = {company["name"], company["security_code"]}
        short = re.sub(r"(?:股份有限公司|有限责任公司|有限公司)$", "", company["name"])
        names.update({short, re.sub(r"集团$", "", short)})
        if any(name and name in text for name in names):
            found.add(company["company_id"])
            outside = outside or company["company_id"] not in allowed
    aliases = [company["name"] for company in scope["companies"]]
    explicit_names = re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}(?:股份有限公司|有限公司|集团)", text)
    if any(not any(name in phrase or phrase in name for name in aliases) for phrase in explicit_names):
        outside = True
    if not found and len(allowed) == 1:
        found = allowed.copy()
    if "两家公司" in text or "两家企业" in text:
        found = allowed.copy() if len(allowed) == 2 else set()
    periods = years(text)
    history = scope["history"]
    if not periods and history and any(term in text for term in ("那年", "那一年", "同一年", "刚才", "上一年")):
        periods = years(history[-1]["user_text"])
        if "上一年" in text and len(periods) == 1:
            periods = [periods[0] - 1]
    keys = [key for key, aliases in METRICS.items() if any(alias in text for alias in aliases)]
    if not keys and history and any(term in text for term in ("刚才", "那年", "同一年", "上一年")):
        keys = [key for key, aliases in METRICS.items() if any(alias in history[-1]["user_text"] for alias in aliases)]
    return found, outside, periods, keys


def fallback(text, scope):
    companies, outside, periods, keys = resolve_scope(text, scope)
    financial = (bool(keys) or "财务" in text) and any(term in text for term in FINANCIAL) and not any(term in text for term in ("不要计算", "只要原文", "只看原文"))
    clarify = None
    if outside or not companies:
        clarify = "请明确选择当前会话资料范围内的企业。"
    elif financial and not periods:
        clarify = "请明确财务期间；报告年度不自动代表指标期间。"
    mode = "deep" if "深度" in text else "synthesis" if any(word in text for word in ("综合", "报告", "总结", "整理")) else "quick"
    actions = ["clarify"] if clarify else ["read_evidence"] + (["read_confirmed_facts"] if financial else [])
    if not clarify and "研究任务" in text:
        actions.append("create_task")
    if not clarify and "报告" in text:
        actions.append("draft_report")
    return IntentProposal(mode=mode, goal=text, company_ids=sorted(companies - (companies if outside else set())),
                          periods=periods, metric_keys=keys, actions=actions, clarifying_question=clarify,
                          requires_confirmed_facts=financial, source_turn_ids=[h["turn_id"] for h in scope["history"]])


def validate_proposal(raw, text, scope):
    proposal = IntentProposal.model_validate(raw)
    expected = fallback(text, scope)
    allowed = {doc["company_id"] for doc in scope["sources"]}
    # Exact goal and explicit/inferred period selection prevent provider scope drift or hidden instructions.
    if (proposal.goal != text or set(proposal.company_ids) - allowed or
            set(proposal.company_ids) != set(expected.company_ids) or
            set(proposal.periods) != set(expected.periods) or
            not set(expected.metric_keys).issubset(set(proposal.metric_keys)) or
            set(proposal.source_turn_ids) - {h["turn_id"] for h in scope["history"]} or
            (expected.requires_confirmed_facts and not proposal.requires_confirmed_facts) or
            (any(term in text for term in ("不要计算", "只要原文", "只看原文")) and proposal.requires_confirmed_facts) or
            (expected.clarifying_question and not proposal.clarifying_question)):
        raise ResearchError("intent_proposal_outside_frozen_scope")
    if len(proposal.company_ids) != len(set(proposal.company_ids)) or len(proposal.periods) != len(set(proposal.periods)):
        raise ResearchError("duplicate_intent_selection")
    return proposal
