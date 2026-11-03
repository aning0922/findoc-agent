"""Private server diagnostics without exception messages, values or provider headers."""
import logging
from pathlib import Path
import traceback


def safe_failure(domain,exc):
    frames=[f'{Path(f.filename).name}:{f.lineno}:{f.name}' for f in traceback.extract_tb(exc.__traceback__)]
    logging.getLogger('findoc.cplus').error('%s failed type=%s frames=%s',domain,type(exc).__name__,frames)
