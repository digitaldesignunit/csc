#!/usr/bin/env bash
#
# End-to-end test of uberspaceconfig/deployment/csc_release_deploy.sh (Linux).
#
# Builds real backend bundles for three versions, serves them through a fake
# GitHub API, replaces supervisorctl with a stub that runs two tiny services
# (backend: /version from the active release; frontend: /api/auth/providers),
# and checks: first deploy, upgrade with venv reuse, a broken release that
# must roll back by itself, a manual rollback, status, pruning, self-update,
# and a release whose own deploy script differs (the run repeats with it, once).
#
#   bash scripts/ci/test_release_deploy.sh
#
# Needs python3 (with venv) on PATH; the backend requirements are installed
# once into the shared venv (all three versions have the same requirements).

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
t="$(mktemp -d)"
pids=()
cleanup() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done
            [ -f "$t/stub.pids" ] && xargs -r kill < "$t/stub.pids" 2>/dev/null || true
            rm -rf "$t"; }
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "ok   $*"; }
free_port() { python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])'; }

export HOME="$t/home" CSC_HOME="$t/home/csc"
mkdir -p "$HOME" "$CSC_HOME/shared/frontend" "$CSC_HOME/bin" "$t/bin" "$t/api/dl"
echo "NEXTAUTH_SECRET=test" > "$CSC_HOME/shared/frontend/.env"

api_port=$(free_port); be_port=$(free_port); fe_port=$(free_port)
export CSC_GITHUB_API="http://127.0.0.1:$api_port" CSC_GITHUB_REPO="owner/repo"
export CSC_BACKEND_URL="http://127.0.0.1:$be_port" CSC_FRONTEND_URL="http://127.0.0.1:$fe_port"
CSC_PYTHON="$(command -v python3)"
export CSC_PYTHON CSC_STATIC_GH_IMAGES="$t/html/gh-interface"
export CSC_HEALTH_TRIES=5   # the broken release must fail fast

# --- releases -----------------------------------------------------------------
make_release() {  # make_release <version> [broken]
  local v="$1" dl="$t/api/dl/v$1" src="$t/src-$1"
  mkdir -p "$dl" "$src"
  # only what the backend bundle is built from
  mkdir -p "$src/src" "$src/uberspaceconfig" "$src/scripts"
  cp -a "$root/src/backend" "$src/src/"
  cp -a "$root/grasshopper_userobjects_xml" "$src/"
  cp -a "$root/uberspaceconfig/deployment" "$src/uberspaceconfig/"
  cp -a "$root/uberspaceconfig/html" "$src/uberspaceconfig/"
  cp -a "$root/scripts/ci" "$src/scripts/"
  sed -i "s/^CSC_VERSION = '.*'$/CSC_VERSION = '$v'/" "$src/src/backend/csc_version.py"
  [ "${2:-}" = broken ] && touch "$src/src/backend/BROKEN"
  # a release whose deploy script differs from the installed one
  [ "${2:-}" = selfupdate ] && echo "# self-update marker $v" >> "$src/uberspaceconfig/deployment/csc_release_deploy.sh"
  bash "$src/scripts/ci/package_release.sh" backend "$v" "$dl" >/dev/null
  mkdir -p "$t/fe-$v/csc-frontend-standalone/public/gh-interface"
  echo "server" > "$t/fe-$v/csc-frontend-standalone/server.js"
  echo "img-$v" > "$t/fe-$v/csc-frontend-standalone/public/gh-interface/pic.txt"
  (cd "$t/fe-$v" && zip -qr "$dl/csc-frontend-$v.zip" csc-frontend-standalone)
  (cd "$dl" && sha256sum "csc-backend-$v.tar.gz" "csc-frontend-$v.zip" > SHA256SUMS)
  mkdir -p "$t/api/repos/owner/repo/releases/tags"
  python3 - "$v" "$api_port" > "$t/api/repos/owner/repo/releases/tags/v$v" <<'PY'
import json, sys
v, port = sys.argv[1], sys.argv[2]
names = [f"csc-backend-{v}.tar.gz", f"csc-frontend-{v}.zip", "SHA256SUMS"]
print(json.dumps({"tag_name": f"v{v}", "assets": [
    {"name": n, "browser_download_url": f"http://127.0.0.1:{port}/dl/v{v}/{n}"}
    for n in names]}))
PY
}
make_release 9.9.9.1
make_release 9.9.9.2
make_release 9.9.9.3 broken
make_release 9.9.9.4 selfupdate
make_release 9.9.9.5 selfupdate
(cd "$t/api" && exec python3 -m http.server "$api_port" --bind 127.0.0.1 >/dev/null 2>&1) &
pids+=($!)
# the server starts in the background: wait until it answers
for _ in $(seq 1 50); do
  curl -fs -o /dev/null "http://127.0.0.1:$api_port/repos/owner/repo/releases/tags/v9.9.9.1" && break
  sleep 0.2
