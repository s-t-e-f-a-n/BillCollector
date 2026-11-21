# -*- coding: utf-8 -*-
"""UI tests for the recipe index page (``/recipes``).

Uses ``nicegui.testing.User`` (no browser), the same pattern as the
recipe editor tests: the main file (pytest.ini ``main_file``) builds the
production wiring against a fresh temp DB (``BC_UI_TEST_DB``), and
``config.RECIPE_DIR`` / ``config.RECIPE_EXTRA_DIR`` are pointed at
per-test temp dirs (the repo's recipes are never touched). The seed
covers the badge states: a valid recipe whose newest conclusive run is
a success (verified), a broken YAML file with a failure run (invalid +
failing), a valid recipe with only an interrupted run (unverified -
interrupted is never evidence), a valid recipe that never ran, and a
service with tasks but no recipe file (the flagged row).
"""

import os
import sys
from pathlib import Path

import pytest
from nicegui import ui

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from billcollector import config  # noqa: E402
from billcollector.db import Database  # noqa: E402
from billcollector.ui import auth  # noqa: E402

GOOD_PASSWORD = "ui-test-pass-1"

# The editor suite's proven-valid recipe (full gate: schema + the
# login/variable/method/notice contracts).
RECIPE = """\
$schema: "recipe-pw-schema.yaml"
services:
- serviceName: "SERVICE"
  description: "Full happy path."
  steps:
  - step: 1
    description: "Open the mock site landing page."
    methods:
    - method: "goto"
      arguments:
      - url: "http://127.0.0.1:8787/happy/"
  - step: 2
    description: "Dismiss the cookie banner."
    graceful: true
    methods:
    - method: "get_by_role"
      arguments:
      - role: "button"
      - name: "Reject"
    - method: "click"
"""

# A broken YAML document (the invalid badge's source; the row's
# valid_error carries its first error line).
BROKEN = "steps: [unclosed\n"


def _recipe(service: str) -> str:
    return RECIPE.replace('"SERVICE"', f'"{service}"')


@pytest.fixture
def testdb():
    """A direct connection to the same DB file the main file created."""
    db = Database(path=os.environ["BC_UI_TEST_DB"])
    yield db
    db.close()


