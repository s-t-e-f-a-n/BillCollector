# -*- coding: utf-8 -*-
"""Recipe index page (``/recipes``).

One row per recipe file: the service name (link to the recipe editor),
the task count, an amber **overlay** badge when the file comes from the
recipe overlay dir (``BC_RECIPE_EXTRA_DIR``), a **valid**/**invalid**
badge (the tooltip carries the first error line), and the **Last
evidence** badge: the newest *conclusive* run of any task of the service
(``success``/``failure``/``needs_attention`` - ``interrupted`` and
``cancelled`` are never evidence) as green **verified** or red
**failing** with the run date, linked to the run's session page
(``/runs/<run_id>``); a service without a conclusive run shows grey
**unverified**. Services that have tasks but no recipe file get a
flagged row (red **no recipe file** badge, task count, no link).

Polling trade-off: the ~2 s refresh re-reads only the evidence column.
The file list and the validation state are computed once on page load -
recipe files change through the editor (which revalidates on save) or
git, and a page refresh revalidates.
"""

from fastapi import Request
from nicegui import ui

from ..db import Database
from ..recipes import list_recipe_files, load_recipe
from .auth import require_auth
from .format import table_column
from .layout import build_layout

# The DB poll interval of the page refresh (the dashboard's ~2 s).
REFRESH_INTERVAL = 2.0

# Run results that are conclusive evidence about a recipe.
CONCLUSIVE_RESULTS = ("success", "failure", "needs_attention")

COLUMNS = [
    table_column("recipe", "Recipe"),
    table_column("tasks", "Tasks", align="right", mono=True),
    table_column("overlay", "Overlay"),
    table_column("valid", "Valid"),
    table_column("evidence", "Last evidence"),
]

# Custom row body: the cells carry links, badges and a tooltip, so they
# render through the QTable body slot (the same runtime-compiler
# constraints as the dashboard's ROW_BODY: no <template v-slot> wrapper,
# no module scope - colors and labels are resolved on the Python side).
ROW_BODY = """
<q-tr :props="props">
  <q-td v-for="col in props.cols" :key="col.name" :props="{ ...props, col: col }">
    <template v-if="col.name === 'recipe'">
      <q-link v-if="props.row.link" :href="'/recipes/' + props.row.link"
              class="no-underline text-blue-700">{{ props.row.name }}</q-link>
      <span v-else class="inline-flex items-center gap-1">
        {{ props.row.name }}
        <q-badge color="red" outline>no recipe file</q-badge>
      </span>
    </template>
    <template v-else-if="col.name === 'overlay'">
      <q-badge v-if="props.row.overlay" color="amber" outline>overlay</q-badge>
    </template>
    <template v-else-if="col.name === 'valid'">
      <q-badge v-if="props.row.valid === null" color="grey" outline>—</q-badge>
      <q-badge v-else :color="props.row.valid ? 'green' : 'red'" outline>
        {{ props.row.valid ? 'valid' : 'invalid' }}
        <q-tooltip v-if="!props.row.valid">{{ props.row.valid_error }}</q-tooltip>
      </q-badge>
    </template>
    <template v-else-if="col.name === 'evidence'">
      <q-link v-if="props.row.evidence_run_id"
              :href="'/runs/' + props.row.evidence_run_id"
              class="no-underline items-center gap-1">
        <q-badge :color="props.row.evidence_color" outline>{{ props.row.evidence }}</q-badge>
        <span class="text-xs font-mono">{{ props.row.evidence_date }}</span>
      </q-link>
      <q-badge v-else color="grey" outline>unverified</q-badge>
    </template>
    <span v-else-if="col.name === 'tasks' && props.row.tasks === 0"
          :class="col.mono ? 'font-mono' : ''" class="text-grey-6">0</span>
    <span v-else :class="col.mono ? 'font-mono' : ''">{{ props.row[col.name] }}</span>
  </q-td>
</q-tr>
"""


def _task_keys(tasks: list[dict]) -> dict[str, list[dict]]:
    """Group the tasks by recipe service key (lowercase, spaces ->
    underscores - the same normalization as ``recipe_path_for``)."""
    grouped: dict[str, list[dict]] = {}
    for task in tasks:
        key = task["service"].lower().replace(" ", "_")
        grouped.setdefault(key, []).append(task)
    return grouped


def _display_name(key: str, grouped: dict[str, list[dict]]) -> str:
    """The Task table's ``service`` string when some task maps to the
    key, else the key with underscores shown as spaces."""
    if key in grouped:
        return grouped[key][0]["service"]
    return key.replace("_", " ")


def _validate(path) -> tuple[bool, str]:
    """The file's validation state: ``(ok, first error line)`` via the
    full gate (``load_recipe`` with ``check_methods=True``)."""
    ok, error, _text, _data = load_recipe(path)
    return (ok, (error or "").split("\n")[0])


def _evidence(db: Database, task_ids: set[int]) -> tuple[str, str, str, int | None]:
    """The service's newest conclusive run as
    ``(label, color, date, run_id)``; ``('unverified', 'grey', '', None)``
    when there is none. ``db.list_runs`` is id-DESC, so the first match
    is the newest."""
    for run in db.list_runs():
        if run["task_id"] in task_ids and run["result"] in CONCLUSIVE_RESULTS:
            label = "verified" if run["result"] == "success" else "failing"
            color = "green" if run["result"] == "success" else "red"
            date = (run["started_at"] or "")[:10]
            return (label, color, date, run["id"])
    return ("unverified", "grey", "", None)


def register_recipe_index(db: Database) -> None:
    """Register the recipe index page (``/recipes``)."""

    @ui.page("/recipes", title="Recipes")
    def recipe_index(request: Request) -> None:
        redirect = require_auth(request)
        if redirect is not None:
            return redirect
        build_layout(active="Recipes")

        ui.label("Recipes").classes("text-h5 font-bold")

        files = list_recipe_files()
        grouped = _task_keys(db.list_tasks())

        # File list, display names and validation: once on page load (the
        # polling trade-off, see the module docstring).
        rows = []
        for key, path, overlay in files:
            valid, valid_error = _validate(path)
            rows.append({
                "key": key,
                "name": _display_name(key, grouped),
                "link": _display_name(key, grouped),
                "tasks": len(grouped.get(key, [])),
                "overlay": overlay,
                "valid": valid,
                "valid_error": valid_error,
            })
        file_keys = {key for key, _p, _o in files}
        for key in sorted(set(grouped) - file_keys):
            rows.append({
                "key": key,
                "name": _display_name(key, grouped),
                "link": None,
                "tasks": len(grouped[key]),
                "overlay": False,
                "valid": None,
                "valid_error": "",
            })

        def refresh_evidence() -> None:
            """DB poll (~2 s): re-read only the Last evidence column."""
            for row in rows:
                task_ids = {t["id"] for t in grouped.get(row["key"], [])}
                row["evidence"], row["evidence_color"], row["evidence_date"], \
                    row["evidence_run_id"] = _evidence(db, task_ids)
            table.rows = rows

        table = ui.table(columns=COLUMNS, rows=rows).classes("w-full")
        table.add_slot("body", ROW_BODY)
        refresh_evidence()
        ui.timer(REFRESH_INTERVAL, refresh_evidence)
