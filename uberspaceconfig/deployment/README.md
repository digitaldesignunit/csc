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

Git Bash or any Unix shell (Windows PowerShell 5.1 drops the empty `-N ""`
argument; there, leave out `-N ""` and press Enter twice at the passphrase
prompts --- the key must have no passphrase):

```bash
ssh-keygen -t ed25519 -N "" -C "github-actions csc deploy" -f csc_deploy_key
ssh-keyscan -t ed25519 columba.uberspace.de > csc_known_hosts
```

GitHub --> repository --> Settings --> Environments --> **New environment** `production`:

- Deployment protection rules: **Required reviewers** --> yourself.
- Environment secrets: `UBERSPACE_SSH_KEY` = contents of `csc_deploy_key`
  (the private key), `UBERSPACE_KNOWN_HOSTS` = contents of `csc_known_hosts`.
- Environment variables: `UBERSPACE_HOST` = `columba.uberspace.de`,
  `UBERSPACE_USER` = `ddu`.
- Repository variable `NEXT_PUBLIC_STATIC_BASE_URL` (frontend build): only for public UI files under `/static/`; catalogue files never use it (decision 8.125). It may be left empty.

Once step 3 works, delete `csc_deploy_key` from your computer; GitHub holds
the only copy.

### 2. On the server: Python, folders, scripts

```bash
python3.13 --version                       # Uberspace 7 ships it
node --version                             # Next 16 needs >= 20.9 (production: 22.23.2)
mkdir -p ~/csc/{releases,venvs,bin,shared/frontend,shared/logs,shared/locks}
cp -a ~/csc/frontend/.env* ~/csc/shared/frontend/        # frontend secrets (old layout)
cp -a ~/csc/backend/logs/. ~/csc/shared/logs/ 2>/dev/null || true
for f in csc_release_deploy.sh csc_deploy_gate.sh; do
  curl -fsSL -o ~/csc/bin/$f \
    https://raw.githubusercontent.com/digitaldesignunit/csc/main/uberspaceconfig/deployment/$f
done
chmod +x ~/csc/bin/*.sh
```

### 2b. On the server: the `gh` CLI (verifies the release attestations)

The deploy checks the backend tar and the frontend zip with
`gh attestation verify` before it installs anything, and stops when `gh` is
missing. Install the static release binary once (it is a single Go binary and
runs on the glibc 2.17 of Uberspace 7); do this **before the first deploy of a
release that carries the check**, because that deploy repeats itself with the new
script and the repeat needs `gh`:

```bash
ver=2.101.0     # the newest release at https://github.com/cli/cli/releases
cd "$(mktemp -d)"
curl -fsSLO https://github.com/cli/cli/releases/download/v$ver/gh_${ver}_linux_amd64.tar.gz
curl -fsSLO https://github.com/cli/cli/releases/download/v$ver/gh_${ver}_checksums.txt
grep " gh_${ver}_linux_amd64.tar.gz\$" gh_${ver}_checksums.txt | sha256sum -c -
tar -xzf gh_${ver}_linux_amd64.tar.gz
mkdir -p ~/bin && install -m 755 gh_${ver}_linux_amd64/bin/gh ~/bin/gh
~/bin/gh --version
```

`gh` needs a token even to read the attestations of a public repository (without
one it stops with "gh auth login"). Create a fine-grained personal access token
on GitHub with **no permissions** (public read is enough; set a long expiry and
note it in your calendar) and store it once for the server account:

```bash
printf '%s' '<the token>' | ~/bin/gh auth login --with-token
~/bin/gh auth status
```

The deploy script puts `~/bin` on its `PATH` itself, so the forced SSH command
finds `gh`; it uses the stored login, or `GITHUB_CSC_DEPLOY_TOKEN` if that
variable is set. Check by hand with
`~/bin/gh attestation verify <file> --repo digitaldesignunit/csc --signer-workflow digitaldesignunit/csc/.github/workflows/release.yml`.
`SHA256SUMS` stays as the check of the download; the attestation is the check
of who built the file.

