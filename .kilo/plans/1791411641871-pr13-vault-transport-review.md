# PR #13 Review — fix: pin vault API requests to validated local targets

> Status: AWAITING-DECISION (2026-10-08) — S3 decision recorded: proposal
> confirmed as-is, Q1 + Q5 accepted; NAS `.env` check pending (S7
> prerequisite); S4 next.

Repo `s-t-e-f-a-n/BillCollector`, PR by **flowcool**, head `76a7b9e`
(`76a7b9ed68a4dd2b10a60004780b0f6b1acdb07d`, 6 commits, branch
`feature/playwright-vault-transport`), declared base `main` = `b62821b`
(current public tip), **actual merge base `2f6952e`** (Oct-4 public tip,
4 commits behind). Created 2026-10-05T08:41Z, last head push
2026-10-07T21:52Z; fetched as `refs/pr/13` 2026-10-07, API head sha matches
(no drift). No issue reference. Review date 2026-10-07, against local state
`dev` = `b4dd3d9` / `main` = `b4dd3d9`, public mirror `github/main` =
`b62821b`.

## Verdict

**Approve with maintainer changes** (S2, 2026-10-08).

The transport is sound and strictly stronger than the replaced `nslookup`
check: every DNS answer is vetted in-process (RFC-1918 + loopback only —
public, mixed, empty and link-local answers incl. cloud metadata
`169.254/16` refused), numeric targets are pinned before send, ambient
proxies/credentials are ignored, redirects are refused, POST replay after a
partial response is excluded (proven by the real loopback test), and the
`nslookup` subprocess dependency is removed. No new network exposure; shared
interfaces unchanged (`--vault` keeps exit 4); no secrets. The 20-test suite
coexists with dev's 11-test PR-#11 suite (forward-compat branches), so the
integrated state passes both regardless of merge order.

Mandatory maintainer changes (executed in S4):
1. **Manual merge of `apps/BillCollector.py`** — the PR head (pre-#11 orphaned
   tip) carries six unsanitized log lines and drops the locked-status log;
   dev's sanitized logging is kept verbatim. Byte-for-byte application would
   fail `tests/test_vault_diagnostics.py`.
2. Manual merges of `README.md` (`.env`-variables hunk only) and
   `CHANGELOG.md` (two bullets appended to dev's `## [Unreleased]`
   `### Fixed`).
3. User decisions on the open questions: breaking-config acceptance (Q1),
   NAS `.env` readiness (Q2), stale-`VAULT_HOST` cleanup (Q5).

Non-blockers: no issue referenced (PR #12 precedent: fix touching no shared
interface → minor gap); the PR body's combined multi-PR proof used stale
heads (S5 re-proves on the exact `dev` tree). The six log regressions are
base-lag artifacts of the pre-#11 tip, not author intent — refusal is not
warranted.

## S3 Decision (2026-10-08)

User confirmed the integration proposal (A–H, presented in S3) as-is:

- **Q1 accepted** — the breaking config change ships: `BW_API_URL` plain-HTTP,
  loopback/private-only; `VAULT_HOST` unused.
- **Q5 accepted** — the stale-`VAULT_HOST` cleanup ships as the fourth commit
  (`refactor: vault: drop dead VAULT_HOST config`: dead `os.getenv` + `defs`
  param, `vault_preflight` docstring, `--vault` help text).
- Commits: 1 `fix: vault: pin API requests to vetted local targets`,
  2 `test: vault: add transport suite, pin --vault preflight`,
  3 `doc: vault: document pinned-HTTP transport contract`,
  4 `refactor: vault: drop dead VAULT_HOST config`.
