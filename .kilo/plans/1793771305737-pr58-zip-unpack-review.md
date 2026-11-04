# PR #58 — review: opt-in bounded single-PDF ZIP extraction

> Status: INTEGRATING (2026-11-04) — S4 applied on dev: all 8 candidate files
> + M1 in the working tree, left dirty for S5 (dev was `f467760`, clean, at
> S4 start); S5 next session validates the exact dirty tree before any commit.

## PR metadata

| Field | Value |
|---|---|
| Title | Add opt-in bounded single-PDF ZIP extraction |
| Author | flowcool |
| Head | `d97d7f324951d343e275db2b1b7cb01a5da0f6b6` (`feature/upstream-zip-s7hrk`), fetched 2026-11-04 as `refs/pr/58`; matches the API head at review time |
| Base (labeled) | `main` @ `24eaa5212459328bc82002d1fe4de21cb9dd6245` (current public tip = PR #57 mirror delivery) |
| Fork point / merge-base | `df634cccadd5c99a49f0c4bee9abfe3629cffd53` (public tip at the PR #44 delivery) |
| Issue refs | #50 (phase b — two-phase split agreed in #50) |
| Created / last head update | 2026-11-01T18:39:37Z / 2026-11-03T22:58:41Z (head `d97d7f3`) |
| PR commits (3) | `4a9bffc` doc (orphaned sanitized tip — see F3), `6e33190` feat: bounded single-PDF ZIP unpacking, `d97d7f3` fix: keep ZIP unpacking scoped to download_all |
| GitHub-reported diff | 110 files, +525 / −25651 — **fork-behind-base artifact**; real content is 8 files, +492 / −4 (see classification) |
| Claimed evidence | `BILLCOLLECTOR_BROWSER_TESTS=1 pytest tests/test_bc_archives.py -q` → 16 tests + 33 subtests, no skips; review correction proof: archives+collection+calendar+recipes → 101 + 33; `run_regression.py --ini tests/bc_regression.ini` → VERDICT: PASS (7 pairs / 8 files); `ruff check apps tests` clean incl. fork's 0.17.1 pin; Bandit 1.9.4 = public baseline, no new medium/high; AI: Codex (disclosed); no vault/provider access |

### Local state at review time (2026-11-04)

- Gitea `dev` = `origin/dev` = `c1ab80a` (PR #57 delivery + plans cleanup); working tree clean.
- Gitea `main` = `4bd0f92`; GitHub `main` = `24eaa52` (PR #57 mirror tip, sanitized).

## Verdict

**Approve.** The feature is opt-in, additive, and fail-closed by construction:
complete bounded validation happens before any persistence callback runs, the
default download path is byte-for-byte untouched (`nullcontext` passthrough),
and the persistence adapters see a minimal download stand-in with exactly the
three attributes they use. Integration needs standard manual 3-way merges
(CHANGELOG, README, RECIPE_METHODS, collection.py) because `dev` moved past
the fork point — all resolutions are additive and change no PR intent. One
optional maintainer-side hardening (M1, basename length cap) is proposed for
the S3 gate.

## Verified facts

- **F1 — Head stable.** Fetched `refs/pr/58` = `d97d7f3…` = API head; no move
  since the 2026-11-03T22:58Z update.
- **F2 — Fork point.** Merge-base `df634cc` is an ancestor of `github/main`
  (public tip of the PR #44 delivery, 2026-11-01).
- **F3 — Orphaned public-history commit.** PR commit `4a9bffc`
  ("doc: method-chain contract, README validation note, changelog (C3, issue #27)")
  is **not** in the current public lineage. It is exactly the sanitized PR #44
  delivery tip: its tree = Gitea `26377b0` minus the STRIP paths (verified:
  `git diff 26377b0 4a9bffc` = 102 files, 25627 deletions, all `openwiki/` +
  private paths). The mirror rewrites history on every sync (full Gitea history
  + sanitized tip, `sync_github.sh` force-push), so the fork's base commit was
  orphaned by later syncs. Its content (C3 docs) is already on public `main`
  via `26377b0`. The 110-file/−25651 GitHub diff is the same artifact plus the
  PR #57 mirror commits (`24eaa52`/`ca72481`) the fork predates.
- **F4 — Real content.** `git diff 4a9bffc..refs/pr/58` = exactly 8 files,
  +492 / −4.
- **F5 — Pre-image checks vs `dev` `c1ab80a`.** 2 clean adds
  (`apps/billcollector/archives.py`, `tests/test_bc_archives.py`); 2 clean
  auto 3-way merges (0 conflicts: `recipe-pw-schema.yaml`,
  `doc/RECIPE_AUTHORING.md`); 4 manual 3-way merges, all additive
  (CHANGELOG 1, README 1, RECIPE_METHODS 2, collection.py 3 conflicts —
  adjacent-line, keep-both; no semantic collision).
- **F6 — Adapter interface.** `downloads.track_download` (downloads.py:219)
  uses exactly `download.suggested_filename`, `download.url`,
  `download.save_as(str)` (lines 232/238/245/254) — `_PDFDownload` provides
  all three; the plain-basename guard (downloads.py:233) is defense-in-depth
  over `_member_name`.
- **F7 — Calendar scoping.** Runtime calendar validator
  (calendar.py:71-74) already rejects any `download_options` key beyond the
  four base keys (message "calendar download options are invalid") — the PR's
  schema `not: required: [unpack]` aligns the raw schema with it; the PR test
  asserts exactly this behavior.
- **F8 — Metadata bound verified.** Replicated `_BoundedZipReader` in a
  throwaway script: 100/1000/4000 tiny members parse; 6000/10000 →
  `ValueError: ZIP metadata exceeds the read bound` before persistence. The
  bound is per individual read (stdlib reads the central directory in a few
  large reads, so total metadata read is effectively capped near ~2× the
  bound); the PR pins the 6000-member rejection in its test suite.
- **F9 — Test dependency.** `pypdf==6.21.2` is already declared
  (apps/requirements.txt:41) and installed in `apps/.venv`.
- **F10 — Test helpers.** `_Listing` / `_Page` / `_Events` exist on `dev`
  (tests/test_bc_collection.py:220/83/31); the PR does not modify
  `test_bc_collection.py`, so the import resolves on the dev tree.
- **F11 — Doc anchors.** `doc/RECIPE_AUTHORING.md#pagination-empty-lists-and-downloads`
  resolves (heading "Pagination, empty lists and downloads" on both PR and
  dev); RECIPE_METHODS relative link `RECIPE_AUTHORING.md#…` is valid.
- **F12 — Cross-PR.** PR #58 is the only open PR (verified via API 2026-11-04).
- **F13 — Hygiene.** `git diff --check 4a9bffc refs/pr/58` clean; no CRLF
  issues; no PR file under `.kilo/`, `.private/`, `.vscode/`, `openwiki/`,
  `AGENTS.md`, `.openwikiignore`, or `.github/workflows/`.
- **F14 — Secrets.** Manual review of the full real diff (GitHub Advanced
  Security unavailable on the repo): synthetic `*.invalid` domain, explicit
  fake token, no credentials/keys in code or tests.
- **F15 — Deployment relevance.** None: the PR touches only
  `apps/billcollector/{archives,collection}.py`, the recipe schema, docs and
  tests — no `Dockerfile`, `.dockerignore`, `BillCollector.sh`,
  `install_docker-image.sh`, `deploy_remote.sh`, INI keys, or `.env` handling.

## Code review findings

### apps/billcollector/archives.py (new, 104 lines)

- `_BoundedZipReader` (L24-32): wraps the raw file with a 256 KiB per-read cap
  for ZIP metadata. Verified behavior in F8.
- `_PDFDownload` (L34-45): frozen dataclass carrying `url`,
  `suggested_filename`, `source`; `save_as` = `shutil.copyfile` from the
  private temp file. Matches the adapter interface exactly (F6).
- `_member_name` (L36-52): validates on `orig_filename` (retains NULs that
  `ZipInfo.filename` silently truncates); rejects empty names, backslashes,
  colons, control chars (<32) and DEL (127), and empty/`.`/`..` path
  components; requires a regular file via `S_IFMT` external_attr kind plus the
  DOS directory bit; requires a `.pdf` suffix (case-insensitive); returns the
  basename (safe subdirectories are flattened).
- `pdf_download` (L66-104): context manager; all validation before `yield`:
  transport 0 < size ≤ 32 MiB (seek-to-end probe); exactly one member; member
  name safe; not encrypted (flag bit 0); compression stored/deflated only;
  0 < file_size ≤ 64 MiB and 0 < compress_size ≤ 32 MiB (bomb rejected before
  opening the member); streams into a fixed-name file in a private
  `TemporaryDirectory` in 64 KiB chunks with an overflow probe read;
  `total != member.file_size` fails closed; CRC is verified by the zipfile
  reader on read-to-EOF; temp bytes removed on success, rejection and callback
  failure (TemporaryDirectory context).
- **M1 (nit, optional maintainer hardening):** no basename length cap — a
  valid ZIP name > 255 bytes passes `_member_name` and the adapter's
  basename guard, then fails at publication with `OSError` (fail-closed,
  retryable). Proposed: reject `len(parts[-1]) > 255` in `_member_name`.
- **M2 (nit):** `unpack` + `incremental` combination not explicitly tested;
  orthogonal by construction (unpack wraps the document, incremental adds
  `source_key` in the same save call).

### apps/billcollector/collection.py (+11/−2)

- `unpack` added to the `download_all` options set; strict validation
  `unpack must be pdf when supplied` (only key-presence + const, no boolean
  coercion traps).
- Save path: `prepared = pdf_download(download) if options.get("unpack") ==
  "pdf" else nullcontext(download)`; the persistence call runs inside
  `with prepared as document:` — validation failure raises before
  `save_download` is called, so rejected archives create no row and do not
  mark the key complete (pinned by
  `test_collection_rejection_preserves_completed_items_and_retry`).
- Default path: `nullcontext(download)` passes the original download object
  through untouched (pinned by `test_default_passes_zip_through_untouched`).
- Imports: `from contextlib import nullcontext`, `from .archives import
  pdf_download`.

### apps/recipes_playwright/recipe-pw-schema.yaml (+7/−1)

- `downloadAllMethod` gains `unpack: {const: pdf}` under
  `additionalProperties: false`.
- `replacement_calendar.download_options` becomes an `allOf` of the base
  reference and `not: required: [unpack]` — the "scoped to download_all"
  fix (commit `d97d7f3`).

### tests/test_bc_archives.py (new, 346 lines)

15 synthetic tests (run without a browser) + 1 loopback-Chromium test gated on
`BILLCOLLECTOR_BROWSER_TESTS=1`. Coverage: unchanged bytes + name flattening +
temp cleanup (stored and deflated); 512 KiB member streamed in chunks; cleanup
when persistence raises; member count/type rejections (0, 2 members,
non-PDF, dir entries, html payload, empty); 11 unsafe-path variants + NUL;
6 special file types + DOS dir bit; inclusive size bounds (mocked limits,
boundary-inclusive) + bomb rejected before `ZipFile.open`; 6000-tiny-member
metadata bound; false-metadata stream bounds (double and truncated streams);
truncated/corrupt/encrypted/BZIP2 archives; SHA-256 dedup across different ZIP
envelopes through the real `db` + `downloads.track_download` adapter (identical
hash, duplicate row, consumer invoked once); schema const acceptance/rejection
vs runtime `download_all` rejection parity; calendar schema + runtime
`validate_options` rejection of `unpack`; partial-failure completed-key
behavior + retry on the fixed archive; default ZIP passthrough. The browser
test drives the real `runner._collection_actions(ctx, {})["download_all"]`
against a loopback HTTP server (valid + path-escape ZIPs) with a real
Playwright Chromium download and isolated db/profile. No secrets (F14).

### Docs

- `doc/RECIPE_AUTHORING.md` (+18): ZIP transport contract paragraph inside
  "Pagination, empty lists and downloads" (PR L96-112): one member incl.
  directory entries, regular file + `.pdf` + `%PDF-` signature, rejected
  characters/types, 32/64 MiB bounds, 256 KiB metadata bound, unchanged
  bytes to the normal save path/hash/notice identity, no record on rejection,
  earlier items remain saved, default unchanged, not supported in
  `replacement_calendar.download_options`.
- `doc/RECIPE_METHODS.md` (+4): options-table row for `unpack` (no) +
  semantics link to the ZIP transport contract.
- `README.md` (+2): two continuation lines on the "Bounded collections"
  bullet.
- `CHANGELOG.md` (+4): `[Unreleased]` / `Added` entry citing issue #50.

### Process check (CONTRIBUTING.md)

Issue #50 referenced (phase b of the agreed two-PR split); intended behavior
and verification stated; proof shipped (claimed — S5 re-runs on the dev tree);
AI assistance disclosed (Codex); no secrets (F14); no new network exposure
(validation is local to the downloaded file); shared interface = recipe
contract (schema + `download_all` options), agreed in #50 before code. Pass.

## Risks

- **R1 — 3-way merges.** All four manual merges are additive keep-both
  resolutions (dev's `allow_empty`/`incremental` (PR #57) + C4/C8 docs vs the
  PR's `unpack` additions). Risk of dropped context is low; the S5 targeted
  suite (archives + collection + calendar + recipes) plus full regression
  covers the seams.
- **R2 — Per-read metadata bound.** Not a cumulative cap; effective under the
  stdlib's reading pattern (F8). Documented as "metadata reads are limited to
  256 KiB" in the contract doc — accurate.
- **R3 — Long basenames (M1).** Fail-closed `OSError` at publication; retry
  possible; optional one-line hardening proposed.
- **R4 — Head stability.** Fork base is stale by design (orphaned tip); if
  the author pushes before S4, S4 preflight re-checks the head hash and
  re-runs pre-image checks.
- **R5 — unpack+incremental combination (M2).** Not explicitly pinned;
  construction is orthogonal.

## Integration plan (S4, on Gitea `dev`)

Preflight: on `dev`, clean tree; `git ls-remote github refs/pull/58/head` =
`d97d7f3…`; re-run pre-image checks (dev may have moved).

| File | Action | Detail |
|---|---|---|
| `apps/billcollector/archives.py` | apply from head | new file, byte-for-byte |
| `tests/test_bc_archives.py` | apply from head | new file, byte-for-byte |
| `apps/billcollector/collection.py` | manual 3-way | 3 additive conflicts: (1) options set → `"key_attribute", "max_items", "timeout_ms", "event_window_ms", "allow_empty", "incremental", "unpack"`; (2) unpack validation block kept after dev's incremental validation, before `key_attribute = …`; (3) `save_completed` → wrap dev's if/else in the PR's `with prepared as document:` using `document` as the save argument (exact intended shape in S3 proposal) |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | auto 3-way (0 conflicts) | verify result: `unpack: {const: pdf}` present, `download_options` allOf/not intact |
| `CHANGELOG.md` | manual (1 conflict) | insert the PR's 3-line entry at the top of `### Added` under `## [Unreleased]` (newest-first order, matching the PR #57 entry placement) |
| `README.md` | manual (1 conflict) | keep dev's "Bounded collections" paragraph incl. the `allow_empty` sentence; append the PR's two continuation lines (`Set optional `unpack: pdf`…` + the ZIP transport contract link) after it |
| `doc/RECIPE_AUTHORING.md` | auto 3-way (0 conflicts) | verify placement: ZIP paragraph before the `### Opt-in incremental downloads` subsection, inside the shared section (anchor stays valid) |
| `doc/RECIPE_METHODS.md` | manual (2 conflicts) | options table: keep dev's `allow_empty` row, add the PR's `unpack` row after it; semantics paragraph: keep dev's `allow_empty` sentence, append the PR's ZIP transport contract link sentence after "cannot be nested." |
| all other files in the GitHub diff | skip | fork-behind-base artifacts (F3): private-path deletions and PR #57 mirror content already on `dev`; never applied |
| M1 (optional, S3 gate) | maintainer change | `archives._member_name`: reject `len(parts[-1]) > 255` with the existing unsafe-path error |

Tree left dirty after S4 (S5 validates the exact content before any commit).

### Exact merge shapes (S3, confirmed as-is 2026-11-04)

`collection.py` imports: `from contextlib import nullcontext` after
`import time`; `from .archives import pdf_download` before
`from .interrupt import RunInterrupted`.

`collection.py` options set:

    names={
        "key_attribute", "max_items", "timeout_ms", "event_window_ms",
        "allow_empty", "incremental", "unpack",
    },

`collection.py` unpack validation (after dev's `keyed_save` check, before
`key_attribute = …`):

    if "unpack" in options and options["unpack"] != "pdf":
        raise CollectionError("unpack must be pdf when supplied")

`collection.py` `save_completed` (dev's if/else wrapped in the PR's context,
`document` as save argument):

    def save_completed(download):
        prepared = (pdf_download(download) if options.get("unpack") == "pdf"
                    else nullcontext(download))
        with prepared as document:
            if incremental:
                record = save_download(
                    document, source_key=source_key(key_attribute, expected_key)
                )
            else:
                record = save_download(document)
        completed_keys.add(expected_key)
        return record

M1 (`archives._member_name`, appended condition, existing error message):

    if (not name or "\\" in name or ":" in name
            or any(ord(char) < 32 or ord(char) == 127 for char in name)
            or any(part in {"", ".", ".."} for part in parts)
            or len(parts[-1]) > 255):
        raise ValueError("ZIP member path is unsafe")

### S7 commits (confirmed as-is 2026-11-04, one concern each)

1. `feat: opt-in download_all unpack: pdf (bounded single-PDF ZIP transport)` —
   `archives.py` (+M1), `collection.py`, `recipe-pw-schema.yaml`
2. `test: bounded ZIP extraction coverage for download_all` —
   `tests/test_bc_archives.py`
3. `doc: ZIP transport contract, unpack option, changelog entry` —
   `CHANGELOG.md`, `README.md`, `doc/RECIPE_AUTHORING.md`,
   `doc/RECIPE_METHODS.md`

### S3 gate (2026-11-04)

- User confirmed the proposal as-is (A–E + M1 + the three S7 commits).
- Preflight re-verified at the gate: PR head `d97d7f3` unchanged
  (`git ls-remote github refs/pull/58/head` = fetched `refs/pr/58`);
  `dev` = `origin/dev` = `71b2df9`, clean tree (untracked
  `.private/notes.txt` only — private note, untouched). dev's move since
  S1 (`c1ab80a` → `71b2df9`) is doc-only plan commits → pre-image checks
  stand.
- Issue #50 verified **open** at the gate; PR body says "Refs #50, phase
  two" (no auto-close). Both phases land with this delivery → S7 closes
  #50 with a user-confirmed comment per the publication routine.

### S4 application record (2026-11-04)

Preflight re-run, all green: `git ls-remote github refs/pull/58/head` =
`d97d7f3…` = fetched `refs/pr/58` (unchanged); `dev` = `origin/dev` =
`f467760`, clean tree (untracked `.private/notes.txt` only, private note,
untouched); dev's move since S3 gate (`71b2df9` → `f467760`) and since S1
(`c1ab80a` → `f467760`) is doc-only plan commits → pre-image checks stand.

Applied per the confirmed plan (tree left dirty, uncommitted):

| File | Result |
|---|---|
| `apps/billcollector/archives.py` | applied from head byte-for-byte, then M1 appended (`len(parts[-1]) > 255` in the unsafe-path condition) — diff vs PR head = M1 line only (verified) |
| `tests/test_bc_archives.py` | applied from head byte-for-byte (verified) |
| `apps/billcollector/collection.py` | manual 3-way per confirmed shapes: imports, options set + `unpack`, validation block after the `keyed_save` check, `save_completed` wrapped in `with prepared as document:` — diff matches the S3 shapes exactly |
| `apps/recipes_playwright/recipe-pw-schema.yaml` | auto 3-way, 0 conflicts (F5); `unpack: {const: pdf}` present, `download_options` allOf/not intact (verified) |
| `CHANGELOG.md` | manual: PR's 3-line entry inserted at the top of `### Added` under `## [Unreleased]`, above the PR #57 entry (newest-first) |
| `README.md` | manual: dev's `allow_empty` sentence kept; PR's two continuation lines (`Set optional `unpack: pdf`…` + ZIP transport contract link) appended after it |
| `doc/RECIPE_AUTHORING.md` | auto 3-way, 0 conflicts (F5); ZIP paragraph inside "Pagination, empty lists and downloads" (L87 section), before `### Opt-in incremental downloads` (L125) — anchor stays valid |
| `doc/RECIPE_METHODS.md` | manual: keep-both — `allow_empty` row kept, PR's `unpack` row added after it; semantics keep dev's `allow_empty` sentence + PR's ZIP contract link sentence appended after "cannot be nested." |

`git status` after S4: 6 modified + 2 untracked new (the 8 candidates) +
pre-existing untracked `.private/notes.txt`. S5 validates this exact dirty
tree before any commit.

## Validation plan (S5, from repo root, `apps/.venv`, exact dev tree)

1. PR unit tests (claimed 16 + 33 subtests, no skips):
   `BILLCOLLECTOR_BROWSER_TESTS=1 apps/.venv/bin/python -m pytest tests/test_bc_archives.py -q`
   (requires Chromium; if the browser is unavailable, run
   `apps/.venv/bin/python -m unittest tests.test_bc_archives -v` and record
   the browser-class skip + reason).
2. PR's targeted correction suite (claimed 101 + 33, no skips):
   `BILLCOLLECTOR_BROWSER_TESTS=1 apps/.venv/bin/python -m pytest tests/test_bc_archives.py tests/test_bc_collection.py tests/test_bc_calendar.py tests/test_bc_recipes.py -q`
3. Full regression (claimed VERDICT: PASS, 7 scenarios / 8 PDFs, exit 0):
   `apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini`
   (fresh isolated db; re-initialize via `BillCollectorServices_pw.DatabaseManager`
   if the 0-byte gitignored `apps/db/bc.db` needs the `Service` table).
4. `apps/.venv/bin/python -m ruff check apps tests` → clean (F821/E4/E7/E9);
   bandit on the changed files → nothing new beyond the known baseline.
5. If any failure requires a fix: fix on `dev`, new dev-commits cycle, re-run;
   a fix that materially changes PR intent → S3 refusal branch.

## Deployment validation

Not deployment-relevant (F15): no `Dockerfile`, `.dockerignore`,
`BillCollector.sh`, `install_docker-image.sh`, `deploy_remote.sh`, INI keys or
`.env` handling touched. The S5 skip is recorded here; the user confirms the
recorded skip at the S5 gate before S6/S7 may commit or push to `main`.

## Out of scope

Phase (a) incremental keys (delivered with PR #57); multi-member or
non-PDF archives; recursive/nested extraction; default download behavior
(unchanged); database migration (none — the feature is row-free).

## Open questions

None blocking. M1 (basename length cap) decided at the S2 gate, 2026-11-04:
**include** the one-line maintainer hardening in the S3 proposal.
