"""Evidence limits of annual-report excerpts, independent of provider availability."""
import re


def outside_annual_evidence(query: str, report_years: tuple[int, ...]) -> bool:
    """Reject explicit live facts, guaranteed futures and exclusive causal proofs.

    These scopes cannot be certified by immutable historical annual reports.
    A year mentioned in an ordinary excerpt query remains eligible when it is a
    disclosed current/comparative period. No company names or gold values enter
    this gate; an explicitly unselected-source request has no selected authority.
    """
    text = ''.join(query.split())
    live_price = bool(re.search(r'(实时|现在|当前|此刻).*?(股价|股票.*?价格|交易价格)', text))
    exclusive_cause = bool(re.search(r'(证明|保证).*?(完全|唯一|全部).*?(造成|导致|原因|因为)', text))
    explicit_unselected = bool(re.search(r'(未选|未提供|范围外).*?(资料|企业|公司|年报)', text))
    years = [int(y) for y in re.findall(r'(\d{4})年', text)]
    future = bool(report_years and years and max(years) > max(report_years))
    return live_price or exclusive_cause or explicit_unselected or future
