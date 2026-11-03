"""Bounded local HTTP proof: fresh lease, explicit official import, real READY.

No provider calls or human confirmations. Reads only the dedicated demo-login
file supplied by the operator; never records credentials, cookies or headers.
"""
import argparse
from pathlib import Path
from uuid import uuid4
import json
import time

from dotenv import dotenv_values
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--origin', default='http://127.0.0.1:14540')
    parser.add_argument('--login-config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = dotenv_values(args.login_config, interpolate=False)
    evidence = {'tier': 'REAL_HTTP_PDF_BGE_MILVUS', 'provider_calls': 0,
                'human_approvals': 0, 'steps': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2))

    with httpx.Client(base_url=args.origin, trust_env=False, timeout=180,
                      headers={'Origin': args.origin}) as client:
        def request(method, path, **kwargs):
            response = client.request(method, '/api' + path, **kwargs)
            evidence['steps'].append({'method': method, 'path': path,
                                      'status': response.status_code})
            print(method, path, response.status_code, flush=True)
            save()
            if response.status_code >= 400:
                # Only safe business response bodies, never request/auth headers.
                evidence['last_error'] = response.json()
                save()
                response.raise_for_status()
            return response.json()

        for _ in range(180):
            status = client.get('/api/demo/status').json()
            if status.get('service_state') != 'resetting':
                break
            time.sleep(.5)
        login_id = str(uuid4())
        request('POST', '/demo/login', json={'operation_id': login_id,
                'username': config['DEMO_USERNAME'], 'password': config['DEMO_PASSWORD']})
        for _ in range(180):
            result = client.get('/api/demo/operations/' + login_id).json()
            if result.get('claimable'):
                break
            if result.get('state') == 'failed':
                raise RuntimeError('runtime_reset_failed')
            time.sleep(.5)
        else:
            raise RuntimeError('runtime_claim_timeout')
        request('POST', '/demo/claim', json={'operation_id': str(uuid4()),
                                           'attempt_operation_id': login_id})
        evidence['session'] = request('GET', '/demo/session')
        companies = request('GET', '/companies')
        result = request('POST', '/cplus/discovery/searches', json={
            'operation_id': str(uuid4()), 'mode': 'companies', 'query': '600690'})
        company = next(c for c in result['items'] if c['security_code'] == '600690'
                       and c['exchange'] == 'SSE')
        result = request('POST', '/cplus/discovery/searches', json={
            'operation_id': str(uuid4()), 'mode': 'announcements',
            'security_id': company['security_id'], 'report_year': 2025,
            'kind': 'annual_fulltext'})
        evidence['announcements'] = result
        report = next(r for r in result['items'] if r['kind'] == 'annual_fulltext'
                      and r['language'] == 'zh')
        known = next((c for c in companies if c['security_code'] == '600690'
                      and c['exchange'] == 'SSE'), None)
        operation_id = str(uuid4())
        imported = request('POST', '/cplus/discovery/imports', json={
            'operation_id': operation_id, 'candidate_id': report['candidate_id'],
            'candidate_digest': report['candidate_digest'], 'confirmed': True,
            'company_id': known['company_id'] if known else None,
            'create_company': known is None})
        evidence['import'] = imported
        save()
        if imported['state'] != 'completed':
            raise RuntimeError('import_unknown_no_replay')
        document_id = imported['document_id']
        for _ in range(180):
            document = client.get('/api/documents/' + document_id).json()
            if document.get('status') in ('ready', 'failed'):
                break
            time.sleep(1)
        evidence['document'] = document
        save()
        if document.get('status') != 'ready':
            raise RuntimeError('official_pdf_not_ready')
        evidence['metadata'] = request('GET', f'/documents/{document_id}/metadata')
        evidence['source'] = request('GET', f'/documents/{document_id}/source',
                                    params={'company_id': imported['company_id']})
        # Same operation: read-only recovery; it must not repeat download/binding.
        recovered = request('GET', '/cplus/discovery/imports/' + operation_id)
        evidence['same_operation_recovery_equal'] = recovered == imported
        save()
        request('POST', '/demo/logout', json={'operation_id': str(uuid4())})
        evidence['result'] = 'PASS'
        save()


if __name__ == '__main__':
    main()