### 3. On the server: authorize the deploy key (restricted)

Append **one line** to `~/.ssh/authorized_keys` --- the prefix limits the key to
the gate script, whatever GitHub (or anyone holding the key) sends. Append it
with these commands rather than an editor (nano on Uberspace 7 wraps long
lines, which breaks the entry):

```bash
# the whole line from csc_deploy_key.pub, "ssh-ed25519 AAAAC3Nza... github-actions csc deploy"
key='PASTE THE LINE FROM csc_deploy_key.pub HERE'
if [[ "$key" == "ssh-ed25519 AAAA"* ]]; then
  [ -z "$(tail -c1 ~/.ssh/authorized_keys)" ] || echo >> ~/.ssh/authorized_keys
  echo "command=\"$HOME/csc/bin/csc_deploy_gate.sh\",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty $key" >> ~/.ssh/authorized_keys
  chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
  ssh-keygen -lf ~/.ssh/authorized_keys   # must list the ED25519 deploy key
else
  echo "not a public key: $key"
fi
```

Check from your computer (needs the private key): `ssh -i csc_deploy_key
ddu@columba.uberspace.de status` prints the deploy status.

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
curl -s http://127.0.0.1:8000/version              # {"version":"0.5.1.0",...}
supervisorctl status
```

Log in on the website once. If something is wrong, put the old paths back in
both `.ini` files and run `supervisorctl reread && supervisorctl update` --- the old
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

Optional, in the service environment of the backend (`fastapi.ini`):
`CSC_GH_TOKEN_HOURS` (default `6`, from 1 to 24) is the lifetime in hours of the
token of a sign-in from the Grasshopper client (`X-CSC-Client:
gh-userobjects/...`); every other sign-in keeps
`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`. Leave it unset unless the 6 hours are wrong.

### 6. Approve the waiting deploy

In GitHub --> Actions --> the release run --> **Review deployments** --> approve. It
connects with the deploy key, re-activates the installed release, runs the
health check and finishes the setup (GH interface images, script self-update).
From now on every release deploys this way.

### 7. Afterwards

- Photo metadata (0.5.1.0 only): back up, dry run, then clean:

  ```bash
  tar czf ~/snapshot_photos_$(date +%y%m%d).tgz -C ~/csc_assets_private snapshot_photos
  curl -fsSL -o ~/migrate_strip_photo_gps.py \
    https://raw.githubusercontent.com/digitaldesignunit/csc/v0.5.1.0/scripts/db_maintenance/migrate_strip_photo_gps.py
  CSC_BACKEND_DIR=~/csc/current/backend ~/csc/current/venv/bin/python ~/migrate_strip_photo_gps.py \
    --photos-dir ~/csc_assets_private/snapshot_photos --dry-run
  # then the same without --dry-run
  ```

- Once a few releases ran well: remove the old layout
  (`~/csc/backend`, `~/csc/frontend`, `~/csc/venv`, `~/csc/_gh_repo`,
  `~/csc_deploy*.sh`).

## Everyday use

| what | how |
|---|---|
| release | tag `v<version>` on main, approve the deploy in GitHub |
| redeploy / roll back / status | Actions --> **Deploy** --> run with `deploy v<version>`, `rollback` or `status` |
| same on the server | `~/csc/bin/csc_release_deploy.sh v<version>` / `--rollback` / `--status` |
| deploy log | `~/csc/shared/logs/deploy.<YYYY-MM-DD>.log` (one file a day; the crontab deletes those older than 14 days) |
| maintenance page | `~/csc/bin/csc_maintenance.sh on` / `off` / `status` (below) |

**The deploy runs the release's own scripts.** After the download is verified,
a release whose `deploy/csc_release_deploy.sh` differs from the script that is
running is installed into `~/csc/bin/` and the run is repeated with it (the
log says "release carries a different deploy script"; `CSC_DEPLOY_REEXEC=1`
marks the repeat, so it happens once; the deploy lock is kept). A change to a
deploy script therefore takes effect with the release that carries it.

## Maintenance mode

For a cutover or a migration the web domain shows a static page, while the
frontend may be stopped, restarted or deployed (decision 8.137). The script
ships with every release into `~/csc/bin/` (with `maintenance/`, the page
template and the `.htaccess`):

```bash
~/csc/bin/csc_maintenance.sh on          # page + 503 for every path, domain --> Apache
~/csc/bin/csc_maintenance.sh status      # backends, page installed?, since when
~/csc/bin/csc_maintenance.sh off         # domain --> the frontend on port 3000 again
~/csc/bin/csc_maintenance.sh on --dry-run   # prints the commands, changes nothing
```

`on` writes `index.html` and an `.htaccess` into the domain's own document root,
`/var/www/virtual/$USER/<domain>/`, and runs
`uberspace web backend set <domain>/ --apache` (the same for `www.<domain>`,
below); `off` puts the backends back as they were and removes the two files.
Every path answers `503` with `Retry-After`, `Cache-Control: no-store` and
`noindex`.

**The document root.** On Uberspace 7 a folder `/var/www/virtual/$USER/<domain>`
is the document root of that domain alone (manual, "DocumentRoot", section
"Additional DocumentRoots": "You can create folders (and symlinks) in the form
of `/var/www/virtual/<username>/<domain>`"); `~/html` (that is
`/var/www/virtual/$USER/html`) stays the root of every other domain and is
never written by the script: nothing in it, the static host and the API domain
included, is touched, so the import and the geometry runner keep working. A
production account usually has no such folder yet, so `on` creates it (only
that folder, never the one above) and records that in
`~/csc/shared/.maintenance_docroot_created`; `off` removes the two files and
then the folder, but only if the script created it and nothing else is in it.
A folder that was there before stays, with its other files, and `on` refuses to
overwrite an `index.html` or `.htaccess` it did not write. `status` names the
document root and says whether the script created it; `--dry-run` prints the
`mkdir` and `rmdir` as well. Do not delete `~/html` (the manual warns that the
additional document roots depend on it).

**The www subdomain** (`CSC_MAINT_INCLUDE_WWW`, default `1`; `0` leaves www
alone). Apache serves `www.<domain>` from `/var/www/virtual/$USER/www.<domain>`
when that path exists, and (by our reading; the manual does not say it) from `~/html`
otherwise; with only the domain's folder the www
address could show `~/html` instead of the page. So `on` makes
`/var/www/virtual/$USER/www.<domain>` a symlink to the domain's document root
when nothing is there, and records that in
`~/csc/shared/.maintenance_www_docroot_created`; `off` removes the link, only
if the script made it. A folder or link that was there before stays untouched;
`on` uses it only when it resolves to the same folder and otherwise stops
before changing anything. The manual allows symlinks in this place ("folders
(and symlinks)") but not into `/home` (Apache has no access there), and does
not mention `FollowSymLinks`: the target here is below `/var/www/virtual`, and
the page for www is part of the test on a test subdomain below.

**The backends.** `on` reads `uberspace web backend list` and records the line
of the domain and (with www) of `www.<domain>` in
`~/csc/shared/.maintenance_backends`: no backend of its own, Apache, or an
http port. `off` restores exactly that: the same port, Apache, or
`uberspace web backend del <host>/` when there was none. If a host has a
backend the script cannot restore (a redirect, for instance), `on` stops before
it changes anything; set `CSC_MAINT_INCLUDE_WWW=0` or handle the host by hand.
A second `on` keeps the first record. Without a record (an `on` of an older
version of the script, or a second `off`) `off` sets the domain to the frontend
port, as before; www is changed only while the maintenance flag
(`~/csc/shared/.maintenance_on`) exists, else the log says "www left as it is",
so a second `off` never creates a www backend. `status` shows
the www backend (now, and before the maintenance), the www document root and
who made it.

The domain, the port and the folders are settings (`CSC_MAINT_DOMAIN`, default
`2ndchances.build`; `CSC_MAINT_PORT`, default `3000`; `CSC_MAINT_DOCROOT` and
`CSC_MAINT_WWW_DOCROOT`, which are treated the same way).

The text of the page is `~/csc/shared/maintenance.txt` when it exists, else a
default. Plain text: every line is a paragraph (HTML-escaped); a line
`end: <when>` sets "Expected back", a line `contact: <how>` the contact line:

```
We are moving the catalog to a new version.
end: Sunday 18:00
contact: a mail address or a phone number
```

A deploy leaves the mode as it is and says so at the end of its log.

**Runbook of a cutover or a migration:** start with `csc_maintenance.sh on`
and `touch ~/csc/shared/READ_ONLY` (below), do the work (stop the frontend,
migrate, deploy), check the site through an SSH tunnel
(`ssh -L 3000:127.0.0.1:3000 <account>`, then `http://127.0.0.1:3000`; the
frontend answers there while the domain shows the page), end with
`rm ~/csc/shared/READ_ONLY` and `csc_maintenance.sh off`.

