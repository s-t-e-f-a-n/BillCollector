# PR #57 — S1 review: opt-in incremental download keys

> Status: PLANNED (2026-11-03) — plan for executing pr-review stage S1 in a new
> implementation session ("review PR #57"). S2–S7 are later, user-gated sessions.

## Context

- Lane: `pr-review` skill, PR **#57** "feat: add opt-in incremental download keys"
  by flowcool. Stage 1 (S1) of 7; this plan covers S1 only.
- PR #57 is phase (a) of issue **#50** (two phases, separate PRs agreed in
  #50 comment `6560325930`); phase (b) `unpack: pdf` is PR **#58** — a separate
  lane, not part of this session.

### Agreed shape (issue #50, maintainer comment 6560325930)

- Additive **nullable** `Download.source_key` column, scoped to **(task, key)**;
  no new table, no backfill of old rows, no default change; non-opt-in recipes
  behave exactly as today.
- Incremental run that skips all known keys → **success** with an explicit
  "all items known" result (distinguishable from failed collection).
- **Keys do not establish revisions**: opt-in is a per-recipe declaration that
  the portal never corrects delivered notices in place; correction-capable
  portals (Bourse Direct) must not opt in and must use `notice_identity` (#41).
  The declaration belongs in the recipe contract doc.
- Re-baseline requirement: proof re-run against public `main` tip (was
  `4a9bffc` when agreed; tip since moved to `eb06503`).

### PR metadata (at planning time)

| Field | Value |
|---|---|
| Head | `24e8492601079ac28c2823357264fffcceefde3a` (`flowcool:feature/upstream-incremental-6z1ew`) |
| Base (labeled) | `main` @ `eb06503dcd56da70d9677d2910a51c9dc486442a` |
| Commits | 2 |
| GitHub-reported diff | 114 files, +452 / −25665 — **expect fork-behind-base noise**; the −25665 suggests the head branched before the #24 delivery lane landed (`4a9bffc` era), not at `eb06503`. Merge-base analysis (task 3) is the arbiter. |
| mergeable_state | `dirty` (GitHub check pending at planning time) |
| Claimed baseline | public `main` `4a9bffc4…`, "re-fetched before publication" |
| Claimed evidence | `pytest` on 6 test modules: 132 passed + 17 subtests, no skips; `ruff check apps tests` clean; isolated legacy regression `tests/run_regression.py --ini tests/bc_regression.ini --keep-downloads` → VERDICT: PASS (7 pairs / 8 files); Bandit 1.9.4: 4 medium, identical to public baseline; AI assistance disclosed (Codex); no vault/provider/production access |

### Local state (record at session start; re-verify)

- Gitea `dev` = `c377736`, Gitea `main` = `2485719`, GitHub `main` = `eb06503`;
  working tree clean.
- `dev` has moved since `4a9bffc` through the #24 delivery lane (delivery state
  machine, retry paths, UI, `delivery_attempts` migration, docs) — pre-image
  checks must run against `dev`, the integration target.

## S1 tasks (per pr-review skill S1, steps 1–9)

1. **Fetch PR ref (inspection-only):**
   `git fetch github refs/pull/57/head:refs/pr/57` (delete the ref first if it
   exists), record the head hash. If it differs from `24e8492…`, the head moved:
   diff new vs. reviewed head, re-run S1; never review a stale head.
2. **Record local state:** `dev`, Gitea `main`, `github/main` tips.
3. **Merge-base analysis:** `git merge-base refs/pr/57 github/main`;
   `git log --oneline <mb>..refs/pr/57` to list the PR commits; flag any
   orphaned public-history commits (recommits of sanitized tips). Use the
   three-dot diff `<mb>...refs/pr/57` as the ground-truth change set, not the
   GitHub-reported 114-file stat.
4. **Classify every file** in the three-dot diff:
   - added/modified public path → **candidate**;
   - deleted but already absent from current `github/main` → comparison
     artifact (fork-behind-base noise), skip;
   - any path under `.kilo/`, `.private/`, `.vscode/`, `openwiki/`, `AGENTS.md`,
     `.openwikiignore`, or `.github/workflows/` → **flag, never auto-apply**.
