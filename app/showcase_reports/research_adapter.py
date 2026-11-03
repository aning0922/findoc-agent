"""Projection of server-verified jobs only. No browser-provided findings or model calls."""
import json

from .models import Finding, VerifiedJobSnapshot


def project_verified_job(value):
    origin = value['data_origin']
    findings = []
    for item in value['findings']:
        findings.append(Finding(
            finding_id=item['finding_id'], kind=item['kind'], text=item['text'],
            financial_refs=[json.dumps(ref, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
                            for ref in item.get('financial_refs', [])],
            evidence_refs=item.get('evidence_refs', []), data_origin=origin,
            source_status={'current_valid': 'current', 'not_applicable': 'current'}.get(item['source_status'], 'unavailable'),
            transcription_review_status=item['transcription_review_status'],
            interpretation_review_status=item['interpretation_review_status'],
            numeric_claim_status=item.get('numeric_claim_status'),
        ))
    return VerifiedJobSnapshot(**{key: value[key] for key in (
        'job_id', 'workspace_id', 'state', 'company_name', 'period_label', 'data_origin', 'limitations')},
        findings=findings)
