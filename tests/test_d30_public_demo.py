"""The public artifact cannot serve a runtime or execute business requests."""
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading

import pytest

from scripts.serve_d30_public_demo import handler_for, load_package


def package(root: Path):
    raw = b'<!doctype html><p>historical-only</p>'
    (root / 'index.html').write_bytes(raw)
    (root / 'private.env').write_text('must-not-be-served')
    manifest = dict(schema='d30-public-files-v1', files={'index.html': dict(
        bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())})
    (root / 'release-public-manifest.json').write_text(json.dumps(manifest))
    return raw, manifest


def test_http_only_serves_frozen_whitelist_and_never_executes(tmp_path):
    raw, _ = package(tmp_path)
    files = load_package(tmp_path)
    (tmp_path / 'index.html').write_text('changed-on-disk-after-start')
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(files))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def request(method, path):
            connection = HTTPConnection('127.0.0.1', server.server_port)
            connection.request(method, path)
            response = connection.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
            connection.close()
            return result
        status, headers, body = request('GET', '/')
        assert status == 200 and body == raw
        assert "connect-src 'none'" in headers['Content-Security-Policy']
        assert "script-src 'none'" in headers['Content-Security-Policy']
        assert request('HEAD', '/index.html')[2] == b''
        for path in ['/private.env', '/.env', '/api/health', '/api/research/tasks',
                     '/../private.env', '/%2e%2e/private.env', '/%69ndex.html',
                     '/index.html?path=private.env', '//private.env']:
            assert request('GET', path)[0] == 404, path
        for method in ['POST', 'PUT', 'PATCH', 'DELETE', 'TRACE', 'OPTIONS', 'CONNECT']:
            assert request(method, '/api/research/tasks')[0] == 405
            assert request(method, '/index.html')[0] == 405
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_modified_or_symlinked_payload_is_refused(tmp_path):
    raw, manifest = package(tmp_path)
    (tmp_path / 'index.html').write_bytes(raw + b'bad')
    with pytest.raises(ValueError):
        load_package(tmp_path)
    (tmp_path / 'index.html').unlink()
    (tmp_path / 'index.html').symlink_to(tmp_path / 'private.env')
    with pytest.raises(ValueError):
        load_package(tmp_path)
    manifest['files']['../private.env'] = manifest['files'].pop('index.html')
    (tmp_path / 'release-public-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_package(tmp_path)
