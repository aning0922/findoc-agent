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
    parser.add_argument(
        "--manual-existing-sha",
        action="append",
        default=[],
        help="Root explicitly approved manual upload to an existing exact registry company only",
    )
    args = parser.parse_args()
    manifest = json.loads(args.input_manifest.read_text())
    if isinstance(manifest, dict):
        if (
            set(manifest) != {"schema_version", "files"}
            or manifest["schema_version"] != "cplus-public-seed-additions-v1"
        ):
            raise ValueError("invalid_input_manifest_schema")
        manifest = manifest["files"]
    result = asyncio.run(
        build_additive_seed(
            args.base,
            args.destination,
            manifest,
            manual_existing_shas=args.manual_existing_sha,
            bundle_path=args.bundle,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
