# Deployment on Uberspace

Releases are built by GitHub Actions and deployed with `csc_release_deploy.sh`
(see the main README, "Releases and deployment"). This file is the **one-time
setup** of a server, including the conversion of the old layout
(`~/csc/backend`, `~/csc/frontend`, `~/csc/venv`, deploys cloned from `main`).

| file | role |
|---|---|
| `csc_release_deploy.sh` | install a release, switch `~/csc/current`, restart, health-check, roll back; `--install`, `--rollback`, `--status` |
| `csc_deploy_gate.sh` | the only command the GitHub deploy key may run (`deploy v<version>` / `rollback` / `status`) |

Both are installed to `~/csc/bin/` and replace themselves with the copy shipped
in every release after a successful deploy.

## One-time setup

Replace `ddu` / `columba.uberspace.de` with your user and host.

### 1. On your computer: deploy key and GitHub environment

```bash
ssh-keygen -t ed25519 -N "" -C "github-actions csc deploy" -f csc_deploy_key
ssh-keyscan -t ed25519 columba.uberspace.de > csc_known_hosts
```

GitHub → repository → Settings → Environments → **New environment** `production`:

- Deployment protection rules: **Required reviewers** → yourself.
- Environment secrets: `UBERSPACE_SSH_KEY` = contents of `csc_deploy_key`
  (the private key), `UBERSPACE_KNOWN_HOSTS` = contents of `csc_known_hosts`.
- Environment variables: `UBERSPACE_HOST` = `columba.uberspace.de`,
  `UBERSPACE_USER` = `ddu`.
- Repository variable `NEXT_PUBLIC_STATIC_BASE_URL` stays as it is (frontend build).

Then delete `csc_deploy_key` from your computer; GitHub holds the only copy.

### 2. On the server: Python, folders, scripts

```bash
python3.13 --version                       # Uberspace 7 ships it
mkdir -p ~/csc/{releases,venvs,bin,shared/frontend,shared/logs}
cp -a ~/csc/frontend/.env* ~/csc/shared/frontend/        # frontend secrets (old layout)
cp -a ~/csc/backend/logs/. ~/csc/shared/logs/ 2>/dev/null || true
for f in csc_release_deploy.sh csc_deploy_gate.sh; do
  curl -fsSL -o ~/csc/bin/$f \
    https://raw.githubusercontent.com/digitaldesignunit/csc/main/uberspaceconfig/deployment/$f
done
chmod +x ~/csc/bin/*.sh
```

### 3. On the server: authorize the deploy key (restricted)

Append **one line** to `~/.ssh/authorized_keys` — the prefix limits the key to
the gate script, whatever GitHub (or anyone holding the key) sends:

```
command="/home/ddu/csc/bin/csc_deploy_gate.sh",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA…(contents of csc_deploy_key.pub)
```

### 4. First release: install, then move the services over

Tag and push the release (main README). While the workflow's **deploy** job
waits for your approval, install the release without activating it:

```bash
~/csc/bin/csc_release_deploy.sh --install v0.5.1.0
ln -sfn ~/csc/releases/0.5.1.0 ~/csc/current
```

Point the services at `~/csc/current` (compare with the templates in
`../etc/services.d/`): in `~/etc/services.d/fastapi.ini`

```
directory=%(ENV_HOME)s/csc/current/backend
command=%(ENV_HOME)s/csc/current/venv/bin/gunicorn --config %(ENV_HOME)s/csc/current/backend/conf.py
    GH_XML_CACHE_DIR="/home/ddu/csc/current/backend/static/ghxml",
```

(no `--reload` any more) and in `~/etc/services.d/frontend.ini`
`directory=%(ENV_HOME)s/csc/current/frontend`. Then:

```bash
supervisorctl reread && supervisorctl update       # restarts both
curl -s http://127.0.0.1:8000/version              # {"version":"0.5.1.0",…}
supervisorctl status
```

Log in on the website once. If something is wrong, put the old paths back in
both `.ini` files and run `supervisorctl reread && supervisorctl update` — the old
layout is untouched until step 7.

### 5. Cron jobs and `.bash_profile`

```bash
crontab -l > ~/crontab.backup
sed -e 's#/home/ddu/csc/venv/bin/python3.9#/home/ddu/csc/current/venv/bin/python#g' \
    -e 's#/home/ddu/csc/backend/logs/#/home/ddu/csc/shared/logs/#g' \
    -e 's#/home/ddu/csc/backend/#/home/ddu/csc/current/backend/#g' \
    -e '/ghxml_sync/d' ~/crontab.backup | crontab -
crontab -l
```

In `~/.bash_profile` set
`export GH_XML_CACHE_DIR="/home/ddu/csc/current/backend/static/ghxml"` and remove
`GITHUB_DEPLOY_URL`, `GITHUB_USERNAME`, `GITHUB_CSC_DEPLOY_TOKEN` (the old
clone-based deploy). Compare with `../.bash_profile.example`.

### 6. Approve the waiting deploy

In GitHub → Actions → the release run → **Review deployments** → approve. It
connects with the deploy key, re-activates the installed release, runs the
health check and finishes the setup (GH interface images, script self-update).
From now on every release deploys this way.

### 7. Afterwards

- Photo metadata (0.5.1.0 only): back up, dry run, then clean:

  ```bash
  tar czf ~/snapshot_photos_$(date +%y%m%d).tgz -C ~/html/csc_assets snapshot_photos
  curl -fsSL -o ~/migrate_strip_photo_gps.py \
    https://raw.githubusercontent.com/digitaldesignunit/csc/v0.5.1.0/scripts/db_maintenance/migrate_strip_photo_gps.py
  CSC_BACKEND_DIR=~/csc/current/backend ~/csc/current/venv/bin/python ~/migrate_strip_photo_gps.py \
    --photos-dir ~/html/csc_assets/snapshot_photos --dry-run
  # then the same without --dry-run
  ```

- Once a few releases ran well: remove the old layout
  (`~/csc/backend`, `~/csc/frontend`, `~/csc/venv`, `~/csc/_gh_repo`,
  `~/csc_deploy*.sh`).

## Everyday use

| what | how |
|---|---|
| release | tag `v<version>` on main, approve the deploy in GitHub |
| redeploy / roll back / status | Actions → **Deploy** → run with `deploy v<version>`, `rollback` or `status` |
| same on the server | `~/csc/bin/csc_release_deploy.sh v<version>` / `--rollback` / `--status` |
| deploy log | `~/csc/shared/logs/deploy.log` |
