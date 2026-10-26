# BillCollector

![BillCollector EyeCatcher](/doc/BillCollector_EyeCatcher.jpg)

## Table of Contents

- [What is BillCollector?](#what-is-billcollector)
- [How does it work?](#how-does-it-work)
- [Contributing](#contributing)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
    - [Docker Environment](#docker-environment)
    - [Vault of Secrets](#vault-of-secrets)
    - [Enabling DNS and HTTPS with Let's Encrypt certs](#enabling-dns-and-https-with-lets-encrypt-certs)
  - [Installing the Daemon](#installing-the-daemon)
  - [Pause notifications (ntfy)](#pause-notifications-ntfy)
- [Daemon Mode](#daemon-mode)
  - [Environment Variables](#environment-variables)
  - [Container Semantics](#container-semantics)
- [Using the Web UI](#using-the-web-ui)
- [Configure BillCollector](#configure-billcollector)
  - [Vaultwarden and Bitwarden](#vaultwarden-and-bitwarden)
  - [Web Service Config](#web-service-config)
- [Migrating from Cron to the Daemon](#migrating-from-cron-to-the-daemon)
- [Debugging](#debugging)
  - [Local Development Environment](#local-development-environment)
  - [F5 Debug Workflow](#f5-debug-workflow)
- [Legacy Batch Mode (Deprecated)](#legacy-batch-mode-deprecated)
- [Local Regression Test Environment](#local-regression-test-environment)
- [Docker Build Context Check](#docker-build-context-check)
- [Docker Layer Cache Reuse](#docker-layer-cache-reuse)
- [Development & Deployment](#development--deployment)
- [What's Next](#whats-next)

## What is BillCollector?

> BillCollector is the automated front end for processing important documents in personal web portals that previously had to be tediously downloaded by hand.
>
> Invoices and documents that are regularly stored by service providers in the respective online account are automatically retrieved by BillCollector and stored locally in a download folder from where it may be consumed by a document management system like Paperless-ngx.

BillCollector uses:

- Vaultwarden as a safe vault of the login data for the online accounts
- Playwright (for Python) driving a Chromium as the browser front end of the service provider's online portal
- SQLite to record the step-by-step progress of every run (performed actions, interactive elements found, results)

The primary mode is a self-hosted daemon with a web UI: it schedules each task on its own cron expression, runs the browser headful on an allocated virtual display (watchable live over noVNC), supervises every run, and pauses for your help when a portal changes - all without shell access to the daemon. The legacy cron-driven batch mode (a headless `docker run` per cron tick) is **deprecated**; it keeps working unchanged as the rollback path (see [Legacy Batch Mode](#legacy-batch-mode-deprecated)).

Following diagram depicts the complete BillCollector Ecosystem:

![BillCollector Ecosystem](/doc/BillCollector.svg)

## How does it work?

Your server runs the BillCollector daemon (in Docker, per the [Quick Start](#quick-start)), which exposes a download folder to the server's file system. The daemon integrates Chromium (via Playwright) to interact with the service provider's online portal; its scheduler fires each task on its own cron expression, and every run is visible live in the web UI.

For each run, BillCollector scripts the service, gets the secret login data from Vaultwarden via the Bitwarden API, accesses the web service via the configured Playwright recipes, and downloads the documents.

Every step of every service run is recorded in a local SQLite database (`apps/db/bc.db`): the method chain that was executed, the interactive elements that were found on the page, and the result. This makes failed runs diagnosable and is the foundation for the planned self-healing/assisted-repair features. A failed service/user pair aborts only its own run: the remaining services continue, every started run is finalized in the DB, and the process exits with code 1 if any pair failed. A second concurrent start of the legacy batch path (overlapping cron starts, two manual runs) is rejected by a `flock` guard; the daemon rejects a double start of a task by its run claim.

With a document-processing document management system (DMS) such as Paperless ngx in place, the downloaded file is consumed, automatically analyzed, tagged, and sorted.

## Contributing

### How You Can Help

- **Star this project** on GitHub.
- **Share** it with your network.
- **Contribute** recipes for more web services - see how to [Configure BillCollector](#configure-billcollector) and get familiar with the YAML recipes. Share your recipes 🙂🙂🙂
- **Contribute code** - fork this repository, create a branch from `main`, and open a pull request against `main`. There is no CI pipeline yet: changes are validated in the [local regression test environment](#local-regression-test-environment) and in production runs before being integrated. The contribution rules (ownership, PR requirements, proof, security, AI-assisted code) are in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Discuss** your ideas for improvements, more use cases and any comments by leaving notes in the Discussion area.

> 💡 **Tip**  
> Make yourself familiar with the Playwright [Locator API](https://playwright.dev/python/docs/locators): BillCollector recipes are nothing but chains of locator calls and actions.  
> `playwright codegen <url>` lets you walk through your web portal to record a draft of the procedure - don't forget to delete the cookies of that web portal to start with a clean session when training the procedure. `helpers/BillCollectorCreateRecipe_pw.py` can translate the codegen Python output into a BillCollector YAML recipe.

### Contributors

External contributions are welcome and credited:

- [flowcool](https://github.com/flowcool) — secret-free vault request diagnostics (PR #11), Docker build context hardening that keeps private runtime artifacts out of the image (PR #12), the vault transport: in-process DNS vetting with requests pinned to validated local targets (PR #13), and Playwright image hardening that validates Python dependencies at build time and strips the pip/wheel installers from the runtime image (PR #16).

## Quick Start

BillCollector requires the following services:

- Docker environment
- Vaultwarden (docker image: vaultwarden/server:latest) with Bitwarden API (<https://bitwarden.com/help/vault-management-api/>) in one docker stack
- Secure HTTPS access for account management and usage of Vaultwarden with:
  - nginxproxymanager with Let's Encrypt (docker image: jc21/nginx-proxy-manager:latest)
  - Duckdns account & config -> redirect to local IP address

### Prerequisites

#### Docker Environment

It is assumed that you have a docker environment up and running. There are different options you can choose from: Docker Desktop on a Linux or Windows machine or for your Mac, docker on the command line, etc.

I have it running on my self-built Mini-ITX Intel Pentium J5040 NAS hardware equipped with the Debian Linux based NAS operating system [openmediavault](https://www.openmediavault.org/) (OMV).

#### Vault of Secrets

BillCollector uses the self-hosted [Vaultwarden](https://github.com/dani-garcia/vaultwarden) password manager.

Why Vaultwarden?

1. It is a resource-light-weight alternative to Bitwarden.
2. It is compatible with the Bitwarden Vault Management API integrated in the [Bitwarden CLI](https://github.com/bitwarden/cli) which BillCollector uses for login data retrieval.
3. It stores your login data safely.
4. It is feature-rich, including the management of Time-Based One-Time (TOTP) passwords.

> 💡 **Tip**  
> On [Vaultwarden Docker](https://github.com/s-t-e-f-a-n/Vaultwarden), you'll get the Vaultwarden and the Bitwarden CLI as a `Dockerfile` and a `docker-compose.yml`. Follow the installation guide over there.

#### Enabling DNS and HTTPS with Let's Encrypt certs

> 💡 **Tip**  
> This configuration will not only support your BillCollector setup but also improves the user experience when accessing all your other locally running dockerized web services:**

Vaultwarden only allows secure HTTPS access by default. Suppose you want to run an instance of Vaultwarden that can only be accessed from your local network by name instead of IP address and you want to use Let's Encrypt certificates.

Currently, the simplest option is offered by [Duck DNS](https://www.duckdns.org) as a free Domain Name Service (DNS) in combination with the locally dockerized [Nginx Proxy Manager](https://nginxproxymanager.com).

The cool thing about DuckDNS is not only that it is free of charge but also that it allows wildcard domains and local IP address names. For the latter, however, DNS rebind protection must also be configured in your router.

The only downside of Duck DNS is that you cannot freely choose your domain name because it will follow the naming scheme [https://\<your subdomain\>.duckdns.org](duckdns.org).

Steps to follow:

1. If you don't already have an account, create one at <https://www.duckdns.org/>. Define a subdomain name either used as a wildcard domain (e.g., my-domain.duckdns.org) or just a single domain name.

   ![MyDuckDNS](/doc/Screenshot%202025-02-27%20234458.jpg)

2. Configure the DNS Rebind Protection in your router: For Fritz!Box routers go to `/Heimnetz/Netzwerk/Netzwerkeinstellungen/DNS-Rebind-Schutz` and enter the hostname you configured in Duck DNS.

3. Check the setup of your domain name was successful.
   On your Windows machine `<WIN>R cmd` and enter `nslookup <your subdomain\>.duckdns.org`. The response should look similar as follows:

   ![nslookup](/doc/Screenshot%202025-02-28%20002726.jpg)

   Alternatively, on your Linux machine use a tool like `dig` to check Duck DNS is resolving your domain name.

4. Now we are ready to install NPM from the guide at the [Nginx Proxy Manager](https://nginxproxymanager.com).

   a. After you've run your NPM container the first time, enter the web UI using the default credentials and change them to your private ones.

   b. Go to `SSL Certificates`, Press `Add SSL Certificate` and choose `Let's Encrypt`.
      - In the form fill in the field `Domain Names` either with wildcard like `*.my-domain.duckdns.org` and `my-domain.duckdns.org` or just a single domain like `my-vw.duckdns.org`.
      - In the same form fill in the field `Email address for Let's Encrypt` you want Let's Encrypt to link the certificates in their database with.
      - Enable the switch `Use DNS Challenge`, choose `DuckDNS` from the list and enter the token from step 1 into the text box by replacing `your-duckdns-token` in `dns_duckdns_token=your-duckdns-token`.
      - You may leave `Propagation Seconds` blank or fill in a number of seconds to wait for DNS propagation before it fails.
      - Enable the switch `I agree...` and press `Save`.
      - Now it may take some seconds to finalize the Let's Encrypt DNS Challenge.
      - When finished successfully, a new SSL certificate is configured with an expiry in some months which will be updated automatically by your NPM.

   c. Go to `Hosts`, choose `Proxy Hosts`, and Press `Add Proxy Host`.
      - In the form of tab `Details` fill in the domain name you want to access Vaultwarden locally, like `vault.my-domain.duckdns.org` (using your wildcard domain) or `my-vw.duckdns.org`.
      - In the same form fill `Scheme` with `http`, `Forward Hostname/IP` with the IP address of your Vaultwarden Host (i.e., the IP of your Host running the docker in your local environment), and `Forward Port` with the port Vaultwarden is listening on (typically 80 for HTTP).
      - In the form of tab `SSL` enter the SSL certificate name(s) configured in step b. and enable the switches `Force SSL` and `HTTP/2 Support`.
      - Press `Save`.

   d. Test the accessibility of your Vaultwarden Web UI in your browser by entering [https://vault.my-domain.duckdns.org](https://vault.my-domain.duckdns.org) or [https://my-vw.duckdns.org](https://my-vw.duckdns.org).

### Installing the Daemon

Now that we have done a good job installing all the prerequisites, we are focusing on installing the BillCollector daemon which is as simple as follows:

1. Download this git repository to a folder in your local docker environment assuming a Linux bash terminal, e.g., `git clone https://github.com/s-t-e-f-a-n/BillCollector.git`.

2. Create the data folders the container user (UID/GID 1000 by default, or your `APP_UID`/`APP_GID`) writes to - **before** the first `up`, because Docker would create a missing bind-mount folder root-owned, and the container could not write into it:

   ```bash
   mkdir -p apps/Downloads apps/db apps/data apps/browser/profiles
   sudo chown -R 1000:1000 apps/Downloads apps/db apps/data apps/browser
   ```

   (Use your own uid/gid if you override `APP_UID`/`APP_GID` in the root `.env`.)

3. Create the app configuration the container reads read-only at `/apps/.env` (a missing file makes Docker create a *directory* instead, which breaks the mount):

   ```bash
   cp apps/.env.example apps/.env
   ```

   and set `BW_API_URL` to the HTTP URL of your local `bw serve` API (e.g., `http://<local-ip>:8087`; it must resolve only to loopback/private addresses, HTTPS is refused). See [Vaultwarden and Bitwarden](#vaultwarden-and-bitwarden).

4. Optionally, create a root `.env` with the compose variables - all of them have defaults, the file is optional: `TZ` (daemon calendar dates and cron schedules, default `UTC`), `BC_UI_PORT` (published UI port, default `8766`), `NTFY_HOST` (push server for pause notifications, default `https://ntfy.sh`), `NTFY_BASE_URL` (LAN-absolute deep links, with the bundled ntfy), `APP_UID`/`APP_GID` (container user).

   Set `TZ=Europe/Zurich`, for example, to use local dates and schedules.
   Compose reads `TZ` from the shell first, then the root `.env`; an unset
   or empty value uses `UTC`. The image imposes no timezone. Compose passes
   its resolved value into the container, so `TZ` in `apps/.env` cannot
   override it. For direct Python execution, an exported `TZ` wins over
   `apps/.env`. With `docker run`, pass `--env TZ=Europe/Zurich` or mount
   `apps/.env` read-only at `/apps/.env`. Docker does not automatically
   forward the host shell's `TZ`. If neither runtime source sets `TZ`,
   the daemon uses `UTC`.
   Use an IANA name such as `Europe/Zurich`; an invalid zone stops startup.
   After changing the Compose setting, recreate the daemon with
   `docker compose up -d billcollector` and check the task schedules.

5. On your Linux console enter `docker compose up -d --build` which builds the docker image `billcollector:latest` from the root `Dockerfile` and starts the daemon (`python3 -m billcollector serve`). The image runs as a non-root user (UID/GID 1000, overridable at build time with the `APP_UID`/`APP_GID` build args).

   Python dependencies are validated during the image build. The final container does not include `pip` or `wheel`; update `apps/requirements.txt` and rebuild the image when changing dependencies. Local virtual environments keep their installers.

6. Open the published UI port in your browser (default `http://<your-host>:8766/`). The first start shows a set-password form (or seeds the password from `BC_UI_PASSWORD` in `apps/.env`); afterwards you sign in with that password.

7. Walk the **onboarding wizard**: check and save your vault API URL (or skip it and fix it later in Settings), review the tasks imported from your INI file (or add a new task), enable the tasks the daemon should run on schedule, and finish.

8. Collect your first document: on the **Dashboard** press **Run now** for an enabled task - watch the run live (session page, noVNC tab) until it reaches `success`; the document appears on the Downloads page and in the consumer folder. Every step is driven from the browser, no shell access to the daemon needed.

### Pause notifications (ntfy)

A fresh installation sends no notifications: the `ntfy topic` setting starts empty, and a paused run (or a blocked login) only pushes when you set a topic. To opt in, open **Settings** and set an **ntfy topic** - choose your own topic name, it is the install-specific destination the pushes are sent to.

The push server defaults to the public [ntfy.sh](https://ntfy.sh). To run your own push server in the same stack instead:

1. Add `NTFY_HOST=http://ntfy` to the root `.env` (optional: `NTFY_BASE_URL=http://<your-host>:2086` for LAN-absolute deep links).
2. Start the stack with `docker compose --profile ntfy up -d` - the `ntfy` service (image `binwiederhier/ntfy`, port `2086`) comes up together with BillCollector.

## Daemon Mode

The daemon is BillCollector's primary mode: `python3 -m billcollector serve` (the `command` of the compose service). It binds to `127.0.0.1:8000` by default (`--host`/`--port`, or `BC_UI_HOST`, override both) - inside the container `BC_UI_HOST=0.0.0.0` makes the UI reachable from the LAN.

On the first start (while the task list is still empty), the `[Playwright]` sections of `bc_default.ini` and `bc_test.ini` are imported as tasks - each (service, user) pair becomes one task, initially **disabled**, with a default monthly cron (`0 0 1 * *`). You enable a task and set its cron schedule per task from the UI; the Task table in the database is the source of truth, and the daemon rebuilds its scheduler jobs from it on every start (a missed run coalesces into a single catch-up run).

### Environment Variables

`apps/.env` (mounted read-only at `/apps/.env`) is the app configuration; the compose service additionally sets `BC_UI_HOST` and `NTFY_HOST` itself (these win over the file):

- `BW_API_URL=<http-URL of your local bw serve API, e.g., http://<local-ip>:8087>`; it must resolve only to loopback/private addresses, HTTPS is refused
- `BW_API_HOST=127.0.0.1:8087` (optional): Host header for a `bw serve` in another container
- `BC_UI_HOST`: daemon UI bind host (default `127.0.0.1`; set `0.0.0.0` inside the container)
- `BC_UI_PASSWORD` (optional): seeds the UI password hash on the first start (a hash set via the UI is never overwritten)
- `NTFY_HOST`: push server for the pause notifications (default `https://ntfy.sh`)
- `BC_CHROMIUM_ARGS=--disable-software-rasterizer`: dev-host launch workaround only; leave unset for stock behavior
- `VAULT_HOST` is no longer used, see [doc/vault_transport.md](doc/vault_transport.md)

The vault API can also be configured from the UI (the onboarding wizard's vault step or the Settings page, fields `vault_api_url` / `vault_api_host`): a non-empty Settings value wins over the environment, so a wrong URL can be fixed from the browser even though `apps/.env` is mounted read-only. An empty value falls back to the environment (legacy env-only deployments are unchanged).

### Container Semantics

From the compose file (`docker-compose.yml`):

- **UI port** `${BC_UI_PORT:-8766}:8000` - the daemon UI.
- **noVNC live view** websockify ports `6080-6095` - one port per allocated Xvfb display (websockify port = `6080 + (display - display_start)`); the range matches the default Settings `display_start=99` / `display_count=16` - change them together if you change the display range.
- **Volumes**: `./apps/.env` (read-only), `./apps/Downloads`, `./apps/db`, `./apps/data`, `./apps/browser/profiles` (profiles only - mounting all of `apps/browser` would hide the Chromium build installed in the image).
- **`host.docker.internal:host-gateway`** - reach host-local services (Vaultwarden, `bw serve`, the mock portal) from the container as `http://host.docker.internal:<port>`. Vaultwarden itself stays a prerequisite in its own compose stack.
- `restart: unless-stopped`, `init: true`, a health check on `/_alive`, and the non-root user from the `APP_UID`/`APP_GID` build args.

## Using the Web UI

All pages require sign-in (a session cookie set on `/login`).

- **Login** (`/login`) - the one-time set-password form on a fresh start, then the password login.
- **Onboarding** (`/onboarding`) - the first-start wizard, active until you finish it (while active, every other authenticated page redirects to it). Upgraded installs (a password is set and at least one task is enabled) are auto-completed on daemon start, so you normally see it once, on a fresh install:
  1. **Vault** - the vault API URL (+ optional host override) with a **Check** button (the same DNS vetting + status check the run preflight makes: reachable and unlocked / reachable but locked / network error) and **Save** (the Settings keys `vault_api_url` / `vault_api_host`; empty is allowed = environment fallback). Skipping is allowed but flagged: while no URL resolves, runs fail at the vault preflight.
  2. **Tasks** - the imported task list (id, service, user, cron, whether the recipe file exists) with per-task enable toggles, an **Import from INI** button (re-runs the import: only (service, user) pairs missing from the table are added - including ones you deleted; existing tasks are left untouched), and a **New task** form (service, user, cron, enabled; the recipe path and the per-task browser profile dir are derived as in the INI import).
  3. **Finish** - a summary (task counts, missing recipe files, vault state) and **Finish onboarding**.
- **Dashboard** (`/`) - all tasks with their status (color-coded, `waiting` rows highlighted), last/next run, latest download, a Login column (available / pending / blocked for tasks with a phased login), and a `[N waiting]` badge for paused runs; a live log pane following the active run and a step-screenshot strip; per row **Run now** (works for disabled tasks as a manual one-off, schedule untouched; disabled while the login is blocked), **Stop**, and **Edit** (cron + enabled); toolbar **Run (filtered)** (enqueues all enabled tasks in the filtered set, skipping blocked ones) and **Add task**.
- **Task detail** (`/tasks/<id>`) - the run history of one task with the per-step records, step screenshots, and downloads; for a phased login the budget state (unproven attempts / limit) and, while idle and locked, a **Clear login block** button (grants exactly one further attempt, profile and schedule preserved).
- **Session** (`/runs/<id>`) - the live view of one run (the ntfy deep-link target): while it runs, you watch the progress; while it is paused, you get the "Copilot" view - a screenshot, the numbered interactive elements, click/fill/press/drag actions, and Resume / Cancel - plus a noVNC tab that shows the actual browser window. A step that failed and paused also offers a Repair link into the recipe editor.
- **Recipe editor** (`/recipes/<service>`) - edit the YAML recipe with schema validation, and optionally auto-commit the change to git (Settings switch).
- **Downloads** (`/downloads`) - the downloaded files of all runs; a file whose sha256 was already seen for the same task is marked as a duplicate (the consumer hook is not re-run for it).
- **Settings** (`/settings`) - UI password, ntfy topic, pause deadline, max concurrency, display start, download directory, UI base URL, VNC password, the vault API URL/host, and the git auto-commit switch. Each field writes its own Settings row on save, so an invalid value only fails that field.

**Pausing a stuck run.** A non-graceful step that still fails after three attempts, a failed download, or an explicit `wait_user` recipe step does not abort the run: it pauses (the task shows `waiting`), stores a machine-readable pause context on the run, pushes an ntfy notification with a deep link to the session page, and waits - until you resume or cancel it from the UI, or the pause deadline passes (default 30 minutes, configurable in Settings). A `wait_user` step pauses before execution and is consumed on resume (not re-executed - a consumed CAPTCHA code cannot be re-entered); it can carry an optional `prompt` and an optional `until` locator, the pause then completing as soon as that element appears on the page.

**Blocking repeated login failures.** A task whose recipe uses the phased `login` step (contract in [doc/SAFE_LOGIN.md](doc/SAFE_LOGIN.md)) consumes one attempt of a persistent budget per unproven login transaction (default limit 2, configurable per task and per recipe); reaching the limit locks the task for login runs until you clear the block from the task detail page - one attempt, schedule and profile preserved - or a later run proves the session. Locking sends one ntfy notification (deep link when the UI base URL is set), and a concurrent second start of the same task is refused by a per-task file lock held for the duration of the run.

For a cron-style single-shot run without the daemon, `python3 -m billcollector run <task_id>` executes one task run.

## Configure BillCollector

### Vaultwarden and Bitwarden

First and once, for the basic configuration you need to adapt the `.env` file located in the `/apps` folder. Use the `.env.example` as a template (the Quick Start does this in step 3):

- `cp apps/.env.example apps/.env`
- The Docker wrapper mounts `apps/.env` read-only at `/apps/.env`; credentials are excluded from the image and Python retains dotenv quoting/interpolation. For direct `docker run`, mount the same file read-only. `.env` changes take effect at the next run without a rebuild; INI files and recipes are still baked into the image and need a rebuild (legacy step 4 of [Legacy Batch Mode](#legacy-batch-mode-deprecated)).
- define the .env-variables:
  - `BW_API_URL=<http-URL of your local bw serve API e.g., http://<local-ip>:8087>`; it must resolve only to loopback/private addresses, HTTPS is refused
  - `BW_API_HOST=127.0.0.1:8087` (optional): Host header for a `bw serve` in another container
  - `VAULT_HOST` is no longer used, see [doc/vault_transport.md](doc/vault_transport.md)

The vault API can equally be configured from the UI (wizard or Settings; [Daemon Mode → Environment Variables](#environment-variables)).

### Web Service Config

The BillCollector configuration for each web service from which you want to retrieve documents consists of three parts:

1. A Vaultwarden entry provides the login data for each of your private web service login:
   - `Name`: name of the web service
   - `User Name`: your secret login name to the web service
   - `Password`: your secret password to the web service
   - (optional and dependent on the web service) `TOTP`: key from your web service
   - `URI 1`: the web service's web address where BillCollector should start from

2. A list of service entries in `/apps/bc_default.ini` represents the script for collecting all bills:
   - Under the `[Playwright]` section, enter line by line the name of the web service matching the `Name` of the service's entry in Vaultwarden (1).
   - For web services where you have more than one login data for (e.g., family members having different accounts at the same mobile phone provider) you can enter the line in the following format: `<Name of web service>=<your name>, <additional name>`.

      *Example ini script (synthetic names - replace with your own services
      and accounts):*

      ```ini
      [Playwright]
      ExampleMobile=John, Jane
      ExampleUtility=
      ```

   In daemon mode this INI list is the starting point for the task list: it is imported into the Task table on the first daemon start (or via **Import from INI** in the wizard), and from then on the per-task cron and enabled state live in the UI, not in the INI.

3. A YAML recipe defines the browser automation, which typically starts at login and ends at the download of the wanted document from the web service portal:
   - The recipes are placed in the subfolder `apps/recipes_playwright` and follow the naming convention `recipe-pw__<serviceName>.yaml` where `<serviceName>` is the service's `Name` from Vaultwarden in lower case with spaces replaced by underscores (e.g., `Freenet Mobilfunk` -> `recipe-pw__freenet_mobilfunk.yaml`).
   - The basic concept of the BillCollector recipes is summarized as follows:
     - YAML format
     - One recipe per web portal identified by the yaml element `serviceName` and its filename `recipe-pw__<serviceName>`.
     - Each recipe is structured in numbered `steps`, executed in ascending `step` order.
     - Each step is a chain of `methods`: Playwright Page/Locator calls executed in order. Locator methods (`locator` for CSS selectors, `get_by_role`, `get_by_label`, `get_by_text`, `get_by_title`, `get_by_placeholder`, `get_by_test_id`) yield a locator that is chained into the following action (`click`, `fill`, `press`, `first`). Page-level methods include `goto` (open the start URL), `content_frame` (enter an iframe) and `close`.
     - Downloads: a step with the `expect_download` method wraps the nested `steps` that trigger the download; the file is saved into the Downloads folder. A re-downloaded file that is byte-identical to one already tracked for the same task (same sha256) is recorded as a duplicate and the consumer hook is not re-run for it.
     - Bounded pagination: use one page locator followed by `click_until_absent`. Its single options object requires `progress_selector`, `max_clicks`, and `timeout_ms`. `timeout_ms` is the total browser-action budget. Every click must increase the visible progress count or make the pager absent or hidden. This action supports cumulative "load more" controls. It rejects page-replacement pagination and virtualized lists because their visible item count does not increase.
     - Bounded collections: use one page locator followed by `download_all`. Its single options object requires `key_attribute`, `max_items`, `timeout_ms`, and `event_window_ms`. `timeout_ms` bounds the browser actions and observations for the whole collection. Persistence (`save_as`, hashing, consumers, and SQLite) remains synchronous and cannot be preempted by that browser deadline. `event_window_ms` is the full attribution window observed after each click, so `timeout_ms` must exceed the actual item count multiplied by `event_window_ms`, with additional time for browser actions. The engine reports the required and remaining budgets before its first click when the minimum attribution-window budget cannot fit. The key must be non-empty and unique for every item. The ordered key set must remain stable while each control produces exactly one download. `download_all` also rejects a suggested filename already saved earlier in the run instead of overwriting it.
     - Collection actions are terminal steps. They cannot be nested below `expect_download` or use `graceful: true`. Their explicit bounds prevent silent truncation and automatic retry after partial side effects. An operator-requested resume of `download_all` skips the stable item keys already persisted by that step and processes only the remaining items.
     - Variables: `{{USERNAME}}`, `{{PASSWORD}}` and `{{OTP}}` (all three from Vaultwarden, linked to the web service) are substituted at run time.
     - **Daemon date variables** (issue #26): `{{TODAY}}`, `{{DATE_TO}}`,
       `{{DATE_FROM}}`, and `{{TODAY-Nd}}` / `{{TODAY+Nd}}` expand inside
       any method argument string, including nested lists and dictionaries.
       Dictionary keys stay unchanged. Credential placeholders also work inline;
       replacement values are never parsed a second time.
       Each task has a **Date window (inclusive days)**, default 90:
       `DATE_TO = TODAY`, `DATE_FROM = TODAY - (window - 1)` calendar days.
       `TZ` selects the daemon date and scheduling timezone; absent `TZ` means
       UTC, and an invalid zone is rejected. One instant is captured before
       browser launch and remains fixed through retries and interactive resume.
       Output defaults to `YYYY-MM-DD`; a suffix such as
       `{{DATE_FROM|%d/%m/%Y}}` allows only `%Y`, `%m`, `%d`, `%%` and literal
       separators `-`, `/`, `.`, `_`, or ASCII space. A format must contain a
       date directive. Dates must stay within `0001-01-01` to `9999-12-31`.
       Unknown variables, malformed delimiters, invalid formats and date overflow
       fail before browser or vault access. Errors identify the argument location
       without its value. The daemon recipe editor shares the syntax validator.
       On the task detail page, **Start date for this run** accepts a strict
       `YYYY-MM-DD` no later than `DATE_TO`. It replaces only `DATE_FROM`,
       stays in memory through resume and is never saved or replayed on restart.
       The next run uses the normal window. The legacy batch checker and its
       exact-key credential substitution remain unchanged.
     - `graceful: true` on a step: a failure of that step is recorded (log + DB) and the run continues with the next step; without it, a failure aborts the service's run (after three attempts, in daemon mode the run pauses for your help instead - see [Using the Web UI](#using-the-web-ui)).
     - A `wait_user` step: an explicit pause point for operator input (e.g., a CAPTCHA you have to solve by hand). It can carry an optional `prompt` and an optional `until` locator (the pause completes when that element appears, or on resume); the step is consumed, not re-executed.
     - There is a YAML schema named `recipe-pw-schema.yaml` which includes the rules to be followed by the YAML recipes.
   - In daemon mode the recipe can also be edited in the UI [recipe editor](#using-the-web-ui) (schema validation, optional git auto-commit) - handy when a portal changes and a paused run links you straight to the failing recipe.

> 💡 **Tip**  
> When creating new recipes, make use of AI, e.g., let yourself be helped by Copilot - that speeds up creating the YAML recipe 🚀.
> `helpers/BillCollectorCheckRecipe.py` validates a recipe (YAML syntax + schema) and is also used by `BillCollector.py` at run time:
> `Usage: python3 helpers/BillCollectorCheckRecipe.py <recipe.yaml> [<schema.yaml>]`.

*Example of a YAML recipe (excerpt, real `winsim` recipe):*

```yaml
services:
- serviceName: winsim
  steps:
  - step: 1
    methods:
    - method: goto
      arguments:
      - url: "https://service.winsim.de/"
  - step: 3
    methods:
    - method: locator
      arguments:
      - selector: "#UserLoginType_alias"
    - method: fill
      arguments:
      - value: "{{USERNAME}}"
  - step: 5
    methods:
    - method: get_by_label
      arguments:
      - text: "Servicewelt-Passwort:"
    - method: fill
      arguments:
      - value: "{{PASSWORD}}"
  - step: 6
    methods:
    - method: get_by_title
      arguments:
      - text: "Login"
      - exact: true
    - method: click
  # ... further steps: confirm the dialog, open "Meine Rechnung", select the invoice ...
  - step: 11
    methods:
    - method: expect_download
    steps:
    - step: 12
      methods:
      - method: get_by_role
        arguments:
        - role: "link"
        - name: "Rechnung"
        - exact: true
      - method: click
  - step: 13
    methods:
    - method: close
```

## Migrating from Cron to the Daemon

You are running BillCollector with cron (`BillCollector.sh` in the crontab) and want to move to the daemon:

1. **Import the tasks.** Your INI file is already known to the daemon: on its first start the `[Playwright]` sections of `bc_default.ini`/`bc_test.ini` are imported as tasks (each (service, user) pair, initially disabled with a default monthly cron). If the daemon already started, press **Import from INI** in the onboarding wizard, or add a task from the dashboard **Add task** dialog.
2. **Set the schedules.** Open each task's **Edit** dialog on the Dashboard, set its cron (a 5-field crontab expression, e.g., `0 6 1,15 * *` for the 1st and 15th at 06:00), and enable it.
3. **Verify one run.** Press **Run now** for the task, watch the session page until the run reaches `success`, and check the document on the Downloads page and in the consumer folder.
4. **Stop the cron entry.** Comment out or delete the crontab line that calls `BillCollector.sh`. **Rollback = re-enable the cron entry**: the legacy path keeps working unchanged.

During the overlap period both paths can coexist safely against themselves: the legacy wrapper holds the shared `apps/.bc.lock` run lock (an overlapping cron start is rejected), and the daemon serializes its own runs per task. Just don't let both run the same (service, user) pair at the same time - they share the download folder and the same database.

## Debugging

### Local Development Environment

Use vscode when extending BillCollector - either the coded or, more likely, the collection of recipes.

There is an installation script for the local environment. It installs Python3, a Python virtual environment with all required Python modules, and Playwright's Chromium (plus the required system dependencies) into `apps/.venv`. It is tested under WSL2 and Ubuntu 24.04 LTS. Run the following command on your Linux command line:

- `bash install_local.sh playwright`

### F5 Debug Workflow

Debug one task run (a new or a broken recipe) against the daemon's task table:

```bash
cd apps && source .venv/bin/activate
python3 -m billcollector run <task_id> --debug
```

(or `PYTHONPATH=apps python3 -m billcollector run <task_id> --debug` from the repository root.)

What happens:

- The run uses the same engine as the daemon: the task's recipe, the vault credentials, the per-task browser profile, and the per-step DB recording.
- The browser runs headful on an allocated virtual display (Xvfb, from the configured range - default `:99`), so no physical display is needed. The display stack must be installed on the dev host: `install_local.sh` already installs `xvfb`; additionally `sudo apt install x11vnc websockify novnc`.
- The run's browser is viewable in your browser over noVNC: open `http://localhost:<websockify port>/vnc.html` (websockify serves the noVNC web client from the `novnc` apt package). The port is printed in the log line `Display stack started for :N (x11vnc port ..., websockify port ...)`; websockify port = `6080 + (display - display_start)`.
- `--debug` pauses before every step: `Step N: <description> [press Enter to continue]` on stdin - step through the portal and watch what the engine sees. A closed stdin (EOF) logs once and continues without pausing.
- Every step is recorded in the SQLite DB (`apps/db/bc.db`) together with the interactive elements that were found on the page - use these records to identify and fix failing steps.

VS Code launch configuration (`.vscode/launch.json` in your local clone - not committed to the repository):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "BillCollector: run task 1 (debug)",
      "type": "debugpy",
      "request": "launch",
      "module": "billcollector",
      "args": ["run", "1", "--debug"],
      "cwd": "${workspaceFolder}/apps",
      "console": "integratedTerminal"
    }
  ]
}
```

The `integratedTerminal` console is what makes the per-step Enter pause work under F5 (the debugger shares that terminal's stdin). Adjust the task id, and add `"justMyCode": false` when you want to step into Playwright.

## Legacy Batch Mode (Deprecated)

> **Deprecated** — the cron-driven batch mode (this section) is superseded by the [daemon](#daemon-mode): per-task scheduling, live supervision, and pause-and-step-in. `BillCollector.sh` keeps working unchanged as the rollback path for the daemon; new setups should use the [Quick Start](#quick-start), and existing cron setups should follow [Migrating from Cron to the Daemon](#migrating-from-cron-to-the-daemon).

### The BillCollector Installation and Docker Deployment

1. Download this git repository to a folder in your local docker environment assuming a Linux bash terminal, e.g., `git clone https://github.com/s-t-e-f-a-n/BillCollector.git`.

2. [Configure BillCollector](#configure-billcollector) needs to be done. After each change in configuration proceed again with step 4.

3. Create a `.env` file in the repository folder from the template `.env.example` and set `CONSUMER_DIR` to your `Paperless-ngx` instance's consumption folder and `DB_DIR` to the database folder inside it (the installation script reads both; the soft links are created automatically).

4. On your Linux console enter `./install_docker-image.sh` which builds the docker image `billcollector:latest` and sets the soft links to the inbox of your `Paperless-ngx` to let BillCollector collect bills periodically. The image runs as a non-root user (UID/GID 1000, overridable at build time with the `APP_UID`/`APP_GID` build args).

5. Let your server's cron call your BillCollector periodically (e.g., bi-monthly) by calling `</path/to/your/billcollector-git-clone-folder/BillCollector.sh bc_default.ini>`.

The wrapper's call format is `<ini> [debug]`: the ini is the list of web services to run, and `debug` (or `True`/`1`) runs Chromium headed with per-step logging instead of headless. `BillCollector.sh` holds an exclusive `flock` on `apps/.bc.lock` for the whole run, so an overlapping cron start is rejected, and it runs the same `billcollector:latest` image the daemon uses (`docker run … python3 ./BillCollector.py <ini> [debug]`, with `apps/.env` mounted read-only).

## Local Regression Test Environment

A self-contained regression environment tests the scraping engine against a local mock portal instead of the real web services:

- `tests/mock_portal/` - a small web portal (ASGI/uvicorn, `127.0.0.1:8787`) with sites covering the main scenarios: happy path with OTP and downloads, bad login, graceful step failure, download failure, empty document list, and CAPTCHA-style friction.
- `tests/scenarios.py` - the expected outcome of every (service, user) pair.
- `tests/run_regression.py` - the harness: starts the mock portal, executes every pair of a scope INI through the production scraping engine, and checks the engine return value, the DB rows, the downloaded files, and the exit semantics.

From the repository root:

```bash
apps/.venv/bin/python tests/run_regression.py --ini tests/bc_regression.ini
```

Useful options: `--ini tests/bc_regression_happy.ini` (success-only scope), `--keep-downloads` (don't delete the test downloads afterwards), `--port <n>`, and `--vault` (preflight a real Vaultwarden - env, DNS, unlock, sync - and fetch credentials, URL and TOTP from the corresponding vault items instead of `scenarios.py`; requires a vault provisioned with those test items, i.e. the maintainer's dev setup - the default mode above is fully self-contained and needs no vault).

Exit codes: `0` all expectations matched · `1` at least one expectation deviated · `2` the mock portal could not be started · `3` a real BillCollector run holds the run lock · `4` the `--vault` preflight failed.

## Docker Build Context Check

The `.dockerignore` keeps local credentials, logs, browser sessions and other runtime artifacts out of the Docker build context. To prove that it really works, `tests/check_docker_context.py` builds a worst-case image (`FROM scratch`, `COPY . /`) from a scratch context filled with synthetic canary files — no real checkout data, no registry access — and checks that every excluded artifact stays out of the image while every source file stays in:

From the repository root, on a machine with Docker and BuildKit:

```bash
python3 tests/check_docker_context.py
```

Expected output: `Docker context: 19 private canaries excluded, 5 source files retained`. Useful options: `--dockerignore <path>` to check a different `.dockerignore` (e.g., a previous version as a negative control). Run this check whenever you change the `.dockerignore`, the `Dockerfile` or add new runtime artifacts.

## Docker Layer Cache Reuse

The `Dockerfile` orders the expensive, rarely-changing steps (python3/pip `apt` install, `pip3 install -r requirements.txt`, `playwright install --with-deps chromium ffmpeg`, the fonts `apt` install) **before** the application code is copied, and the build is deliberately given no build arg whose value changes on every deploy — a Dockerfile `ARG` value is part of the BuildKit cache key of every `RUN` step, so a per-commit value (like a git revision) would force a full rebuild on every deploy. The result:

- Rebuilding the same tree (re-running `install_docker-image.sh` or `deploy_remote.sh` without a new commit) is an all-`CACHED` build.
- A code-only change under `apps/` re-runs only the final `COPY` and `chown` steps.
- A `requirements.txt` change re-runs `pip3 install` and the steps after it, but not the python3 `apt` step or the base image.

The deployed commit is recorded in the deploy log (`deploy_remote.sh` prints `git log -1`) rather than as an image label.

## Development & Deployment

BillCollector uses a trunk-based model with release tags:

- **`main`** — the verified production state. It only moves forward once a milestone has been validated in a production run, so `main` is always safe to deploy from.
- **Release tags** (e.g. `v0.3`) — snapshots of validated releases, for pinning a deployment or rolling it back: point the deployment's `GIT_BRANCH` variable (see `.env.example`) at the tag and re-run `deploy_remote.sh`, or simply `git checkout v0.3` in your clone and rebuild the image.

Day-to-day development happens on an upstream repository that is not mirrored here. Once a milestone has been validated, it is promoted to `main` and this repository is updated accordingly - so `main` reflects the published production state, not in-flight work.

To contribute code, see [Contributing](#contributing).

## What's Next

The self-hosted daemon with its web UI is now the primary mode: per-task scheduling, live supervision, pause-and-step-in, a first-start onboarding wizard, and a Docker Compose package to stand it up. The cron-driven batch system is deprecated but keeps running unchanged alongside it as the rollback path. The recorded step data and the machine-readable pause context are the foundation for the planned self-healing / assisted-repair features: when a portal changes, BillCollector pauses, shows what it found, and - with your help or on its own - adapts the recipe. See [CHANGELOG.md](CHANGELOG.md) for the history of feature updates and changes.
