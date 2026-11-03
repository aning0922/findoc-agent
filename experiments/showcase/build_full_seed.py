"""Freeze selected public demo histories from a stopped disposable HTTP runtime; zero LLM."""

import argparse
import json
from pathlib import Path

from app.showcase_seed.build import build_full_seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--public-allowlist", type=Path, required=True)
    parser.add_argument("--seed-version", required=True)
    parser.add_argument("--job-id", action="append", required=True)
    parser.add_argument("--report-id", action="append", default=[])
    parser.add_argument("--conversation-id", action="append", default=[])
    parser.add_argument("--memory-id", action="append", default=[])
    parser.add_argument("--preference-key", action="append", default=[])
    parser.add_argument("--complete-product-seed", action="store_true")
    args = parser.parse_args()
    result = build_full_seed(
        args.source,
        args.destination,
        public_allowlist=json.loads(args.public_allowlist.read_text()),
        job_ids=args.job_id,
        report_ids=args.report_id,
        conversation_ids=args.conversation_id,
        memory_ids=args.memory_id,
        preference_keys=args.preference_key,
        seed_version=args.seed_version,
        complete_product_seed=args.complete_product_seed,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
