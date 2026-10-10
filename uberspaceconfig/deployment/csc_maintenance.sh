#!/usr/bin/env bash
#
# Maintenance mode of the CSC web domain (decision 8.137).
#
#   csc_maintenance.sh on [--dry-run]      show the maintenance page for the web domain
#   csc_maintenance.sh off [--dry-run]     point the domain back to the frontend
#   csc_maintenance.sh status              backends, and whether the page is installed
#
# `on` writes index.html (from the template, with the text of
# ~/csc/shared/maintenance.txt when it exists) and an .htaccess into the web
# domain's own document root, /var/www/virtual/$USER/<domain>/, that answers
# every path with status 503, Retry-After and the page, and then points the
# domain's backend to Apache:
#
#   uberspace web backend set <domain>/ --apache
#
# `off` points it back (`--http --port <port>`) and removes the two files. The
# rest of ~/html, the static host and the API domain are not touched; the
# frontend may be stopped, restarted or deployed meanwhile (a deploy leaves the
# mode as it is and says so in its log).
#
# The text file (optional) is plain text: every line becomes a paragraph (HTML-
# escaped); a line "end: <when>" sets the expected end, a line "contact: <how>"
# the contact line. Without it a default text is shown.
#
# Settings (environment): CSC_MAINT_DOMAIN (default 2ndchances.build),
# CSC_MAINT_PORT (the frontend, default 3000), CSC_MAINT_DOCROOT (default
# /var/www/virtual/$USER/<domain>), CSC_MAINT_TEXT, CSC_HOME (default ~/csc).
#
# Checking the site during maintenance: ssh -L 3000:127.0.0.1:3000 <account> and
# open http://127.0.0.1:3000 (the frontend answers there while the domain shows
# the page).

set -euo pipefail

CSC_HOME="${CSC_HOME:-$HOME/csc}"
DOMAIN="${CSC_MAINT_DOMAIN:-2ndchances.build}"
PORT="${CSC_MAINT_PORT:-3000}"
DOCROOT="${CSC_MAINT_DOCROOT:-/var/www/virtual/${USER:-$(id -un)}/$DOMAIN}"
TEXT_FILE="${CSC_MAINT_TEXT:-$CSC_HOME/shared/maintenance.txt}"
FLAG="$CSC_HOME/shared/.maintenance_on"   # read by csc_release_deploy.sh
MARKER="CSC maintenance mode"             # first words of our .htaccess
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DRY=0

log() { echo "[$(date -Iseconds)] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

usage() { sed -n '2,31p' "$0"; exit 2; }

# where the page sources are: next to this script when installed in ~/csc/bin
# (maintenance/), else in the repository (uberspaceconfig/html/maintenance/)
template_dir() {
  local dir
  for dir in "$HERE/maintenance" "$HERE/../html/maintenance"; do
    [ -f "$dir/index.template.html" ] && { echo "$dir"; return 0; }
  done
  die "no maintenance/index.template.html next to this script"
}

run() {  # run <command...>: print it; run it unless --dry-run
  echo "+ $*"
  [ "$DRY" = 1 ] || "$@"
}

render() {  # render <template dir>: the page on stdout
  python3 - "$1/index.template.html" "$TEXT_FILE" <<'PY'
import html
import os
import sys

template = open(sys.argv[1], encoding="utf-8").read()
default = ("We are updating the catalog. It will be back shortly; "
           "please try again later.")
lines = []
if os.path.isfile(sys.argv[2]):
    with open(sys.argv[2], encoding="utf-8", errors="replace") as handle:
        lines = [line.strip() for line in handle if line.strip()]
end = contact = ""
paragraphs = []
for line in lines:
    key, _, value = line.partition(":")
    if key.strip().lower() == "end" and value.strip():
        end = value.strip()
    elif key.strip().lower() == "contact" and value.strip():
        contact = value.strip()
    else:
        paragraphs.append(line)
message = "".join("  <p>%s</p>\n" % html.escape(p, quote=True)
                  for p in (paragraphs or [default]))
end_html = ('  <p class="small">Expected back: %s</p>\n' % html.escape(end, quote=True)
            if end else "")
contact_html = ('  <p class="small">Contact: %s</p>\n' % html.escape(contact, quote=True)
                if contact else
                '  <p class="small">Questions: the contact address in the imprint, '
                'once the site is back.</p>\n')
page = (template.replace("{{MESSAGE}}\n", message)
        .replace("{{END}}\n", end_html)
        .replace("{{CONTACT}}\n", contact_html))
sys.stdout.write(page)
PY
}

installed() { [ -f "$DOCROOT/index.html" ] && grep -q "$MARKER" "$DOCROOT/.htaccess" 2>/dev/null; }

maintenance_on() {
  local dir page
  dir=$(template_dir)
  [ -d "$DOCROOT" ] || die "the document root $DOCROOT does not exist (set CSC_MAINT_DOCROOT)"
  page=$(render "$dir")
  log "maintenance ON for $DOMAIN (document root $DOCROOT)"
  if [ "$DRY" = 1 ]; then
    echo "+ write $DOCROOT/index.html ($(printf '%s' "$page" | wc -c) bytes, text: ${TEXT_FILE})"
    echo "+ write $DOCROOT/.htaccess (from $dir/maintenance.htaccess)"
  else
    printf '%s\n' "$page" > "$DOCROOT/index.html.new"
    cp "$dir/maintenance.htaccess" "$DOCROOT/.htaccess.new"
    mv -f "$DOCROOT/index.html.new" "$DOCROOT/index.html"
    mv -f "$DOCROOT/.htaccess.new" "$DOCROOT/.htaccess"
  fi
  run uberspace web backend set "$DOMAIN/" --apache
  if [ "$DRY" = 1 ]; then echo "+ touch $FLAG"; else mkdir -p "$(dirname "$FLAG")"; date -Iseconds > "$FLAG"; fi
  log "the site shows the maintenance page; run '$(basename "$0") off' when it is ready"
}

maintenance_off() {
  log "maintenance OFF for $DOMAIN"
  run uberspace web backend set "$DOMAIN/" --http --port "$PORT"
  if installed || [ "$DRY" = 1 ]; then
    # only the files this script wrote
    run rm -f "$DOCROOT/index.html" "$DOCROOT/.htaccess"
  fi
  if [ "$DRY" = 1 ]; then echo "+ rm -f $FLAG"; else rm -f "$FLAG"; fi
  log "the domain points to the frontend on port $PORT again"
}

maintenance_status() {
  echo "domain:        $DOMAIN"
  echo "document root: $DOCROOT"
  if installed; then echo "page:          installed"; else echo "page:          not installed"; fi
  if [ -f "$FLAG" ]; then echo "mode:          ON since $(cat "$FLAG")"; else echo "mode:          off"; fi
  echo "backends:"
  uberspace web backend list || echo "  (uberspace web backend list failed)"
}

main() {
  local command="${1:-}"
  shift || true
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) DRY=1 ;;
      *) usage ;;
    esac
    shift
  done
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || die "bad domain: $DOMAIN"
  [[ "$PORT" =~ ^[0-9]{2,5}$ ]] || die "bad port: $PORT"
  case "$command" in
    on)     maintenance_on ;;
    off)    maintenance_off ;;
    status) maintenance_status ;;
    *)      usage ;;
  esac
}

main "$@"
