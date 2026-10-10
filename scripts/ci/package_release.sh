#!/usr/bin/env bash
#
# Package one part of a CSC release into <outdir>. Used by the release workflow
# and by scripts/ci/test_release_deploy.sh.
#
#   package_release.sh backend  <version> <outdir>  -> csc-backend-<version>.tar.gz
#   package_release.sh frontend <version> <outdir>  -> csc-frontend-<version>.zip
#                                                     (needs `npm run build` first)
#   package_release.sh gh       <version> <outdir>  -> csc-gh-interface-<version>.zip
#
# backend tarball:  backend/ (src/backend + static/ghxml from the XML exports),
#                   deploy/ (server scripts and the maintenance page), VERSION
# frontend zip:     csc-frontend-standalone/ (Next standalone + static + public)
# gh zip:           "CSC Grasshopper Interface <version>"/ (UserObjects, examples,
#                   the library folder csc_gh, README, LICENSE)

set -euo pipefail

part="${1:?part: backend | frontend | gh}"
version="${2:?version}"
outdir="$(mkdir -p "${3:?outdir}" && cd "$3" && pwd)"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

case "$part" in
  backend)
    mkdir -p "$stage/backend" "$stage/deploy"
    # the server's copy of the backend: no caches, logs or local settings
    tar -C "$root/src/backend" \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='logs' \
      --exclude='*.env' --exclude='dev.env*' --exclude='static/ghxml' \
      -cf - . | tar -C "$stage/backend" -xf -
    mkdir -p "$stage/backend/static/ghxml"
    cp "$root"/grasshopper_userobjects_xml/*.xml "$stage/backend/static/ghxml/"
    cp "$root"/uberspaceconfig/deployment/csc_release_deploy.sh \
       "$root"/uberspaceconfig/deployment/csc_deploy_gate.sh \
       "$root"/uberspaceconfig/deployment/csc_maintenance.sh "$stage/deploy/"
    # the page and the .htaccess of the maintenance mode (decision 8.137)
    mkdir -p "$stage/deploy/maintenance"
    cp "$root"/uberspaceconfig/html/maintenance/* "$stage/deploy/maintenance/"
    chmod +x "$stage"/deploy/*.sh
    printf '%s\n' "$version" > "$stage/VERSION"
    grep -q "^CSC_VERSION = '$version'$" "$stage/backend/csc_version.py" \
      || { echo "csc_version.py does not say $version" >&2; exit 1; }
    tar -C "$stage" -czf "$outdir/csc-backend-$version.tar.gz" backend deploy VERSION
    ;;
  frontend)
    fe="$root/src/frontend"
    [ -f "$fe/.next/standalone/server.js" ] \
      || { echo "no .next/standalone/server.js: run npm run build first" >&2; exit 1; }
    bundle="$stage/csc-frontend-standalone"
    mkdir -p "$bundle/.next"
    cp -a "$fe/.next/standalone/." "$bundle/"
    cp -a "$fe/.next/static" "$bundle/.next/static"
    # the contents of public/, into the folder Next's tracing may have made
    # already (the GH page reads public/gh-interface at run time): copying the
    # folder itself nested it as public/public/ in 0.6.0.0 and 0.6.0.1
    if [ -d "$fe/public" ]; then
      mkdir -p "$bundle/public"
      cp -a "$fe/public/." "$bundle/public/"
    fi
    [ -f "$bundle/public/logo/ddu_logo_black.png" ] \
      || { echo "bundle has no public/logo/ddu_logo_black.png" >&2; exit 1; }
    [ ! -e "$bundle/public/public" ] \
      || { echo "bundle has a nested public/public" >&2; exit 1; }
    cp -a "$fe/scripts/start-standalone.cjs" "$bundle/start-standalone.cjs"
    # secrets come from ~/csc/shared/frontend on the server, never from the build
    rm -f "$bundle"/.env*
    (cd "$stage" && zip -qr "$outdir/csc-frontend-$version.zip" csc-frontend-standalone)
    ;;
  gh)
    name="CSC Grasshopper Interface $version"
    mkdir -p "$stage/$name/UserObjects"
    cp "$root"/grasshopper_userobjects/*.ghuser "$stage/$name/UserObjects/"
    cp "$root"/grasshopper_release/DDU_CSC_GrasshopperInterface_Example_*.gh "$stage/$name/"
    # the shared library (decision 8.111): a first install by hand copies this
    # folder to %APPDATA%\McNeel\Rhinoceros\8.0\scripts\csc_gh; CSC_Update
    # installs and updates it from the server afterwards
    mkdir -p "$stage/$name/csc_gh"
    cp "$root"/grasshopper_lib/csc_gh/*.py "$stage/$name/csc_gh/"
    cp "$root/README.md" "$root/LICENSE" "$stage/$name/"
    (cd "$stage" && zip -qr "$outdir/csc-gh-interface-$version.zip" "$name")
    ;;
  *)
    echo "unknown part: $part" >&2; exit 2 ;;
esac
echo "packaged $part $version into $outdir"
