# GitHub Issue Replies — #9 (vault diagnostics) and #10 (DOM/SQLite tracking)

> Status: DONE — executed 2026-10-08 22:37–22:38Z via GitHub API (store credential
> helper; no `gh` CLI; `jq` absent → payloads built with `python3`). #9: comment
> 6070451198 posted, issue closed (22:38:05Z). #10: comment 6070460327 posted,
> left open — fix arrives as flowcool's PR, triaged later per the ~20-min rule.
> No code changes; reply bodies lived in `/tmp` only.
> Both issues opened 2026-10-05 by flowcool. Decisions: #9 = reply + close
> (already implemented on `main`); #10 = agree to retention policy, welcome small
> PR against current `main` (user-confirmed 2026-10-08).

## Context

- Repo `github` remote = `https://github.com/s-t-e-f-a-n/BillCollector.git`;
  `main` = `dev` = `247afc1` (sanitized mirror tip `af6f061`). No `gh` CLI on this
  machine — GitHub API via the `store` credential helper (verified working during
  the PR #14–16 triage, plan `1791489933220`).
- Closed issues #4 (2025, install script) and #5 (2025, contact-spam) have no
  pending questions — no reply needed.
- Established flowcool triage pattern (checklist `1791489933220`): concise, exact
  comments; adopt well-scoped novel work, defer the rest; any incoming PR gets
  triaged later against current `main` (~20 min rule).

## Verified facts (basis for the replies)

### Issue #9 — already implemented on `main`

| Claim in issue | Verified state |
|---|---|
| Failed requests put bodies/URLs/raw exceptions in diagnostics | Fixed by `4ba35c3` (2026-10-06, one day after the issue): `vault_request` now logs `network error (<class>)`, `server error <status>`, `Client error: <status>` — no body, no URL, no raw exception (`apps/BillCollector.py:48-71`) |
| Messages flow to stdout, rotating log, UI stream | `setup_logging()` silences urllib3/dependency loggers (`apps/helpers/BillCollectorHelpers.py:67-70`); UI is a pure subprocess supervisor streaming stdout (`apps/bc_ui.py:3,101`) → covered |
| Proposed scope (status/attempt/category; keep 10 s, 3×, backoff, 4xx, TOTP) | All present: `VAULT_TIMEOUT=10`, `VAULT_MAX_ATTEMPTS=3`, `VAULT_RETRY_BACKOFF=2` (`apps/BillCollector.py:37-39`), 4xx final with status, TOTP 400 → None |
| Offline unit tests, synthetic values, mocked HTTP, marker-absence asserts | `tests/test_vault_diagnostics.py` (212 lines, commit `259a8f6`, 2026-10-06) — `SYNTHETIC_SENSITIVE_VALUE` marker + full URL asserted absent from all diagnostics; retry/backoff (`sleep [2,4]`) and TOTP behavior asserted unchanged |
| — | PR #13 transport (merged 2026-10-08, `a42c2dd`) adds a 2nd layer: `vault_transport.py:90-97` reduces request exceptions to the class name before any handler sees them; the diagnostics suite also exercises the `vault_http_request` path |

### Issue #10 — all three findings verified accurate

1. **Live input value as locator name** — `apps/BillCollectorServices_pw.py:311`:
   `accessible_name = (aria_label.strip() or placeholder.strip() or value.strip() or label_text.strip())`
   for textboxes; `PageState` is created at the start of every step
   (`process_step`, line 585), so after a `fill` step the password is in the
   `interactive_elements` JSON persisted to SQLite (`insert_page_status`, lines
   118-130). Real credential leak.
2. **Raw exception text in step errors/logs** — line 637
   `fail_step({"method": …, "message": str(e)})` → `page_state.set_error` (595) →
   DB; logged at 597 (graceful), 511 (abort), 412/514 (`logger.exception`),
   480-485 (download errors). Playwright messages can embed URLs (navigation) or
   element text.
3. **Link/download URLs in tracking** — line 376-377 stores every link `href` in
   `interactive_elements`; lines 487-490 store `download.url` in the finalized
   service run; line 407 logs the whole `file_downloaded` list (incl. URLs) at
   INFO.

Additional fact for the reply: the DB is **write-only** — nothing reads
`interactive_elements` back yet; self-healing is planned (README:49, CHANGELOG:139)
but not implemented → no compatibility constraint on the locator-name change.

## Decisions

- **#9**: post the "already implemented" reply, then **close** the issue.
- **#10**: post the policy-agreement reply (user-confirmed), **leave open** —
  the implementation arrives as flowcool's PR and is triaged later per the
  established pattern.

## Draft replies (final text)

### Reply for issue #9 (post, then close)

```
Thanks @flowcool — this one is already implemented. The diagnostics fix landed
Oct 6 (`4ba35c3`) with the offline unit suite (`259a8f6`,
`tests/test_vault_diagnostics.py`), both on `main`. Current behavior:

- 4xx is final: `Client error: <status>` with the status code, no body
- 5xx / network failures: `Attempt N/3 failed: server error <status>` /
  `network error (<exception class>)` — no body, no request URL, no raw
  exception text
- 10 s timeout, 3 attempts, 2 s × N backoff, final 4xx status, TOTP 400 →
  "no TOTP" warning — unchanged from v0.4
- The PR #13 transport (merged Oct 8) adds a second layer:
  `vault_transport.py` reduces request exceptions to the class name before any
  handler sees them, and `setup_logging()` silences the dependency loggers
  (urllib3), so nothing reaches stdout, the rotating log or the manual UI
  stream (the UI only supervises the subprocess stdout)

The test suite asserts both the absence of synthetic sensitive markers (value +
URL) and the unchanged retry/TOTP behavior — your proposed verification,
verbatim. Closing this as implemented; if you find a path the suite doesn't
cover, open a new issue.
```

### Reply for issue #10 (post, leave open)

```
Thanks @flowcool — all three findings check out against the current code, and
I can agree to the retention policy:

1. Structural DOM/locator evidence and the SQLite schema stay.
2. No live input values as locator names. `set_interactive_elements` currently
   falls back to `input.value` for unlabeled textboxes
   (`BillCollectorServices_pw.py:311`) — drop `value` from that chain; keep
   aria-label → placeholder → label text, else the role.
3. URLs: keep `scheme://host/path`, strip query and fragment (that is where
   signed tokens and session data live) — for link hrefs and download URLs alike.
