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
# On Uberspace 7 a folder /var/www/virtual/$USER/<domain> is the document root of
# that domain alone ("Additional DocumentRoots", manual.uberspace.de/web-
# documentroot/); ~/html stays the root of every other domain and is never
# written. When the folder does not exist `on` creates it and records that in
# ~/csc/shared/.maintenance_docroot_created; `off` removes the two files and,
# only if the script created the folder and it is empty then, the folder. A
# folder that was there before stays.
#
# The www subdomain (CSC_MAINT_INCLUDE_WWW=1, the default) is handled the same
# way. Apache serves www.<domain> from /var/www/virtual/$USER/www.<domain> when
# that exists, else from ~/html; so `on` makes that path a symlink to the
# domain's document root when nothing is there (the manual allows symlinks in
# this place, but not into /home), and records it in
# ~/csc/shared/.maintenance_www_docroot_created. `off` removes the link only if
# the script made it. A folder or link that was there before stays; it is used
# only when it resolves to the same folder, else `on` stops.
#
# `on` records the backend of the domain and of www
# (`uberspace web backend list`) in ~/csc/shared/.maintenance_backends; `off`
# restores exactly that: the same port, Apache, or `backend del` when there was no
# backend of its own. Without a record `off` sets the domain to the frontend port
# (as before) and www too, but only while the flag file exists (else www is left).
# The static host and the API domain are not touched; the frontend may be
# stopped, restarted or deployed meanwhile (a deploy leaves the mode as it is
# and says so in its log).
#
# The text file (optional) is plain text: every line becomes a paragraph (HTML-
# escaped); a line "end: <when>" sets the expected end, a line "contact: <how>"
# the contact line. Without it a default text is shown.
#
# Settings (environment): CSC_MAINT_DOMAIN (default 2ndchances.build),
# CSC_MAINT_PORT (the frontend, default 3000), CSC_MAINT_DOCROOT (default
# /var/www/virtual/$USER/<domain>; an override is treated the same way),
# CSC_MAINT_WWW_DOCROOT (default /var/www/virtual/$USER/www.<domain>),
# CSC_MAINT_INCLUDE_WWW (1: www too, the default; 0: www is left alone),
# CSC_MAINT_TEXT, CSC_HOME (default ~/csc).
#
# Checking the site during maintenance: ssh -L 3000:127.0.0.1:3000 <account> and
# open http://127.0.0.1:3000 (the frontend answers there while the domain shows
# the page).

set -euo pipefail

CSC_HOME="${CSC_HOME:-$HOME/csc}"
DOMAIN="${CSC_MAINT_DOMAIN:-2ndchances.build}"
INCLUDE_WWW="${CSC_MAINT_INCLUDE_WWW:-1}"  # also set the www subdomain to maintenance
WWW="www.$DOMAIN"
PORT="${CSC_MAINT_PORT:-3000}"
VIRTUAL="/var/www/virtual/${USER:-$(id -un)}"
DOCROOT="${CSC_MAINT_DOCROOT:-$VIRTUAL/$DOMAIN}"
WWWROOT="${CSC_MAINT_WWW_DOCROOT:-$VIRTUAL/$WWW}"   # where Apache looks for www
TEXT_FILE="${CSC_MAINT_TEXT:-$CSC_HOME/shared/maintenance.txt}"
FLAG="$CSC_HOME/shared/.maintenance_on"   # read by csc_release_deploy.sh
CREATED="$CSC_HOME/shared/.maintenance_docroot_created"   # the folder this script made
CREATED_WWW="$CSC_HOME/shared/.maintenance_www_docroot_created"   # the link this script made
BACKENDS="$CSC_HOME/shared/.maintenance_backends"   # the backends before `on`
MARKER="CSC maintenance mode"             # first words of our .htaccess
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
DRY=0

log() { echo "[$(date -Iseconds)] $*"; }
die() { log "ERROR: $*" >&2; exit 1; }

usage() { sed -n '2,56p' "$0"; exit 2; }

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

created_by_us() {  # the folder this script created for DOCROOT, not yet removed
  [ -f "$CREATED" ] && [ "$(cat "$CREATED")" = "$DOCROOT" ]
}

created_www_by_us() {  # the link this script created for WWWROOT, not yet removed
  [ -f "$CREATED_WWW" ] && [ "$(cat "$CREATED_WWW")" = "$WWWROOT" ]
}