5. **Conflict + pre-image check against Gitea `dev`** (per candidate): dev file
   byte-identical to PR head (skip) / byte-identical to the PR base pre-image
   (hunk applies cleanly) / diverged (needs manual adaptation). List dev files
   changed since the merge base (conflict list) — the #24 delivery lane touched
   the download/UI/recovery area, so expect some divergence to adjudicate.
6. **Code review, per file/function, with line refs** — behavior preserved vs.
   changed. Focus:
   - `download_all(incremental=...)`: bounded non-empty stable key list
     validation; known-key skip for (task, key attribute); each new download
     saved with its `source_key`; all-keys-known → `Run.result=success` +
     explicit "all items known" log (matches #50 decision 3).
   - `Download.source_key`: nullable, additive migration, no backfill, old
     rows stay NULL (matches #50 decision 2).
   - Keys survive duplicate-download audit rows and publication-journal
     recovery (claimed).
   - Default acquisition and `incremental: false` unchanged; legacy runner keeps
     its positional save callback and rejects opt-in before clicking.
   - Correction boundary: no revision detection via keys; recipe contract doc
     carries the "portal never corrects in place" declaration (matches #50
     decision 4) — verify the doc change is present and sanitized.
   - Test review: coverage of the claimed evidence, synthetic markers, no
     secrets, pinned behavior. Note out-of-scope residuals explicitly (ZIP
     extraction, C4/C8, archive protocol must be absent).
7. **Process check (CONTRIBUTING.md):** issue referenced (#50 ✓); intended
   behavior + verification stated ✓; proof shipped (record as *claimed* — S5
   re-runs it on the dev tree); AI assistance disclosed ✓; no secrets in code,
   tests, or artifacts; no new network exposure; shared interfaces (Download
   schema, `download_all` recipe contract) agreed in #50 before code ✓ — verify
   the PR matches the agreed shape exactly (nullable column, (task, key)
   scope, no default change, no-op success semantics).
8. **Cross-PR:** PR #58 (phase b) is the only other open PR; per #50 the two
   touch disjoint parts of the download path — note ordering, tests passing in
   either merge order are a plus, not a requirement. No other PRs/lanes touch
   this PR's diff (#51/#52/#59 lanes are separate).
9. **Plan doc + gate:**
   - Create the review plan doc `.kilo/plans/<epoch-ms>-pr57-incremental-keys-review.md`
     (first line after title: `> Status: REVIEWING (date) — …`) with PR
     metadata (author, head hash, base, issue refs, local dev/main/github-main
     tips), Verified facts, Code review findings, Risks, and the file
     classification table. Verdict/Integration/Validation sections are filled
     in S2.
   - Propose the doc-only commit to `dev` (dev-commits style, one doc commit;
     user confirms), push to Gitea `origin/dev`.
   - Gate: findings complete → user decides to proceed to S2 (verdict +
     integration plan).

## Constraints

- Read-only on the repo: `git fetch` of the PR ref (local ref only) and the
  doc-only plan commit are the only mutations. No source edits, no applying PR
  content, no comments on the PR, no push of PR content anywhere.
- PR refs are inspection-only: never merged into the Gitea lineage.
- If GitHub API is needed, the Bearer token from `~/.git-credentials` goes to
  a shell variable and is never printed; the read-only GitHub MCP tools are
  preferred.
- No public-facing text is produced in S1; nothing reaches the GitHub mirror.
- `.kilo/` plan content never reaches GitHub (mirror strips it).

## Failure modes

- PR head moved since `24e8492` → re-run S1 on the new head (skill rule).
- `dev` moved again before S4 → pre-image checks re-run then; S1 findings stay
  valid as of the recorded tips.
- Merge-base differs from expectation (not in the `4a9bffc` era) → re-derive
  the classification; the GitHub 114-file stat is not a finding.

## Deliverable

S1 findings presented at the user gate: PR head hash + metadata, recorded local
tips, merge-base result, file classification table (candidates / artifacts /
flags), pre-image and conflict list against `dev`, per-file code review
findings with line refs, process-check result, cross-PR note; plan doc
committed to `dev` with Status: REVIEWING.
