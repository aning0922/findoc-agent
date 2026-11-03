"""Bounded public-source preflight. Download only the repository's known official PDFs.

This is D01 evidence, not a general search service. It never touches existing PDFs.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import time

import httpx
import pymupdf

REPO = Path(__file__).resolve().parents[2]
ALLOWED = {'www.midea.com.cn', 'static.cninfo.com.cn', 'disc.static.szse.cn'}


async def main() -> None:
    output = Path(tempfile.mkdtemp(prefix='findoc-c-official-sources-'))
    sources = json.loads((REPO / 'product/validation/sources.json').read_text())
    semaphore = asyncio.Semaphore(2)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        async def download(source):
            async with semaphore:
                start = time.monotonic()
                result = dict(id=source['id'], url=source['url'], status='failed')
                try:
                    url = httpx.URL(source['url'])
                    if url.scheme != 'https' or url.host not in ALLOWED:
                        raise ValueError('not_official_allowlist')
                    async with client.stream('GET', url) as response:
                        result['http_status'] = response.status_code
                        if response.status_code != 200:
                            raise ValueError('non_success_or_redirect')
                        data = bytearray()
                        async for part in response.aiter_bytes():
                            data.extend(part)
                            if len(data) > 20 * 1024 * 1024:
                                raise ValueError('download_limit')
                    content = bytes(data)
                    if not content.startswith(b'%PDF-'):
                        raise ValueError('not_pdf')
                    digest = hashlib.sha256(content).hexdigest()
                    target = output / (source['id'] + '.pdf')
                    target.write_bytes(content)
                    with pymupdf.open(stream=content, filetype='pdf') as pdf:
                        cover = ''.join(pdf[0].get_text().split())
                        company = '美的集团' if source['id'].startswith('midea') else '格力电器'
                        year = source['id'].split('-')[1]
                        identity = company in cover and year in cover and '年度报告' in cover
                        result.update(pages=len(pdf), cover_identity_match=identity)
                    result.update(status='downloaded', sha256=digest, bytes=len(content),
                                  matches_historical_sha=digest == source['sha256'], local_file=str(target))
                except Exception as exc:
                    result.update(error_type=type(exc).__name__, error_code=str(exc) if isinstance(exc, ValueError) else 'transport_or_parse_error')
                result['elapsed_seconds'] = round(time.monotonic()-start, 3)
                return result
        results = await asyncio.gather(*(download(source) for source in sources))
    manifest = output / 'preflight.json'
    manifest.write_text(json.dumps({'data_level':'PUBLIC_OFFICIAL_PDF_HTTP_NO_LLM',
                                   'results':results}, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'manifest':str(manifest),'results':results}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
