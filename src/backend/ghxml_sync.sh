#!/usr/bin/env bash

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Configuration (overridable via environment variables)
GH_REPO_PATH="${GH_REPO_PATH:-/home/ddu/csc/_gh_repo}"
GH_REPO_BRANCH="${GH_REPO_BRANCH:-main}"
GH_XML_SRC_SUBDIR="${GH_XML_SRC_SUBDIR:-grasshopper_userobjects_xml}"
GH_XML_CACHE_DIR="${GH_XML_CACHE_DIR:-/home/ddu/csc/backend/static/ghxml}"
LOG_DIR="${LOG_DIR:-/home/ddu/csc/backend/logs}"
LOCK_FILE="${LOCK_FILE:-/home/ddu/csc/backend/.ghxml_sync.lock}"

mkdir -p "${LOG_DIR}" || true
mkdir -p "${GH_XML_CACHE_DIR}" || true

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "[$(date -Iseconds)] Another ghxml_sync is running; exiting." >&2
  exit 0
fi

log() {
  echo "[$(date -Iseconds)] $*"
}

fail() {
  echo "[$(date -Iseconds)] ERROR: $*" >&2
  exit 1
}

# Read GitHub repo URL and token from environment variables
GH_REPO_URL="${GITHUB_REPO_URL:-}"
GH_REPO_TOKEN="${GITHUB_CSC_GH_TOKEN:-}"

if [ -z "${GH_REPO_URL}" ] || [ -z "${GH_REPO_TOKEN}" ]; then
  fail "GITHUB_REPO_URL or GITHUB_CSC_GH_TOKEN environment variable is not set"
fi

log "Starting GH XML sync"

# Prepare authenticated URL
AUTH_URL=$(echo "${GH_REPO_URL}" | sed "s|https://github.com/|https://${GH_REPO_TOKEN}@github.com/|")

# Clone repo if it doesn't exist (with sparse checkout for XML folder only)
if [ ! -d "${GH_REPO_PATH}/.git" ]; then
  log "Repo not found at ${GH_REPO_PATH}. Cloning repository (XML folder only)..."
  REPO_DIR=$(dirname "${GH_REPO_PATH}")
  mkdir -p "${REPO_DIR}" || fail "Failed to create repo directory: ${REPO_DIR}"
  
  # Clone with minimal depth and no checkout
  git clone --depth=1 --branch "${GH_REPO_BRANCH}" --no-checkout "${AUTH_URL}" "${GH_REPO_PATH}" || fail "git clone failed"
  
  # Enable sparse checkout
  git -C "${GH_REPO_PATH}" sparse-checkout init --cone || fail "sparse-checkout init failed"
  
  # Configure sparse checkout to only include the XML directory
  git -C "${GH_REPO_PATH}" sparse-checkout set "${GH_XML_SRC_SUBDIR}" || fail "sparse-checkout set failed"
  
  # Checkout only the sparse paths
  git -C "${GH_REPO_PATH}" checkout "${GH_REPO_BRANCH}" || fail "git checkout failed"
  
  log "Repository cloned successfully (XML folder only)"
else
  # Update existing sparse checkout if needed
  git -C "${GH_REPO_PATH}" remote set-url origin "${AUTH_URL}" || true
  
  # Ensure sparse checkout is configured
  if ! git -C "${GH_REPO_PATH}" sparse-checkout list >/dev/null 2>&1; then
    log "Enabling sparse checkout..."
    git -C "${GH_REPO_PATH}" sparse-checkout init --cone || fail "sparse-checkout init failed"
    git -C "${GH_REPO_PATH}" sparse-checkout set "${GH_XML_SRC_SUBDIR}" || fail "sparse-checkout set failed"
  fi
  
  # Fetch latest changes
  git -C "${GH_REPO_PATH}" fetch --depth=1 origin "${GH_REPO_BRANCH}" || fail "git fetch failed"
  
  # Reset to latest (will only affect sparse checkout paths)
  git -C "${GH_REPO_PATH}" reset --hard "origin/${GH_REPO_BRANCH}" || fail "git reset --hard failed"
  
  log "Repository updated (XML folder only)"
fi

SRC_DIR="${GH_REPO_PATH}/${GH_XML_SRC_SUBDIR}"
if [ ! -d "${SRC_DIR}" ]; then
  fail "Source XML directory not found: ${SRC_DIR}"
fi

# Mirror files to cache directory
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --chmod=Du=rwx,Dg=rx,Do=rx,Fu=rw,Fg=r,Fo=r \
    --exclude ".git/" \
    "${SRC_DIR}/" "${GH_XML_CACHE_DIR}/" || fail "rsync failed"
else
  # Fallback without rsync: simple copy (no deletion of removed files)
  find "${SRC_DIR}" -type f -name '*.xml' | while read -r f; do
    rel="${f#${SRC_DIR}/}"
    dst_dir="${GH_XML_CACHE_DIR}/$(dirname "$rel")"
    mkdir -p "$dst_dir"
    tmp="${dst_dir}/.$(basename "$rel").tmp"
    cp "$f" "$tmp" && mv "$tmp" "${dst_dir}/$(basename "$rel")"
  done
fi

COUNT=$(find "${GH_XML_CACHE_DIR}" -maxdepth 1 -type f -name '*.xml' | wc -l | awk '{print $1}')
log "Sync complete. Cached XML files: ${COUNT}"

exit 0


