# BillCollector

![BillCollector EyeCatcher](/doc/BillCollector_EyeCatcher.jpg)

## Table of Contents

- [What is BillCollector?](#what-is-billcollector)
- [How does it work?](#how-does-it-work)
- [Contributing](#contributing)
- [Quick Start](#quick-start)
  - [Docker Environment](#docker-environment)
  - [Vault of Secrets](#vault-of-secrets)
  - [Enabling DNS and HTTPS with Let's Encrypt certs](#enabling-dns-and-https-with-lets-encrypt-certs)
  - [The BillCollector Installation](#the-billcollector-installation-and-docker-deployment)
  - [Manual Run UI](#manual-run-ui)
- [Configure BillCollector](#configuration)
  - [Vaultwarden and Bitwarden](#vaultwarden-and-bitwarden)
  - [Local Development & Debugging](#local-development--debugging)
  - [Web Service Config](#web-service-config)
- [Local Regression Test Environment](#local-regression-test-environment)
- [Docker Build Context Check](#docker-build-context-check)
- [Development & Deployment](#development--deployment)
- [What's Next](#whats-next)

## What is BillCollector?

> BillCollector is the automated front end for processing important documents in personal web portals that previously had to be tediously downloaded by hand.
>
> Invoices and documents that are regularly stored by service providers in the respective online account are automatically retrieved by BillCollector and stored locally in a download folder from where it may be consumed by a document management system like Paperless-ngx.

BillCollector uses:

- Vaultwarden as a safe vault of the login data for the online accounts
- Playwright (for Python) driving a headless Chromium as the browser front end of the service provider's online portal
- SQLite to record the step-by-step progress of every run (performed actions, interactive elements found, results)

Chromium is operated headless by default, so that BillCollector can do its job on a Raspberry PI or a NAS, headless integrated into the cron-scheduler on a regular basis.

Following diagram depicts the complete BillCollector Ecosystem:

![BillCollector Ecosystem](/doc/BillCollector.svg)

## How does it work?

Scheduled, for instance, bi-monthly, your server's cron daemon runs the BillCollector docker container which exposes a download folder to the server's file system. The docker container integrates Chromium (via Playwright) to interact with the service provider's online portal.

For each container run, BillCollector scripts the `List of Services`, gets the secret login data from Vaultwarden via the Bitwarden API, accesses the web service via the configured Playwright recipes, and downloads the documents.

Every step of every service run is recorded in a local SQLite database (`apps/db/bc.db`): the method chain that was executed, the interactive elements that were found on the page, and the result. This makes failed runs diagnosable and is the foundation for the planned self-healing/assisted-repair features. A failed service/user pair aborts only its own run: the remaining services continue, every started run is finalized in the DB, and the process exits with code 1 if any pair failed. A second concurrent start (overlapping cron starts, UI run plus manual run) is rejected by a `flock` guard.

With a document-processing document management system (DMS) such as Paperless ngx in place, the downloaded file is consumed, automatically analyzed, tagged, and sorted.

## Contributing

### How You Can Help

- **Star this project** on GitHub.
- **Share** it with your network.
- **Contribute** recipes for more web services - see how to [Configure BillCollector](#configuration) and get familiar with the YAML recipes. Share your recipes 🙂🙂🙂
- **Contribute code** - fork this repository, create a branch from `main`, and open a pull request against `main`. There is no CI pipeline yet: changes are validated in the [local regression test environment](#local-regression-test-environment) and in production runs before being integrated. The contribution rules (ownership, PR requirements, proof, security, AI-assisted code) are in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Discuss** your ideas for improvements, more use cases and any comments by leaving notes in the Discussion area.

> 💡 **Tip**  
> Make yourself familiar with the Playwright [Locator API](https://playwright.dev/python/docs/locators): BillCollector recipes are nothing but chains of locator calls and actions.  
> `playwright codegen <url>` lets you walk through your web portal to record a draft of the procedure - don't forget to delete the cookies of that web portal to start with a clean session when training the procedure. `helpers/BillCollectorCreateRecipe_pw.py` can translate the codegen Python output into a BillCollector YAML recipe.

## Quick Start

BillCollector requires the following services:

- Docker environment
- Vaultwarden (docker image: vaultwarden/server:latest) with Bitwarden API (<https://bitwarden.com/help/vault-management-api/>) in one docker stack
- Secure HTTPS access for account management and usage of Vaultwarden with:
  - nginxproxymanager with Let's Encrypt (docker image: jc21/nginx-proxy-manager:latest)
  - Duckdns account & config -> redirect to local IP address

### Docker Environment

It is assumed that you have a docker environment up and running. There are different options you can choose from: Docker Desktop on a Linux or Windows machine or for your Mac, docker on the command line, etc.

I have it running on my self-built Mini-ITX Intel Pentium J5040 NAS hardware equipped with the Debian Linux based NAS operating system [openmediavault](https://www.openmediavault.org/) (OMV).

### Vault of Secrets

BillCollector uses the self-hosted [Vaultwarden](https://github.com/dani-garcia/vaultwarden) password manager.

Why Vaultwarden?

1. It is a resource-light-weight alternative to Bitwarden.
2. It is compatible with the Bitwarden Vault Management API integrated in the [Bitwarden CLI](https://github.com/bitwarden/cli) which BillCollector uses for login data retrieval.
3. It stores your login data safely.
4. It is feature-rich, including the management of Time-Based One-Time (TOTP) passwords.

> 💡 **Tip**  
> On [Vaultwarden Docker](https://github.com/s-t-e-f-a-n/Vaultwarden), you'll get the Vaultwarden and the Bitwarden CLI as a `Dockerfile` and a `docker-compose.yml`. Follow the installation guide over there.

### Enabling DNS and HTTPS with Let's Encrypt certs

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

### The BillCollector Installation and Docker Deployment

Now that we have done a good job installing all the prerequisites, we are focusing on installing the BillCollector docker which is as simple as follows:

1. Download this git repository to a folder in your local docker environment assuming a Linux bash terminal, e.g., `git clone https://github.com/s-t-e-f-a-n/BillCollector.git`.

2. [Configure BillCollector](#configuration) needs to be done. After each change in configuration proceed again with step 3.

3. Create a `.env` file in the repository folder from the template `.env.example` and set `CONSUMER_DIR` to your `Paperless-ngx` instance's consumption folder and `DB_DIR` to the database folder inside it (the installation script reads both; the soft links are created automatically).

4. On your Linux console enter `./install_docker-image.sh` which builds the docker image `billcollector:latest` and sets the soft links to the inbox of your `Paperless-ngx` to let BillCollector collect bills periodically. The image runs as a non-root user (UID/GID 1000, overridable at build time with the `APP_UID`/`APP_GID` build args).

5. Let your server's cron call your BillCollector periodically (e.g., bi-monthly) by calling `</path/to/your/billcollector-git-clone-folder/BillCollector.sh bc_default.ini`.

Python dependencies are validated during the image build. The final container
does not include `pip` or `wheel`; update `apps/requirements.txt` and rebuild the
image when changing dependencies. Local virtual environments keep their installers.

### Manual Run UI

Besides cron, BillCollector ships with a minimal web UI for manual runs. From the `apps` directory run:

```bash
python3 bc_ui.py
```

This opens a NiceGUI supervisor page on port 8000 where you select an INI file and a service, start or stop the run of that single service, and watch its output line by line. The UI is a pure subprocess supervisor: it launches `BillCollector.py <ini> --service <NAME>` and streams its stdout, so the scraping code stays untouched. A run left behind by a previous UI instance is cleaned up when the UI starts.

## Configuration

### Vaultwarden and Bitwarden

First and once, for the basic configuration you need to adapt the `.env` file located in the `/apps` folder. Use the `.env.example` as a template:

- `cp .env.example .env`
- The Docker wrapper mounts `apps/.env` read-only at `/apps/.env`; credentials
  are excluded from the image and Python retains dotenv quoting/interpolation.
  For direct `docker run`, mount the same file read-only. `.env` changes take effect
  at the next run without a rebuild; INI files and recipes are still baked into
  the image and need step 3 again.
- define the .env-variables:
  - `VAULT_HOST=<hostname of your vault e.g., vault.my-domain.duckdns.org>`
  - `BW_API_URL=<http/https-URL of the bitwarden API e.g., http://<local-ip>:8087>`

### Local Development & Debugging

Use vscode when extending BillCollector - either the coded or, more likely, the collection of recipes.

There is an installation script for the local environment. It installs Python3, a Python virtual environment with all required Python modules, and Playwright's Chromium (plus the required system dependencies) into `apps/.venv`. It is tested under WSL2 and Ubuntu 24.04 LTS. Run the following command on your Linux command line:

- `bash install_local.sh playwright`

For debugging, run `BillCollector.py` in debug mode - either via F5 in vscode or `python3 BillCollector.py bc_test.ini debug`:

- Uses `bc_test.ini` as the list of web services to run.
- Chromium runs headed, so you can watch the run in a browser window.
- Every step is recorded in the SQLite DB (`apps/db/bc.db`) together with the interactive elements that were found on the page - use these records to identify and fix failing steps.

The Selenium-era per-step SPACE pause is not yet wired into the Playwright engine.

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

     *Example ini script:*

     ```ini
     [Playwright]
     winSIM=Stefan, Auto, Brigitte, Eva, Anna
     KabelDeutschland=
     Freenet Mobilfunk=
     ```

3. A YAML recipe defines the browser automation, which typically starts at login and ends at the download of the wanted document from the web service portal:
   - The recipes are placed in the subfolder `apps/recipes_playwright` and follow the naming convention `recipe-pw__<serviceName>.yaml` where `<serviceName>` is the service's `Name` from Vaultwarden in lower case with spaces replaced by underscores (e.g., `Freenet Mobilfunk` -> `recipe-pw__freenet_mobilfunk.yaml`).
   - The basic concept of the BillCollector recipes is summarized as follows:
      - YAML format
      - One recipe per web portal identified by the yaml element `serviceName` and its filename `recipe-pw__<serviceName>`.
      - Each recipe is structured in numbered `steps`, executed in ascending `step` order.
      - Each step is a chain of `methods`: Playwright Page/Locator calls executed in order. Locator methods (`locator` for CSS selectors, `get_by_role`, `get_by_label`, `get_by_text`, `get_by_title`, `get_by_placeholder`, `get_by_test_id`) yield a locator that is chained into the following action (`click`, `fill`, `press`, `first`). Page-level methods include `goto` (open the start URL), `content_frame` (enter an iframe) and `close`.
      - Downloads: a step with the `expect_download` method wraps the nested `steps` that trigger the download; the file is saved into the Downloads folder.
      - Variables: `{{USERNAME}}`, `{{PASSWORD}}` and `{{OTP}}` (all three from Vaultwarden, linked to the web service) are substituted at run time.
      - `graceful: true` on a step: a failure of that step is recorded (log + DB) and the run continues with the next step; without it, a failure aborts the service's run.
      - There is a YAML schema named `recipe-pw-schema.yaml` which includes the rules to be followed by the YAML recipes.

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

BillCollector is moving from a cron-driven batch tool towards a self-hosted daemon: a NiceGUI web UI that schedules the runs, watches them live, and lets you step in when a portal changes (pause, inspect the page, repair the recipe, resume). The batch system described above keeps running unchanged in the meantime. See [CHANGELOG.md](CHANGELOG.md) for the history of feature updates and changes.
