#!/usr/bin/env bash
#
# Test of uberspaceconfig/deployment/csc_maintenance.sh (Linux).
#
# `uberspace` is a stub that records its calls. Checks: a missing document root
# is created by `on` and removed again by `off` (the script records that it made
# it), an existing folder and its files stay, files of another folder are never
# touched, a folder that got other files meanwhile stays, foreign files are not
# overwritten, --dry-run changes nothing and prints the mkdir and rmdir, the
# parent folder is never created, status says who made the folder. The www
# subdomain: its document root is a link made by `on` and removed by `off` (an
# existing folder or link stays, a foreign one stops `on`), the backends before
# `on` (none, a port) are restored, CSC_MAINT_INCLUDE_WWW=0 leaves www alone.
#
#   bash scripts/ci/test_maintenance.sh
#
# Needs python3 (the page is rendered with it).

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="$root/uberspaceconfig/deployment/csc_maintenance.sh"
t="$(mktemp -d)"
trap 'rm -rf "$t"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "ok   $*"; }

mkdir -p "$t/bin" "$t/csc/shared" "$t/virtual"
cat > "$t/bin/uberspace" <<STUB
#!/usr/bin/env bash
echo "\$*" >> "$t/uberspace.calls"
[ "\$*" = "web backend list" ] && cat "$t/backend.list" 2>/dev/null
exit 0
STUB
chmod +x "$t/bin/uberspace"
export PATH="$t/bin:$PATH" CSC_HOME="$t/csc" CSC_MAINT_DOMAIN="example.org" CSC_MAINT_PORT=3000
export CSC_MAINT_TEXT="$t/none.txt" USER="${USER:-tester}"
docroot="$t/virtual/example.org"           # the folder of the domain, under the account's folder
wwwroot="$t/virtual/www.example.org"       # where Apache looks for the www subdomain
export CSC_MAINT_DOCROOT="$docroot" CSC_MAINT_WWW_DOCROOT="$wwwroot"
other="$t/virtual/html"                    # ~/html: the root of every other domain
mkdir "$other"
echo "keep me" > "$other/index.html"
printf 'Require all granted\n' > "$other/.htaccess"
before=$(cd "$other" && sha256sum index.html .htaccess)

run() { bash "$script" "$@"; }
calls() { cat "$t/uberspace.calls" 2>/dev/null || true; }
changing_calls() { calls | grep -v '^web backend list$' || true; }   # the list only reads
reset_calls() { rm -f "$t/uberspace.calls"; }
created_file="$t/csc/shared/.maintenance_docroot_created"
printf '%s\n' "/ apache (default)" "example.org/ http:3000 => OK, listening: PID 1, node" > "$t/backend.list"

# 1. a missing folder is created by `on` and removed by `off` ----------------------
[ ! -e "$docroot" ] || fail "test setup"
run on > "$t/log1" 2>&1 || { cat "$t/log1"; fail "on with a missing folder"; }
[ -d "$docroot" ] || fail "the document root was not created"
[ -f "$docroot/index.html" ] && grep -q "CSC maintenance mode" "$docroot/.htaccess" || fail "the page was not written"
[ "$(cat "$created_file")" = "$docroot" ] || fail "the created folder was not recorded"
[ -f "$t/csc/shared/.maintenance_on" ] || fail "the flag was not written"
calls | grep -qx "web backend set example.org/ --apache" || fail "backend not set to Apache"
out=$(run status 2>&1 || true)
grep -q "created by this script" <<< "$out" || { echo "$out"; fail "status does not say the script made the folder"; }
grep -q "$docroot" <<< "$out" || fail "status does not name the document root"
ok "a missing document root is created and recorded"

run on > "$t/log1b" 2>&1 || { cat "$t/log1b"; fail "a second on"; }
[ "$(cat "$created_file")" = "$docroot" ] || fail "a second on lost the record"
ok "a second on is harmless"

