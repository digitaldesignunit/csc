#!/usr/bin/env bash
#
# Deploy a CSC release on Uberspace.
#
#   csc_release_deploy.sh v0.5.1.0     download, install and switch to a release
#   csc_release_deploy.sh --rollback   switch back to the previously active release
#   csc_release_deploy.sh --status     show the active release and what is installed
#   csc_release_deploy.sh --install v0.5.1.0   only download and install (no switch;
#                                      used once when converting a server to this layout)
#
# Layout (see README, "Releases and deployment"):
#   ~/csc/releases/<version>/{backend,frontend,deploy,VERSION,venv -> ../../venvs/<hash>}
#   ~/csc/venvs/<hash>/        one venv per requirements + constraints content
#   ~/csc/current              symlink to the active release (services + cron use it)
#   ~/csc/shared/frontend/     .env / .env.local of the frontend (linked into each release)
#   ~/csc/shared/logs/         backend logs (linked as backend/logs into each release)
#   ~/csc/bin/                 this script + csc_deploy_gate.sh (updated by each deploy)
#
# A deploy never touches the database. If the new release fails its health check the
# previous one is switched back and restarted.

set -euo pipefail

CSC_HOME="${CSC_HOME:-$HOME/csc}"
REPO="${CSC_GITHUB_REPO:-digitaldesignunit/csc}"
GITHUB_API="${CSC_GITHUB_API:-https://api.github.com}"   # overridden by the CI test
PYTHON="${CSC_PYTHON:-python3.13}"
KEEP_RELEASES="${CSC_KEEP_RELEASES:-5}"
HEALTH_TRIES="${CSC_HEALTH_TRIES:-60}"   # x 2 s per service
BACKEND_URL="${CSC_BACKEND_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${CSC_FRONTEND_URL:-http://127.0.0.1:3000}"
STATIC_GH_IMAGES="${CSC_STATIC_GH_IMAGES:-$HOME/html/csc_assets/static/gh-interface}"
GITHUB_TOKEN="${GITHUB_CSC_DEPLOY_TOKEN:-${GITHUB_CSC_GH_TOKEN:-}}"

RELEASES="$CSC_HOME/releases"
VENVS="$CSC_HOME/venvs"
SHARED="$CSC_HOME/shared"
CURRENT="$CSC_HOME/current"
PREVIOUS_FILE="$CSC_HOME/.previous_release"
TAG_RE='^v[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$'

DEPLOY_WORK=""
trap 'rm -rf "${DEPLOY_WORK:-}" "${DEPLOY_TARGET_TMP:-}"' EXIT

log() { echo "[$(date -Iseconds)] $*"; }
die() { log "ERROR: $*"; exit 1; }

github() {  # github <url> <outfile>: public repo; a token only raises rate limits
  if [ -n "$GITHUB_TOKEN" ]; then
    curl -fsSL --retry 3 -H "Authorization: Bearer $GITHUB_TOKEN" -o "$2" "$1"
  else
    curl -fsSL --retry 3 -o "$2" "$1"
  fi
}

version_of() { cat "$1/VERSION"; }

active_release() { if [ -L "$CURRENT" ]; then readlink -f "$CURRENT"; fi; }

switch_to() {  # atomic symlink swap
  ln -sfn "$1" "$CURRENT.new"
  mv -Tf "$CURRENT.new" "$CURRENT"
}

healthy() {  # healthy <version>: backend reports it, frontend auth answers JSON
  local version="$1" got="" _
  for _ in $(seq 1 "$HEALTH_TRIES"); do
    got=$(curl -fsS --max-time 5 "$BACKEND_URL/version" 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["version"])' 2>/dev/null || true)
    [ "$got" = "$version" ] && break
    sleep 2
  done
  [ "$got" = "$version" ] || { log "backend reports '${got:-nothing}', expected $version"; return 1; }
  for _ in $(seq 1 "$HEALTH_TRIES"); do
    if curl -fsS --max-time 10 "$FRONTEND_URL/api/auth/providers" 2>/dev/null \
        | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
      return 0
    fi
    sleep 2
  done
  log "frontend /api/auth/providers does not answer JSON"
  return 1
}