async def _login(user, testdb) -> None:
    """Seed the password and authenticate the simulated session."""
    auth.set_password_hash(testdb, auth.hash_password(GOOD_PASSWORD))
    response = await user.http_client.post(
        "/login", data={"password": GOOD_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def _seed_files(tmp_path, monkeypatch, broken=()) -> Path:
    """The temp RECIPE_DIR with one recipe file per seeded service
    (the keys in ``broken`` carry the broken YAML document instead)."""
    recipe_dir = tmp_path / "recipes"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "RECIPE_DIR", recipe_dir)
    monkeypatch.setattr(config, "RECIPE_EXTRA_DIR", None)
    for key in ("svc-a", "svc-b", "svc-c", "svc-d"):
        text = BROKEN if key in broken else _recipe(key)
        (recipe_dir / config.recipe_filename_for(key)).write_text(
            text, encoding="utf-8")
    return recipe_dir


def _seed_tasks(testdb) -> dict:
    """One task per service key plus the file-less svc-e. The evidence
    states come from fixed started_at stamps: svc-a's newest conclusive
    run is a success (the older failure must not win), svc-b a failure,
    svc-c only an interrupted run, svc-d none, svc-e a success."""
    ids = {}
    for key in ("svc-a", "svc-b", "svc-c", "svc-d", "svc-e"):
        ids[key] = testdb.create_task(key, "user1", enabled=True)
    run_a1 = testdb.create_run(ids["svc-a"])
    testdb.update_run(run_a1, started_at="2026-10-09 08:00:00",
                      ended_at="2026-10-09 08:04:00", result="failure")
    run_a2 = testdb.create_run(ids["svc-a"])
    testdb.update_run(run_a2, started_at="2026-10-11 08:00:00",
                      ended_at="2026-10-11 08:04:00", result="success")
    run_b = testdb.create_run(ids["svc-b"])
    testdb.update_run(run_b, started_at="2026-10-10 09:00:00",
                      ended_at="2026-10-10 09:05:00", result="failure")
    run_c = testdb.create_run(ids["svc-c"])
    testdb.update_run(run_c, started_at="2026-10-10 10:00:00",
                      ended_at="2026-10-10 10:02:00", result="interrupted")
    run_e = testdb.create_run(ids["svc-e"])
    testdb.update_run(run_e, started_at="2026-10-12 08:00:00",
                      ended_at="2026-10-12 08:03:00", result="success")
    return {"ids": ids, "run_a1": run_a1, "run_a2": run_a2,
            "run_b": run_b, "run_c": run_c, "run_e": run_e}


def _table_rows(user) -> list[dict]:
    """The recipe index table's rows (the single ui.table on the page)."""
    (table,) = user.find(kind=ui.table).elements
    return table.rows


async def test_rows_badges_and_evidence(user, testdb, tmp_path, monkeypatch):
    """One row per recipe file (key order) then the file-less service:
    the valid/invalid badges with the first error line, the evidence
    badges (verified / failing / unverified with the run date and the
    ``/runs/<id>`` row target), and the no-recipe-file row."""
    _seed_files(tmp_path, monkeypatch, broken={"svc-b"})
    seed = _seed_tasks(testdb)
    await _login(user, testdb)
    await user.open("/recipes")

    rows = _table_rows(user)
    # Files first (sorted by key), then the no-recipe-file service.
    assert [r["key"] for r in rows] == \
        ["svc-a", "svc-b", "svc-c", "svc-d", "svc-e"]
    by_key = {r["key"]: r for r in rows}

    row_a = by_key["svc-a"]
    assert row_a["name"] == "svc-a"
    assert row_a["link"] == "svc-a"
    assert row_a["tasks"] == 1
    assert row_a["overlay"] is False
    assert row_a["valid"] is True
    # The newest conclusive run wins: the success over the older failure.
    assert row_a["evidence"] == "verified"
    assert row_a["evidence_color"] == "green"
    assert row_a["evidence_date"] == "2026-10-11"
    assert row_a["evidence_run_id"] == seed["run_a2"]

    row_b = by_key["svc-b"]
    assert row_b["valid"] is False
    assert row_b["valid_error"].startswith("invalid YAML")
    assert row_b["evidence"] == "failing"
    assert row_b["evidence_color"] == "red"
    assert row_b["evidence_date"] == "2026-10-10"
    assert row_b["evidence_run_id"] == seed["run_b"]

    # An interrupted run is never evidence; svc-d never ran.
    assert by_key["svc-c"]["valid"] is True
    assert by_key["svc-c"]["evidence"] == "unverified"
    assert by_key["svc-c"]["evidence_run_id"] is None
    assert by_key["svc-d"]["evidence"] == "unverified"

    # The file-less service: the flagged row (no link, no validation)
    # still carries its evidence from the task's runs.
    row_e = by_key["svc-e"]
    assert row_e["link"] is None
    assert row_e["tasks"] == 1
    assert row_e["valid"] is None
    assert row_e["overlay"] is False
    assert row_e["evidence"] == "verified"
    assert row_e["evidence_run_id"] == seed["run_e"]


async def test_overlay_file_shadows_the_builtin(user, testdb, tmp_path,
                                                monkeypatch):
    """A recipe file in RECIPE_EXTRA_DIR shadows the built-in file of
    the same key: one row for the key (not two), the overlay flag, and
    the validation of the overlay file (the built-in is broken here, so
    a row validating the built-in would be invalid)."""
    _seed_files(tmp_path, monkeypatch, broken={"svc-a"})
    _seed_tasks(testdb)
    extra = tmp_path / "recipes-extra"
    extra.mkdir()
    (extra / config.recipe_filename_for("svc-a")).write_text(
        _recipe("svc-a"), encoding="utf-8")
    monkeypatch.setattr(config, "RECIPE_EXTRA_DIR", extra)

    await _login(user, testdb)
    await user.open("/recipes")

    rows = _table_rows(user)
    assert [r["key"] for r in rows] == \
        ["svc-a", "svc-b", "svc-c", "svc-d", "svc-e"]
    (row_a,) = (r for r in rows if r["key"] == "svc-a")
    assert row_a["overlay"] is True
    assert row_a["valid"] is True
    assert row_a["evidence"] == "verified"


async def test_empty_table_when_no_files_or_tasks(user, testdb, tmp_path,
                                                  monkeypatch):
    """No recipe files and no tasks: an empty table."""
    recipe_dir = tmp_path / "recipes-empty"
    recipe_dir.mkdir()
    monkeypatch.setattr(config, "RECIPE_DIR", recipe_dir)
    monkeypatch.setattr(config, "RECIPE_EXTRA_DIR", None)

    await _login(user, testdb)
    await user.open("/recipes")
    assert _table_rows(user) == []


async def test_unauthenticated_request_redirects_to_login(user):
    response = await user.http_client.get("/recipes", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_row_links_use_native_anchors():
    """The row body's links must be native <a> elements, not q-link.

    The browserless User simulation never compiles the client template, so
    it cannot catch an unresolved Quasar component: NiceGUI's bundled
    Quasar UMD does not export QLink, and a q-link in the runtime-compiled
    body slot rendered as an inert custom element in the browser (no link
    behavior, no hover affordance).
    """
    from billcollector.ui.recipe_list import ROW_BODY

    assert "<q-link" not in ROW_BODY
    # The service-name link (editor) and the evidence link (run page).
    assert ROW_BODY.count("<a v-if=") == 2
    assert "'/recipes/' + props.row.link" in ROW_BODY
    assert "'/runs/' + props.row.evidence_run_id" in ROW_BODY


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
