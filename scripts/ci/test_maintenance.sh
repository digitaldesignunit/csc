#!/usr/bin/env bash
#
# Test of uberspaceconfig/deployment/csc_maintenance.sh (Linux).
#
# `uberspace` is a stub that records its calls. Checks: a missing document root
# is created by `on` and removed again by `off` (the script records that it made
# it), an existing folder and its files stay, files of another folder are never
# touched, a folder that got other files meanwhile stays, foreign files are not
# overwritten, --dry-run changes nothing and prints the mkdir and rmdir, the
# parent folder is never created, status says who made the folder.
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
STUB
chmod +x "$t/bin/uberspace"
export PATH="$t/bin:$PATH" CSC_HOME="$t/csc" CSC_MAINT_DOMAIN="example.org" CSC_MAINT_PORT=3000
export CSC_MAINT_TEXT="$t/none.txt" USER="${USER:-tester}"
docroot="$t/virtual/example.org"           # the folder of the domain, under the account's folder
export CSC_MAINT_DOCROOT="$docroot"
other="$t/virtual/html"                    # ~/html: the root of every other domain
mkdir "$other"
echo "keep me" > "$other/index.html"
printf 'Require all granted\n' > "$other/.htaccess"
before=$(cd "$other" && sha256sum index.html .htaccess)

run() { bash "$script" "$@"; }
calls() { cat "$t/uberspace.calls" 2>/dev/null || true; }
reset_calls() { rm -f "$t/uberspace.calls"; }
created_file="$t/csc/shared/.maintenance_docroot_created"

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
[ -z "$(calls)" ] || fail "dry-run called uberspace"
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

echo "all maintenance tests passed"
