from copy import deepcopy
import hashlib
import io
import tarfile

import pytest
from app.cplus_seed.curate_financial import choose_current, verify_bundle


def cell(year=2025):
    return dict(
        metric_key="revenue",
        time=dict(
            kind="duration",
            period_start=f"{year}-01-01",
            period_end=f"{year}-12-31",
            period_type="annual",
        ),
        basis="PRC_GAAP",
        scope="consolidated",
        currency="CNY",
        normalized_unit="CNY_YUAN",
        source_kind="fast_text",
        financial_review="unconfirmed",
        extraction_status="candidate",
        normalized_decimal="170447058533.57",
    )


def test_current_year_only_unique_unconfirmed_comparable():
    current = cell()
    previous = cell(2024)
    chosen, missing = choose_current([previous, current], 2025)
    assert chosen == [current] and len(missing) == 4
    assert choose_current([current, deepcopy(current)], 2025)[0] == []
    assert choose_current([{**current, "basis": "unknown"}], 2025)[0] == []
    assert choose_current([{**current, "financial_review": "confirmed"}], 2025)[0] == []


def test_bundle_hashes_payload_and_manifest(tmp_path):
    manifest_raw = b"manifest content"
    candidate_raw = b"candidate content"

    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    manifest = {"files": [{"path": "candidate.json", "sha256": digest(candidate_raw)}]}
    bundle = tmp_path / "seed.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        for name, raw in (("manifest.json", manifest_raw), ("candidate.json", candidate_raw)):
            member = tarfile.TarInfo("showcase-cplus-seed-v3/" + name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    assert verify_bundle(bundle, manifest, digest(manifest_raw)) == 2
    with pytest.raises(ValueError, match="bundle_file_checksum_failed"):
        verify_bundle(bundle, manifest, "0" * 64)
    changed = {"files": [{"path": "candidate.json", "sha256": digest(b"changed")}]}
    with pytest.raises(ValueError, match="bundle_file_checksum_failed"):
        verify_bundle(bundle, changed, digest(manifest_raw))
