"""Build a NEW synthetic mechanism seed; never reads an existing runtime or PDFs."""
import argparse
import json
from pathlib import Path

from app.demo.seed import build_synthetic_seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest, digest = build_synthetic_seed(args.destination.resolve())
    print(json.dumps({"manifest_sha256": digest, "seed_version": manifest["seed_version"],
                      "complete_product_seed": False, "data_origin": manifest["data_origin"]}))


if __name__ == "__main__":
    main()