done
curl -fsS -o /dev/null "http://127.0.0.1:$api_port/repos/owner/repo/releases/tags/v9.9.9.1" \
  || fail "fake GitHub API did not start"

# --- supervisorctl stub: (re)start the two tiny services -----------------------
# 9>&-: the services must not inherit the deploy lock (fd 9); the real
# supervisorctl only asks supervisord, so nothing inherits it on the server
cat > "$t/bin/supervisorctl" <<EOF
#!/usr/bin/env bash
[ -f "$t/stub.pids" ] && xargs -r kill < "$t/stub.pids" 2>/dev/null
sleep 0.3
python3 "$t/backend_stub.py" $be_port 9>&- & echo \$! > "$t/stub.pids"
python3 "$t/frontend_stub.py" $fe_port 9>&- & echo \$! >> "$t/stub.pids"
EOF
chmod +x "$t/bin/supervisorctl"
cat > "$t/backend_stub.py" <<EOF
import http.server, json, os, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        rel = os.path.realpath("$CSC_HOME/current")
        broken = os.path.exists(os.path.join(rel, "backend", "BROKEN"))
        body = json.dumps({"version": "broken" if broken else
                           open(os.path.join(rel, "VERSION")).read().strip()}).encode()
        self.send_response(200); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
EOF
cat > "$t/frontend_stub.py" <<'EOF'
import http.server, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"credentials": {}}')
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
EOF
export PATH="$t/bin:$PATH"
cp "$root/uberspaceconfig/deployment/"*.sh "$CSC_HOME/bin/"
chmod +x "$CSC_HOME/bin/"*.sh   # as on the server (step 2 of the deploy README)
deploy() { "$CSC_HOME/bin/csc_release_deploy.sh" "$@"; }
active() { cat "$CSC_HOME/current/VERSION"; }

# --- scenario -----------------------------------------------------------------
deploy --install v9.9.9.1 > "$t/log0" 2>&1 || { cat "$t/log0"; fail "install only"; }
[ -f "$CSC_HOME/releases/9.9.9.1/.complete" ] || fail "install-only did not install"
[ ! -e "$CSC_HOME/current" ] || fail "install-only switched current"
ok "install only (server conversion)"

deploy v9.9.9.1 > "$t/log1" 2>&1 || { cat "$t/log1"; fail "first deploy"; }
[ "$(active)" = 9.9.9.1 ] || fail "9.9.9.1 not active"
[ -L "$CSC_HOME/current/venv" ] && [ -x "$CSC_HOME/current/venv/bin/python" ] || fail "venv link"
[ -L "$CSC_HOME/current/backend/logs" ] || fail "logs not shared"
[ -L "$CSC_HOME/current/frontend/.env" ] || fail ".env not linked"
[ -f "$CSC_HOME/current/backend/static/ghxml/DDU_CSC_Session.xml" ] || fail "ghxml missing"
[ "$(cat "$t/html/gh-interface/pic.txt")" = img-9.9.9.1 ] || fail "static GH images"
[ -x "$CSC_HOME/bin/csc_maintenance.sh" ] || fail "csc_maintenance.sh not shipped to bin/"
[ -f "$CSC_HOME/bin/maintenance/index.template.html" ] \
  && [ -f "$CSC_HOME/bin/maintenance/maintenance.htaccess" ] || fail "maintenance page not shipped"
