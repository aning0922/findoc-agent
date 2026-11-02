"""Bounded context and conservative reference resolution, without a planner LLM."""

from dataclasses import dataclass
import re
from typing import Any

import tiktoken

from app.conversations.models import ResolvedQuery, Turn
from app.conversations.repository import ConversationError
from app.conversations.service import TurnExecution
from app.memory.candidates import extract_user_memory_candidates
from app.memory.service import MemoryService
from app.rag.calculation_intent import requires_financial_analysis
from app.research.models import canonical
from app.conversations.summaries import Summary, SummaryRepository

METRICS = {
    "revenue": ("营业收入", "营收"),
    "net_profit_parent": ("归属于母公司股东的净利润", "归母净利润", "净利润"),
    "operating_cash_flow": ("经营活动产生的现金流量净额", "经营现金流", "现金流"),
}
LABELS = {"revenue": "营业收入", "net_profit_parent": "归母净利润",
          "operating_cash_flow": "经营活动产生的现金流量净额"}
ENCODING = tiktoken.get_encoding("cl100k_base")


def tokens(text: str) -> int:
    return len(ENCODING.encode(text, disallowed_special=()))


@dataclass(frozen=True)
class ConversationContext:
    turns: tuple[Turn, ...]
    preferences: tuple[dict[str, str], ...]
    memory_generation: int
    # Only untrusted user text and structural focus; never historical answer numbers.
    prompt_data: str
    summary: Summary | None = None


def load_context(execution: TurnExecution, memory: MemoryService) -> ConversationContext:
    snapshot = memory.recall_context()
    excluded = memory.excluded_source_turn_ids()
    summary = SummaryRepository(execution.repository).read(execution.turn.conversation_id,
                                                         snapshot.generation, excluded)
    if summary and summary.covered_through_seq != execution.turn.seq - 9:
        summary = None  # An unprocessed gap cannot authorize old focus.
    summary_data = summary.model_dump(exclude={"source_turn_ids", "source_digest"}) if summary else None
    if summary_data and tokens(canonical(summary_data)) > 512:
        raise ConversationError("context_budget_error", 409)
    recent = execution.repository.detail(execution.turn.conversation_id, limit=9).turns
    selected: list[Turn] = []
    payloads: list[dict[str, Any]] = []
    for turn in reversed(recent):
        if (turn.seq >= execution.turn.seq or turn.status not in ("completed", "refused")
                or turn.turn_id in excluded
                or extract_user_memory_candidates(turn.user_text, turn.turn_id)
                or (turn.result and turn.result.memory_candidates)):
            continue
        payload = {"turn_id": turn.turn_id, "user_text": turn.user_text,
                   "focus": turn.resolved_query.model_dump() if turn.resolved_query else None}
        if tokens(canonical([payload, *payloads])) > 4096:
            summary, summary_data = None, None
            break  # Whole-message suffix only; never reach past an omitted focus.
        selected.insert(0, turn)
        payloads.insert(0, payload)
        if len(selected) == 8:
            break
    preferences = tuple({"key": item.key, "value": item.value} for item in snapshot.items[:5])
    if tokens(canonical(preferences)) > 256:
        raise ConversationError("context_budget_error", 409)
    data = canonical({"recent_user_data": payloads, "confirmed_preferences": preferences,
                      "structural_summary": summary_data})
    return ConversationContext(tuple(selected), preferences, snapshot.generation, data, summary)


