"""D30 production integration in an exclusively new root; no human actions.

Reuse the audited D28 lifecycle/observer without reading its runtime or receipts.
This CLI deliberately has no accept, save-facts, resume or save-report command.
"""
import argparse
import json
from pathlib import Path
import time

from scripts.d28_demo import prepare, qa, serve, write

BASE = "ec4d624ed4c933e0d7ccebe246fda2acb5b2855e"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "serve", "prepare", "qa"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--hf-home", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--reports", type=Path)
    parser.add_argument("--api-port", type=int, default=18180)
    parser.add_argument("--web-port", type=int, default=14280)
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    marker = root / "d30-root.json"
    if args.action == "init":
        root.mkdir(parents=True, exist_ok=False)
        write(marker, dict(schema="d30-clean-root-v1", root=str(root), baseline=BASE,
                           created_at=time.time(), copied_business_data=False,
                           human_acceptance="pending"))
        print(json.dumps(dict(root=str(root), empty=True)))
        return
    identity = json.loads(marker.read_text())
    if identity["schema"] != "d30-clean-root-v1" or identity["root"] != str(root):
        raise ValueError("D30 root identity mismatch")
    if args.action == "serve":
        if not args.credentials:
            parser.error("serve needs an external --credentials path")
        serve(args, root)
        return
    if not args.out:
        parser.error("evidence needs an unused --out directory")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    import httpx
    with httpx.Client(base_url=f"http://127.0.0.1:{args.web_port}/api", timeout=240,
                      trust_env=False) as client:
        client.get("/health").raise_for_status()
        if args.action == "prepare":
            prepare(root, client, out)
        else:
            if not args.reports or not args.reports.is_file():
                parser.error("qa needs this runtime's preparation --reports evidence")
            qa(root, client, out, args.reports)


if __name__ == "__main__":
    main()
