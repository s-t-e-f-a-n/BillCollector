# Chromium sandbox

Candidate contract: [upstream issue #28](https://github.com/s-t-e-f-a-n/BillCollector/issues/28).
Runtime policy: required Chromium sandbox isolation for both application launch
paths; see the limits section before deploying to another host.

Both the daemon and legacy batch launcher request `chromium_sandbox=True`.
An unsupported sandbox fails browser startup. Neither path retries with the
sandbox disabled. Existing run result and exit-code handling remain in place.
There is no automatic fallback and no environment switch to disable protection.

`BC_CHROMIUM_ARGS` still supports ordinary launch workarounds. It rejects
`--no-sandbox`, `--disable-setuid-sandbox`, `--disable-seccomp-filter-sandbox`,
`--disable-namespace-sandbox`, `--disable-gpu-sandbox`, `--single-process` and `--in-process-gpu`,
including single-dash and `=value` forms. These switches conflict with the isolation requirement.
This denylist is not a complete validator for all Chromium command-line options.
Only trusted operators must control this environment variable.

## Container prerequisites

Keep the image's nonroot user. The reference Compose service selects
`docker/chromium-seccomp.json`. It is the complete official Playwright profile
from commit `54c711571a37de525377e6f3d3608c3e029b1829`, copied without modification:

- [Source](https://github.com/microsoft/playwright/blob/54c711571a37de525377e6f3d3608c3e029b1829/utils/docker/seccomp_profile.json)
- SHA256: `cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849`
- Source license: Apache-2.0; see `docker/PLAYWRIGHT-LICENSE`.

The alternate allowlist permits namespace setup, including `clone`, `setns` and
`unshare`. This changes the container's kernel-call policy. Review the complete
profile before adopting or upgrading it. Do not treat it as three additions to
every version of Docker's default profile. Pin and review future replacements.
The Dockerfile alone cannot select a host-side seccomp profile. Custom launchers
must pass `--security-opt seccomp=/absolute/path/to/chromium-seccomp.json`.

The host must support unprivileged user namespaces. AppArmor or another host
policy can still deny them. This candidate does not change those policies.
Do not add `SYS_ADMIN`, privileged mode, host networking or a sandbox-disabling
flag to make a failed launch pass. Record the exact host/image failure first.
Native installs also require working kernel sandbox support.

## Reproducible isolated proof

Build from a disposable checkout. Use no real `.env`, vault, provider or data.
The runner pins the local Docker socket, resolves the image ID, refuses root,
creates a unique labelled container with network none and no host bind mounts,
and copies only the synthetic checker into it. The image's anonymous Downloads
volume is new. Cleanup checks the exact container ID and label, removes that
container and volume, and verifies that the container is gone.

```sh
docker build -t billcollector-sandbox:check .
python3 tests/run_sandbox_container.py --image billcollector-sandbox:check \
  --profile docker/chromium-seccomp.json --expect active --output tmp/sandbox-active
```

Expected: active sandbox for daemon and batch, PDF download from a loopback
fixture, daemon storage preserved across context restarts, exit 0, and
`cleanup_verified: true` in the receipt. The headed browser checks
`chrome://sandbox`. Both launchers check live renderer PID namespaces and an
additional seccomp filter relative to the Python parent. Docker's filter alone
does not count as Chromium sandbox proof. The headless shell does not implement
`chrome://sandbox`.

The checker retains stdout, stderr and a receipt in a new output directory.
The process has a bounded timeout. Reuse the same artifact's existing proof
unless inputs or environment change. Before CI, create ignored `tmp/` as needed.

On the qualified development host, the paired default-policy control is:

```sh
python3 tests/run_sandbox_container.py --image billcollector-sandbox:check \
  --expect blocked --output tmp/sandbox-default
```

Expected on that host: both launchers reject with a demonstrated namespace or
sandbox denial. Other Docker policies may permit the sandbox already. A working
default policy must not be weakened to manufacture this negative control.
The recorded fork qualification covers the positive policy; it does not assume
that every runner's default policy denies namespaces.

At baseline `42d4337`, both application launches ran without the sandbox. A
test-only `--force-sandbox` wrapper demonstrates that the pinned profile fixes
the runtime prerequisite before changing the application launch options. This
wrapper is only for baseline qualification and is not a production input.

## Limits and rollback

The local result qualifies the exact tested image and host. It does not prove
compatibility on UGreen or another host. Tests use a synthetic PDF and storage;
no real portal or account is required. Full pytest and the existing mock-portal
regression remain required for the candidate. No CI infrastructure is introduced
by this upstream contribution. Earlier fork qualification is linked in the PR.

Rollback the focused candidate commit. Before a real deployment, retain the
previous image and Compose revision. A deployment or a host policy change needs
its own authorization. Disabling the sandbox changes the security posture and
must not be presented as an equivalent supported mode.
