#!/usr/bin/env bash
#
# Test of the Grasshopper bundle of scripts/ci/package_release.sh: it ships the
# interface file DDU_CSC_GrasshopperInterface_<x>.gh with the highest x not
# newer than the release version (and no older one next to it), the examples
# stay, and a release without a fitting interface file fails with a message.
#
#   bash scripts/ci/test_package_gh.sh
#
# Needs zip and unzip.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
t="$(mktemp -d)"
trap 'rm -rf "$t"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "ok   $*"; }

# a small repository: the script itself and the files the gh bundle takes
mkdir -p "$t/scripts/ci" "$t/grasshopper_userobjects" "$t/grasshopper_release" "$t/grasshopper_lib/csc_gh"
cp "$root/scripts/ci/package_release.sh" "$t/scripts/ci/"
: > "$t/grasshopper_userobjects/DDU_CSC_Actor.ghuser"
: > "$t/grasshopper_lib/csc_gh/__init__.py"
echo readme > "$t/README.md"; echo licence > "$t/LICENSE"
for v in 0.6.0.0 0.6.1.0 0.7.0.0 0.9.0.0 0.10.0.0; do
  echo "$v" > "$t/grasshopper_release/DDU_CSC_GrasshopperInterface_$v.gh"
done
for n in 01 02; do
  echo "example $n" > "$t/grasshopper_release/DDU_CSC_GrasshopperInterface_Example_$n.gh"
done

# the interface files inside the bundle of a version, one per line
shipped() {
  local out="$t/out-$1"
  rm -rf "$out"
  bash "$t/scripts/ci/package_release.sh" gh "$1" "$out" >/dev/null 2>"$t/err" || return 1
  unzip -Z1 "$out/csc-gh-interface-$1.zip" \
    | sed -n 's#.*/DDU_CSC_GrasshopperInterface_\(.*\)\.gh$#\1#p' | grep -v '^Example_' | sort
}

expect() {   # <release version> <interface version that ships>
  local got
  got="$(shipped "$1")" || fail "$1: packaging failed: $(cat "$t/err")"
  [ "$got" = "$2" ] || fail "$1 ships '$got', not '$2'"
  ok "release $1 ships interface $2 and no other"
}

expect 0.6.1.0 0.6.1.0        # the file of the release itself, not 0.6.0.0
expect 0.6.2.0 0.6.1.0        # no file of its own: the newest one before it
expect 0.6.0.5 0.6.0.0
expect 0.8.0.0 0.7.0.0        # a newer file (0.9, 0.10) is never shipped early
expect 0.9.5.0 0.9.0.0
expect 0.10.0.0 0.10.0.0      # 0.10 is newer than 0.9 (version order, not text order)

# the examples are still in the bundle
unzip -Z1 "$t/out-0.6.1.0/csc-gh-interface-0.6.1.0.zip" | grep -q 'Example_01.gh$' \
  || fail 'the examples are missing from the bundle'
ok 'the examples are in the bundle'

# no file that fits: a clear message and no bundle
if shipped 0.5.0.0 >/dev/null 2>&1; then fail 'a release older than every interface file was packaged'; fi
grep -q 'no grasshopper_release/DDU_CSC_GrasshopperInterface_<x>.gh with x <= 0.5.0.0' "$t/err" \
  || fail "the message does not say what is missing: $(cat "$t/err")"
[ ! -e "$t/out-0.5.0.0/csc-gh-interface-0.5.0.0.zip" ] || fail 'a bundle was written without an interface file'
ok 'a release without a fitting interface file fails with a message'

# only examples: the same
rm "$t"/grasshopper_release/DDU_CSC_GrasshopperInterface_0*.gh
if shipped 0.6.1.0 >/dev/null 2>&1; then fail 'a release without any interface file was packaged'; fi
ok 'a folder with only the examples fails too'
echo 'all package tests passed'