## Read-only mode

A maintenance step that touches the database or the asset folders (restore,
purge, migration, cutover, a script from `scripts/db_maintenance/`) must not run
while users write. The switch is a file:

```bash
touch ~/csc/shared/READ_ONLY        # before the step: every write is refused
# ... the maintenance step ...
rm ~/csc/shared/READ_ONLY           # after it: writes are accepted again
```

While the file exists:

- every request other than GET, HEAD and OPTIONS is answered `503` with a
  `Retry-After` header and `{"detail": "read-only: maintenance"}`, before its
  body is read: registration, uploads, the web app's changes and the Grasshopper
  writes included. Reads keep working. Every gunicorn worker looks at the file on
  every request, so `touch` and `rm` take effect at once, with no restart;
- sign-in (`POST /auth/token`) stays open so you can check the site, and writes
  nothing to the database: the per-address limit still holds but is counted in
  the memory of each worker, the failed-sign-in count per account is paused (an
  account that was locked before stays locked), and the account is not changed;
- `/version` and `/health/db` report `"read_only": true`; the web app shows a
  banner on every page and disables its write buttons (it asks `/version` once a
  minute); a Grasshopper component that writes shows `read-only: maintenance`
  as its error;
- the geometry runner, the component map job, `usermaintenance.py` and
  `geometrymaintenance.py` skip their run and log one line ("skipped, the
  read-only flag is set"); a `--dry-run` still runs. The next cron run after
  `rm` picks the work up.

The path is `CSC_READ_ONLY_FLAG` (default `~/csc/shared/READ_ONLY`); leave it
unset on the server. The flag does not replace the maintenance page: `touch`
stops the writes, `csc_maintenance.sh on` hides the frontend; use both for a
cutover, the flag alone for a short database step. A deploy leaves the flag as
it is; remove it yourself when the work is done. Check it with
`curl -s http://127.0.0.1:8000/version`.

**To verify once on the server, before the first use:** that Apache serves
the per-domain folder for a domain whose backend is `--apache` (the manual says
the folder form is allowed, it does not show this exact use). Try it on a test
subdomain (`uberspace web domain add test.<domain>` and `www.test.<domain>`,
`csc_maintenance.sh on` with `CSC_MAINT_DOMAIN=test.<domain>`, open both
addresses, then `off`: the folder and the link it made are gone again, the
backends are as before); this has not been checked on the production account
yet. If Apache does not follow the link, `on` shows `~/html` at the www address:
then use a real folder with the two files instead of the link (change the script) or set `CSC_MAINT_INCLUDE_WWW=0`.
