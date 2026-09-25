# Ubuntu 20.04 → 24.04 WSL Migration (BillCollector Dev Environment)

Companion to `.kilo/plans/1790364274061-billcollector-nicegui-daemon-plan.md`
(M0 step 0). This plan covers **host + VS Code + Python environment only**; the M0
code steps (1–6) and the rest of the daemon plan are unchanged and follow afterwards.

## Verified facts (2026-09-25, old dev host)

- Windows 11 25H2 (no elevation needed for `wsl --install`), WSL2, no `.wslconfig`.
- Distros: `ubuntu` (20.04.6, the default distro), `podman-machine-default`
  (untouched by this plan).
- WSL online catalog on this machine: valid name is **`Ubuntu`**
  (`wsl --list --online`); `Ubuntu-24.04` is rejected. The MS Store "Ubuntu" app
  is Ubuntu 24.04 LTS — verify after install (step A gate).
- Cross-distro mounts `/mnt/wsl/<distro>` do **not** exist on this machine
  (checked from both distros) → data moves via a tarball staged on `/mnt/c`.
- Repo size 1.3 GB. Excludable for the move: `apps/.venv` (165 MB, Python 3.8 —
  rebuilt), `apps/chrome-linux64*` + `apps/chromedriver-linux64*` (~533 MB,
  Selenium-era, removed by daemon-plan M0 step 1), `apps/recipes_selenium`,
  `__pycache__`. Kept: `.git`, `apps/db` (9.8 MB), `apps/Downloads` (784 KB),
  `apps/browser` (557 MB, incl. `profile`/`profile.ref` with symlinks),
  `apps/recipes_playwright`, both `.env` files.
- Symlinks live only in `apps/browser/profile.ref/Singleton*` and `apps/.venv`
  → use `tar` (preserves them), not `cp -a` over 9p.
- Recipe `$schema` lines embed the absolute path
  `/home/stefan/projects/BillCollector` → same username + path in the new distro.
- PyPI pins verified to exist and accept Python 3.12: `playwright==1.63.0`
  (>=3.10), `nicegui==3.17.1` (>=3.10,<4), `apscheduler==3.11.3` (>=3.8),
  `bcrypt==5.0.0` (>=3.8).
- `helpers/BillCollectorCheckRecipe.py` must be run as a module —
  `.venv/bin/python -m helpers.BillCollectorCheckRecipe <recipe>` (plain script
  form fails with `ModuleNotFoundError: No module named 'helpers'`).
- Git: `credential.helper = store`, identity in `~/.gitconfig`, Gitea HTTP
  credentials in `~/.git-credentials` (NAS: `solg.fritz.box:3030`).
- VS Code: the **Windows client** is the source of truth — user settings at
  `C:\Users\stefan\AppData\Roaming\Code\User\settings.json` (theme, gitea,
  kilo-code, roo-cline, cmake, …), 41 extensions incl. `remote-wsl`,
  `ms-python.python`, `ms-python.debugpy`. No per-distro user settings exist on
  the old distro (no `~/.config/Code/User`); its remote server holds only
  `kilocode.kilo-code` — VS Code did not mirror the client extension list there.
  Stale Windows-side setting: `python.analysis.extraPaths` points at the dead
  python3.8/selenium venv path.
- Python: old distro uses pyenv (3.8 default shim, 3.10.17/3.11.5 installed);
  24.04 ships system Python 3.12 → pyenv is not needed and is not migrated.
- No local crontab — production cron runs on the remote NAS (out of scope).

## Decisions

1. **New distro alongside the old one.** `ubuntu` (20.04) stays untouched and
   remains the default until verification passes; optional unregister only later.
2. **Same username `stefan`, same path** `/home/stefan/projects/BillCollector`
   (recipe `$schema` dependency).
3. **Rename the new distro to `Ubuntu-24.04`** right after install — avoids two
   look-alike "Ubuntu" entries in the `wsl -l` / VS Code remote picker and
   matches the naming used in the daemon plan.
4. **Copy = one tarball staged on `/mnt/c`**, with exclusions (≈700 MB), plus
   `~/.gitconfig` + `~/.git-credentials`.
