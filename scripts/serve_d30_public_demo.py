"""Loopback-only static allowlist server. No app, DB, proxy or model imports."""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlsplit


def load_package(root):
    root = root.resolve()
    manifest_path = root / 'release-public-manifest.json'
    if manifest_path.is_symlink():
        raise ValueError('symlinked manifest')
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest['schema'] != 'd30-public-files-v1':
        raise ValueError('unknown public manifest schema')
    files = {}
    for name, expected in manifest['files'].items():
        if '/' in name or '\\' in name or name in ('.', '..'):
            raise ValueError('invalid public filename')
        if Path(name).suffix not in ('.html', '.css', '.md', '.json'):
            raise ValueError('unsupported public file type')
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('public payload is missing or symlinked')
        raw = path.read_bytes()
        if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError('public payload hash mismatch: ' + name)
        files['/' + name] = raw
    files['/release-public-manifest.json'] = manifest_bytes
    files['/'] = files['/index.html']
    return files


def handler_for(files):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reject_method(self):
            self.send_response(405)
            self.send_header('Allow', 'GET, HEAD')
            self.send_header('Content-Length', '0')
            self.end_headers()

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = reject_method

        def do_HEAD(self):
            self.do_GET(head=True)

        def do_GET(self, head=False):
            url = urlsplit(self.path)
            path = unquote(url.path)
            raw = files.get(path) if not url.query and path == url.path else None
            self.send_response(200 if raw is not None else 404)
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'self'; script-src 'none'; connect-src 'none'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Type', mimetypes.guess_type(path)[0] or ('text/html' if path == '/' else 'application/octet-stream'))
            self.send_header('Content-Length', str(len(raw) if raw is not None else 0))
            if path.endswith('.md'):
                self.send_header('Content-Disposition', f'attachment; filename="{path[1:]}"')
            self.end_headers()
            if raw is not None and not head:
                self.wfile.write(raw)
    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--port', type=int, default=14290)
    args = p.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(load_package(args.root)))
    print(f'http://127.0.0.1:{server.server_port} · isolated static history', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
