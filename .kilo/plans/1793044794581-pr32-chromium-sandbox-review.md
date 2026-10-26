# PR #32 review: require and qualify Chromium sandbox isolation

> Status: INTEGRATING (2026-10-26) — S3 gate confirmed
> (2026-10-26T21:14Z): integrate as-is — 11 PR-head byte-faithful files +
> 4 manual merges, M1/M2 applied, 5 commits. Tree still clean; next: S4
> selective integration on dev.

## PR metadata

- Author: flowcool; head `52bc1c92e7c9f849864b47cce0e3f8755840dd28` (branch
  `feature/upstream-sandbox-20261024` in flowcool's fork). `git ls-remote
  github refs/pull/32/head` matches the local `refs/pr/32` at review time
  (re-verified during this session, 2026-10-26).
- Base: the PR's base ref points at current public `main` `5116627`, but the
  branch content is based on the orphaned public tip `b4cf023f` (PR body:
  "extracted from reviewed fork PR51 onto current public main b4cf023f…").
  GitHub `mergeable_state: dirty` — expected, main moved after the fork point
  (the #33 delivery); handled by file-level application in S4.
- Issue ref: #28 (five-point sandbox contract, proposed in the issue body
  before code: "May I own this focused contribution, and do you accept this
  default-on/no-fallback behavior and the reference container policy?").
- Local state at review: `dev` `e6273da`, Gitea `main` `181a9cc`
  (= `origin/main`), `github/main` `5116627`.
- Actual PR content: 1 commit above the orphaned base (`52bc1c9`); 15 files,
  +1613/−2. The fork-only `sandbox-candidate.yml` workflow is excluded by the
  author (no `.github/workflows/` file in the PR — verified).
- Cross-PR: open PRs at review time are #32, #34, #35, #39, #40, #41. #34
  (next in the sequencing) touches `runner.py`/`db.py`/`config.py` regions
  with no hunk overlap against #32's hunks (verified against dev); #35/#39/
  #40/#41 arrived after the sequencing decision — out of scope for this
  chain, no known overlap with #32's 15 files, and they do not change #32's
  position in the order.

## Merge-base / orphan analysis

- `git merge-base refs/pr/32 github/main` = `71c7d69` — a raw Gitea commit
  whose tree still contains the private agent paths (`.kilo/`, `openwiki/`,
  `.private/`, `.vscode/`, `AGENTS.md`, `.openwikiignore`,
  `.github/workflows/openwiki-update.yml`).
- The PR branch carries the **orphaned sanitized commit** `b4cf023f`
  ("doc: collection: document bounded collection actions") — public main at
  fork time, replaced by the re-sanitization after the #30/#31 deliveries,
  no longer reachable from `github/main`. Flagged per skill; not re-applied —
  its content already exists on both dev and the current mirror (as `4b336d2`).
- All `D` entries in the full merge-base diff (97 files) are these private
  paths: comparison artifacts (absent from current `github/main`), **skip,
  never apply**. No `A`/`M` under any private path.

## Verdict

**Approve.** The #28 five-point contract is implemented exactly as agreed:
(1) `chromium_sandbox=True` in both launch paths; (2) no unsandboxed retry —
launch failures surface through the existing failure paths (daemon
`runner.py:944-950` `failure_record("launch_persistent_context", e)`; batch
`InitBrowser` catch → `None`), exit behavior preserved; (3) pinned profile
byte-identical to the official Playwright source at the cited commit
(verified below), wired into the reference Compose service via `security_opt`,
no `privileged`/`SYS_ADMIN`/host networking; (4) reproducible container proof
shipped (owned labelled container, network none, nonroot image check, profile
SHA pin, synthetic PDF + persistence + renderer kernel evidence, receipts with
verified cleanup); (5) host caveats documented and the denylist guard rejects
sandbox-disabling launch arguments. Two doc-only nits are recorded as S3
decision points (M1, M2). No shared-interface change: no DB schema, recipe
contract, control protocol, or exit-code change (stated in the PR and
verified in the diff).

## Verified facts

- Issue #28 contract (issue body): the five "Proposed focused contract"
  points listed above. The PR body maps its Evidence to each point; S1
  verified the mapping against the diff (all five implemented).
- Pinned profile: `docker/chromium-seccomp.json` SHA256
  `cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849` —
  **byte-identical** (`cmp`) to the upstream source fetched from
  `raw.githubusercontent.com/microsoft/playwright/54c711571a37de525377e6f3d3608c3e029b1829/utils/docker/seccomp_profile.json`.
  `docker/PLAYWRIGHT-LICENSE` is the Apache-2.0 text with CRLF line endings
  (preserved by the new `.gitattributes`: `-text` + `whitespace=cr-at-eol`).
- Pre-image check against dev (PR base `b4cf023f`):
  - byte-identical to base (hunks apply cleanly): `.gitattributes` (new),
    `doc/CHROMIUM_SANDBOX.md` (new), `docker-compose.yml`,
    `docker/PLAYWRIGHT-LICENSE` (new), `docker/chromium-seccomp.json` (new),
    `apps/BillCollectorServices_pw.py`, `tests/check_chromium_sandbox.py`
    (new), `tests/check_image_runtime.py`, `tests/run_sandbox_container.py`
    (new), `tests/test_bc_browser_sandbox.py` (new),
    `tests/test_sandbox_container_receipt.py` (new) — 11 files.
  - diverged (hunks verified **non-overlapping** with dev's changes since the
    base): `apps/billcollector/config.py` (PR: `chromium_args()` guard at
    ~L99-111; dev C1/#33 changed `DEFAULT_SETTINGS` at ~L51-58),
    `apps/billcollector/runner.py` (PR: `chromium_sandbox=True` in
    `_launch_browser` at ~L312; dev #33 added the `sqlite3` import and the
    `recover_downloads` call in `_run_task`), `README.md` (PR: header
    paragraph above `## Table of Contents`, lines 2-6; dev C1/C2/#30/#33
    README changes are all in other regions), `CHANGELOG.md` (PR:
    Unreleased/Added bullet; dev: Unreleased entries for #30/#31/#33).
- Daemon launch-failure path (contract point 2): `runner.py:944-950` wraps
  `_launch_browser` in `except Exception → logger.error(failure_record(
  "launch_persistent_context", e)) → return …, True, None` — the new
  `ValueError` from `chromium_args()` flows through this existing path; the
  batch `InitBrowser` catches it in its existing `except Exception` → `None`
  (unit test asserts `InitBrowser` returns `None` and the launcher is not
  called).
- Guard logic: normalizes `arg.split("=", 1)[0].lstrip("-")` and matches
  against the 7-flag denylist (`--no-sandbox`, `--disable-setuid-sandbox`,
  `--disable-seccomp-filter-sandbox`, `--disable-namespace-sandbox`,
  `--disable-gpu-sandbox`, `--single-process`, `--in-process-gpu`);
  single/double-dash and `=value` forms covered by the 18-case unit
  parametrization; safe arguments (`--disable-software-rasterizer`,
  `--lang=en`) pass through (tested). The doc explicitly scopes this as a
  denylist, not a complete validator.
- No secrets in the PR diff: all test/checker data is synthetic
  (`synthetic.pdf`, `127.0.0.1` loopback, `network none`, no vault/provider/
  host mounts — the container script verifies no host binds and only the
  anonymous `/apps/Downloads` volume). No new network exposure: the checker's
  HTTP server binds `127.0.0.1:0` inside a `network none` container; the
  compose change adds a restriction (seccomp profile), not an exposure.
- PR process check (CONTRIBUTING.md): one focused change; targets `main`;
  issue #28 opened before code with the contract; intended behaviour +
  verification commands + expected results in the PR body (pytest/ruff/bandit
  counts, docker build, both `run_sandbox_container.py` receipts with expected
  verdicts); proof shipped (41 new unit tests + qualification tools + fork PR51
  cross-reference); AI assistance disclosed ("Codex prepared, reconciled and
  tested the contribution. The contributor owns its behaviour, licensing and
  evidence."); no secrets; no new network exposure; no shared-interface change.
- Image/context facts for S5: `Dockerfile` copies only `apps/` into the image
  (`COPY apps/. .`), so `docker/chromium-seccomp.json` and the license are
  host-side files consumed by Compose `security_opt` from the repo checkout —
  consistent with the doc statement "The Dockerfile alone cannot select a
  host-side seccomp profile." The PR changes no `Dockerfile`, `.dockerignore`,
  shell script, or INI; `tests/check_docker_context.py` uses a fixed synthetic
  canary list (19 excluded / 5 retained), so the new `docker/` files do not
  change its expected output.

## Code review findings

- `apps/billcollector/runner.py` (`_launch_browser`): +1 line
  `chromium_sandbox=True` on `launch_persistent_context`. Behaviour change:
  on a host where Chromium's sandbox cannot start, the run now fails at launch
  (existing failure path, no fallback) instead of running unsandboxed. This is
  the intended #28 contract point 1/2.
- `apps/BillCollectorServices_pw.py` (`InitBrowser`): +1 line, same option on
  the legacy batch path; its existing `except Exception → None` preserves the
  batch failure behaviour (the PR's "Merge Danger" notes the blast radius is
  browser startup only).
- `apps/billcollector/config.py` (`chromium_args()`): returns the split
  `BC_CHROMIUM_ARGS` list as before, but raises `ValueError("BC_CHROMIUM_ARGS
  must not disable Chromium sandbox isolation")` when a denylisted flag is
  present. Behaviour change: an env value that used to be accepted
  (e.g. `--no-sandbox`) now fails both launchers at argument resolution.
  Intended (contract point 5); the error message is sanitized (no paths).
- `docker-compose.yml`: `security_opt: [seccomp=./docker/chromium-seccomp.json]`
  on the `billcollector` service (relative to the compose project dir = the
  NAS repo checkout). No other service or resource change.
- `docker/chromium-seccomp.json` (new, 831 lines): official Playwright
  alternate allowlist; byte-identical to the pinned upstream (verified);
  permits `clone`/`setns`/`unshare` for the namespace sandbox — the doc
  requires pin + review before any replacement.
- `docker/PLAYWRIGHT-LICENSE` (new, 202 lines): Apache-2.0, CRLF preserved.
- `.gitattributes` (new, 3 lines): path-scoped only (the two `docker/`
  files); no global EOL policy change.
- `doc/CHROMIUM_SANDBOX.md` (new, 97 lines): contract reference, prerequisites
  (nonroot user, host user-namespace support, AppArmor caveats), profile
  source/hash/pin, the two reproducible proof commands with expected results,
  the host-specific `--expect blocked` negative control, limits ("does not
  prove compatibility on UGreen or another host"), and rollback. Consistent
  with the code (checked line-by-line). Two wording nits → M1/M2 below.
- `tests/check_image_runtime.py`: docstring run command gains the
  `--security-opt seccomp=…` line; `launch(headless=…, chromium_sandbox=True)`.
  Consistent with the new policy.
- `tests/test_bc_browser_sandbox.py` (new, 21 tests): both launch paths request
  `chromium_sandbox=True` (kwargs assertion); 18-case denylist rejection
  (2 prefixes × 9 flags) asserting `ValueError` from the daemon path and
  `None` from the batch path with the launcher never called; safe-argument
  passthrough.
- `tests/test_sandbox_container_receipt.py` (new, 20 tests): 5 cleanup steps ×
  2 failure types × primary-fail/success — the receipt retains
  `cleanup_verified: false` + the failure type and the primary error; a failed
  ownership inspection never proceeds to removal. No Docker contact (subprocess
  mocked).
- `tests/check_chromium_sandbox.py` (new, 197 lines, manual tool): Xvfb +
  synthetic loopback portal; daemon (headed) checks `chrome://sandbox`
  (namespace/seccomp lines), both modes check live renderer kernel evidence
  (`NSpid` depth + extra `Seccomp_filters` + `NoNewPrivs` vs the Python parent —
  Docker's own filter explicitly does not count); synthetic PDF download;
  daemon profile persistence across context restarts (`localStorage` +
  `Preferences`); `--expect blocked` requires a demonstrated denial marker
  ("No usable sandbox" / "Operation not permitted" / "Failed to move to new
  namespace") — a bare launch failure is not accepted as proof; refuses root;
  `--force-sandbox` is a baseline probe only.
- `tests/run_sandbox_container.py` (new, 135 lines, manual tool): pins
  `--host unix:///var/run/docker.sock` (no ambient `DOCKER_HOST`); requires a
  nonroot image; verifies the profile SHA before use; unique labelled
  container (`sandbox.owner`), `--network none`, no `--cap-add`, no host binds,
  only the anonymous `/apps/Downloads` volume; bounded timeouts (120 s /
  900 s); retains `stdout.log`/`stderr.log`/`receipt.json`; cleanup re-verifies
  the exact container ID + label before `stop`/`rm --volumes`, then verifies
  container absence and volume removal — an unverified cleanup raises.

## Risks

- **NAS host policy (primary deployment risk):** the seccomp profile permits
  unprivileged user-namespace syscalls, but the host (AppArmor or policy) can
  still deny them. The S5 smoke run on the NAS is the deciding check: if the
  NAS denies namespace setup, the launch fails there (by contract, no
  fallback) — record the exact host/image failure first (per the PR doc) and
  return to the user for a decision; do not weaken the policy to manufacture a
  pass. The PR explicitly claims no UGreen/other-host qualification.
- `chromium_sandbox=True` changes production launch behaviour on every host:
  any host that previously ran unsandboxed (the baseline `42d4337` state) will
  now fail launch unless it supports the sandbox + the Compose profile is in
  place. That is the point of #28, but it makes the S5 NAS smoke run a hard
  gate, not a formality.
- The batch launcher's `except Exception → None` swallows the guard's
  `ValueError` into a logged error — consistent with its existing error
  style, but the daemon (structured `failure_record`) and the batch (plain
  log) report the same rejection differently. Accepted (batch path is legacy;
  behaviour preserved per contract point 2).
- dev has diverged from the PR base in 4 files; merges are manual but the
  hunks are verified non-overlapping (S4 re-checks pre-images).
- If the author pushes a new head, S1 must re-run on the new head (failure
  mode); the current head is the reviewed one.

## Integration plan (S4, Gitea dev)

| File | Action | Note |
|---|---|---|
| `.gitattributes` | apply PR head (new) | base-identical |
| `doc/CHROMIUM_SANDBOX.md` | apply PR head (new) + M1/M2 if confirmed | base-identical |
| `docker-compose.yml` | apply PR head | base-identical |
| `docker/PLAYWRIGHT-LICENSE` | apply PR head (new) | CRLF preserved (verify after copy) |
| `docker/chromium-seccomp.json` | apply PR head (new) | verify SHA256 after copy |
| `apps/BillCollectorServices_pw.py` | apply PR head | base-identical |
| `tests/check_chromium_sandbox.py` | apply PR head (new) | |
| `tests/check_image_runtime.py` | apply PR head | base-identical |
| `tests/run_sandbox_container.py` | apply PR head (new) | |
| `tests/test_bc_browser_sandbox.py` | apply PR head (new) | |
| `tests/test_sandbox_container_receipt.py` | apply PR head (new) | |
| `apps/billcollector/config.py` | manual | apply the `chromium_args()` guard hunk to dev's current content (keep dev's C1 `ntfy_topic` opt-in + #33 timeout row in `DEFAULT_SETTINGS`) |
| `apps/billcollector/runner.py` | manual | apply the `chromium_sandbox=True` line in `_launch_browser` to dev's current content (keep dev's #33 `recover_downloads` block) |
| `README.md` | manual | apply the header paragraph (above `## Table of Contents`) to dev's current README |
| `CHANGELOG.md` | manual | merge the PR's Unreleased/Added entry into dev's `## [Unreleased]` (Keep a Changelog order; entry first in `### Added`, above the #33 crash-recovery bullet) |

Optional maintainer-side changes (S3 decision):

- M1 (nit): `doc/CHROMIUM_SANDBOX.md` line 2 "This fork candidate is not an
  accepted upstream runtime policy." is fork-era wording; once integrated this
  **is** the accepted upstream runtime policy. Proposed replacement: "Runtime
  policy: required Chromium sandbox isolation for both application launch
  paths; see the limits section before deploying to another host."
  **Confirmed by the user at the S2 gate (2026-10-26T20:37Z); apply as-is at
  S4.**
- M2 (nit): `doc/CHROMIUM_SANDBOX.md` "On the qualified agentvm host, the
  paired default-policy control is:" names a specific host in a public doc.
  Proposed replacement: "On the qualified development host, the paired
  default-policy control is:". **Confirmed by the user at the S2 gate
  (2026-10-26T20:37Z); apply as-is at S4.**

Both are doc-only; no behavioural change. If the user declines either, the
PR head text is kept as-is (byte-faithful to the reviewed content).

## S3 execution record (2026-10-26)

- Preflight at proposal time: `dev` = `origin/dev` = `729e7e3`, clean tree;
  `git ls-remote github refs/pull/32/head` = `52bc1c9` (unchanged since S1);
  Gitea `main` `181a9cc`, `github/main` `5116627` unchanged.
- S3 gate: user confirmed the integration proposal **as-is**
  (2026-10-26T21:14Z). Confirmed proposal:
  - Byte-faithful from `refs/pr/32` (11 files): `.gitattributes` (new),
    `docker-compose.yml`, `docker/PLAYWRIGHT-LICENSE` (new, CRLF re-verified
    after copy), `docker/chromium-seccomp.json` (new, SHA256
    `cc3e61ca…1cc7849` re-verified after copy),
    `apps/BillCollectorServices_pw.py`, `tests/check_chromium_sandbox.py`
    (new), `tests/check_image_runtime.py`, `tests/run_sandbox_container.py`
    (new), `tests/test_bc_browser_sandbox.py` (new),
    `tests/test_sandbox_container_receipt.py` (new),
    `doc/CHROMIUM_SANDBOX.md` (new, + M1/M2).
  - Manual (4 files, hunks verified non-overlapping with dev):
    `apps/billcollector/config.py` `chromium_args()` guard (dev function body
    base-identical; dev's `DEFAULT_SETTINGS` change untouched),
    `apps/billcollector/runner.py` `chromium_sandbox=True` in
    `_launch_browser` (~L311; dev's #33 `recover_downloads` block untouched),
    `README.md` header paragraph above `## Table of Contents` (dev header
    base-identical), `CHANGELOG.md` Unreleased/Added: PR entry first, above
    the #33 crash-recovery bullet (all existing bullets kept).
  - No files skipped (all 15 PR files are candidates; the merge-base `D`
    private-path entries are comparison artifacts, never applied).
  - Commits (one concern each, dev-commits style):
    1. `feat: browser — require Chromium sandbox in both launch paths,
       reject sandbox-disabling args` — `config.py`, `runner.py`,
       `BillCollectorServices_pw.py`
    2. `docker: pin Playwright seccomp profile in the Compose service` —
       `docker-compose.yml`, `docker/chromium-seccomp.json`,
       `docker/PLAYWRIGHT-LICENSE`, `.gitattributes`
    3. `test: sandbox — launch kwargs, arg denylist, container receipt
       coverage` — `test_bc_browser_sandbox.py`,
       `test_sandbox_container_receipt.py`, `check_image_runtime.py`
    4. `test: sandbox — isolated container/host qualification tools` —
       `run_sandbox_container.py`, `check_chromium_sandbox.py`
    5. `doc: sandbox — policy doc (M1/M2 applied), README paragraph,
       CHANGELOG entry (PR #32, issue #28)` — `doc/CHROMIUM_SANDBOX.md`,
       `README.md`, `CHANGELOG.md`
- M1/M2 applied as-is at S4 (confirmed at the S2 gate; replacement text in
  the Integration plan above).

## Validation plan (S5)

Code checks — from the repo root with `apps/.venv/bin/python` on the exact
integrated dev tree:

- PR unit suites: `apps/.venv/bin/python -m pytest
  tests/test_bc_browser_sandbox.py tests/test_sandbox_container_receipt.py -q`
  → expected 41 passed (21 + 20).
- Full pytest: `apps/.venv/bin/python -m pytest tests/ -q` → all pass
  (dev baseline 487 + 41 new; environment skips allowed).
- Regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0, 7 scenarios / 8 PDFs, `VERDICT: PASS`
  (exit 3 → a real run holds the lock, stop it first).
- `ruff check apps tests` → nothing new beyond the known baseline.
- bandit on the changed files → nothing new beyond the known baseline
  (the new tools carry justified `# nosec B404/B603/B108/B101`-style markers;
  test-code `assert` idioms as in the #33 delivery).

Deployment-process validation — **trigger fires** (the PR changes
`docker-compose.yml` runtime configuration and adds `docker/` host-side
policy files; it changes the app's browser launch behaviour). Per the
sequencing decision, S5 runs the **full block on the NAS** (Docker-capable
deploy host), scheduled to the NAS window:

- `bash -n` on changed shell scripts → n/a (the PR changes no shell script;
  record that).
- From the exact dev tree on the NAS: `bash install_docker-image.sh` → build
  succeeds.
- `python3 tests/check_docker_context.py` → `Docker context: 19 private
  canaries excluded, 5 source files retained` (fixed synthetic list — the new
  `docker/` files are host-side and do not change the expectation).
- PR's own qualification on the NAS (qualifies the NAS host itself):
  `python3 tests/run_sandbox_container.py --image billcollector-sandbox:check
  --profile docker/chromium-seccomp.json --expect active --output
  tmp/sandbox-active` and the `--runtime-regression` variant → receipts with
  exit 0, `cleanup_verified: true`, removed anonymous volumes.
- Smoke run the way the deploy runs it (`BillCollector.sh` on the NAS): the
  service comes up **with** the new Compose seccomp profile and
  `chromium_sandbox=True` in place, then stop it. This is the deciding check
  for the primary risk above (NAS policy vs unprivileged namespaces).
- Record host, validated tree hash, and every result in this doc's
  Deployment validation section; the user confirms the result (or a failure
  with the exact host/image error) before S6/S7 proceed.

## Deployment validation

- Pending S5 on the NAS (see Validation plan). Not to be skipped: the
  `docker-compose.yml` + `docker/` changes are the deploy surface.

## Out of scope

- The fork-only `sandbox-candidate.yml` workflow (excluded by the author; no
  CI infrastructure is introduced upstream).
- Host-policy changes (AppArmor profiles, UGreen-specific qualification) —
  explicitly not claimed by the PR.
- Native (non-Docker) install hardening — documented as a prerequisite only.
- The reserved `--expect disabled` checker option (not exercised by the PR's
  evidence).
- The new PRs #35/#39/#40/#41 (post-sequencing arrivals; separate
  sequencing decision).
- Issue #28 closure mechanics (S7 decision point: the contract is delivered
  by this PR; close #28 with a comment or leave open per user decision).

## Open questions

- ~~S3 gate: user review of the verdict + integration plan; M1 / M2 decisions
  (default: apply both — doc-only).~~ — **Confirmed at the S2 gate,
  2026-10-26T20:37Z**: verdict approve, M1 and M2 both applied, plan doc
  committed as `fcaafe6` and pushed to origin/dev.
- ~~S3 gate: confirm the exact integration proposal.~~ — **Confirmed
  as-is 2026-10-26T21:14Z** (recorded in the S3 execution record above).
  Next: S4 selective integration on dev.
- S5 gate: the NAS window for the full deployment-validation block; if the
  NAS smoke run fails on namespace policy, the decision path (per the PR doc:
  record the exact failure first) is a user call.
- S7 gate: PR close comment text; issue #28 close-or-leave decision + comment
  text; Discussion summary text.
