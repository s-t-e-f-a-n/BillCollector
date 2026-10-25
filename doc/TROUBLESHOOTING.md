# Troubleshoot by symptom

Start with the task detail and session pages. Note the run ID, failed step and
error category. Keep account names, screenshots, pause contexts, logs and PDFs
private. Inspect a bounded local log if needed; redact it before sharing.

| Symptom | Likely cause / check | Safe next action | Proof of resolution |
|---|---|---|---|
| Container exits or cannot write the database/downloads | Bind path is missing, a file mount became a directory, or UID/GID differs. | Stop the new instance. Check that `apps/.env` is a file and that the configured UID/GID can write the mounted directories. Correct the specific path. | Container stays healthy; the UI loads and a setting survives restart. |
| `/_alive` is 200 but collection fails | Health checks do not contact the vault or portal. | Read the run's actual error and use the relevant row below. | Vault check and one manual collection both pass. |
| Vault URL not set, DNS unavailable, or non-local HTTP address error | Wrong API URL, hostname or Settings override. HTTPS and public addresses are rejected by the transport. | In Settings or onboarding, check the effective URL. A non-empty saved setting overrides the environment. Use the private HTTP `bw serve` endpoint, not the Vaultwarden web URL. | **Vault → Check** reports reachable and unlocked. |
| Vault reachable but locked | `bw serve` cannot supply credentials while locked. | Unlock it through the vault's own supported workflow. Do not put an unlock secret in a recipe or log. | The vault check reports unlocked; the next approved run reaches the portal. |
| Vault HTTP 4xx | Item name or optional HTTP Host header does not match. | Check task service/account against `<service> <account>`. Set `BW_API_HOST` only when the API requires it. A 400 from the TOTP endpoint alone means no TOTP; other 4xx are failures. | The intended item resolves without exposing its values; one manual run reaches login. |
| Portal session expired | Stored cookies no longer prove the authenticated state. | Check the recipe's success marker. A phased login can authenticate once within its budget. If manual work is required, use the supported session controls. | The final success marker is visible and collection proceeds. |
| Login blocked or pending | The phased-login budget is exhausted, or an attempt remains unresolved after interruption. | Stop automatic attempts. Inspect the last run. When idle and blocked, **Clear login block** allows one further attempt. Pending and blocked are different states; do not edit database counters. | One approved attempt proves the final session and resets the budget. |
| Changed selector / `step_failed` | Locator no longer matches, matches several controls, or the expected page is absent. | Inspect the session context. Use the repair link to propose a targeted locator change. Validate it and keep a source copy outside the container before recreation. Resume only when replay of that step is safe. | The intended control is unique and the corrected step completes. |
| Browser or virtual display cannot start | Missing runtime binaries, missing browser build, exhausted display range, or profile already in use. | For Docker, rebuild from the checkout. For host execution, check Xvfb, x11vnc, websockify and noVNC packages. Use distinct task profiles and wait for owned runs to stop; do not remove another run's locks. | A new run allocates and releases its display and profile normally. |
| UI works but noVNC does not | noVNC is a separate websockify endpoint; UI login does not authenticate it. The local quick start leaves its ports unpublished. | Use the UI's supported controls. Review issue #27 F03 before configuring a permanent external access path. Do not publish the range to make the error disappear. | Both routing and channel authentication are explicitly verified for the chosen deployment. |
| `download_failed` / partial collection | Server error, missing event, ambiguous control, changing list or exhausted bound. Earlier successful files may already exist. | Inspect the run's downloads and the portal list. Preserve prior records. Correct the cause before a deliberate resume. Never assume an unsuccessful run downloaded nothing. | Expected files are present once, with the intended keys/content and a complete run record. |
| Duplicate badge | The same task already recorded this file's SHA-256. | Check the original Download record. The file can still be saved; consumer hooks are skipped for duplicates. Do not delete state to force archive delivery. | The original record and the downstream archive agree on the document. |
| No new documents, but run says `failure` | Current result logic requires a successful download. Empty-result semantics are still under review. | Compare the portal list and run evidence. Record an empty-list outcome separately; do not invent a missing file or repeatedly rerun login. | The portal has no expected new document; later releases may provide a dedicated result. |
| File downloaded, archive has nothing | A download is not an archive receipt. The default consumer registry has no integration. Consumer exceptions are logged and do not force run failure. | Check the configured download directory, consumer/mover and archive ingestion separately. Preserve the source file during diagnosis. | The archive contains the intended document and can open it. |

## Bounded local checks

From the checkout used by the [quick start](QUICKSTART.md):

```bash
docker compose -p billcollector-local -f docker-compose.yml -f compose.local.yaml ps
docker compose -p billcollector-local -f docker-compose.yml -f compose.local.yaml logs --tail 80 billcollector
curl --fail --silent --show-error http://127.0.0.1:8766/_alive
```

Logs can contain private filenames or task identities. The recipe validation
errors in older public versions can also contain input values. Keep the output
local. Share only the run ID, step, category and a redacted excerpt.

**Reset profile** deletes that task's browser profile after confirmation. It is
not a general repair action and does not clear a login block. Preserve cookies
and evidence unless a deliberate cold login is required. For persistent data,
stop writes and take a recoverable copy before any migration or restoration.