run off > "$t/log2" 2>&1 || { cat "$t/log2"; fail "off"; }
[ ! -e "$docroot" ] || fail "the folder the script made was not removed"
[ ! -e "$created_file" ] || fail "the record stayed"
[ ! -e "$t/csc/shared/.maintenance_on" ] || fail "the flag stayed"
calls | grep -qx "web backend set example.org/ --http --port 3000" || fail "backend not set back"
ok "off removes the files and the folder it made"

# 2. an existing folder stays -------------------------------------------------------
reset_calls
mkdir "$docroot"
echo "mine" > "$docroot/other.txt"
run on > "$t/log3" 2>&1 || { cat "$t/log3"; fail "on with an existing folder"; }
[ ! -e "$created_file" ] || fail "an existing folder was recorded as created"
out=$(run status 2>&1 || true)
grep -q "existing folder" <<< "$out" || { echo "$out"; fail "status does not say the folder existed"; }
run off > "$t/log4" 2>&1 || { cat "$t/log4"; fail "off"; }
[ -d "$docroot" ] && [ "$(cat "$docroot/other.txt")" = mine ] || fail "an existing folder or its file was removed"
[ ! -e "$docroot/index.html" ] && [ ! -e "$docroot/.htaccess" ] || fail "the two files stayed"
ok "an existing folder and its files stay"

# an empty existing folder stays as well
rm -f "$docroot/other.txt"
run on > /dev/null 2>&1 && run off > /dev/null 2>&1
[ -d "$docroot" ] || fail "an empty existing folder was removed"
ok "an empty folder that was there before stays"
rmdir "$docroot"

# 3. a folder the script made keeps other files that came meanwhile -----------------
run on > /dev/null 2>&1
echo "later" > "$docroot/later.txt"
run off > "$t/log5" 2>&1 || { cat "$t/log5"; fail "off with a foreign file"; }
[ -f "$docroot/later.txt" ] || fail "a foreign file was deleted"
grep -q "not empty" "$t/log5" || fail "the kept folder was not reported"
[ ! -e "$created_file" ] || fail "the record stayed"
rm -rf "$docroot"
ok "a folder that is not empty after off stays"

# 4. files in another folder are never touched ---------------------------------------
run on > /dev/null 2>&1 && run off > /dev/null 2>&1
after=$(cd "$other" && sha256sum index.html .htaccess)
[ "$before" = "$after" ] || fail "files of another folder changed"
ok "the files of another folder are untouched"

# 5. foreign files in the document root are not overwritten ---------------------------
mkdir "$docroot"
echo "their page" > "$docroot/index.html"
if run on > "$t/log6" 2>&1; then cat "$t/log6"; fail "overwrote a foreign index.html"; fi
grep -q "not overwritten" "$t/log6" || fail "no message for the foreign file"
[ "$(cat "$docroot/index.html")" = "their page" ] || fail "the foreign file changed"
rm -rf "$docroot"
ok "a foreign index.html is not overwritten"

# 6. --dry-run changes nothing and prints mkdir and rmdir -----------------------------
reset_calls
dry=$(run on --dry-run 2>&1)
[ ! -e "$docroot" ] && [ ! -e "$created_file" ] && [ ! -e "$t/csc/shared/.maintenance_on" ] || fail "dry-run changed something"
grep -q "+ mkdir $docroot" <<< "$dry" || { echo "$dry"; fail "dry-run on does not print the mkdir"; }
[ -z "$(changing_calls)" ] || fail "dry-run changed a backend"
run on > /dev/null 2>&1
dry=$(run off --dry-run 2>&1)
grep -q "+ rmdir $docroot" <<< "$dry" || { echo "$dry"; fail "dry-run off does not print the rmdir"; }
[ -d "$docroot" ] && [ -f "$docroot/index.html" ] || fail "dry-run off removed something"
run off > /dev/null 2>&1
ok "--dry-run prints the mkdir and the rmdir and changes nothing"

# 7. the folder above is never created -------------------------------------------------
export CSC_MAINT_DOCROOT="$t/no-such-account/example.org"
if run on > "$t/log7" 2>&1; then cat "$t/log7"; fail "created a folder under a missing parent"; fi
[ ! -e "$t/no-such-account" ] || fail "the parent folder was created"
grep -q "does not exist" "$t/log7" || fail "no message for the missing parent"
export CSC_MAINT_DOCROOT="$docroot"
ok "the folder above the document root is never created"

