"""Conservative Chinese polarity rules for the finite extractive QA boundary.

Only explicit negative verb/object phrases are removed. Any remaining calculation
term, question about negation, double negation or mixed request retains the existing
confirmed-fact/Decimal gate. No language model determines authorization.
"""

import re

TERMS = ("同比", "增幅", "增长率", "差额", "相差", "计算", "增长了多少")
OBJECT = r"(?:同比|增幅|增长率|差额|相差|增长了多少)"
OBJECTS = OBJECT + r"(?:[、和与及]" + OBJECT + r")*"
NEGATIVE = r"(?:请)?(?:不(?:需要|要|用|必|需)?|无需|勿|别|禁止)(?:自行|再|进行|做)?"
FORWARD = re.compile(
    NEGATIVE + r"(?:(?:计算|算|求)(?:" + OBJECTS + r")?|" + OBJECTS + r"(?:计算|分析|(?=$|[，,。；;])))"
)
POSTFIX = re.compile(OBJECTS + NEGATIVE + r"(?:计算|算|求)")
DOUBLE_NEGATIVE = re.compile(
    r"(?:不要|别|勿|不能|不是|并非)(?:不|无需|不要|不用)(?:计算|算|求|做|进行)"
)


def requires_financial_analysis(query: str) -> bool:
    text = re.sub(r"\s+", "", query)
    if not any(term in text for term in TERMS):
        return False
    if DOUBLE_NEGATIVE.search(text) or re.search(r"吗|是否|要不要|能否|该不该", text):
        return True
    # Substitutions never consume a clause delimiter or a second positive verb.
    remaining = FORWARD.sub(" ", POSTFIX.sub(" ", text))
    return any(term in remaining for term in TERMS)
