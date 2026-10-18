"""Compact Git acceptance evidence; complete immutable task/results remain in SQLite/local JSON."""
from typing import Any


def trim(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: trim(v) for k, v in value.items() if k not in {
            'review', 'evidence', 'basis_evidence', 'source_evidence', 'evidence_ids',
            'bbox', 'raw_cells', 'scope_header', 'year_header',
        }}
    if isinstance(value, list):
        return [trim(v) for v in value]
    return value


def compact(proof: dict[str, Any], full_path: str, full_sha: str) -> dict[str, Any]:
    result = {k:v for k,v in proof.items() if k != 'cases'}
    result.update(full_local_proof=full_path, full_local_proof_sha256=full_sha,
                  snapshots_trimmed_for_git=True, persistent_results_unmodified=True, cases=[])
    for case in proof['cases']:
        task = case.get('result')
        record = {k:trim(v) for k,v in case.items() if k not in ('result','waiting')}
        wait = case['waiting']
        record['waiting'] = {k:trim(wait[k]) for k in ('task_id','graph_version','revision','status','budget','input')}
        if task:
            content = task['final_research_content']
            record['result'] = {k:task[k] for k in ('task_id','operation_id','graph_version','status',
                'revision','error_code','budget','execution_status','publication_eligibility')}
            record['result']['human_review_status'] = content['human_review_status'] if content else 'pending'
            record['result']['outcome'] = content['outcome'] if content else task['status']
            record['result']['verified_operating_attribution'] = False
            record['result']['test_mode'] = 'simulated_test'
            if content:
                record['financial_facts'] = trim(content['financial_facts'])
                record['deterministic_analysis'] = trim(content['deterministic_analysis'])
                record['validated_citations'] = content['operating_descriptions']
                record['model_interpretations'] = content['model_interpretations']
                record['unresolved_questions'] = content['unresolved_questions']
                record['limitations'] = content['limitations']
                record['retrieval_hits'] = content['evidence_appendix']['retrieval_hits']
                request = content['evidence_appendix']['model_request']
                record['model_request_summary'] = {k:v for k,v in request.items() if k!='prompt'}
                record['model_request_summary'].update(prompt_characters=len(request['prompt']),
                    prompt_summary=request['prompt'][:700])
                record['model_attempts'] = content['model_attempts']
        result['cases'].append(record)
    return result
