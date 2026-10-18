"""HTTP projection remains independent of the unchanged Run/Result and model budget."""

from contextlib import closing
from unittest.mock import AsyncMock

import pytest

from app.research.models import Result, canonical
from tests.test_d17_history import setup, post  # noqa: F401


def database_rows(h):
    with closing(h.registry._connect()) as c:
        names = [
            r[0]
            for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ]
        return {
            n: sorted([tuple(r) for r in c.execute(f'SELECT * FROM "{n}"')], key=str) for n in names
        }


def test_focus_read_does_not_rewrite_rerun_retrieve_or_publish_a_fact(setup):  # noqa: F811
    h, repo, client, body, adapter, model, *_ = setup
    run = post(setup)
    raw = canonical(repo.get(run["run_id"]).model_dump())
    before = database_rows(h)
    calls = (
        adapter.search.call_count,
        model.generate.call_count,
        h.embedder.call_count,
        h.indexer.call_count,
    )
    for _ in range(2):
        response = client.get("/research/runs/" + run["run_id"] + "/focus")
        assert response.status_code == 200
        projection = response.json()
        assert projection["status"] == "unlocated" and projection["focus"] is None
        assert (
            projection["run_id"] == run["run_id"]
            and projection["run_integrity_sha256"] == run["integrity_sha256"]
        )
        assert response.headers["cache-control"] == "no-store"
    assert canonical(repo.get(run["run_id"]).model_dump()) == raw
    assert database_rows(h) == before
    assert (
        adapter.search.call_count,
        model.generate.call_count,
        h.embedder.call_count,
        h.indexer.call_count,
    ) == calls
    with pytest.raises(ValueError):
        Result.model_validate({**run["result"], "focus": projection})


def test_failed_focus_verification_is_safe_and_does_not_hide_or_modify_history(setup):  # noqa: F811
    h, repo, client, body, adapter, model, selection, preparer, rag = setup
    run = post(setup)
    before = database_rows(h)
    preparer.prepare_many = AsyncMock(side_effect=RuntimeError("SECRET source transport"))
    result = client.get("/research/runs/" + run["run_id"] + "/focus")
    assert result.status_code == 503 and "SECRET" not in result.text
    assert client.get("/research/runs/" + run["run_id"]).json() == run
    assert database_rows(h) == before and model.generate.call_count == 1


def test_invalidated_source_cannot_grant_focus_or_old_pdf_but_history_remains(setup):  # noqa: F811
    h, repo, client, *_ = setup
    run = post(setup)
    h.correct()
    before = database_rows(h)
    projection = client.get("/research/runs/" + run["run_id"] + "/focus")
    assert projection.status_code in (404, 409)
    old = client.get("/research/runs/" + run["run_id"]).json()
    assert old["result"] == run["result"] and old["integrity_sha256"] == run["integrity_sha256"]
    assert old["source_states"][0]["status"] == "expired"
    assert h.query("file", company_id=h.company.company_id).status_code == 404
    assert database_rows(h) == before