4. Step errors: keep step number, method name and a fixed failure category
   (timeout / strict-mode / navigation / download / other). No raw exception
   text — same pattern as the vault diagnostics fix.
5. Proof via a synthetic local page and a temporary SQLite database, including
   a filled password input with no label/placeholder and an error after
   credential entry — same approach as `tests/test_vault_diagnostics.py`.

On your self-healing question: the database is currently write-only —
self-healing is planned but not implemented yet — so the locator-name change
has no compatibility cost. What the design will need from the recording:
roles + accessible names from static attributes (label / aria-label / title /
placeholder / element text) and the locator-candidate structure. The link path
(without query/fragment) helps disambiguate. Nothing needs live values or full
URLs.

A small PR against current `main` is welcome; I'll review it like any other
contribution.
```

## Execution steps (implementation session)

1. Write the two reply bodies to `/tmp/kilo/reply-issue-9.md` and
   `/tmp/kilo/reply-issue-10.md` exactly as above.
2. Obtain the token (store credential helper, same as the PR #14–16 triage)
   without printing it:
   `TOKEN=$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill | grep '^password=' | cut -d= -f2)`
3. Post #9 comment:
   `curl -sS -X POST -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" https://api.github.com/repos/s-t-e-f-a-n/BillCollector/issues/9/comments -d "$(jq -n --rawfile body /tmp/kilo/reply-issue-9.md '{body: $body}')"`
4. Close #9:
   `curl -sS -X PATCH -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" https://api.github.com/repos/s-t-e-f-a-n/BillCollector/issues/9 -d '{"state":"closed"}'`
5. Post #10 comment: same POST to `/issues/10/comments` with
   `/tmp/kilo/reply-issue-10.md`.
6. Do not print `$TOKEN`; do not commit the reply files (they live in `/tmp`).

## Validation

- `GET /repos/s-t-e-f-a-n/BillCollector/issues/9` → `state: "closed"`, comment
  present; `GET .../issues/10` → `state: "open"`, comment present (check via
  API or the issue pages).
- Optional: re-run the referenced suite in the implementation session:
  `python3 tests/test_vault_diagnostics.py` (blocked in plan mode; last full
  regression on this tree was VERDICT: PASS on 2026-10-08).

## Out of scope

- No code changes in this session — the #10 fix arrives as flowcool's PR,
  triaged later against current `main` (~20 min rule from the checklist).
- Closed issues #4/#5 (2025) — no pending questions, no reply.
- Daemon plan (Wave 1, plan `1790364274061`) continues separately.
- Optional follow-up (only if asked): commit this plan file to `dev` with a
  `doc: plans:` message per repo convention, and record the outcome in the
  plan's status header.
