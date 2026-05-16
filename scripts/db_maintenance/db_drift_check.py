"""Drift check: local JSON dumps vs live MongoDB.

Compares the local ``mongodb_collections_local/*.json`` snapshots against the
live MongoDB collections (``components``, ``components_archive``,
``component_identities``, ``component_snapshots``) and reports any drift:

* documents present only in local (deleted on live since the dump),
* documents present only on live (added since the dump),
* documents in both but with differing content (per top-level field).

Read-only: never writes anything to either source. Outputs a log file and a
machine-readable JSON summary under ``logs/``.

Usage
-----
::

    conda run -n csc python scripts/db_maintenance/db_drift_check.py

Optional flags:

* ``--local-dir <path>``      override the local dumps directory
                              (default: ``mongodb_collections_local/``)
* ``--collections-prefix``    override the local-file prefix
                              (default: ``csc.``)
* ``--verbose``               echo per-doc diffs to console too

Mongo connection: reads ``MONGO_URI`` from env, falling back to
``scripts/config/dbconfig.json`` (same pattern as the other db_maintenance
scripts).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from pymongo import MongoClient
from pymongo.errors import PyMongoError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCAL_DIR = REPO_ROOT / "mongodb_collections_local"
DEFAULT_FILE_PREFIX = "csc."
LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "db_drift_check.log"
JSON_REPORT = LOG_DIR / "db_drift_check.json"

COLLECTIONS = [
    "components",
    "components_archive",
    "component_identities",
    "component_snapshots",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("db_drift_check")
logger.setLevel(logging.INFO)
logger.handlers.clear()
_fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_fh)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_sh)


# ---------------------------------------------------------------------------
# Mongo connection (matches the other db_maintenance scripts)
# ---------------------------------------------------------------------------
def load_mongo_config() -> Dict[str, str]:
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        return {"uri": mongo_uri}

    candidates = [
        REPO_ROOT / "scripts" / "config" / "dbconfig.json",
        Path("..") / "config" / "dbconfig.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        with candidate.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        server = cfg.get("server")
        db = cfg.get("db")
        user = cfg.get("user")
        pwd = cfg.get("pwd")
        if not (server and db and user and pwd):
            raise RuntimeError(
                f"{candidate} incomplete (need server/db/user/pwd)"
            )
        return {"uri": f"mongodb+srv://{user}:{pwd}@{server}/{db}"}

    raise RuntimeError(
        "No Mongo config (set MONGO_URI or "
        "scripts/config/dbconfig.json with server/db/user/pwd)."
    )


def connect():
    cfg = load_mongo_config()
    client = MongoClient(cfg["uri"], serverSelectionTimeoutMS=10000)
    db = client.get_default_database()
    if db is None:
        db_name = cfg["uri"].split("/")[-1].split("?")[0]
        db = client[db_name]
    db.list_collection_names()
    return client, db


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_local_collection(
    local_dir: Path, prefix: str, collection: str
) -> Dict[str, Dict[str, Any]]:
    path = local_dir / f"{prefix}{collection}.json"
    if not path.exists():
        raise FileNotFoundError(f"Local dump not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array of documents")
    indexed: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        _id = row.get("_id")
        if _id is None:
            raise ValueError(f"Row without _id in {path}: {row!r}")
        indexed[str(_id)] = row
    return indexed


def load_live_collection(db, collection: str) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for row in db[collection].find({}):
        _id = row.get("_id")
        if _id is None:
            raise ValueError(f"Live row without _id in {collection}")
        indexed[str(_id)] = row
    return indexed


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _summarize_complex(value: Any) -> str:
    if isinstance(value, dict):
        return f"<dict, {len(value)} keys>"
    if isinstance(value, list):
        return f"<list, {len(value)} items>"
    return f"<{type(value).__name__}>"


def diff_doc(
    local: Dict[str, Any], live: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Return a list of top-level field differences between two docs."""
    differences: List[Dict[str, Any]] = []
    all_keys = set(local.keys()) | set(live.keys())
    for key in sorted(all_keys):
        has_local = key in local
        has_live = key in live
        if not has_local and has_live:
            value = live[key]
            differences.append({
                "field": key,
                "kind": "added_in_live",
                "live": value if isinstance(value, _SCALAR_TYPES)
                else _summarize_complex(value),
            })
            continue
        if has_local and not has_live:
            value = local[key]
            differences.append({
                "field": key,
                "kind": "removed_in_live",
                "local": value if isinstance(value, _SCALAR_TYPES)
                else _summarize_complex(value),
            })
            continue
        lval = local[key]
        rval = live[key]
        if lval == rval:
            continue
        if isinstance(lval, _SCALAR_TYPES) and isinstance(rval, _SCALAR_TYPES):
            differences.append({
                "field": key,
                "kind": "changed_scalar",
                "local": lval,
                "live": rval,
            })
        else:
            differences.append({
                "field": key,
                "kind": "changed_complex",
                "local": _summarize_complex(lval),
                "live": _summarize_complex(rval),
            })
    return differences


