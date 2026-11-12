# Start the daemon

This guide targets the public daemon, not the deprecated batch wrapper.
Use a fresh checkout and separate data directories for the first check.
Validation baseline: public revision `d9362b3` (2026-10-25). Recheck the limits
after upgrading.
[Limits and pending work](#limits-and-pending-work) identify what this guide
cannot yet qualify for a permanent installation.

## Prerequisites

| Required | Check |
|---|---|
| Linux host with Docker Engine and the Compose plugin | `docker version` and `docker compose version` succeed. The Dockerfile accepts `linux/amd64`. |
| Git and permission to build and run containers | `git --version` succeeds. |
| An existing, unlocked `bw serve` API for a real account | The onboarding **Vault → Check** reports reachable and unlocked. A Vaultwarden web page alone is not this API. |
| One supported portal recipe and a matching vault item | The recipe filename, task service and vault item follow the [author guide](RECIPE_AUTHORING.md). |

DuckDNS, a reverse proxy, public DNS and a new Vaultwarden installation are
optional. They are not prerequisites for a local check. Set up a new vault
separately if you do not already have one. Never expose `bw serve` publicly.

## Prepare a fresh checkout

```bash
git clone https://github.com/s-t-e-f-a-n/BillCollector.git
cd BillCollector
git rev-parse HEAD
mkdir -p apps/Downloads apps/db apps/data apps/browser/profiles apps/recipes
cp apps/.env.example apps/.env
```

Prefer no clone and no local build? The README's
[Quick Start - Run the published image](../README.md#run-the-published-image)
pulls the prebuilt image from the GitHub Container Registry instead; the host
setup (the data directories below, `apps/.env`) is the same.

Record the revision with your installation notes. In `apps/.env`, replace the
`BW_API_URL` placeholder with the private HTTP URL of your **bw serve API**.
For an API on the Docker host, use `http://host.docker.internal:8087` if its
actual listening port is 8087. `127.0.0.1` inside the daemon container refers
to that container. Set `BW_API_HOST` only if the API requires a different HTTP
Host header; see [vault transport](vault_transport.md).

The default container UID/GID is `1000:1000`. Give that identity write access
to the five new data directories (the fifth, `apps/recipes`, is the user
recipe overlay and may stay empty). For this fresh checkout only:

```bash
sudo chown -R 1000:1000 apps/Downloads apps/db apps/data apps/browser apps/recipes
```

If you choose another UID/GID, set `APP_UID` and `APP_GID` in the root `.env`
and use those values for ownership. Keep the application `apps/.env` distinct
from the optional root `.env`: the former configures the vault; the latter
supplies Compose substitutions. Do not copy the remote-deployment placeholders
from the root `.env.example` for this local setup.

Set `TZ=Europe/Zurich`, for example, in the root `.env` for local task
schedules. The override below passes it into the container. An exported
shell `TZ` takes precedence; an unset or empty value uses `UTC`.
This explicit setting avoids the image's Europe/Berlin default on the
validation baseline. `TZ` in `apps/.env` cannot override a container
environment value. After changing the zone, recreate the daemon and check
the task schedules.

## Build, start and check

For a first check on the Docker host, use this override. It replaces the
reference container name and image tag, and replaces the port list with one
loopback UI port. It does not publish
noVNC ports. [`!override`](https://docs.docker.com/reference/compose-file/merge/#replace-value)
requires Docker Compose 2.24.4 or later.

```bash
cat > compose.local.yaml <<'YAML'
services:
  billcollector:
    container_name: !reset null
    image: billcollector-local:quickstart
    environment:
      TZ: ${TZ:-UTC}
    ports: !override
      - "127.0.0.1:8766:8000"
YAML
docker compose -p billcollector-local -f docker-compose.yml -f compose.local.yaml config --quiet
docker compose -p billcollector-local -f docker-compose.yml -f compose.local.yaml up -d --build billcollector
docker compose -p billcollector-local -f docker-compose.yml -f compose.local.yaml ps
curl --fail --silent --show-error http://127.0.0.1:8766/_alive
```

Expected: the service starts and the health endpoint returns HTTP 200.
This proves the daemon is alive. It does not prove vault access or collection.
Open `http://127.0.0.1:8766/login` on the Docker host. Set the UI password.
Finish onboarding:

1. **Vault:** save the API URL and optional Host header, then use **Check**.
   A saved non-empty value takes precedence over `apps/.env`.
2. **Tasks:** add one service and account. Keep it disabled while testing.
   Shipped INI files contain no active personal accounts.
3. **Finish:** check the summary, then finish onboarding.

The UI password protects the daemon UI. It does not configure the separate
noVNC channel. The loopback override above deliberately leaves that channel
unpublished while its deployment design is under review.

## Collect the first document

For a real account, first confirm the vault item and recipe match. A task with
service `ExampleMobile` and account `Home` looks up the item `ExampleMobile Home`.
The portal URL comes from the recipe's `goto` step, not from the item's URI.
Keep unrelated tasks disabled.

Press **Run now** for that single task. A disabled task can run manually without
changing its schedule. Inspect the task and run pages:

- A successful run ends as `success` and has at least one successful download.
- The Downloads page lists the file. The default host path is `apps/Downloads`.
- If the run pauses, use the [symptom guide](TROUBLESHOOTING.md). Do not repeat
  submissions merely because the page appears slow.

Open the expected document locally. Check its identity and content before
configuring a schedule. File creation does not prove delivery to Paperless or
another archive: the bundled consumer registry is empty. Configure and verify
that downstream integration separately.

For a credential-free check first, use the [synthetic recipe proof](RECIPE_AUTHORING.md#test-without-a-real-account).
It proves recipe execution and downloads against loopback fixtures. It does not
qualify a provider or the complete Docker onboarding path.

To stop this fresh instance without removing its bind-mounted data:

```bash
docker compose -p billcollector-local -f docker-compose.yml -f compose.local.yaml stop billcollector
```

## Limits and pending work

- Recipe storage (issue #27 F02, resolved by the user recipe overlay): the
  reference Compose file mounts `apps/recipes` as the overlay
  (`BC_RECIPE_EXTRA_DIR`). A per-service file there shadows the built-in
  recipe of the same name, and the UI recipe editor saves into it, so a
  synthetic UI edit survives container recreation with identical content.
  Built-in recipes stay maintainer-owned and update with the image; a shadow
  keeps winning across image upgrades until you update or delete it (no
  auto-merge). The mounted folder is the durable store (export = copy the
  directory); mounting a git checkout instead of a plain folder enables the
  git auto-commit history. See [Adding or updating recipes via the mounted
  directory](RECIPE_AUTHORING.md#adding-or-updating-recipes-via-the-mounted-directory).
- The separate noVNC routing/authentication design remains maintainer-owned
  (issue #27 F03). This guide qualifies local UI access only.
- Broader pre-run method validation (C3/F08) and empty-run semantics must be
  checked against the public version you install. Do not assume approval means
  integration.
- The current runner can report `failure` when there are no documents. The
  default filename path can also be reused by later downloads. Keep the first
  check isolated from an existing document archive.

Until those items are integrated and verified, this is a local first-check
procedure. A permanent deployment and a real-provider collection require their
own acceptance proof.
