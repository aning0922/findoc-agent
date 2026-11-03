"""Small, source-exact model projections; saved findings retain their full refs."""


def annual_prompt_evidence(pairs):
    result = []
    for pair in pairs[:3]:
        item = {"topic": pair["topic"]}
        for side in ("left", "right"):
            item[side] = [
                {
                    "evidence_id": ref["evidence_id"],
                    "document_id": ref["source_ref"]["document_id"],
                    "report_year": ref["source_ref"]["report_year"],
                    "physical_page": ref["physical_page"],
                    "text": ref["text"][:400],
                    "excerpt_is_prefix": len(ref["text"]) > 400,
                }
                for ref in pair[side]["evidence_refs"][:2]
            ]
        result.append(item)
    return result
