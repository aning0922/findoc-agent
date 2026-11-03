import copy
import json

from app.cplus.prompts import annual_prompt_evidence
from app.showcase_research.provider import tokens


def test_three_topics_project_both_exact_prefixes_within_existing_budget():
    pairs = []
    for topic in ["经营风险", "主要业务", "研发"]:
        pair = {"topic": topic}
        for side in ["left", "right"]:
            pair[side] = {
                "evidence_refs": [
                    {
                        "evidence_id": side + str(index) + "a" * 64,
                        "physical_page": 10 + index,
                        "source_ref": {
                            "document_id": side,
                            "report_year": 2025,
                            "unused_large_metadata": "不可发给模型" * 2000,
                        },
                        "text": ("经营风险研发业务，按原文核查。" * 200)[:1600],
                    }
                    for index in range(2)
                ]
            }
        pairs.append(pair)
    original = copy.deepcopy(pairs)
    projected = annual_prompt_evidence(pairs)
    raw = json.dumps(projected, ensure_ascii=False)
    assert len(raw.encode()) < 48000
    assert tokens(raw) < 8500  # reserves additional prompt/instructions framing
    assert pairs == original
    for before, after in zip(pairs, projected):
        assert before["topic"] == after["topic"]
        for side in ["left", "right"]:
            assert len(after[side]) == 2
            for full, small in zip(before[side]["evidence_refs"], after[side]):
                assert small["evidence_id"] == full["evidence_id"]
                assert small["text"] == full["text"][:400]
                assert small["excerpt_is_prefix"] is True
                assert small["document_id"] == full["source_ref"]["document_id"]
                assert small["physical_page"] == full["physical_page"]