# 8. the www subdomain ----------------------------------------------------------------
created_www="$t/csc/shared/.maintenance_www_docroot_created"
saved="$t/csc/shared/.maintenance_backends"
clean() { rm -rf "$docroot" "$wwwroot" "$created_file" "$created_www" "$saved" "$t/csc/shared/.maintenance_on"; reset_calls; }
backends() { printf '%s\n' "$@" > "$t/backend.list"; }
state_clean() {
  [ ! -e "$docroot" ] && [ ! -e "$wwwroot" ] && [ ! -L "$wwwroot" ] && [ ! -e "$created_file" ] && [ ! -e "$created_www" ] && [ ! -e "$saved" ]
}
clean

# 8a. no www backend before: a link is made, removed again, the backend is deleted
backends "/ apache (default)" "example.org/ http:3000 => OK, listening: PID 1, node"
run on > "$t/log8" 2>&1 || { cat "$t/log8"; fail "on with www"; }
[ -L "$wwwroot" ] && [ "$(readlink -f "$wwwroot")" = "$(readlink -f "$docroot")" ] || fail "the www link was not made"
[ "$(cat "$created_www")" = "$wwwroot" ] || fail "the www link was not recorded"
[ -f "$wwwroot/index.html" ] || fail "the page is not reachable through the www link"
calls | grep -qx "web backend set www.example.org/ --apache" || fail "www not set to Apache"
out=$(run status 2>&1 || true)
grep -q "link made by this script" <<< "$out" && grep -q "www backend:" <<< "$out" && grep -q "before maintenance: none" <<< "$out"   || { echo "$out"; fail "status does not show the www backend and root"; }
reset_calls
run on > /dev/null 2>&1 || fail "second on"
grep -q '^www none$' "$saved" || fail "a second on overwrote the record of the backends"
run off > "$t/log9" 2>&1 || { cat "$t/log9"; fail "off with www"; }
[ ! -L "$wwwroot" ] && [ ! -e "$wwwroot" ] || fail "the www link was not removed"
[ ! -e "$created_www" ] && [ ! -e "$saved" ] || fail "a record stayed"
calls | grep -qx "web backend del www.example.org/" || { calls; fail "no www backend before: it was not deleted"; }
calls | grep -qx "web backend set example.org/ --http --port 3000" || fail "the domain was not set back to its port"
state_clean || fail "state left behind"
ok "www: link made and removed, no previous backend deleted, domain port restored"

# 8b. a www backend with a port before: the same port again; none for the domain
backends "/ apache (default)" "www.example.org/ http:4000 => OK, listening: PID 2, node"
run on > /dev/null 2>&1 || fail "on"
run off > "$t/log10" 2>&1 || { cat "$t/log10"; fail "off"; }
calls | grep -qx "web backend set www.example.org/ --http --port 4000" || { calls; fail "the www port was not restored"; }
calls | grep -qx "web backend del example.org/" || fail "the domain had no backend before: not deleted"
state_clean || fail "state left behind"
ok "www: a previous port is restored, a domain without backend is deleted again"

# 8c. an existing link to our folder, or an existing foreign folder
backends "/ apache (default)"
mkdir "$docroot"; ln -s "$docroot" "$wwwroot"
run on > /dev/null 2>&1 || fail "on with an existing www link"
[ ! -e "$created_www" ] || fail "an existing link was recorded as made by us"
run off > /dev/null 2>&1 || fail "off"
[ -L "$wwwroot" ] || fail "an existing www link was removed"
clean
mkdir "$wwwroot"; echo "their www" > "$wwwroot/index.html"
if run on > "$t/log11" 2>&1; then cat "$t/log11"; fail "wrote to a foreign www folder"; fi
grep -q "not touched" "$t/log11" || fail "no message for the foreign www folder"
[ "$(cat "$wwwroot/index.html")" = "their www" ] || fail "the foreign www folder changed"
[ ! -e "$docroot" ] && [ -z "$(changing_calls)" ] || fail "something was changed before the refusal"
out=$(run status 2>&1 || true)
grep -q "existing folder" <<< "$out" || { echo "$out"; fail "status does not say the www folder existed"; }
rm -rf "$wwwroot"
ok "an existing www link or folder stays; a foreign one stops on before any change"

