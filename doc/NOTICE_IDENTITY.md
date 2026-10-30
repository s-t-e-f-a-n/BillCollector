> Issue #38 implementation. Existing recipes retain the baseline byte-hash
> download path. The notice path builds on the #33 staged-publication and
> crash-recovery pipeline, which remains unchanged.

# Notice identity and PDF revisions

The collector owns repeat suppression. Paperless owns archive storage. A
download record is not an archive receipt. This feature does not change
delivery recovery, consumer error handling, run results, scheduling, or
financial import behavior.

## Recipe interface

Opt in on a daemon `expect_download`, `download_all`, or `replacement_calendar`
step. For example:

```yaml
step: 4
notice_identity:
  query_parameters: [account, notice]
methods:
  - method: expect_download
steps:
  - step: 1
    methods:
      - method: get_by_role
        arguments: [{role: link}, {name: Download}]
      - method: click
```

Use the provider's stable account, document kind and source notice identifier.
The example uses invented field names. It is not a Bourse Direct recipe.
The recipe must verify the selected account and document kind before download.
A date or filename alone is insufficient. Include a source discriminator when
several notices can exist on the same day. The task must represent one account.

The source identity includes the HTTP(S) origin, URL path and declared query
fields. The database lookup scopes that identity to the task. Each field must occur exactly once with a nonblank value. Credentials
in the URL authority, blob URLs and missing or repeated fields are refused.
Undeclared query fields can include session tokens and do not affect identity.
The collector stores only a SHA-256 digest of this identity. It does not retain
the selected query values. Existing sanitized download URL retention still
applies. Do not use a query credential as an identity field.

## Revision rule: pdf-graph-v1

The revision hashes the parsed PDF object graph with pypdf 6.21.2. It retains
page content, encoded streams, fonts, images, annotations, attachments, forms,
XMP, document metadata and local destination targets. Original bytes are never
rewritten. The following generation differences do not create a revision:

- Trailer `/ID` and Info `/CreationDate` and `/ModDate`.
- Indirect object numbers, dictionary order and stream `/Length`.
- A generated alias of form `[A-Za-z]{3}_[A-Za-z0-9]{6}` for a single named
  destination in a single-child name tree, its
  matching `/Limits`, and matching local `/Dest` and `/GoTo` references.
  Destination targets and outline titles remain part of the revision. External
  links to that alias are outside this content-identity contract.

Text equality is never a dedup key. A change to any other retained graph value
creates another revision. Recompression, XMP timestamp changes or a different
object-sharing layout can conservatively create another revision. This is not
a claim that all visually equivalent PDFs deduplicate. Changing this rule needs
a new fingerprint version and fresh acceptance evidence.

A new source or revision publishes its untouched original through the existing
consumer path. An unchanged revision points to the first original and does not
publish or call consumers again. Download rows retain the raw hash and size of
each attempt plus `duplicate_of_id`. Regenerated duplicate bytes are discarded
from temporary staging. Earlier revisions remain available. Equal filenames
receive unique output paths; opted-in collection steps permit those names.
Default collection steps retain their existing collision guard.

Encrypted, empty, oversized (>20 MiB), malformed or unsupported PDFs fail the
step without a revision record or publication. Traversal stops at 100,000 nodes
or depth 100. Parser diagnostics are suppressed and warnings reject identity.
The parser does not decode content streams. The existing runner failure/pause
contract applies; there is no text-only fallback.

## Existing databases and recovery

The schema adds nullable `source_identity` and `revision_sha256` columns and an
index. Existing rows and raw-SHA behavior remain intact. There is no automatic
historical conversion or private-file scan. The first opted-in acquisition of
an old notice can publish once because historical rows have no source identity.
A later acquisition of that revision is suppressed, including after DB reopen.
Different sources can publish identical bytes; different tasks never share the
notice-identity dedup key. A task/account reconfiguration needs its own history
and recovery decision.

The existing publication/consumer/DB crash window remains unchanged. There is
no exactly-once consumer guarantee. Keep existing originals and database backup
procedures. An unavailable archive copy is not recovered by re-downloading an
unchanged revision; use the archive recovery procedure.

Rollback: revert the code commit. Keep the additive columns; the old engine
ignores them. Restore a pre-change DB backup only under an independently approved
recovery plan. Never downgrade a live database automatically.

## Isolated verification

```bash
apps/.venv/bin/python -m pytest -q tests/test_notice_identity.py
```

Expected: all tests pass. The browser test uses intercepted loopback downloads,
original synthetic PDFs, equal filenames, three runs, one correction and no
external service. Other tests cover reloads, account/source separation, hashed
identities, invalid input, legacy migration and non-text corrections.