5. **VS Code: nothing migrates to the distro as "settings"** — they live on the
   Windows client and stay. The new distro gets the VS Code server + needed
   remote extensions on first connection (Kilo Code, plus explicit
   `ms-python.python` / `ms-python.debugpy` for F5). One-time: select
   `apps/.venv` as interpreter. Remove the stale `python.analysis.extraPaths`
   entry on the Windows side.
6. **Python: system `python3` (3.12.3) + `python3-venv`**, no pyenv. venv per
   daemon-plan M0 0.3/0.4: direct pins → install → full `pip freeze`.
7. **Playwright system libs via `playwright install --with-deps`** (fresh 24.04
   distro has none; equivalent to the `Dockerfile_pw` apt list).

## Steps

### A. Install the new distro (Windows PowerShell)

```powershell
wsl --install -d Ubuntu --no-launch
wsl -d Ubuntu                    # first boot: create user — name MUST be "stefan"
wsl -d Ubuntu cat /etc/os-release   # GATE: must say VERSION="24.04" (Noble)
wsl --rename Ubuntu Ubuntu-24.04
wsl -l -v                        # expect: ubuntu (Running, 2), Ubuntu-24.04 (2)
```

If the gate fails (distro is 22.04): install the Store app "Ubuntu 24.04"
instead and repeat from the first boot.

### B. Base setup (new distro, as `stefan`)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git
python3 --version                # expect 3.12.x
which python3                    # expect /usr/bin/python3 (no pyenv shim)
mkdir -p ~/projects
```

### C. Copy repo + git identity (tar staging via /mnt/c)

```bash
# --- in the OLD distro (ubuntu / 20.04): ---
mkdir -p /mnt/c/tmp/bc-migration
cp ~/.gitconfig ~/.git-credentials /mnt/c/tmp/bc-migration/
tar -C ~/projects \
    --exclude='BillCollector/apps/.venv' \
    --exclude='BillCollector/apps/chrome-linux64' \
    --exclude='BillCollector/apps/chrome-linux64.zip' \
    --exclude='BillCollector/apps/chromedriver-linux64' \
    --exclude='BillCollector/apps/chromedriver-linux64.zip' \
    --exclude='BillCollector/apps/recipes_selenium' \
    --exclude='BillCollector/apps/__pycache__' \
    --exclude='BillCollector/apps/helpers/__pycache__' \
    -cf /mnt/c/tmp/bc-migration/BillCollector.tar BillCollector

# --- in the NEW distro (Ubuntu-24.04): ---
tar -C ~/projects -xf /mnt/c/tmp/bc-migration/BillCollector.tar
cp /mnt/c/tmp/bc-migration/.gitconfig /mnt/c/tmp/bc-migration/.git-credentials ~/
chmod 600 ~/.git-credentials
rm -rf /mnt/c/tmp/bc-migration        # staging gone when done
```

Notes:
- The copy carries the uncommitted working-tree changes
  (`doc/TODO.txt`, `doc/BillCollector.drawio`, `install_docker-image.sh`,
  `.kilo/`, `.vscode/settings.json`) — expected.
- Excluded Selenium artifacts and `recipes_selenium` are intentionally not
  migrated (daemon-plan M0 step 1 removes them; they stay on the old distro).
- Git identity + Gitea credentials copied in B/C; otherwise the Gitea HTTP
  remote would prompt for auth.

### D. VS Code (Windows client unchanged; provision the new remote)

1. Windows side: no changes — settings, keybindings (none), snippets (empty),
   and the 41 extensions all stay on Windows.
2. VS Code → Remote-WSL → **"WSL: Ubuntu-24.04"** → open
   `/home/stefan/projects/BillCollector`. First connect auto-downloads the
   server and installs `kilocode.kilo-code` (agent).
3. In the new remote's integrated terminal, make the workspace F5-capable
   (the old remote had only Kilo Code, so do not assume mirroring):

   ```bash
   code --list-extensions
   code --install-extension ms-python.python
   code --install-extension ms-python.debugpy
   code --install-extension ms-python.vscode-pylance
   ```

4. Workspace state: `.vscode/settings.json` + `.vscode/launch.json` arrived
   with the repo copy. After step E, run
   **Python: Select Interpreter → `/home/stefan/projects/BillCollector/apps/.venv/bin/python`**.
5. Windows-side cleanup (Settings UI): delete the `python.analysis.extraPaths`
   entry — it points at the dead `…/python3.8/site-packages/selenium/` path.

### E. Python environment (new distro)

1. Replace `apps/requirements.txt` with the direct pins (daemon-plan M0 0.3):

   ```
   playwright==1.63.0
   nicegui==3.17.1
   apscheduler==3.11.3
   bcrypt==5.0.0
   sqlalchemy
   PyYAML
   jsonschema
   requests
   python-dotenv
   nslookup
   flatten-json
   sshkeyboard
   ```

2. Build the venv and install (fresh 24.04 has no pyenv; system 3.12 is used):

   ```bash
   cd ~/projects/BillCollector/apps
   python3 -m venv .venv
   .venv/bin/pip install --upgrade pip
   .venv/bin/pip install -r requirements.txt
   sudo PLAYWRIGHT_BROWSERS_PATH="$PWD/browser" \
        .venv/bin/playwright install --with-deps chromium ffmpeg
   .venv/bin/pip freeze > requirements.txt     # full freeze on 3.12
   ```

3. Optional: delete the copied Playwright-1.48 browsers
   (`apps/browser/chromium-1140`, `apps/browser/ffmpeg-1010`) once the new
   `chromium-*` dir exists.

### F. Verification

```bash
cd ~/projects/BillCollector/apps
python3 --version                          # 3.12.x
.venv/bin/python --version                 # 3.12.x
.venv/bin/playwright --version             # 1.63.0
for f in recipes_playwright/recipe-pw__*.yaml; do
    .venv/bin/python -m helpers.BillCollectorCheckRecipe "$f" || echo "FAILED: $f"
