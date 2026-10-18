"""Read-only audit of every extant D19/D20 isolated task and checkpoint; no migration."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from app.research.task_repository import TaskRepository  # noqa: E402
from app.research.task_checkpointer import TaskCheckpointer  # noqa: E402

rows = []
base = Path(tempfile.gettempdir())
for folder in sorted([*base.glob('findoc-d19-*'), *base.glob('findoc-d20-*')]):
    for db in folder.rglob('documents.db'):
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        def connect():
            conn = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        with closing(connect()) as conn:
            if not conn.execute("SELECT name FROM sqlite_master WHERE name='template_tasks'").fetchone():
                continue
            tasks = conn.execute('SELECT * FROM template_tasks').fetchall()
            checked = 0
            invalid = []
            checkpoints = 0
            for task in tasks:
                repo = TaskRepository(SimpleNamespace(_connect=connect), task['workspace_id'])
                try:
                    value = repo.decode(task)
                    if value['schema_version'] != 'persistent-template-task-v1':
                        continue
                    checked += 1
                    saver = TaskCheckpointer(repo, task['task_id'], 'readonly-audit')
                    for table in ('template_checkpoints', 'template_checkpoint_writes'):
                        for row in conn.execute(f'SELECT * FROM {table} WHERE task_id=?', (task['task_id'],)):
                            saver.unpack(row)
                            checkpoints += 1
                    if value['waiting_checkpoint']:
                        assert saver.get_tuple(saver.config('') | {'configurable': {'thread_id':task['task_id']}})
                except Exception as exc:
                    invalid.append(dict(task_id=task['task_id'], error=type(exc).__name__))
        after = hashlib.sha256(db.read_bytes()).hexdigest()
        assert before == after
        if tasks:
            rows.append(dict(database=str(db), tasks=len(tasks), valid_v1=checked,
                             checkpoints_and_writes=checkpoints, invalid=invalid,
                             bytes_unchanged=True, sha256=after))
proof = dict(databases=rows, valid_v1=sum(r['valid_v1'] for r in rows),
    checkpoint_records=sum(r['checkpoints_and_writes'] for r in rows), read_only=True,
    invalid_records=[r for r in rows if r['invalid']], note='Includes intentionally corrupted regression databases; no repair or upgrade.')
(root / 'product/validation/d21-a-v1-history.json').write_text(json.dumps(proof, indent=2)+'\n')
print(json.dumps(dict(valid_v1=proof['valid_v1'], checkpoints=proof['checkpoint_records'],
                     deliberately_corrupt_databases=len(proof['invalid_records']))))
assert proof['valid_v1'] > 0