# 8d. a backend this script cannot restore (a redirect) stops on
clean
backends "/ apache (default)" "www.example.org/ redirect:https://example.org"
if run on > "$t/log12" 2>&1; then cat "$t/log12"; fail "on with a www redirect"; fi
grep -q "cannot restore" "$t/log12" || fail "no message for the backend that cannot be restored"
state_clean && [ -z "$(changing_calls)" ] || fail "something was changed before the refusal"
ok "a backend that cannot be restored stops on before any change"

# 8e. CSC_MAINT_INCLUDE_WWW=0 leaves www alone
clean
backends "/ apache (default)"
CSC_MAINT_INCLUDE_WWW=0 run on > "$t/log13" 2>&1 || { cat "$t/log13"; fail "on without www"; }
[ ! -e "$wwwroot" ] && [ ! -L "$wwwroot" ] || fail "a www link was made"
! calls | grep -q "www.example.org" || fail "www was touched"
CSC_MAINT_INCLUDE_WWW=0 run off > /dev/null 2>&1 || fail "off without www"
! calls | grep -q "www.example.org" || fail "off touched www"
state_clean || fail "state left behind"
ok "CSC_MAINT_INCLUDE_WWW=0 leaves www alone"

# 8f. --dry-run prints everything and changes nothing
clean
backends "/ apache (default)" "www.example.org/ http:4000 => OK, listening"
dry=$(run on --dry-run 2>&1)
state_clean && [ -z "$(changing_calls)" ] || fail "dry-run on changed something"
grep -q "+ ln -s $docroot $wwwroot" <<< "$dry" && grep -q "record the backends" <<< "$dry"   || { echo "$dry"; fail "dry-run on does not print the link and the record"; }
run on > /dev/null 2>&1
reset_calls
dry=$(run off --dry-run 2>&1)
grep -q "web backend set www.example.org/ --http --port 4000" <<< "$dry" && grep -q "+ rm $wwwroot" <<< "$dry"   || { echo "$dry"; fail "dry-run off does not print the www steps"; }
[ -L "$wwwroot" ] && [ -f "$saved" ] && [ -f "$created_www" ] || fail "dry-run off removed something"
[ -z "$(changing_calls)" ] || fail "dry-run off changed a backend"
run off > /dev/null 2>&1
state_clean || fail "state left behind"
ok "--dry-run prints the www steps and changes nothing"

# 9. no record of the www backend: only while the maintenance flag exists
clean
backends "/ apache (default)" "example.org/ http:3000 => OK, listening"
run on > /dev/null 2>&1 || fail "on"
run off > /dev/null 2>&1 || fail "off"
reset_calls
run off > "$t/log14" 2>&1 || { cat "$t/log14"; fail "a second off"; }
! calls | grep -q "www.example.org" || { calls; fail "a second off touched www"; }
grep -q "www left as it is" "$t/log14" || fail "a second off does not say that www stays"
clean
run off > "$t/log15" 2>&1 || fail "off without on"
! calls | grep -q "www.example.org" || fail "off without on and without flag touched www"
# an off without a record while the flag exists falls back to the frontend port
clean
date -Iseconds > "$t/csc/shared/.maintenance_on"
run off > "$t/log16" 2>&1 || { cat "$t/log16"; fail "off with flag, no record"; }
calls | grep -qx "web backend set www.example.org/ --http --port 3000" || { calls; fail "no fallback to the frontend port"; }
calls | grep -qx "web backend set example.org/ --http --port 3000" || fail "the domain was not set to the frontend port"
clean
ok "without a record www is changed only while the flag exists"

echo "all maintenance tests passed"
