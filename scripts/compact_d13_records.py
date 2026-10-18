"""Keep all distinct responses, archive raw artifacts locally, omit unused PDF evidence catalogs."""

import hashlib
import json
from pathlib import Path

root = Path.cwd()
archive = root / "data/30d-foundation/d13-raw-records"
archive.mkdir(parents=True, exist_ok=True)
for name in (
    "d13-product-measurements.json",
    "d13-legacy-product-measurements.json",
    "d13-real-comparisons.json",
    "d13-real-analyses.json",
):
    path = root / "product/validation" / name
    raw = path.read_bytes()
    (archive / name).write_bytes(raw)
    counts = {"omitted_whole_pdf_catalog_ids": 0, "identical_response_repeats": 0}

    def compact(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if key == "evidence_ids":
                    # Facts retain every selected amount/basis evidence ID, page and geometry.
                    counts["omitted_whole_pdf_catalog_ids"] += len(item)
                    result["whole_pdf_evidence_catalog_count"] = len(item)
                elif key in ("analyses", "responses") and isinstance(item, list):
                    seen = set()
                    distinct = []
                    for entry in item:
                        identity = json.dumps(entry, sort_keys=True, ensure_ascii=False)
                        if identity in seen:
                            counts["identical_response_repeats"] += 1
                        else:
                            seen.add(identity)
                            distinct.append(compact(entry))
                    result[key] = distinct
                    result[key + "_observed_count"] = len(item)
                else:
                    result[key] = compact(item)
            return result
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value

    value = compact(json.loads(raw))
    value["record_storage"] = dict(
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_local_archive=str((archive / name).relative_to(root)),
        policy="All distinct responses and every selected fact/evidence retained; omit whole-PDF unselected catalogs and identical repeated responses",
        counts=counts,
    )
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(name, counts)
