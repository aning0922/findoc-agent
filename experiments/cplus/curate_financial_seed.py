"""Create a new v3 preset-candidate seed; never writes financial-service databases."""

import argparse
import json
from pathlib import Path
from app.cplus_seed.curate_financial import build_curated_seed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--proof-json", type=Path, required=True)
    args = parser.parse_args()
    if args.proof_json.exists():
        raise FileExistsError("proof_output_exists")
    proof = build_curated_seed(args.parent, args.destination, args.bundle)
    with args.proof_json.open("x") as out:
        json.dump(proof, out, ensure_ascii=False, indent=2)
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
