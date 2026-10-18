"""Read-only D23 HTTP entry: python scripts/run_report_history.py /path/documents.db."""

import argparse
from pathlib import Path
import sys
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.api.report_history import create_report_history_app  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--workspace", default="demo")
    parser.add_argument("--port", type=int, default=18091)
    args = parser.parse_args()
    uvicorn.run(
        create_report_history_app(args.database, args.workspace), host="127.0.0.1", port=args.port
    )
