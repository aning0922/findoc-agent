"""Exact-scope read-only discovery; simulated receipts never gain production rights."""

import json
import sqlite3
from unittest.mock import Mock
import pytest
from tests.test_financial_reviews import financial_harness, preview, accept_payload
from tests.test_d10_financial_facts import persist


def logical_state(h):
    with sqlite3.connect(h.db) as c:
        return {
            name: sorted(c.execute(f'SELECT * FROM "{name}"').fetchall(), key=str)
            for (name,) in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


def discovered(h, **changes):
    return h.client.get(
        "/financial-facts/acceptances", params={**h.selection, **changes}
    )


def accepted(h, identity):
    r = h.client.post(
        "/financial-facts/confirmations",
        json=accept_payload(h, preview(h), request_id=identity),
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_discovery_lists_all_exact_receipts_without_selection_extraction_or_writes(
    tmp_path,
):
    h = financial_harness(tmp_path)
    a, b = accepted(h, "d29-first"), accepted(h, "d29-second")
    assert persist(h, a).status_code == 200
    state = logical_state(h)
    h.candidates.collect_metrics = Mock(
        side_effect=AssertionError("read must not extract")
    )
    r = discovered(h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert (
        data["schema"] == "financial-acceptance-discovery-v1"
        and data["automatic_selection"] is False
    )
    assert {x["receipt_id"] for x in data["items"]} == {
        a["receipt_id"],
        b["receipt_id"],
    }
    assert {x["request_id"] for x in data["items"]} == {"d29-first", "d29-second"}
    assert all(x["confirmation_kind"] == "simulated_test" for x in data["items"])
    assert logical_state(h) == state
    assert (
        h.client.get("/financial-facts/persisted/" + b["receipt_id"]).status_code == 404
    )
    assert (
        h.client.get("/financial-facts/persisted/" + a["receipt_id"]).json()[
            "production_calculable"
        ]
        is False
    )


@pytest.mark.parametrize(
    "scope",
    [
        dict(periods=[2031]),
        dict(metric_keys=["revenue"]),
        dict(source_revision="0" * 64),
    ],
)
def test_discovery_does_not_guess_different_scope(tmp_path, scope):
    h = financial_harness(tmp_path)
    accepted(h, "d29-scope")
    state = logical_state(h)
    r = discovered(h, **scope)
    if "source_revision" in scope:
        assert r.status_code == 409
    else:
        assert r.status_code == 200 and r.json()["items"] == []
    assert logical_state(h) == state


def test_discovery_isolates_workspace_kind_and_revocation(tmp_path):
    h = financial_harness(tmp_path)
    a = accepted(h, "d29-isolation")
    for workspace, kind in [("other", "simulated_test"), ("demo", "local_operator")]:
        assert (
            h.receipts.acceptance_ids_for_scope(
                workspace_id=workspace,
                confirmation_kind=kind,
                **{k: v for k, v in h.selection.items() if k != "review_schema"},
            )
            == ()
        )
    # D19 app migration supplies the revocation ledger. Make its canonical table
    # in this older D9 fixture; only test writes the fixture, GET remains read-only.
    with sqlite3.connect(h.db) as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS financial_acceptance_revocations (workspace_id TEXT, receipt_id TEXT, confirmation_kind TEXT, revoked_at TEXT, reason TEXT)"
        )
        c.execute(
            "INSERT INTO financial_acceptance_revocations VALUES (?,?,?,?,?)",
            (
                "demo",
                a["receipt_id"],
                "simulated_test",
                a["accepted_at"],
                "test revoked",
            ),
        )
    state = logical_state(h)
    r = discovered(h)
    assert r.status_code == 200 and r.json()["items"] == []
    assert logical_state(h) == state


def test_discovery_rejects_corrupted_receipt_and_invalid_selection(tmp_path):
    h = financial_harness(tmp_path)
    a = accepted(h, "d29-corruption")
    assert discovered(h, periods=[2031, 2031]).status_code == 422
    with sqlite3.connect(h.db) as c:
        c.execute("DROP TRIGGER IF EXISTS immutable_financial_acceptance_update")
        triggers = c.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='financial_acceptance_receipts'"
        ).fetchall()
        for (name,) in triggers:
            c.execute(f'DROP TRIGGER "{name}"')
        review = a["review"]
        review["candidates"][0]["value_cny_yuan"] = "99999"
        c.execute(
            "UPDATE financial_acceptance_receipts SET review_json=? WHERE receipt_id=?",
            (json.dumps(review), a["receipt_id"]),
        )
    state = logical_state(h)
    r = discovered(h)
    assert (
        r.status_code == 500
        and r.json()["detail"]["code"] == "confirmation_integrity_error"
    )
    assert logical_state(h) == state
