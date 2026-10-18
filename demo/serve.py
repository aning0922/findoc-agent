"""Loopback-only, manifest-pinned static rehearsal. Files are loaded once into memory.
Does not serve a filesystem directory and cannot load application modules.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit
from package import HEADERS, HERE, PREFIX, READING, require, spec

TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.png': 'image/png'}
ALIASES = {'/' + PREFIX: '/' + PREFIX + 'index.html', '/' + READING: '/' + READING + 'index.html'}
REDIRECTS = {'/' + PREFIX.rstrip('/'): '/' + PREFIX, '/' + READING.rstrip('/'): '/' + READING}


def load_package(root, artifact_path):
    require(root.is_dir() and not root.is_symlink(), 'Invalid root')
    require(not artifact_path.is_symlink(), 'Symlinked artifact manifest')
    artifact = json.loads(artifact_path.read_bytes())
    require(artifact['schema'] == 'findoc-portfolio-artifact-v1', 'Wrong schema')
    public = artifact['public_files']
    metadata = artifact['hosting_metadata']
    require(set(metadata) == {'_headers', '_redirects'} and not set(public) & set(metadata), 'Invalid metadata')
    require(len(public) == artifact['public_count'] == 22, 'Wrong public count')
    specs = {**public, **metadata}
    require(len(specs) == artifact['deployment_file_count'] == 24, 'Wrong deployment count')
    # Check symlinks including intermediate directories before reading any file.
    actual = set()
    for p in root.rglob('*'):
        require(not p.is_symlink(), 'Symlink in deployment')
        if p.is_file():
            actual.add(p.relative_to(root).as_posix())
    require(actual == set(specs), 'Unexpected or missing deployment file')
    files = {}
    for name, expected in specs.items():
        parts = PurePosixPath(name).parts
        require(bool(parts) and not name.startswith('/') and all(re.fullmatch(r'[a-zA-Z0-9_][a-zA-Z0-9._-]*', x) and x not in ('.', '..') for x in parts), 'Unsafe name')
        require(name in metadata or (name == '404.html' or name.startswith(PREFIX)) and Path(name).suffix in TYPES, 'Outside public namespace')
        raw = (root / name).read_bytes()
        require(spec(raw) == expected, 'Hash mismatch: ' + name)
        if name in public:
            files['/' + name] = raw
    return files


def handler_for(files):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'FinDocStaticRehearsal/1.0'
        sys_version = ''

        def log_message(self, *args):
            pass

        def send(self, status, raw=b'', mime='text/html; charset=utf-8', extra=None, head=False):
            self.send_response(status)
            for key, value in HEADERS.items():
                self.send_header(key, value)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if not head:
                self.wfile.write(raw)

        def reject(self):
            self.send(405, extra={'Allow': 'GET, HEAD'})

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = reject

        def do_HEAD(self):
            self.do_GET(head=True)

        def do_GET(self, head=False):
            url = urlsplit(self.path)
            path = url.path
            valid = not url.query and not url.netloc and not url.scheme and '%' not in path and '\\' not in path
            if valid and path in REDIRECTS:
                self.send(301, extra={'Location': REDIRECTS[path]}, head=head)
                return
            key = ALIASES.get(path, path)
            raw = files.get(key) if valid else None
            if raw is None:
                self.send(404, files['/404.html'], head=head)
                return
            extra = {'Content-Disposition': 'attachment; filename="' + Path(key).name + '"'} if key.endswith('.md') else {}
            self.send(200, raw, TYPES[Path(key).suffix], extra, head)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=HERE / 'site')
    parser.add_argument('--artifact', type=Path, default=HERE / 'artifact-manifest.json')
    parser.add_argument('--port', type=int, default=14406)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(load_package(args.root, args.artifact)))
    print(f'http://127.0.0.1:{server.server_port}/projects/findoc/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
