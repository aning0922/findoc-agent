"""D29 disposable assembly. Real HTTP/SQLite/PDF; simulated acceptance only."""

import json
import os
from pathlib import Path
import sys
import hashlib
import sqlite3
from urllib.parse import unquote, urlparse


def create_d29_app():
    runtime = Path(os.environ["FINDOC_UX_RUNTIME_ROOT"]).resolve()
    allowed = Path(os.environ["D29_ALLOWED_WORKTREE"]).resolve()
    protected = tuple(
        str(p.resolve()) + os.sep
        for p in allowed.parent.glob("findoc-*")
        if p.resolve() != allowed
    )

    def guard(event, args):
        if event == "socket.connect":
            raise RuntimeError("D29 rejects outgoing service connections")
        if event == "sqlite3.connect" and args[0] != ":memory:":
            value = args[0]
            path = Path(
                unquote(urlparse(value).path)
                if str(value).startswith("file:")
                else value
            ).resolve()
            if not path.is_relative_to(runtime):
                raise RuntimeError("D29 rejects foreign SQLite")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = str(Path(os.fsdecode(args[0])).resolve())
            if any(path.startswith(p) or path == p[:-1] for p in protected):
                raise RuntimeError("D29 rejects protected worktree access")

    sys.addaudithook(guard)
    from tests.support.ux_v21_app import create_ux_v21_app

    app = create_ux_v21_app()
    log = runtime / "http.jsonl"

    @app.get('/__test__/d29-readonly-state')
    async def readonly_state():
        # Evidence only, in the guarded disposable app. Hash every persisted table.
        with sqlite3.connect(f'file:{runtime / "documents.db"}?mode=ro', uri=True) as c:
            names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {name: hashlib.sha256(json.dumps(sorted(c.execute(f'SELECT * FROM "{name}"').fetchall(), key=str), default=str).encode()).hexdigest() for name in names}

    @app.middleware("http")
    async def audit(request, call_next):
        response = await call_next(request)
        with log.open("a") as file:
            file.write(
                json.dumps(
                    dict(
                        method=request.method,
                        path=request.url.path,
                        query=request.url.query,
                        status=response.status_code,
                    )
                )
                + "\n"
            )
        return response

    return app