done                                       # all 7 must pass
```

VS Code (WSL: Ubuntu-24.04 remote):
- Workspace opens with the usual theme/settings (Windows-side) and the Kilo
  Code agent works.
- Integrated terminal:
  `.venv/bin/python -c "import playwright.sync_api, nicegui, apscheduler, yaml, jsonschema, bcrypt; print('imports ok')"`
- F5 (`launch.json` "Python Debugger: Current File" on
  `BillCollectorServices_pw.py` or any file) attaches debugpy with the `.venv`
  interpreter. A full F5 run of `BillCollector.py` + `bc_test.ini` hits the
  real portals — time it deliberately (this is the Playwright 1.48→1.63 drift
  check, daemon-plan M0 0.5).

### G. Cleanup + follow-ups (optional, after F passes)

- `wsl --set-default Ubuntu-24.04` — bare `wsl` then opens 24.04 instead of
  20.04.
- Old distro `ubuntu`: keep as backup. Unregister only after the M0 code
  milestones are done on 24.04: `wsl --unregister ubuntu` (Windows; destructive
  — deletes its ext4 volume).
- Follow-ups in the daemon plan (separate work): F5 real-portal verification +
  NAS image rebuild + next cron run (M0 0.5/step 6), then M0 steps 1–6.

## Risks / edge cases

- **Catalog name `Ubuntu` ≠ guaranteed 24.04** → the step-A gate
  (`/etc/os-release`) catches it; fallback is the Store app "Ubuntu 24.04".
- **First boot is interactive** (username/password creation) — username must be
  exactly `stefan` or the repo path / `$schema` paths break.
- **9p staging** (`/mnt/c/tmp`): 871 GB free, a few minutes for ≈700 MB; the
  staging dir is deleted in step C — don't leave the tarball behind.
- **Fresh dotfiles on 24.04**: no pyenv init block (intended), no esp-idf/
  PATH extras from the old `.profile` (other projects out of scope).
- **Two "Ubuntu" distros during the transition**: bare `wsl` still opens the
  old one until step G; always target `Ubuntu-24.04` explicitly.
- **VS Code remote extensions**: not mirrored automatically (evidenced by the
  old remote holding only Kilo Code) — step D.3 installs what F5 needs; add any
  further extension the same way if one misbehaves in the remote.
- **Git**: identity/credentials copied; first `git` op on the new distro
  should work without prompts (Gitea reachable on the NAS LAN).

## Out of scope

- M0 code steps 1–6 (Selenium code removal, error propagation, vault client,
  flock, logging, Docker non-root) — daemon plan.
- NAS Docker image rebuild + production cron verification — daemon plan 0.5.
- `podman-machine-default`, `.wslconfig` (does not exist), other projects on
  the old distro (esp-idf etc.), dotfile migration beyond git config.
- Settings Sync (not relied upon — all settings live on the Windows client).
