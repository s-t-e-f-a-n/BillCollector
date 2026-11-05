# Bourse Direct engine boundary

This boundary implements the [issue #51 agreement](https://github.com/s-t-e-f-a-n/BillCollector/issues/51#issuecomment-6560326064).
It does not contain or qualify a provider collector. The recipes project owns
the portal selectors, HTML parser and source identity proofs.

## Install the candidate

Install the reviewed catalog Python file as
`apps/recipes_playwright/bourse_direct_adapter.py`, next to the recipes.
`config.RECIPE_DIR` is the fixed installation directory. YAML cannot select a
module, path, entry point or another provider. There is no plugin discovery or
registration API. This is trusted application code. Review it with its recipe;
the capabilities below are an integration interface, not a Python sandbox.
Do not install untrusted Python through the recipe editor.
The file must be owned by the runtime user and must not be group- or
world-writable. A normal `0644` file passes this check. The image build removes
group/world write bits from the installed adapter file.

The file declares a literal `CHAINS` dictionary and `collect(api, options)`:

```python
CHAINS = {
    'calendar_html': [
        {'method': 'frame_locator', 'arguments': [{'selector': 'iframe#calendar'}]},
        {'method': 'locator', 'arguments': [{'selector': 'body'}]},
        {'method': 'inner_html'},
    ],
    'select_account': [
        {'method': 'frame_locator', 'arguments': [{'selector': 'iframe#calendar'}]},
        {'method': 'locator', 'arguments': [{'selector': 'select#nc'}]},
        {'method': 'select_option', 'arguments': [{'value': 'synthetic'}]},
    ],
}

def collect(api, options):
    # Implement the provider checks described below in the recipes project.
    raise NotImplementedError('A qualified provider adapter is required')
```

These selectors are examples, not portal evidence. The Python module may use
standard-library parsers. Keep Playwright access in its declared chains and the
engine's authenticated read methods. Do not import another browser, collector,
vault client or variable engine. Do not hide collection in injected JavaScript.

Load, save and run start parse the literal declaration without importing or
executing the module. Every chain passes the installed Playwright C3 signature
and argument gate. Reserved engine actions are prohibited inside adapter chains.
The engine also validates its authenticated-request chain. Run start freezes the
source and manifest before display, vault or browser access. A concurrent catalog
change cannot replace the code of an admitted run.

## Recipe

Use one service and one task for one account. Before collection, navigate through
ordinary C3 methods and execute one native `login` block. Follow
[SAFE_LOGIN.md](SAFE_LOGIN.md) for stored sessions, password submission and optional
fresh TOTP phases. Its final success locator must prove the authenticated session.
The adapter receives no credential resolver, vault client, task database or login
callback. The runner admits collection only after the native login proof succeeds.

Add this standalone top-level step after that login block:

```yaml
- step: 3
  notice_identity:
    query_parameters: [nc, type, year, month, day]
  methods:
    - method: bourse_direct
      arguments:
        - account_type: PEA
          max_months: 120
          max_items: 200
          timeout_ms: 7200000
```

The fixed identity fields `nc`, `type`, `year`, `month`, and `day` belong to the
engine contract. They are provider-specific and hard-coded in the engine.
Changing these fields requires an engine change and upstream agreement; a
recipe-only change cannot redefine them. See the accepted
[issue #59 boundary](https://github.com/s-t-e-f-a-n/BillCollector/issues/59#issuecomment-6644532027).

The exact options are required. `account_type` is `PEA` or `PEA-PME`.
Bounds are positive integers: at most 120 months, 200 offered items and
7,200,000 milliseconds. No locator prefix, graceful mode, nesting or second
collection is allowed. The historical locator -> `bourse_direct` YAML must be
replaced. No invocation options are introduced.

## Acquisition interface

| Member | Contract |
| --- | --- |
| `api.dates` | Native immutable `DateContext`: `date_from` and `today`, fixed at run start. |
| `api.months` | Descending `(year, month)` tuples for every complete month intersecting the inclusive date window. Rejects an insufficient month budget before adapter execution. |
| `api.call(name, **arguments)` | Execute a declared Page-rooted chain. Optional keyword arguments replace the final method's arguments. Validate the resulting chain with C3 before dispatch. No variable expansion occurs here. Return data only, never a raw browser object. |
| `api.remaining_ms()` | Remaining total acquisition deadline. Raises after expiry. All engine calls check it. Playwright calls with a timeout parameter receive a positive timeout capped to this deadline. |
| `api.offered(count)` | Count all offered items before reading that month, including repeats. Reject a total above `max_items`. An empty month counts zero and still requires source proof. |
| `api.read(url)` | Read unchanged notice HTML bytes through the current authenticated context. Require the entry page's origin, no redirects, exact response URL, HTTP 200 and 1 byte..20 MiB. Dispose each response. Total reads, including originals, are at most `2 * max_items`. |
| `api.save_original(url, filename)` | Read the offered PDF through the same transport. Require `%PDF-` and a plain `.pdf` basename. Pass unchanged bytes and source URL to native `track_download`, with the step's notice identity. Save at most the counted offered items. |

The module must not retain a browser object or implement blocking work outside
these calls. The time budget is enforced at capability boundaries, not by a
Python process sandbox. Calls that return API objects must end in a data read.
Use `read` and `save_original` for source documents so their transport and bounds
apply. Do not fetch originals through a browser chain or a separate HTTP client.

Before each month, prove the offered account and month. Keep PEA and PEA-PME
distinct. Follow offered controls. Prove an explicit empty listing. Reject
ambiguous identity or source drift. Count every offered item. Follow notice HTML
to its unique offered `Format PDF` URL and verify account, type and date before
`save_original`. Read every original before notice-revision comparison. Do not
use a daily source key to skip corrections.

The step runs once automatically. A failure enters the existing runner pause;
an operator resume is an explicit new attempt after inspection. Errors contain
no provider values. No new pending state or receipts are added. Native Run
results remain unchanged, including failure for a completed empty run. Native
at-least-once delivery and `task_id:sha256` keys remain unchanged. Full and
incremental invocations use the same task, recipe and history. This adapter
always reads each offered original before revision comparison. It does not use
`download_all` incremental source keys to skip a notice or its corrections.
The existing `download_all` options `incremental` and `unpack: pdf` keep their
upstream behavior. They are not adapter options. The adapter accepts original
PDFs only; it does not unwrap ZIP transports.

## Isolated engine proof

Install `apps/requirements.txt` and pytest in an isolated environment. From the
checkout root, use the browser cache that matches Playwright 1.63.0:

```sh
PLAYWRIGHT_BROWSERS_PATH=/path/to/browser-cache \
BC_BROWSER_DIR=/path/to/browser-cache \
<isolated-python> -m pytest tests/test_bc_bourse_direct_boundary.py \
  tests/test_bc_method_validation.py tests/test_notice_identity.py \
  tests/test_bc_login.py tests/test_bc_calendar.py tests/test_bc_collection.py \
  tests/test_bc_runner.py tests/test_bc_incremental.py tests/test_bc_archives.py -q
```

The boundary suite installs a synthetic catalog file in a temporary directory.
It proves all C3 gates, rejection before resources, no preflight execution,
frozen source, the actual adapter dispatch, native session proof, authenticated
original reads, unchanged stored bytes, regenerated repeats, material corrections,
source drift, empty proof, bounds and single automatic execution. Existing suites
cover native password/TOTP, dates, collection and notice compatibility.
The native-runner scenarios also check persisted Run outcomes, delivery keys,
and a second run combining adapter reads with incremental ZIP extraction.
The adapter rereads originals while `download_all` skips its known ZIP key.
No provider login, vault, production or private original is used. The recipes
project must still qualify its actual provider file and YAML on this exact
engine commit. The retained negative probe remains a historical-baseline proof.

Recovery: revert this focused engine commit and remove this action from any
unpublished recipe candidate. No database migration or live-state repair is needed.
