#!/bin/bash
# Deploy a CI-built Next.js standalone frontend release to Uberspace.
# Does NOT run `next build` on the host (avoids glibc / SWC issues).
#
# Prerequisites:
#   - GITHUB_REPO_URL  e.g. https://github.com/org/csc
#   - GITHUB_CSC_DEPLOY_TOKEN or GITHUB_CSC_GH_TOKEN (repo read + release assets)
#   - Supervisor service named `frontend` running `node server.js`
#     (see etc/services.d/frontend_ci.ini.example)
#   - Existing ~/csc/frontend/.env preserved across deploys
#
# Usage:
#   bash csc_deploy_frontend_ci.sh                  # latest frontend-* release
#   bash csc_deploy_frontend_ci.sh frontend-0.5.0.1  # specific tag

set -euo pipefail

REQUESTED_TAG="${1:-}"
DEPLOY_DIR="csc_frontend_ci_deploy"
TARGET1="frontend"
ASSET_PREFIX="csc-frontend-standalone-"
TAG_PREFIX="frontend-"

echo "-----------------------------------------------------------------"
echo "----------- CSC FRONTEND CI DEPLOYMENT SCRIPT -------------------"
echo "-----------------------------------------------------------------"
echo ""

# ---- resolve GitHub auth + repo ------------------------------------------------
TOKEN="${GITHUB_CSC_DEPLOY_TOKEN:-${GITHUB_CSC_GH_TOKEN:-}}"
if [ -z "${TOKEN}" ]; then
  echo "ERROR: Set GITHUB_CSC_DEPLOY_TOKEN or GITHUB_CSC_GH_TOKEN"
  exit 1
fi

if [ -z "${GITHUB_REPO_URL:-}" ]; then
  echo "ERROR: Set GITHUB_REPO_URL (e.g. https://github.com/org/repo)"
  exit 1
fi

# Accept https://github.com/org/repo(.git) or git@github.com:org/repo.git
REPO_PATH=$(echo "$GITHUB_REPO_URL" | sed -E 's#^https://github.com/##; s#^git@github.com:##; s#\.git$##')
API_BASE="https://api.github.com/repos/${REPO_PATH}"

echo "-----------------------------------------------------------------"
echo "------------------------ INITIALIZATION -------------------------"
echo "-----------------------------------------------------------------"
echo "INIT: Repository ${REPO_PATH}"
echo "INIT: Target directory ${TARGET1}/ (run this script from ~/csc)"

if [ -d "$DEPLOY_DIR" ]; then
  echo "INIT: Removing existing ${DEPLOY_DIR}"
  rm -rf "$DEPLOY_DIR"
fi
mkdir "$DEPLOY_DIR"
echo "-----------------------------------------------------------------"

# ---- pick release tag + asset --------------------------------------------------
echo "----------------------- RESOLVE RELEASE -------------------------"
echo "-----------------------------------------------------------------"

RELEASE_JSON=$(mktemp)
ASSET_META=$(mktemp)

auth_curl() {
  curl -fsSL \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "$@"
}

if [ -n "$REQUESTED_TAG" ]; then
  echo "GIT: Fetching release for tag ${REQUESTED_TAG}..."
  auth_curl "${API_BASE}/releases/tags/${REQUESTED_TAG}" > "$RELEASE_JSON"
  TAG_NAME="$REQUESTED_TAG"
else
  echo "GIT: Finding latest ${TAG_PREFIX}* release..."
  # List releases and pick the newest tag starting with frontend-
  auth_curl "${API_BASE}/releases?per_page=30" > "$RELEASE_JSON"
  TAG_NAME=$(python3 - "$RELEASE_JSON" "$TAG_PREFIX" <<'PY'
import json, sys
path, prefix = sys.argv[1], sys.argv[2]
releases = json.load(open(path, encoding="utf-8"))
for rel in releases:
    tag = rel.get("tag_name") or ""
    if tag.startswith(prefix) and not rel.get("draft") and not rel.get("prerelease"):
        print(tag)
        break
else:
    sys.exit("No published release found with tag prefix " + prefix)
PY
)
  echo "GIT: Selected tag ${TAG_NAME}"
  auth_curl "${API_BASE}/releases/tags/${TAG_NAME}" > "$RELEASE_JSON"
fi

