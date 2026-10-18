# Follow-up: openwiki boundary — secrets cleanup, plan completion, usage policy

## Goal

Close out the three follow-ups left by the delivered private AI artifacts
boundary plan (`.kilo/plans/completed/1792335541451-private-ai-artifacts-boundary.md`
after workstream B): (A) delete the inert GitHub repo secrets/vars that existed
only for the never-published `openwiki-update.yml` workflow, (C) decide and
write the deferred openwiki usage policy into `AGENTS.md`, (B) record the
boundary plan as delivered and move it to `completed/`.

## Session structure

One new session, three parts in this order: **A → C → B**. B is last so its
completion record can reference the final state of A and C. Each part ends in
an explicit user gate before the next starts. (If the session stalls in C, A and
B can still be finished; B's record then notes the policy as pending.)

## Context (verified 2026-10-18)

- Boundary plan delivered: 7 commits `105f30d..c6ff24f` on Gitea `dev` and
  pushed; `STRIP` covers the 7 private paths; `openwiki/`, `AGENTS.md`,
  `.openwikiignore`, `.github/workflows/openwiki-update.yml` are versioned in
  Gitea only; `openwiki/.run.json` gitignored. The GitHub mirror is untouched
  (next promotion is when the extended Stage 3 listing check runs).
- `openwiki-update.yml` is the standard OpenWiki GitHub Actions template: a
  daily cron (`0 8 * * *`) that runs `openwiki code --update` and opens a
  **public PR** adding `openwiki,AGENTS.md,.github/workflows/openwiki-update.yml`
  (plus `CLAUDE.md` if present). It references four public-repo settings:
  secrets `OPENAI_COMPATIBLE_API_KEY`, `OPENWIKI_LANGSMITH_API_KEY`,
  `LANGSMITH_API_KEY`, and variable `OPENAI_COMPATIBLE_BASE_URL`.
- The workflow is in `STRIP` and is never published (boundary decision #2), so
  any of those settings on the public GitHub repo are inert — including the
  local LLM-gateway API key (solar-llm via the OpenAI-compatible endpoint) and
  a LangSmith key.
- No cross-references to the boundary plan's path exist anywhere in the repo
  (verified by search); `.kilo/plans/README.md`'s Active table does not list it.
- The four deferred usage-policy questions (confirmed with the user 2026-10-18):
  1. **Consult depth** — pure just-in-time vs. mandatory pre-orientation for
     certain task classes.
  2. **Claims usage** — when to consult `openwiki/.claims/**/*.json` and the
     drift rule for stale evidence line-hashes.
  3. **Page-update-on-change** — fix a disagreeing page in the same task vs.
     defer to the periodic local refresh.
  4. **Max-leverage vs. managed block** — the user's policy lives outside the
     `OPENWIKI:START/END` markers (the block is regenerated on every local
     `openwiki code --update` run) and overrides its "optional just-in-time"
     framing where they differ.
- Claims structure (the drift hook): each `.claims/<section>/<page>.json` holds
  claims with `statement` + `evidence[].resource` (`repo://path#Lx-Ly`) + a
  versioned line-hash; `pageVersion` is a sha256 of the page. Stale = the
  evidence no longer matches the current source lines.

## Workstream A — delete the inert workflow secrets (external, no repo change)

1. List what exists on the public repo (names only; credential pattern from the
   deploy skill Stage 4: extract the token from `~/.git-credentials` into a
   shell variable, never print it):
   - `GET https://api.github.com/repos/s-t-e-f-a-n/BillCollector/actions/secrets`
   - `GET https://api.github.com/repos/s-t-e-f-a-n/BillCollector/actions/variables`
2. Present the listing; gate: user confirms exactly which names to delete
   (expected: the four above; any other openwiki-related setting is reported,
   not auto-deleted).
3. Delete each confirmed name:
   - `DELETE .../actions/secrets/{secret_name}`
   - `DELETE .../actions/variables/{variable_name}`
4. Verify: re-run both listings; the deleted names are gone; everything else
   untouched. Report.
5. Optional (user's call): check the Gitea repo settings for the same names
   (UI; Gitea's API surface for Actions secrets is version-dependent) and
   delete if present.
6. Optional (user's call): rotate the local LLM-gateway key. Default: not
   needed — the endpoint is LAN-only and deletion removes the only external
   holder; the session records the decision either way.
- Failure mode: GitHub credential not API-usable -> user deletes in the GitHub
  UI (repo -> Settings -> Secrets and variables -> Actions); report, never
  retry with other tokens (deploy-skill Stage 4 fallback).
- Failure mode: nothing exists (the settings were never created) -> record
  "nothing to delete" and move on.

## Workstream C — openwiki usage policy (decisions + `AGENTS.md`)

1. Walk the four deferred questions one by one with the user (one at a time),
   using these recommended answers as the starting position:
   1. **Consult depth** — just-in-time by default; mandatory pre-orientation
      via `openwiki/quickstart.md`'s task-routing table when the task touches
      two or more modules, the deployment path, or one of the four shared
      interfaces.
   2. **Claims usage** — consult a page's `.claims/` file as the grounding map
      (statement + evidence pointer) before editing code a claim covers; claims
      point at code and never replace reading it; if an evidence line-hash no
      longer matches the current source (or the statement contradicts the
      code), treat the claim as stale and re-verify against the source.
   3. **Page-update-on-change** — follow the wiki's own rule: when a loaded
      page disagrees with the code, fix the page in the same task (small
      doc-only commit via the dev-commits cycle); never batch "fix later"
      unless the user says so for that task.
   4. **Max-leverage vs. managed block** — the policy section below the
      `OPENWIKI:END` marker overrides the managed block's "optional" framing
      where they differ; the managed block itself is never hand-edited
      (regenerated on each local run) and its rewrite diffs are committed as
      they come.
2. Write the decided policy into `AGENTS.md`:
   - New short section (target ~10-15 lines, it is injected into every agent
     context) placed **outside** the `OPENWIKI:START/END` markers, right after
     the *Private agent artifacts* section.
   - Remove the now-obsolete bullet "Detailed openwiki usage policy (consult
     depth, claims usage, page updates on change) is deferred to a follow-up
     task." from *Private agent artifacts*.
   - Never edit inside the markers.
3. Commit + push via the dev-commits skill (one doc commit, per-item
   confirmation), e.g. `doc: AGENTS.md: openwiki usage policy`.
4. Optional (default: skip): local wiki refresh (`openwiki code --update`,
   ~30 min) only if the final policy contains repo-level facts the wiki should
   document; if run, commit `docs: refresh openwiki after usage policy`.

## Workstream B — completion record for the boundary plan

1. Add a dated delivery record to the boundary plan doc (style of
   `git show 0586637`, a "**Delivered (date).**" bullet): commit range
   `105f30d..c6ff24f`, validation summary (7-path STRIP dry-run clean,
   `.run.json` gitignored, deployment.md documents the 7-path STRIP), and a
   pointer to this follow-up plan with the state of A (deleted / nothing to
   delete) and C (policy landed / pending).
2. `git mv .kilo/plans/1792335541451-private-ai-artifacts-boundary.md
   .kilo/plans/completed/` (per `.kilo/plans/README.md`: delivered plans move
   to `completed/`; no cross-references exist to update — verified).
3. Commit + push via the dev-commits skill (one concern per commit):
   - `doc: plans: add the openwiki boundary follow-up plan` — this plan doc
     (committed first, so the record below can reference its final path).
   - `doc: plans: record private AI artifacts boundary completion` — the
     record bullet + the move to `completed/`.

## Validation

- A: both API listings after deletion contain none of the deleted names; all
  other settings unchanged; report names deleted + names found-but-kept.
- C: `AGENTS.md` has the policy section outside the markers and no "deferred to
  a follow-up task" bullet left; the managed block is byte-identical to before;
  `git push origin dev` clean.
- B: the boundary doc is under `.kilo/plans/completed/` with the record
  bullet; this follow-up plan doc is committed under `.kilo/plans/`;
  `git status --short` clean of both files; push clean.
- Whole session: `git log --oneline origin/dev..HEAD` empty at the end (all
  work pushed); no public GitHub mirror change (no sync runs in this session).

## Failure modes

- GitHub credential not API-usable -> UI fallback per workstream A.
- The four policy questions surface a 5th decision during the session ->
  resolve it there with the user; the plan's list is the minimum, not a cap.
- `openwiki code --update` (optional C4) unavailable or failing -> park it;
  the wiki stays as-is (private, cosmetic), per the boundary plan's precedent.
- An openwiki run rewrites the managed `AGENTS.md` block between edits ->
  commit the rewrite diff; never hand-edit inside the markers.

## Out of scope

- Changing the managed block's wording (regenerated by openwiki; user policy
  lives outside it).
- Publishing any wiki content to the community (rejected in the boundary
  decision round).
- Enabling/using Gitea Actions for the private workflow (wiki refresh stays a
  local `openwiki code --update` run).
- DuckDNS content in the public README (pre-existing, not AI-related).