def resolve(execution: TurnExecution, context: ConversationContext) -> tuple[ResolvedQuery, str | None]:
    text = execution.turn.user_text
    compact = re.sub(r"\s+", "", text)
    docs = execution.selection.documents
    companies = execution.repository.registry.list(execution.repository.workspace)
    selected_companies = {d.company_id for d in docs}
    aliases: dict[str, set[str]] = {}
    for company in companies:
        names = {company.name, company.security_code}
        short = re.sub(r"(?:股份有限公司|有限责任公司|有限公司)$", "", company.name)
        if len(short) >= 2:
            names.add(short)
            group_short = re.sub(r"集团$", "", short)
            if len(group_short) >= 2:
                names.add(group_short)
        for name in names:
            aliases.setdefault(re.sub(r"\s+", "", name), set()).add(company.company_id)
    mentioned: set[str] = set()
    for alias, ids in aliases.items():
        if (re.search(r"(?<!\d)" + re.escape(alias) + r"(?!\d)", compact)
                if alias.isdigit() else alias in compact):
            mentioned.update(ids)
    # An unresolved intervening question blocks falling back to an older subject.
    latest = context.turns[-1] if context.turns else None
    previous = latest if (latest and latest.resolved_query
                          and latest.resolved_query.company_id is not None
                          and latest.resolved_query.resolution != "ambiguous") else None
    focus = previous.resolved_query if previous else None
    focus_id = previous.turn_id if previous else None
    if latest is None and context.summary and not context.summary.barrier and context.summary.focus:
        saved = context.summary.focus
        focus = ResolvedQuery(text="结构焦点", company_id=saved.company_id,
            metric_key=saved.metric_key, periods=saved.periods, intent=saved.intent,
            resolution="explicit", context_turn_ids=[])
        focus_id = context.summary.focus_turn_id
    company_id = next(iter(mentioned)) if len(mentioned) == 1 else (
        focus.company_id if not mentioned and focus else
        next(iter(selected_companies)) if len(selected_companies) == 1 and not mentioned else None)
    metrics = [key for key, words in METRICS.items() if any(word in compact for word in words)]
    metric = metrics[0] if len(metrics) == 1 else None
    years = sorted(set(int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", compact)),
                   reverse=True)
    inferred = False
    context_ids: list[str] = []
    reason: str | None = None
    if len(mentioned) > 1 or len(metrics) > 1 or len(years) > 2:
        reason = "ambiguous_reference"
    elif mentioned - selected_companies:
        reason = "outside_company"
    elif any(word in compact for word in ("换一家", "另一家", "未选公司", "未选企业")):
        reason = "new_conversation_required"
    # Unknown explicit company mentions must not silently resolve to the sole source.
    unknown = re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}(?:股份有限公司|有限公司|公司|集团)", compact)
    generic = {"这家公司", "该公司", "本公司", "同一公司", "公司"}
    if any(phrase not in generic and not any(alias in phrase for alias in aliases) for phrase in unknown):
        reason = reason or "unknown_company"
    prefix = re.match(r"^(.*?)(?:19|20)\d{2}年", compact)
    if prefix:
        subject = re.sub(r"^(?:请问|请|帮我|查询|查看|关于|研究|介绍|分析|告诉我|摘录)+", "", prefix[1])
        subject = subject.strip("，,：: ")
        remainder = subject
        for alias in sorted(aliases, key=len, reverse=True):
            remainder = remainder.replace(alias, "")
        remainder = re.sub(r"(?:的|和|与|及|、|，|,)", "", remainder)
        remainder = re.sub(r"^(?:请问|请|帮我|查询|查看|关于|研究|介绍|分析|告诉我|摘录|引用|年报|原文|说明)+",
                           "", remainder)
        if remainder and remainder not in {"它", "这家公司", "该公司", "公司", "那", "那么"}:
            reason = reason or "unknown_company"
    after_year = re.search(r"(?:19|20)\d{2}年(.*?)(?:营业收入|营收|归母净利润|净利润|经营现金流|现金流|主营业务)", compact)
    if after_year:
        subject = after_year[1]
        for alias in sorted(aliases, key=len, reverse=True):
            subject = subject.replace(alias, "")
        subject = re.sub(r"(?:度|的|年报|中|关于|公司|该|这家)", "", subject)
        if subject.strip("的和与及、，,：:"):
            reason = reason or "unknown_company"
    # Named follow-ups have no numeric year or legal suffix ("XX同一年呢").
    # Strip only registered aliases and finite grammatical phrases, never infer brands.
    subjects = []
    for pattern in (
        r"^(.*?)(?:同一年|上一年|那一年|那年|去年)",
        r"^(.+?)呢[？?。]*$",
        r"^(.*?)(?:营业收入|营收|归母净利润|净利润|经营活动产生的现金流量净额|经营现金流|现金流)",
    ):
        match = re.search(pattern, compact)
        if match:
            subjects.append(match[1])
    grammar = ("请问", "帮我", "查询", "查看", "告诉我", "引用", "年报", "原文", "说明",
               "摘录", "研究", "介绍", "分析", "关于", "同比变化", "同比", "变化", "增幅",
               "增长率", "差额", "相差", "比较", "同一年", "上一年", "那一年", "那年", "去年",
               "这家公司", "该公司", "本公司", "公司", "那么", "那", "它", "还有", "也", "的",
               "和", "与", "及", "请", "只", "仅", "不计算", "不要计算")
    for subject in subjects:
        for alias in sorted(aliases, key=len, reverse=True):
            subject = subject.replace(alias, "")
        subject = re.sub(r"(?:19|20)\d{2}年(?:度)?", "", subject)
        for phrase in sorted(grammar, key=len, reverse=True):
            subject = subject.replace(phrase, "")
        if subject.strip("，,：:、；;？? "):
            reason = reason or "unknown_company"
    if reason == "unknown_company":
        company_id = None
    if company_id is None:
        reason = reason or "ambiguous_company"
    # Keep the existing D26 negative-calculation grammar. An explicit request to
    # quote a disclosed phrase is reading, while any remaining positive request
    # for calculation still requires confirmed facts.
    calculation_text = re.sub(r"(?:只|仅)(?:摘录|引用|阅读)(?:同比|增幅|增长率|差额)原文", "", compact)
    compare = (requires_financial_analysis(calculation_text)
               or requires_financial_analysis(calculation_text.replace("比较", "计算"))
               or ("也这样" in compact and focus is not None and focus.intent == "compare_metric"))
    followup = any(w in compact for w in ("上一年", "去年", "那年", "那一年", "它", "呢", "也这样"))
    if metric is None and not metrics and focus and (compare or followup):
        metric, inferred = focus.metric_key, True
    if not years and focus and (compare or followup):
        years, inferred = list(focus.periods), True
        if any(w in compact for w in ("上一年", "去年")) and years:
            years = [max(years) - 1]
    if compare and years:
        years = [years[0], years[1] if len(years) == 2 else years[0] - 1]
    # Never guess a year even with a single report: report year != requested fact period.
    if not years:
        reason = reason or "period_required"
    if any(not any(d.company_id == company_id and y in (d.report_year, d.report_year - 1)
                   for d in docs) for y in years):
        reason = reason or "outside_period"
    if "它" in compact and len(selected_companies) > 1 and not mentioned and focus is None:
        reason = reason or "ambiguous_company"
    if inferred and focus_id:
        context_ids = [focus_id]
    intent = "compare_metric" if compare and metric else (
        "confirmed_metric" if metric and execution.turn.fact_selections else "source_quote")
    if compare and metric is None:
        reason = reason or "metric_required"
    if extract_user_memory_candidates(text, execution.turn.turn_id):
        reason = "preference_confirmation_required"
    if any(w in compact for w in ("实时股价", "预测股价", "保证收益", "买入建议")):
        reason = "unsupported_request"
    if reason:
        intent = "unsupported" if reason == "unsupported_request" else "clarify"
    company = next((c.name for c in companies if c.company_id == company_id), "")
    # For source tools keep the original subject terms (e.g. main business), but
    # replace elliptical metric questions with a standalone evidence request.
    query = (f"{company} {','.join(str(y) for y in years)}年度 {LABELS[metric]}原文"
             if metric else f"{company} {text}")
    return ResolvedQuery(text=query, intent=intent,
        company_id=company_id if company_id in selected_companies else None,
        metric_key=metric, periods=years[:2],
        resolution="ambiguous" if reason else "context" if inferred else "explicit",
        context_turn_ids=context_ids), reason