restart_services() {
  supervisorctl restart fastapi frontend
}

install_release() {  # install_release <tag>: unpack into releases/<version> once
  local tag="$1" version="${1#v}" target="$RELEASES/${1#v}"
  if [ -f "$target/.complete" ]; then
    log "release $version already installed"
    return 0
  fi
  local work
  work=$(mktemp -d "$CSC_HOME/.deploy.XXXXXX")
  DEPLOY_WORK="$work"   # removed by the EXIT trap, also when a step dies

  log "downloading release $tag from $REPO"
  github "$GITHUB_API/repos/$REPO/releases/tags/$tag" "$work/release.json" \
    || die "no GitHub release $tag"
  local backend="csc-backend-$version.tar.gz" frontend="csc-frontend-$version.zip" name url
  for name in "$backend" "$frontend" SHA256SUMS; do
    url=$(python3 - "$work/release.json" "$name" <<'PY'
import json, sys
rel = json.load(open(sys.argv[1], encoding="utf-8"))
for asset in rel.get("assets", []):
    if asset["name"] == sys.argv[2]:
        print(asset["browser_download_url"]); break
else:
    sys.exit("asset %s missing on release %s" % (sys.argv[2], rel.get("tag_name")))
PY
) || die "release $tag lacks $name"
    github "$url" "$work/$name"
  done
  (cd "$work" && grep -E " (\*)?($backend|$frontend)\$" SHA256SUMS | sha256sum -c -) \
    || die "checksum mismatch"

  log "unpacking into $target"
  DEPLOY_TARGET_TMP="$target.tmp"   # a half-unpacked release never survives
  rm -rf "$target.tmp"
  mkdir -p "$target.tmp"
  tar -xzf "$work/$backend" -C "$target.tmp"          # -> backend/ deploy/ VERSION
  unzip -q "$work/$frontend" -d "$work/frontend"       # -> csc-frontend-standalone/
  mv "$work/frontend/csc-frontend-standalone" "$target.tmp/frontend"
  [ "$(version_of "$target.tmp")" = "$version" ] || die "bundle VERSION != $version"

  # shared state: frontend secrets and backend logs live outside releases
  mkdir -p "$SHARED/frontend" "$SHARED/logs"
  local env_file
  for env_file in "$SHARED"/frontend/.env*; do
    [ -e "$env_file" ] && ln -sfn "$env_file" "$target.tmp/frontend/$(basename "$env_file")"
  done
  ls "$target.tmp"/frontend/.env* >/dev/null 2>&1 \
    || die "no $SHARED/frontend/.env* --- the frontend needs its secrets there"
  rm -rf "$target.tmp/backend/logs"
  ln -s "$SHARED/logs" "$target.tmp/backend/logs"

  # one venv per requirements + constraints content, reused across releases
  local hash venv
  hash=$(cat "$target.tmp/backend/requirements.txt" "$target.tmp/backend/constraints.txt" \
    | sha256sum | cut -c1-12)
  venv="$VENVS/$hash"
  if [ ! -f "$venv/.complete" ]; then
    log "building venv $hash with $PYTHON (requirements changed)"
    rm -rf "$venv"
    mkdir -p "$VENVS"
    "$PYTHON" -m venv "$venv"
    "$venv/bin/pip" install -q --upgrade pip
    # binary wheels only (as `invoke check-server-wheels` checks): a missing
    # wheel fails here at once instead of compiling on the server
    "$venv/bin/pip" install -q --only-binary=:all: \
      -r "$target.tmp/backend/requirements.txt" \
      -c "$target.tmp/backend/constraints.txt"
    touch "$venv/.complete"
  else
    log "reusing venv $hash"
  fi
  ln -s "$venv" "$target.tmp/venv"

  rm -rf "$target"
  mv "$target.tmp" "$target"
  DEPLOY_TARGET_TMP=""
  touch "$target/.complete"
}