- **Q2 partial** — local dev host `apps/.env` verified:
  `BW_API_URL=http://solg.fritz.box:8087` resolves to `192.168.1.99` (private,
  plain HTTP) → passes the new policy. The NAS `.env` check from the dev host
  failed (ssh `publickey` denied in the agent session; deploy ssh works from
  the user's shell). User runs the read-only check:
  `ssh root@192.168.1.99 "grep -E '^(BW_API_URL|BW_API_HOST|VAULT_HOST)=' /srv/disk-by-label/Docker/docker-recipes/BillCollector/.env"`.
  NAS readiness remains an S7 promotion prerequisite (operational).

## Verified facts

- Merge base is `2f6952e` — the same pre-#11 orphaned public tip as PR #11 and
  #12. The PR's first commit `38ff01b` ("doc: add CONTRIBUTING.md") is the
  orphaned Oct-4 recommit of Gitea `4456d75` (verified: not an ancestor of
  `github/main`, present in the PR head history).
- 28 files in the diff = **18 deletion artifacts** (all `.kilo/*`,
  `.private/sync_github.sh`, `.vscode/*` — present at the merge base, absent
  at the PR head and at current `github/main`; fork-behind-base comparison
  noise, identical to PR #11/#12, never applied from a PR head) + **10 real
  content files**:
  - `CHANGELOG.md` (+8), `CONTRIBUTING.md` (+72), `README.md` (+4/−3),
    `apps/.env.example` (+2/−2), `apps/BillCollector.py` (+10/−46),
    `apps/requirements.txt` (−1), `apps/vault_transport.py` (+100, new),
    `doc/vault_transport.md` (+39, new), `tests/run_regression.py` (+8/−7),
    `tests/test_vault_transport.py` (+285, new).
- Pre-image checks against Gitea `dev`:
  - **Clean apply** (dev byte-identical to the PR base): `apps/.env.example`,
    `apps/requirements.txt`, `tests/run_regression.py`.
  - **New** (absent on dev): `apps/vault_transport.py`,
    `doc/vault_transport.md`, `tests/test_vault_transport.py`.
  - **No-op**: `CONTRIBUTING.md` (byte-identical to dev).
  - **Diverged → manual**: `apps/BillCollector.py`, `README.md`,
    `CHANGELOG.md`.
- **Key divergence — the PR head regresses PR #11.** `dev`'s
  `BillCollector.py` is byte-identical to `github/main`'s (PR #11's
  sanitization is in both). The PR head, being based on the pre-#11 tip,
  carries six unsanitized log lines that dev has already fixed:
  1. `vault_request` retry warning logs the raw exception (`failed: {e}`) —
     dev: `network error ({type(e).__name__})` with the bounded-diagnostics
     comment;
  2. 4xx `VaultAPIError` appends `- {response.text}` — dev: status only;
  3. 5xx warning appends `- {response.text}` — dev: status only;
  4. final exhaustion error appends `: {url}` (URL holds the vault item
     name) — dev: no URL;
  5. `bitwarden_api_check_status` does `logger.debug(content)` (full status
     body: account email + server URL) — dev: constant string;
  6. `post_json` error appends `- {response.text}` — dev: status only.
  Plus a seventh: `WebRetriDoc` drops the `logger.error("Vault API status:
  locked / check failed …")` line (and its comment) before `sys.exit(1)` —
  dev logs the parsed state (PR #11 finding 4).
  Byte-for-byte application would therefore fail dev's PR-#11 suite
  (`tests/test_vault_diagnostics.py`, 11 tests: marker/URL assertions in
  `assert_safe`) → **manual merge of `apps/BillCollector.py` is mandatory**.
- The real PR content in `BillCollector.py` is 5 structural changes:
  (1) drop `from nslookup import Nslookup`; (2) add `from vault_transport
  import VaultTransportError, pinned_api_url, vault_http_request`; (3) delete
  `extract_ip` / `is_local_ip` / `is_domain_local_ip` (40 lines); (4)
  `vault_request` routes through `vault_http_request(method, url, payload,
  VAULT_TIMEOUT)` with a new `except VaultTransportError → VaultAPIError(str(e))
  from None` clause; (5) `WebRetriDoc` preflight switches from
  `is_domain_local_ip(self.vault)` to
  `pinned_api_url(self.api, VAULT_MAX_ATTEMPTS, VAULT_RETRY_BACKOFF)` with a
  constant info log.
- The two suites coexist by design: dev's PR-#11 tests
  (`tests/test_vault_diagnostics.py:26-36`) switch to patching
  `collector.vault_http_request` when the attribute exists (forward-compat
  with this PR), so the integrated state must pass **both** suites (11 + 20).
- dev constants `VAULT_TIMEOUT = 10`, `VAULT_MAX_ATTEMPTS = 3`,
  `VAULT_RETRY_BACKOFF = 2` (apps/BillCollector.py:77-79) match every
  expected value in the PR's tests (sleep `2/4`, timeout tuple `(5, 10)`,
  `call(…, 10)`).
- Residuals left by the PR (present in the PR head, not part of its diff):
  `os.getenv("VAULT_HOST")` is still loaded into `defs` (BillCollector.py:290,
  both dev and head) and becomes dead config; the `--vault` argparse help
  (`tests/run_regression.py:321`) and the `vault_preflight` docstring
  (lines 86-89) still mention `VAULT_HOST` in the PR head (stale text).
- Process (CONTRIBUTING.md): intended behavior + verification stated (unittest
  command, expected 20 OK, ruff `F821`+`E4,E7,E9`, bandit 1.9.4); proof
  shipped (20-test suite incl. a real synthetic loopback partial-response
  test); AI assistance declared ("under Florent's review and responsibility");
  no secrets (synthetic markers, `127.0.0.1`, ephemeral ports); **no new
  network exposure** — it reduces it (pins to vetted numeric local targets,
  ambient proxies disabled, redirects refused, `nslookup` subprocess dep
  removed); no shared interface touched (DB schema, control protocol, recipe
  contract, exit codes — `--vault` keeps exit 4). Gap: **no issue referenced**;
  issue #10 explicitly carves "vault transport policy" out as a separate
  contribution topic, so no agreed issue exists (PR #12 precedent: fix with no
  shared interface → minor gap, not a blocker).
- Cross-PR: open PRs #14 (CI workflow), #15 (non-root container), #16 (image
  build tooling) — no file overlap with #13's content. The PR body's
  "final combined integration proof" (disposable clone merging five heads)
  used **stale heads** (#13 `5b4243e` vs current `76a7b9e`; #14 `fd38a5f` vs
  `08463b0`; #15 `29cab23` vs `0bae9f4`) — combined proof is stale; S5
  re-proves on the exact `dev` tree. No ordering dependency: #13 lands
  independently (PR #11's tests pass in either merge order).
- GitHub credential in `~/.git-credentials` is **not API-usable** (401
  "Bad credentials" on `GET /pulls/13` with Bearer); PR metadata was fetched
  from the public API unauthenticated. S7's comment/close will need a working
  token or the user's web UI (deploy-skill fallback).

## Code review findings

1. **`apps/vault_transport.py` (new, 100 lines)** — the core.
   - `pinned_api_urls`: hard URL policy (http-only; URL credentials, query,
     fragment, port 0 rejected before any DNS), then **every** `getaddrinfo`
     answer must fall in `10/8`, `172.16/12`, `192.168/16`, `127/8`,
     `fc00::/7`, `::1/128`; public, mixed, empty and link-local (e.g.
     `169.254.169.254` — cloud metadata) answers are refused. Returns
     deterministic sorted numeric targets (IPv4 before IPv6, bracketed IPv6)
     + the original netloc as default Host. Transient DNS
     (`EAI_AGAIN/NONAME/FAIL/NODATA`, portability-guarded) → `requests
     ConnectionError` with a **constant** message (retryable); policy failures
     → `VaultTransportError` (final).
   - Strictly stronger than the replaced code: old `is_domain_local_ip`
     checked only the first A answer of one `nslookup` subprocess call and
     did not even accept loopback; the new code vets all answers in-process
     and pins numeric addresses.
   - `pinned_api_url`: preflight wrapper honoring the caller's retry policy
     (defaults `3/2` = the vault constants).
   - `vault_http_request`: `trust_env = False` (ambient proxy/credential env
     ignored), `allow_redirects=False`, any 3xx → final `VaultTransportError`
     ("redirects are refused"); Host = `BW_API_HOST` override or original
     netloc, validated ASCII without whitespace/control characters (CRLF
     injection refused before any connection); connect budget shared across
     targets `timeout=(t/len(targets), t)`, read timeout stays the full `t`.
   - **Address fallback is restricted to pre-send connection failures**
     (`ConnectTimeout` or `MaxRetryError` whose reason is
     `NewConnectionError`); a body read timeout, reset or partial response is
     re-raised without replaying the request on another address — the right
     call for `POST /sync` idempotency, and proven by the real loopback
     partial-response test. Verified edge: `requests.ReadTimeout` is a
     `ConnectionError` subclass, so it enters the fallback guard but is
     correctly excluded by the `before_send` check.
   - Sanitization: network exceptions are re-raised **with the same class**,
     message replaced, `__cause__` suppressed — keeps the dev retry warning
     meaningful (`network error (ConnectTimeout)`) while stripping URL/body.
   - Minor notes (no action required): the request-path transient-DNS
     `ConnectionError` is raised outside the transport's sanitizing
     try/except (safe only because its message is a constant); `pinned_api_url`
     returns `targets[0], host` which both production callers discard (used
     by tests).
2. **`tests/test_vault_transport.py` (new, 20 tests)** — DNS/HTTP fully
   mocked except `test_partial_response_does_not_replay_post_on_another_address`,
   which runs a real synthetic `ThreadingHTTPServer` on `127.0.0.1` that sends
   `Content-Length: 100` then 1 byte and proves the POST is received exactly
   once (no fallback replay). Coverage: local-range acceptance incl. default
   port 80; public/mixed/empty/link-local rejection before any `Session`;
   unsafe URL forms rejected before DNS; bounded DNS failure; transient DNS
   recovery in preflight and request path; unknown-name retry while a `bw
   serve` sidecar restarts (`EAI_NONAME`/`EAI_FAIL`); preflight caller retry
   policy (`3/6/9` sleeps); 3-attempt DNS exhaustion → `VaultAPIError`;
   fallback only across vetted addresses with `(5, 10)` timeout tuples; read
   timeout and partial response without replay; non-ASCII and CRLF Host
   refusal before connection; proxy/redirect pinning; `BW_API_HOST` override
   + per-request DNS re-check; redirect finality without retry; exception
   sanitization (class kept, cause suppressed); retry/backoff/TOTP/final-4xx
   preservation; preflight vetting the API URL, not the remote backend. No
   secrets.
3. **`apps/BillCollector.py`** — the 5 structural changes (Verified facts);
   the six PR-#11 log regressions and the dropped locked-status log must NOT
   be applied (manual merge, Integration plan).
4. **`tests/run_regression.py`** — `--vault` preflight now calls
   `pinned_api_url(BW_API_URL)` (default `3/2`) instead of
   `is_domain_local_ip(VAULT_HOST)`; `VAULT_HOST` no longer required; exit 4
   semantics unchanged.
5. **`apps/requirements.txt`** — drops `nslookup==1.9.0` (the removed
   function was its only consumer; removes the external-binary dependency).
6. **`.env.example` / `README.md` / `doc/vault_transport.md`** — document the
   new config contract: `BW_API_URL` must be plain HTTP resolving only to
   loopback/private; `BW_API_HOST` optional for a `bw serve` in another
   container (`bw serve` accepts only `Host: 127.0.0.1:<port>` — a
   `localhost:8087` Host gets 403); `VAULT_HOST` unused (the backend may be
   Cloud while the CLI API stays local); HTTPS refused (`bw serve` speaks
   HTTP; no TLS-proxy support). README's "Contribute code … CONTRIBUTING.md"
   pointer already exists on dev.
7. **`CHANGELOG.md`** — two bullets under a new `### Fixed` (one marked
   **Breaking**); manual merge appends them to dev's existing
   `## [Unreleased]` `### Fixed`.

## Risks

- **Breaking config change (operational):** any deployment whose `BW_API_URL`
  resolves to a public address (or over HTTPS) will now exit 1 at the
  `WebRetriDoc` preflight. The local `apps/.env` carries `VAULT_HOST` (a
  public-looking domain) + `BW_API_URL`; the NAS `.env` must be checked/updated
  (LAN IP or private-only name, plain HTTP) **before or together with**
  promotion, or the next production run fails. See Open questions.
- **Direct GitHub merge would reintroduce the pre-#11 log lines** (the 3-way
  merge conflicts on the same hunks) — another reason the Gitea-first manual
  integration is mandatory; never merge on GitHub.
- `bw serve` Host check: a `BW_API_URL` using a non-loopback name needs
  `BW_API_HOST=127.0.0.1:<port>` or every request 403s (documented).
- The PR body's combined (multi-PR) proof is stale (heads moved after the
  disposable-clone test); S5 validation on the exact dev tree is the gate.
