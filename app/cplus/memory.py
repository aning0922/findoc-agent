"""C+ read adapter: a generation check must coexist with publication SHARED locks."""
from contextlib import closing
import sqlite3
from app.research_memory.service import MemoryError


class CPlusMemoryView:
    def __init__(self,base):
        self.base=base

    def __getattr__(self,name):
        return getattr(self.base,name)

    def check_generation(self,expected):
        if type(expected) is not int or expected<0:
            raise MemoryError('invalid_memory_generation',422)
        with closing(sqlite3.connect(self.base.path.resolve().as_uri()+'?mode=ro',uri=True,
                                     timeout=5,isolation_level=None)) as db:
            db.row_factory=sqlite3.Row
            db.execute('BEGIN')
            value=self.base._generation(db)
            db.execute('ROLLBACK')
        if value!=expected:
            raise MemoryError('memory_context_changed')
        return value
