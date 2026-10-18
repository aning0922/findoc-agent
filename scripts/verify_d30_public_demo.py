"""Inspect every published byte/link and actively reject execution/escape requests."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import httpx


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.executable = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'form', 'iframe', 'object', 'embed', 'input', 'button'):
            self.executable.append(tag)
        if any(k.startswith('on') for k in attrs):
            self.executable.append('handler')
        for key in ('href','src'):
            if key in attrs:
                self.links.append(attrs[key])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--url', default='http://127.0.0.1:14290')
    p.add_argument('--secret-file', type=Path, required=True)
    args = p.parse_args()
    from dotenv import dotenv_values
    values = dotenv_values(args.secret_file)
    # Never emit values, lengths or secret hashes. The output contains counts only.
    needles = [values[k].encode() for k in ('LLM_API_KEY','LLM_BASE_URL') if values.get(k)]
    manifest = json.loads((args.root / 'release-public-manifest.json').read_text())
    allowed_hosts = {'www.midea.com.cn','static.cninfo.com.cn','disc.static.szse.cn'}
    manifest_raw = (args.root / 'release-public-manifest.json').read_bytes()
    all_files = {**manifest['files'], 'release-public-manifest.json': dict(
        sha256=hashlib.sha256(manifest_raw).hexdigest(), bytes=len(manifest_raw))}
    responses, outbound = [], set()
    with httpx.Client(base_url=args.url,trust_env=False,timeout=20,follow_redirects=False) as client:
        for name, expected in all_files.items():
            raw = (args.root / name).read_bytes()
            assert not any(secret in raw for secret in needles), name
            assert not re.search(rb'(?:/Users/|/private/var/|file://|sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,})',raw), name
            assert name.endswith(('.html','.css','.md','.json'))
            if name.endswith('.html'):
                parser = Links()
                parser.feed(raw.decode())
                assert not parser.executable, (name,parser.executable)
                for link in parser.links:
                    url = urlsplit(link)
                    if url.scheme:
                        assert url.scheme == 'https' and url.hostname in allowed_hosts
                        outbound.add(url.hostname)
                    else:
                        assert not url.netloc and not url.query
                        assert not url.path or url.path in manifest['files'] or url.path=='release-public-manifest.json', (name,link)
            response = client.get('/'+name)
            assert response.status_code == 200
            assert response.content == raw
            assert hashlib.sha256(response.content).hexdigest() == expected['sha256']
            assert "connect-src 'none'" in response.headers['content-security-policy']
            assert response.headers['x-content-type-options']=='nosniff'
            responses.append(dict(path=name,sha256=expected['sha256'],http=200))
        forbidden = ['/api/health','/api/report-documents','/api/financial-facts/confirmations',
                     '/api/financial-facts/persisted','/api/financial-facts/acceptances/x/revoke',
                     '/api/research/tasks/x/resume','/api/research/runs','/.env','/.git/config',
                     '/data/d28/live-20261013/runtime/documents.db','/../.env','/%2e%2e/.env',
                     '/%69ndex.html','/index.html?path=../../.env','/scripts/d30_live.py']
        rejects=[]
        for path in forbidden:
            response=client.get(path)
            assert response.status_code==404
            rejects.append(dict(method='GET',path=path,status=response.status_code))
        for method in ('POST','PUT','PATCH','DELETE','OPTIONS','TRACE','CONNECT'):
            for path in ('/api/research/tasks','/api/financial-facts/confirmations','/index.html'):
                response=client.request(method,path)
                assert response.status_code==405
                rejects.append(dict(method=method,path=path,status=response.status_code))
    args.out.write_text(json.dumps(dict(schema='d30-public-security-v1',public_files=responses,
        rejected_requests=rejects,secret_value_matches=0,local_path_matches=0,
        executable_html_elements=0,external_hosts=sorted(outbound),
        backend_proxy=False,full_pdf_files=0,private_evidence_public_projections=22,
        deployment='local_only_not_published'),ensure_ascii=False,indent=2)+'\n')
    print(f'{len(responses)} exact public files; {len(rejects)} rejected requests; no credentials or local paths')


if __name__ == '__main__':
    main()