activate() {  # activate <release dir>: switch, restart, check; roll back on failure
  local target="$1" version previous
  version=$(version_of "$target")
  previous=$(active_release)
  if [ "$previous" = "$(readlink -f "$target")" ]; then
    log "release $version is already active; restarting"
  fi
  switch_to "$target"
  log "switched $CURRENT -> $target; restarting services"
  restart_services
  if healthy "$version"; then
    touch "$target/.activated"   # pruning keeps the most recently activated
    [ -n "$previous" ] && [ "$previous" != "$(readlink -f "$target")" ] \
      && echo "$previous" > "$PREVIOUS_FILE"
    return 0
  fi
  if [ -n "$previous" ] && [ -d "$previous" ]; then
    log "release $version is unhealthy; rolling back to $(version_of "$previous")"
    switch_to "$previous"
    restart_services
    healthy "$(version_of "$previous")" || log "previous release is unhealthy too!"
  fi
  die "deploy of $version failed"
}

after_success() {  # static GH images, self-update of these scripts, pruning
  local target="$1" keep dir used r
  if [ -d "$target/frontend/public/gh-interface" ]; then
    mkdir -p "$STATIC_GH_IMAGES"
    cp -a "$target/frontend/public/gh-interface/." "$STATIC_GH_IMAGES/"
  fi
  mkdir -p "$CSC_HOME/bin"
  cp "$target/deploy/"*.sh "$CSC_HOME/bin/"
  chmod +x "$CSC_HOME/bin/"*.sh

  # keep the KEEP_RELEASES most recently activated plus active and previous
  # (a release that never passed its health check is not kept); drop unused venvs
  keep=$(ls -1t "$RELEASES"/*/.activated 2>/dev/null | sed -n "1,${KEEP_RELEASES}p" | xargs -r -n1 dirname | xargs -r -n1 readlink -f)
  keep="$keep"$'\n'"$(active_release)"$'\n'"$(cat "$PREVIOUS_FILE" 2>/dev/null || true)"
  for dir in "$RELEASES"/*/; do
    [ -d "$dir" ] || continue
    dir=$(readlink -f "$dir")
    grep -qxF "$dir" <<< "$keep" || { log "pruning release $(basename "$dir")"; rm -rf "$dir"; }
  done
  # collected first: grep -q in a pipe can cut off the writer (pipefail)
  used=$(for r in "$RELEASES"/*/venv; do readlink -f "$r"; done 2>/dev/null || true)
  for dir in "$VENVS"/*/; do
    [ -d "$dir" ] || continue
    dir=$(readlink -f "$dir")
    if ! grep -qxF "$dir" <<< "$used"; then
      log "pruning venv $(basename "$dir")"
      rm -rf "$dir"
    fi
  done
}

status() {
  echo "active:   $(active_release) ($(version_of "$CURRENT" 2>/dev/null || echo none))"
  echo "previous: $(cat "$PREVIOUS_FILE" 2>/dev/null || echo none)"
  echo "installed:"
  ls -1 "$RELEASES" 2>/dev/null | sed 's/^/  /'
  echo "venvs:"
  ls -1 "$VENVS" 2>/dev/null | sed 's/^/  /'
}

main() {
  mkdir -p "$RELEASES" "$VENVS"
  exec 9>"$CSC_HOME/.deploy.lock"
  flock -n 9 || die "another deploy is running"
  case "${1:-}" in
    --status)
      status ;;
    --install)
      [[ "${2:-}" =~ $TAG_RE ]] || die "usage: --install v<version>"
      install_release "$2"
      log "installed ${2#v} (not active) at $RELEASES/${2#v}" ;;
    --rollback)
      local previous
      previous=$(cat "$PREVIOUS_FILE" 2>/dev/null || true)
      [ -n "$previous" ] && [ -d "$previous" ] || die "no previous release recorded"
      activate "$previous"
      log "rolled back to $(version_of "$previous")" ;;
    v*)
      [[ "$1" =~ $TAG_RE ]] || die "not a release tag: $1"
      install_release "$1"
      activate "$RELEASES/${1#v}"
      after_success "$RELEASES/${1#v}"
      log "deployed ${1#v}" ;;
    *)
      sed -n '2,10p' "$0"; exit 2 ;;
  esac
}

main "$@"