- Deployment-process validation is **triggered** (app runtime config /
  `.env` handling + `requirements.txt` → image content): S5 block on a
  Docker-capable host + user confirmation before S7 may commit/push to
  `main`.

## Integration plan (Gitea-first; per deploy skill)

1. Apply from `refs/pr/13` (new files, verbatim): `apps/vault_transport.py`,
   `doc/vault_transport.md`, `tests/test_vault_transport.py`.
2. Apply cleanly from `refs/pr/13`: `apps/.env.example`,
   `apps/requirements.txt`, `tests/run_regression.py` (pre-images
   byte-identical to dev).
3. Skip: `CONTRIBUTING.md` (byte-identical to dev); all 18 deletion artifacts.
4. **Manual — `apps/BillCollector.py`** (edit dev's file): (a) delete the
   `nslookup` import; (b) add the `vault_transport` import after the
   `BillCollectorServices_pw` import; (c) delete `extract_ip`, `is_local_ip`,
   `is_domain_local_ip`; (d) `vault_request`: replace the
   `requests.request(…)` line with
   `vault_http_request(method, url, payload, VAULT_TIMEOUT)` and insert
   `except VaultTransportError as e: raise VaultAPIError(str(e)) from None`
   before the existing sanitized `except requests.exceptions.RequestException`
   clause (keep dev's clause, comment and all sanitized messages verbatim);
   (e) `WebRetriDoc`: replace the `is_domain_local_ip(self.vault)` block with
   the PR's `pinned_api_url(self.api, VAULT_MAX_ATTEMPTS,
   VAULT_RETRY_BACKOFF)` try/except + `logger.info("Vault API resolves only
   to local addresses")`. Do **not** apply the six PR-#11 log regressions or
   the dropped locked-status log.
5. **Manual — `README.md`**: apply only the `.env`-variables hunk to dev's
   section (replace the `VAULT_HOST`/`BW_API_URL` bullets with the
   pinned-HTTP `BW_API_URL` bullet, the `BW_API_HOST` bullet and the
   `VAULT_HOST` no-longer-used note); keep dev's `.env` mount paragraph and
   all Docker sections (the PR's "removals" there are base-lag noise).
6. **Manual — `CHANGELOG.md`**: append the PR's two bullets to dev's existing
   `## [Unreleased]` `### Fixed` subsection (Keep a Changelog order already
   satisfied).
7. Optional maintainer-side change (user decides in S3): clean up the stale
   `VAULT_HOST` mentions — dead `os.getenv("VAULT_HOST")` in
   `defs(os.getenv("VAULT_HOST"), …)` (BillCollector.py:290), the `--vault`
   help text (run_regression.py:321) and the `vault_preflight` docstring
   (run_regression.py:86-89).

## Validation plan (S5, repo root, venv, exact dev tree)

- `apps/.venv/bin/python -m unittest tests.test_vault_transport -v` → expect
  **20 OK**.
- `apps/.venv/bin/python -m unittest tests.test_vault_diagnostics -v` →
  expect **11 OK** (guards the manual merge; the forward-compat branches now
  exercise `vault_http_request`).
- Full regression: `apps/.venv/bin/python tests/run_regression.py --ini
  tests/bc_regression.ini` → exit 0, 7 scenarios / 8 PDFs, `VERDICT: PASS`.
- ruff (`F821`, `E4/E7/E9`) + bandit on the changed files → nothing new beyond
  the known baseline (B608 dynamic SQL table names, B104 UI bind).
- `pip check` after the `nslookup` requirement drop (venv keeps the installed
  package; only the requirement line changes).
- Scope note: app + transport + config PR → full unit + regression scope, no
  recipe-only shortcut.

## Deployment validation (triggered; S5, before any commit/push to main)

- Trigger: the PR changes app runtime configuration (`.env` handling:
  `VAULT_HOST` dropped, `BW_API_URL` constrained, `BW_API_HOST` added) and
  `apps/requirements.txt` (image content). No shell scripts are touched, so
  `bash -n` has no target (recorded as such).
- On a Docker-capable host (the NAS, same Docker + BuildKit), from the exact
  dev tree: `bash install_docker-image.sh` → build succeeds;
  `python3 tests/check_docker_context.py` → `Docker context: 19 private
  canaries excluded, 5 source files retained`; smoke run the way the deploy
  runs it (`BillCollector.sh`) → service comes up, then stop.
  **Smoke caveat:** the run exercises the new vault preflight — it only passes
  with a locally-resolving plain-HTTP `BW_API_URL` in the host `.env` (see
  Open questions); if the host `.env` is not yet updated, record that the
  mock-scenario regression is the functional gate and the vault preflight is
  config-gated.
- Record host, validated tree hash and every result here; **user confirmation
  is required before S7** (commit/push to `main`).

## Out of scope

- PRs #14, #15, #16 (separate reviews); issue #10 (DOM/SQLite retention); the
  exact item/account identity work (declared separate by the PR author); the
  residual `Service … started.` identity log (PR #11 follow-up); the NAS `.env`
  update itself (operational, user action); the optional stale-`VAULT_HOST`
  cleanup (maintainer call in S3).

## Open questions

1. ~~**Breaking change acceptance**~~ — RESOLVED (S3, 2026-10-08): accepted.
2. **Deployment `.env` readiness** — local dev host verified OK (see S3
   Decision); NAS check pending — user runs the read-only ssh grep above;
   if the NAS `BW_API_URL` does not resolve only to loopback/private, the
   NAS `.env` must be updated before the S7 promotion, or the next
   production run exits 1 at the vault preflight.
3. **No issue referenced** — accept as a fix without an issue (PR #12
   precedent) or ask the author to reference/follow up with an issue.
4. **GitHub API credential unusable** (401) — S7's PR comment + close need a
   working token or the user's web UI.
5. ~~**Optional nit cleanup**~~ — RESOLVED (S3, 2026-10-08): included as
   the fourth commit.