# the backend of a host as `uberspace web backend list` shows it: none (no entry
# of its own), apache, http <port>; anything else (a redirect, ...) returns 1
backend_of() {  # backend_of <host>
  local list field
  list=$(uberspace web backend list) || return 2
  field=$(printf '%s\n' "$list" | awk -v h="$1/" '$1 == h { print $2; exit }')
  case "$field" in
    "")        echo none ;;
    apache)    echo apache ;;
    http:*)    [[ "${field#http:}" =~ ^[0-9]{2,5}$ ]] || return 1; echo "http ${field#http:}" ;;
    *)         echo "$field"; return 1 ;;
  esac
}

# www is handled when asked for, or when `on` changed it (a record exists)
www_touched() {
  [ "$INCLUDE_WWW" = 1 ] || grep -q '^www ' "$BACKENDS" 2>/dev/null || [ -f "$CREATED_WWW" ]
}

restore_backend() {  # restore_backend <label: main|www> <host>
  local saved value
  saved=$(grep "^$1 " "$BACKENDS" 2>/dev/null | head -n 1 || true)
  value="${saved##* }"
  case "$saved" in
    "$1 none")   run uberspace web backend del "$2/" ;;
    "$1 apache") run uberspace web backend set "$2/" --apache ;;
    "$1 http "*) if [[ "$value" =~ ^[0-9]{2,5}$ ]]; then
                   run uberspace web backend set "$2/" --http --port "$value"
                 else
                   die "bad record in $BACKENDS: $saved"
                 fi ;;
    *)           if [ "$1" = www ] && [ ! -f "$FLAG" ]; then
                   # a second `off`, or an `off` that no `on` of this version preceded:
                   # do not create a www backend that was not there
                   log "no record of the www backend and maintenance is off: www left as it is"
                 else
                   log "no record of the backend of $2: setting the frontend port $PORT"
                   run uberspace web backend set "$2/" --http --port "$PORT"
                 fi ;;
  esac
}

installed() { [ -f "$DOCROOT/index.html" ] && grep -q "$MARKER" "$DOCROOT/.htaccess" 2>/dev/null; }

