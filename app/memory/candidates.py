"""Conservative exact-user-utterance mapping. No model/PDF/tool inputs or writes.

The graph must pass the current persisted user's raw text, never generated text.
Quoted, embedded, negated, or ambiguous expressions do not match this finite grammar.
"""
from app.memory.models import MemoryCandidate

EXPRESSIONS = {
    "记住：我更关注现金流": ("analysis_focus", "cash_flow"),
    "记住：我更关注营收": ("analysis_focus", "revenue"),
    "记住：我更关注盈利能力": ("analysis_focus", "profitability"),
    "记住：我偏好均衡分析": ("analysis_focus", "balanced"),
    "记住：我偏好用元展示": ("display_unit", "CNY_YUAN"),
    "记住：我偏好用万元展示": ("display_unit", "CNY_TEN_THOUSAND"),
    "记住：我偏好用亿元展示": ("display_unit", "CNY_HUNDRED_MILLION"),
    "记住：我习惯先看证据": ("research_habit", "evidence_first"),
    "记住：我习惯先比较年度": ("research_habit", "compare_periods_first"),
}


def extract_user_memory_candidates(user_text: str, source_turn_id: str) -> list[MemoryCandidate]:
    match = EXPRESSIONS.get(user_text.strip().removesuffix("。"))
    if match is None:
        return []
    key, value = match
    return [MemoryCandidate(key=key, value=value, source_turn_id=source_turn_id)]