def compare_collection(
    name: str,
    local: Dict[str, Dict[str, Any]],
    live: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    local_ids = set(local.keys())
    live_ids = set(live.keys())

    only_local = sorted(local_ids - live_ids)
    only_live = sorted(live_ids - local_ids)
    shared = local_ids & live_ids

    modified: List[Dict[str, Any]] = []
    for _id in sorted(shared):
        diffs = diff_doc(local[_id], live[_id])
        if diffs:
            modified.append({"_id": _id, "diffs": diffs})

    return {
        "collection": name,
        "counts": {
            "local": len(local),
            "live": len(live),
            "shared": len(shared),
            "only_in_local": len(only_local),
            "only_in_live": len(only_live),
            "modified": len(modified),
        },
        "only_in_local": only_local,
        "only_in_live": only_live,
        "modified": modified,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def _fmt_diff_line(d: Dict[str, Any]) -> str:
    field = d["field"]
    kind = d["kind"]
    if kind == "changed_scalar":
        return f"      {field}: {d['local']!r} -> {d['live']!r}"
    if kind == "changed_complex":
        return f"      {field}: {d['local']} -> {d['live']} (complex)"
    if kind == "added_in_live":
        live = d.get("live", "?")
        return f"      {field}: <missing locally> -> {live!r}"
    if kind == "removed_in_live":
        local = d.get("local", "?")
        return f"      {field}: {local!r} -> <missing on live>"
    return f"      {field}: {kind}"


def render_console_summary(
    results: List[Dict[str, Any]], verbose: bool
) -> None:
    logger.info("")
    logger.info("=" * 72)
    logger.info("DRIFT CHECK SUMMARY")
    logger.info("=" * 72)
    for r in results:
        c = r["counts"]
        logger.info("")
        logger.info(f"Collection: {r['collection']}")
        logger.info(
            f"  local={c['local']}  live={c['live']}  shared={c['shared']}"
        )
        logger.info(
            f"  only_in_local={c['only_in_local']}  "
            f"only_in_live={c['only_in_live']}  "
            f"modified={c['modified']}"
        )
        if r["only_in_local"]:
            logger.info("  -- only in local --")
            for _id in r["only_in_local"][:20]:
                logger.info(f"      {_id}")
            if len(r["only_in_local"]) > 20:
                logger.info(
                    f"      ... and {len(r['only_in_local']) - 20} more"
                )
        if r["only_in_live"]:
            logger.info("  -- only on live --")
            for _id in r["only_in_live"][:20]:
                logger.info(f"      {_id}")
            if len(r["only_in_live"]) > 20:
                logger.info(
                    f"      ... and {len(r['only_in_live']) - 20} more"
                )
        if r["modified"]:
            logger.info("  -- modified docs --")
            shown = r["modified"] if verbose else r["modified"][:20]
            for entry in shown:
                logger.info(f"    {entry['_id']}")
                for d in entry["diffs"]:
                    logger.info(_fmt_diff_line(d))
            if not verbose and len(r["modified"]) > 20:
                logger.info(
                    f"    ... and {len(r['modified']) - 20} more "
                    "(use --verbose to dump all)"
                )

    logger.info("")
    logger.info("=" * 72)
    has_drift = any(
        r["counts"]["only_in_local"]
        or r["counts"]["only_in_live"]
        or r["counts"]["modified"]
        for r in results
    )
    if has_drift:
        logger.info("Result: DRIFT detected.")
    else:
        logger.info("Result: no drift; local dumps match live DB exactly.")
    logger.info(f"Log:  {LOG_FILE}")
    logger.info(f"JSON: {JSON_REPORT}")


def write_json_report(results: List[Dict[str, Any]]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "collections": results,
    }
    JSON_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with JSON_REPORT.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False, default=str)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run(local_dir: Path, prefix: str, verbose: bool) -> int:
    logger.info(f"Loading local dumps from: {local_dir}")
    local_collections: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for name in COLLECTIONS:
        local_collections[name] = load_local_collection(
            local_dir, prefix, name
        )
        logger.info(
            f"  loaded local {name}: {len(local_collections[name])} docs"
        )

    logger.info("Connecting to live MongoDB...")
    try:
        client, db = connect()
    except PyMongoError as exc:
        logger.error(f"Mongo connection failed: {exc}")
        return 1
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1

    try:
        live_collections: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for name in COLLECTIONS:
            live_collections[name] = load_live_collection(db, name)
            logger.info(
                f"  loaded live  {name}: {len(live_collections[name])} docs"
            )

        results: List[Dict[str, Any]] = []
        for name in COLLECTIONS:
            r = compare_collection(
                name, local_collections[name], live_collections[name]
            )
            results.append(r)

        render_console_summary(results, verbose=verbose)
        write_json_report(results)
    finally:
        client.close()

    has_drift = any(
        r["counts"]["only_in_local"]
        or r["counts"]["only_in_live"]
        or r["counts"]["modified"]
        for r in results
    )
    return 0 if not has_drift else 2


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compare local mongodb_collections_local/*.json dumps against "
            "the live MongoDB collections (read-only drift check)."
        )
    )
    ap.add_argument(
        "--local-dir",
        type=Path,
        default=DEFAULT_LOCAL_DIR,
        help=f"Local dumps directory (default: {DEFAULT_LOCAL_DIR})",
    )
    ap.add_argument(
        "--collections-prefix",
        type=str,
        default=DEFAULT_FILE_PREFIX,
        help=(
            "Filename prefix in the local dumps directory "
            f"(default: '{DEFAULT_FILE_PREFIX}')"
        ),
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Dump every modified doc's diff to the console "
            "(not just first 20)"
        ),
    )
    args = ap.parse_args()
    return run(
        local_dir=args.local_dir,
        prefix=args.collections_prefix,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    sys.exit(main())