python3 - "$RELEASE_JSON" "$ASSET_PREFIX" "$ASSET_META" <<'PY'
import json, sys
path, prefix, out = sys.argv[1], sys.argv[2], sys.argv[3]
rel = json.load(open(path, encoding="utf-8"))
assets = rel.get("assets") or []
matches = [a for a in assets if (a.get("name") or "").startswith(prefix) and a["name"].endswith(".zip")]
if not matches:
    sys.exit("No asset matching %s*.zip on release %s" % (prefix, rel.get("tag_name")))
asset = matches[0]
with open(out, "w", encoding="utf-8") as f:
    f.write(str(asset["id"]) + "\n")
    f.write(asset["name"] + "\n")
print("asset_name=%s" % asset["name"])
print("asset_id=%s" % asset["id"])
PY

ASSET_ID=$(sed -n '1p' "$ASSET_META")
ASSET_NAME=$(sed -n '2p' "$ASSET_META")
ZIP_PATH="${DEPLOY_DIR}/${ASSET_NAME}"

echo "GIT: Downloading ${ASSET_NAME} (asset id ${ASSET_ID})..."
curl -fsSL -L \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/octet-stream" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -o "$ZIP_PATH" \
  "${API_BASE}/releases/assets/${ASSET_ID}"

echo "GIT: Download complete ($(du -h "$ZIP_PATH" | cut -f1))"
echo "-----------------------------------------------------------------"

# ---- extract -------------------------------------------------------------------
echo "------------------------ EXTRACT BUNDLE -------------------------"
echo "-----------------------------------------------------------------"
EXTRACT_DIR="${DEPLOY_DIR}/extracted"
mkdir -p "$EXTRACT_DIR"
unzip -q "$ZIP_PATH" -d "$EXTRACT_DIR"

# Zip contains a single top-level folder (csc-frontend-standalone/)
BUNDLE_DIR=$(find "$EXTRACT_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)
if [ -z "$BUNDLE_DIR" ] || [ ! -f "$BUNDLE_DIR/server.js" ]; then
  echo "ERROR: standalone bundle missing server.js under ${EXTRACT_DIR}"
  find "$EXTRACT_DIR" -maxdepth 3 -type f | head -n 50
  exit 1
fi
echo "I/O: Bundle root ${BUNDLE_DIR}"
echo "-----------------------------------------------------------------"

# ---- stop service, sync files, start -------------------------------------------
echo "-------------------------- PROCESSES ----------------------------"
echo "-----------------------------------------------------------------"
echo "SVR: Stopping frontend..."
supervisorctl stop frontend || true
echo "-----------------------------------------------------------------"

echo "------------------------ UPDATE FILES ---------------------------"
echo "-----------------------------------------------------------------"
mkdir -p "${TARGET1}"
echo "I/O: Syncing standalone tree to ${TARGET1}/ (preserving .env*)..."
# `.env*` is never overwritten or deleted: runtime secrets live only on the server.
rsync -a --delete \
  --exclude='.env*' \
  --exclude='node_modules/.cache' \
  "${BUNDLE_DIR}/" "${TARGET1}/"

if [ ! -f "${TARGET1}/server.js" ]; then
  echo "ERROR: ${TARGET1}/server.js missing after sync"
  exit 1
fi

if ! ls "${TARGET1}"/.env* >/dev/null 2>&1; then
  echo "WARNING: no .env file in ${TARGET1}/ — /api/auth/* will return 500."
  echo "WARNING: create ${TARGET1}/.env with NEXTAUTH_SECRET, NEXTAUTH_URL, MONGODB_*, FASTAPI_URL."
fi
echo "-----------------------------------------------------------------"

echo "------------------------- PROCESSES -----------------------------"
echo "-----------------------------------------------------------------"
echo "SVR: Starting frontend..."
supervisorctl start frontend
echo "-----------------------------------------------------------------"

# ---- cleanup -------------------------------------------------------------------
echo "-------------------------- CLEAN UP -----------------------------"
echo "-----------------------------------------------------------------"
rm -f "$RELEASE_JSON" "$ASSET_META"
rm -rf "$DEPLOY_DIR"
echo "DEPLOY: Removed ${DEPLOY_DIR}"
echo "-----------------------------------------------------------------"

echo "--------- CSC - FRONTEND CI DEPLOYMENT COMPLETE -----------------"
echo "-----------------------------------------------------------------"
echo "Tag:   ${TAG_NAME}"
echo "Asset: ${ASSET_NAME}"
echo "-----------------------------------------------------------------"
echo "------------------------ PROCESS  STATUS ------------------------"
echo "-----------------------------------------------------------------"
supervisorctl status
echo "-----------------------------------------------------------------"
echo "--------------------------- THE END -----------------------------"
echo "-----------------------------------------------------------------"
