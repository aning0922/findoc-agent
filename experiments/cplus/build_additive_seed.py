"""Offline additive public seed builder. Never consumes an active runtime."""

import argparse
import asyncio
import json
from pathlib import Path
from app.cplus_seed import build_additive_seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    result = asyncio.run(
        build_additive_seed(
            args.base,
            args.destination,
            json.loads(args.input_manifest.read_text()),
            bundle_path=args.bundle,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