maintenance_on() {
  local dir page main_state="" www_state="" make_link=0
  dir=$(template_dir)
  page=$(render "$dir")
  log "maintenance ON for $DOMAIN (document root $DOCROOT)"

  # all checks first, nothing is changed before they pass
  [ -d "$(dirname "$DOCROOT")" ] || die "$(dirname "$DOCROOT") does not exist: not an Uberspace account? (set CSC_MAINT_DOCROOT)"
  # never over somebody else's files: `off` deletes the two names again
  if [ -d "$DOCROOT" ] && ! installed && { [ -e "$DOCROOT/index.html" ] || [ -e "$DOCROOT/.htaccess" ]; }; then
    die "$DOCROOT already has an index.html or .htaccess that this script did not write: not overwritten"
  fi
  if [ "$INCLUDE_WWW" = 1 ]; then
    [ -d "$(dirname "$WWWROOT")" ] || die "$(dirname "$WWWROOT") does not exist (set CSC_MAINT_WWW_DOCROOT)"
    if [ -e "$WWWROOT" ] || [ -L "$WWWROOT" ]; then
      # Apache serves www from this path when it exists: it must be our folder
      [ "$(readlink -f "$WWWROOT")" = "$(readlink -f "$DOCROOT")" ] \
        || die "$WWWROOT exists and is not the document root $DOCROOT: not touched; remove it or set CSC_MAINT_INCLUDE_WWW=0"
    else
      make_link=1
    fi
    case "$DOCROOT" in "$HOME"/*) log "WARNING: $DOCROOT is below $HOME: Apache cannot follow a link into /home";; esac
  fi
  # the backends before maintenance; kept when the record is there from an earlier `on`
  if [ ! -f "$BACKENDS" ]; then
    main_state=$(backend_of "$DOMAIN") || die "cannot restore the backend of $DOMAIN ('${main_state:-uberspace web backend list failed}'): handle it by hand"
    if [ "$INCLUDE_WWW" = 1 ]; then
      www_state=$(backend_of "$WWW") || die "cannot restore the backend of $WWW ('${www_state:-uberspace web backend list failed}'): handle it by hand or set CSC_MAINT_INCLUDE_WWW=0"
    fi
  fi

  if [ ! -d "$DOCROOT" ]; then
    # the folder becomes the document root of this domain alone; only its own
    # folder is made, never the folder above it
    run mkdir "$DOCROOT"
    if [ "$DRY" = 1 ]; then
      echo "+ record the new folder in $CREATED"
    else
      mkdir -p "$(dirname "$CREATED")"
      printf '%s\n' "$DOCROOT" > "$CREATED"
    fi
  fi
  if [ "$make_link" = 1 ]; then
    run ln -s "$DOCROOT" "$WWWROOT"
    if [ "$DRY" = 1 ]; then
      echo "+ record the new link in $CREATED_WWW"
    else
      mkdir -p "$(dirname "$CREATED_WWW")"
      printf '%s\n' "$WWWROOT" > "$CREATED_WWW"
    fi
  fi
  if [ ! -f "$BACKENDS" ]; then
    if [ "$DRY" = 1 ]; then
      echo "+ record the backends in $BACKENDS: main $main_state${www_state:+, www $www_state}"
    else
      mkdir -p "$(dirname "$BACKENDS")"
      { echo "main $main_state"; [ -z "$www_state" ] || echo "www $www_state"; } > "$BACKENDS"
    fi
  fi
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
  if [ "$INCLUDE_WWW" = 1 ]; then
    run uberspace web backend set "$WWW/" --apache
  fi
  if [ "$DRY" = 1 ]; then echo "+ touch $FLAG"; else mkdir -p "$(dirname "$FLAG")"; date -Iseconds > "$FLAG"; fi
  log "the site shows the maintenance page; run '$(basename "$0") off' when it is ready"
}

maintenance_off() {
  log "maintenance OFF for $DOMAIN"
  restore_backend main "$DOMAIN"
  if www_touched; then
    restore_backend www "$WWW"
  fi
  if [ "$DRY" = 1 ]; then echo "+ forget the backends in $BACKENDS"; else rm -f "$BACKENDS"; fi
  # the www link, only when this script made it
  if created_www_by_us; then
    if [ "$DRY" = 1 ]; then
      echo "+ rm $WWWROOT (the link this script made), and forget it in $CREATED_WWW"
    else
      if [ -L "$WWWROOT" ]; then
        rm -f "$WWWROOT"
      elif [ -e "$WWWROOT" ]; then
        log "$WWWROOT is not a link any more: left as it is"
      fi
      rm -f "$CREATED_WWW"
    fi
  fi
  if installed || [ "$DRY" = 1 ]; then
    # only the files this script wrote
    run rm -f "$DOCROOT/index.html" "$DOCROOT/.htaccess"
  fi
  # the folder only when this script made it and nothing else is in it now
  if created_by_us || { [ "$DRY" = 1 ] && [ ! -d "$DOCROOT" ]; }; then
    if [ "$DRY" = 1 ]; then
      echo "+ rmdir $DOCROOT (only if empty), and forget it in $CREATED"
    elif [ -z "$(ls -A "$DOCROOT" 2>/dev/null)" ]; then
      rmdir "$DOCROOT" 2>/dev/null || true
      rm -f "$CREATED"
    else
      log "$DOCROOT is not empty: the folder stays"
      rm -f "$CREATED"
    fi
  fi
  if [ "$DRY" = 1 ]; then echo "+ rm -f $FLAG"; else rm -f "$FLAG"; fi
  log "the domain is back to its backend from before"
}

saved_backend() {  # saved_backend <main|www>: what `on` recorded, or "no record"
  local saved
  saved=$(grep "^$1 " "$BACKENDS" 2>/dev/null | head -n 1 | cut -d' ' -f2- || true)
  echo "${saved:-no record}"
}

maintenance_status() {
  local now
  echo "domain:        $DOMAIN"
  if [ ! -d "$DOCROOT" ]; then
    echo "document root: $DOCROOT (does not exist yet: 'on' creates it)"
  elif created_by_us; then
    echo "document root: $DOCROOT (created by this script; 'off' removes it when empty)"
  else
    echo "document root: $DOCROOT (existing folder; 'off' keeps it)"
  fi
  if installed; then echo "page:          installed"; else echo "page:          not installed"; fi
  if [ -f "$FLAG" ]; then echo "mode:          ON since $(cat "$FLAG")"; else echo "mode:          off"; fi
  if [ "$INCLUDE_WWW" = 1 ] || www_touched; then
    now=$(backend_of "$WWW" 2>/dev/null) || now="${now:-unknown}"
    echo "www backend:   $now (before maintenance: $(saved_backend www))"
    if created_www_by_us; then
      echo "www root:      $WWWROOT (link made by this script to $(readlink "$WWWROOT" 2>/dev/null || echo "?"); 'off' removes it)"
    elif [ -L "$WWWROOT" ]; then
      echo "www root:      $WWWROOT (existing link to $(readlink "$WWWROOT"); 'off' keeps it)"
    elif [ -e "$WWWROOT" ]; then
      echo "www root:      $WWWROOT (existing folder; 'off' keeps it)"
    else
      echo "www root:      $WWWROOT (does not exist: www is served from ~/html; 'on' links it)"
    fi
  else
    echo "www:           left alone (CSC_MAINT_INCLUDE_WWW=0)"
  fi
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
