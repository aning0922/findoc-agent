"""Real SQLite lock interaction in disposable synthetic memory, no provider."""
import sqlite3
from threading import Thread
import pytest
from app.cplus.memory import CPlusMemoryView
from app.research_memory.service import MemoryError
from tests.test_research_memory import make
from tests.test_document_sources import Harness


def test_read_generation_inside_publication_fence_without_write_escalation(tmp_path):
    memory=make(Harness(tmp_path))
    view=CPlusMemoryView(memory)
    generation=view.check_generation(0)
    outcomes=[]
    with memory.publication_guard(generation):
        assert view.check_generation(generation)==generation
        def writer():
            try:
                with sqlite3.connect(memory.path,timeout=.05) as db:
                    db.execute("UPDATE generation SET value=value+1 WHERE workspace='demo'")
                outcomes.append('committed')
            except sqlite3.OperationalError:
                outcomes.append('blocked')
        thread=Thread(target=writer)
        thread.start()
        thread.join(1)
        assert not thread.is_alive() and outcomes==['blocked']
        assert view.check_generation(generation)==generation
    with sqlite3.connect(memory.path) as db:
        db.execute("UPDATE generation SET value=value+1 WHERE workspace='demo'")
    with pytest.raises(MemoryError,match='memory_context_changed'):
        view.check_generation(generation)