ok "first deploy"

deploy v9.9.9.2 > "$t/log2" 2>&1 || { cat "$t/log2"; fail "upgrade"; }
[ "$(active)" = 9.9.9.2 ] || fail "9.9.9.2 not active"
grep -q "reusing venv" "$t/log2" || fail "venv not reused"
grep -q "9.9.9.1" "$CSC_HOME/.previous_release" || fail "previous not recorded"
ok "upgrade reuses the venv"

if deploy v9.9.9.3 > "$t/log3" 2>&1; then cat "$t/log3"; fail "broken release deployed"; fi
[ "$(active)" = 9.9.9.2 ] || fail "no automatic rollback (active: $(active))"
grep -q "rolling back" "$t/log3" || fail "rollback not logged"
ok "broken release rolled back automatically"

deploy --rollback > "$t/log4" 2>&1 || { cat "$t/log4"; fail "manual rollback"; }
[ "$(active)" = 9.9.9.1 ] || fail "manual rollback target"
ok "manual rollback"

out=$(deploy --status) && grep -q "9.9.9.1" <<< "$out" || fail "status"
ok "status"

CSC_KEEP_RELEASES=1 deploy v9.9.9.2 > "$t/log5" 2>&1 || { cat "$t/log5"; fail "redeploy"; }
[ -d "$CSC_HOME/releases/9.9.9.2" ] && [ -d "$CSC_HOME/releases/9.9.9.1" ] \
  || fail "active/previous pruned"
[ ! -d "$CSC_HOME/releases/9.9.9.3" ] || fail "old release not pruned"
[ "$(ls "$CSC_HOME/venvs" | wc -l)" = 1 ] || fail "unused venvs kept"
ok "pruning keeps active + previous"

SSH_ORIGINAL_COMMAND="deploy v9.9.9.2; rm -rf /" "$CSC_HOME/bin/csc_deploy_gate.sh" \
  > /dev/null 2>&1 && fail "gate accepted an injected command"
out=$(SSH_ORIGINAL_COMMAND="status" "$CSC_HOME/bin/csc_deploy_gate.sh") \
  && grep -q "9.9.9.2" <<< "$out" || fail "gate status"
ok "deploy gate"

# a release that carries a changed deploy script: the old script installs it
# into bin/ and the run repeats with it, so the change applies at once
deploy v9.9.9.4 > "$t/log6" 2>&1 || { cat "$t/log6"; fail "self-updating release"; }
[ "$(active)" = 9.9.9.4 ] || fail "9.9.9.4 not active after the repeat"
grep -q "different deploy script" "$t/log6" || fail "re-exec not logged"
grep -q "self-update marker 9.9.9.4" "$CSC_HOME/bin/csc_release_deploy.sh" \
  || fail "release script not installed before the repeat"
[ "$(grep -c 'different deploy script' "$t/log6")" = 1 ] || fail "re-exec more than once"
ok "a release with a changed deploy script is deployed by that script"

# the guard: a repeat never repeats again (the script differs from 9.9.9.5's)
CSC_DEPLOY_REEXEC=1 deploy v9.9.9.5 > "$t/log7" 2>&1 || { cat "$t/log7"; fail "guarded deploy"; }
! grep -q "different deploy script" "$t/log7" || fail "guard did not hold"
[ "$(active)" = 9.9.9.5 ] || fail "9.9.9.5 not active"
ok "the re-exec guard holds"

echo "all deploy tests passed"
