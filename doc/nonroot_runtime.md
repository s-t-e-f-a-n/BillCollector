# Non-root container runtime

The Playwright image defaults to UID/GID `1000:1000`, configurable with `APP_UID`/`APP_GID` build args. Application source and
browser binaries stay root-owned. Writable paths are limited to `/apps/db`,
`/apps/Downloads` and `/apps/runtime`; the current disposable profile is under
`/apps/runtime/profile`. This preserves the current reset-on-run behavior;
per-account session persistence is a separate contribution.

The wrapper runs as the invoking non-root host UID/GID. It mounts the existing
DB and Downloads paths and creates a private profile tmpfs for that identity.
It forwards `.env` at runtime and refuses root invocation. A trusted pre-existing
Downloads symlink remains supported, including the configured DMS inbox.
The wrapper never recursively chowns or chmods existing operator directories.
The upstream installer retains its separate, documented mount-ownership setup.

For existing root-owned runtime data, stop the run and choose an operator-managed
ownership/ACL migration first. The chosen UID must be able to traverse and write
the DB and download paths, including existing SQLite/log/lock files and the
wrapper's host lock `apps/.bc.lock` (a root-owned one makes the wrapper exit 1); the DMS must
retain its required read/consume permissions. Do not blindly change an entire
Paperless consume tree. The wrapper detects directory permissions, and runtime
checks surface incompatible existing files.

Direct Docker users must provision bind permissions for the image UID (1000 by default) or their chosen
`--user`, and mount `apps/.env` read-only at `/apps/.env` (dotenv syntax is preserved). For arbitrary UID/GID runs,
add `--tmpfs /apps/runtime:uid=<uid>,gid=<gid>,mode=0700`. The log and process lock
default to `/apps/db/bc.log` and `/apps/db/.bc.lock` in the image; the wrapper
retains its separate host lock at `apps/.bc.lock`. Cooperating direct containers
share the process lock when sharing the same DB mount. Direct local Python runs
keep the old path defaults unless the environment overrides them.

Non-root execution does not enable Chromium sandboxing; that is a separate gate.
No output topology, run-result or database schema change is included.

Verification: build `Dockerfile` into an isolated tag, then run
`python3 tests/check_nonroot_container.py <image>`. Tests use no live mounts or
vault. Rollback is reverting this patch/rebuilding the previous image; no state
migration or production deployment is performed by the contribution.

The wrapper forwards the operator's supplementary numeric groups using
`--group-add`, so shared Paperless/DB permissions match the host preflight.
Direct Docker users need equivalent group mapping when access depends on a
secondary group. Existing directory permissions are never changed by the wrapper.

The single Dockerfile, configurable UID/GID, OCI labels and dependency-layer
cache layout from upstream main are preserved. This contribution adds source
protection and host identity mapping to the existing non-root baseline.
Container checks cover the configured default identity and arbitrary UIDs;
run them on a custom APP_UID/APP_GID build as well when changing those args.
The packaged manual UI is documented for local Python execution. This check
covers the CLI container only: the UI still writes supervisor state under
/apps, so launching it against this protected tree needs a separate agreed
writable UI state path. Local Python UI usage is unchanged.
