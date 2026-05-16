"""M1 follow-up: backfill `manufactured_precision = "unknown"` for legacy
rows where both `manufactured_precision` and `manufactured_at` are null.

Context
-------
After `m1_phase1_completion.py` ran for the 49 live + 1 archive corian
panels, the remaining legacy catalog still carries ~642 rows with
`manufactured_precision: null` and `manufactured_at: null`. These rows are
semantically "unknown manufacturing date", but the precision field is left
as `null` rather than the explicit `"unknown"` value the legacy schema
allows. Migrating that ambiguity into the new `ComponentIdentity` model is
undesirable; this script normalizes it before M3 runs.

Rule
----
For every legacy row in `components` and `components_archive`:

* `manufactured_precision is None` **and** `manufactured_at is None`
  -> set `manufactured_precision = "unknown"`.
* `manufactured_precision is None` **and** `manufactured_at is not None`
  -> **do not touch**. This is a data anomaly (precision claim missing for a
  known timestamp). Surface for manual review.
* `manufactured_precision is not None` -> leave alone.

Safety
------
* Dry-run by default. Use `--apply` to commit.
* Refuses to `--apply` when any anomaly rows exist; use
  `--force-anomalies` to proceed regardless (still does not touch them).
* Idempotent: re-running after a clean apply finds 0 candidates and does
  nothing.

Mongo connection: `MONGO_URI` env or `scripts/config/dbconfig.json`.

Usage
-----
::

    conda run -n csc python \\
        scripts/db_maintenance/m1_phase1_precision_backfill.py
    conda run -n csc python \\
        scripts/db_maintenance/m1_phase1_precision_backfill.py --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "m1_phase1_precision_backfill.log"

COLLECTIONS = ["components", "components_archive"]
UNKNOWN_VALUE = "unknown"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("m1_phase1_precision_backfill")
logger.setLevel(logging.INFO)
logger.handlers.clear()
_fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_fh)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_sh)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Mongo connection
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
# Classification
# ---------------------------------------------------------------------------
def classify_collection(
    db, collection: str
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Return (safe_ids, anomaly_rows) for one collection.

    * `safe_ids`: docs where precision is null AND manufactured_at is null.
    * `anomaly_rows`: docs where precision is null but manufactured_at is
      a non-null value; each entry has the row's `_id` and the offending
      `manufactured_at` value.
    """
    cursor = db[collection].find(
        {"manufactured_precision": None},
        projection={"_id": 1, "manufactured_at": 1},
    )
    safe: List[str] = []
    anomalies: List[Dict[str, Any]] = []
    for row in cursor:
        if row.get("manufactured_at") is None:
            safe.append(str(row["_id"]))
        else:
            anomalies.append({
                "_id": str(row["_id"]),
                "manufactured_at": row.get("manufactured_at"),
            })
    return safe, anomalies


def scan(db) -> Dict[str, Dict[str, Any]]:
    """Return classification per collection."""
    out: Dict[str, Dict[str, Any]] = {}
    for collection in COLLECTIONS:
        safe, anomalies = classify_collection(db, collection)
        out[collection] = {"safe": safe, "anomalies": anomalies}
    return out


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def report(classification: Dict[str, Dict[str, Any]]) -> None:
    logger.info("")
    logger.info("=" * 72)
    logger.info("CLASSIFICATION")
    logger.info("=" * 72)
    total_safe = 0
    total_anom = 0
    for collection, info in classification.items():
        n_safe = len(info["safe"])
        n_anom = len(info["anomalies"])
        total_safe += n_safe
        total_anom += n_anom
        logger.info("")
        logger.info(f"Collection: {collection}")
        logger.info(
            f"  safe (precision=null AND manufactured_at=null): {n_safe}"
        )
        logger.info(
            f"  anomalies (precision=null, manufactured_at set): {n_anom}"
        )
        if info["anomalies"]:
            logger.info("  -- anomalies --")
            for entry in info["anomalies"]:
                logger.info(
                    f"      {entry['_id']}  "
                    f"manufactured_at={entry['manufactured_at']!r}"
                )
    logger.info("")
    logger.info(f"TOTAL safe-to-backfill: {total_safe}")
    logger.info(f"TOTAL anomalies:        {total_anom}")


def apply_backfill(db, classification: Dict[str, Dict[str, Any]]) -> int:
    """Run `update_many` per collection. Returns total modified count."""
    logger.info("")
    logger.info("=" * 72)
    logger.info("APPLY")
    logger.info("=" * 72)
    total_modified = 0
    for collection, info in classification.items():
        ids = info["safe"]
        if not ids:
            logger.info(f"{collection}: nothing to do (0 safe rows)")
            continue
        result = db[collection].update_many(
            {
                "_id": {"$in": ids},
                "manufactured_precision": None,
                "manufactured_at": None,
            },
            {"$set": {"manufactured_precision": UNKNOWN_VALUE}},
        )
        logger.info(
            f"{collection}: matched={result.matched_count}  "
            f"modified={result.modified_count}  "
            f"(expected={len(ids)})"
        )
        total_modified += result.modified_count
    return total_modified


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run(dry_run: bool, force_anomalies: bool) -> int:
    logger.info("=" * 72)
    logger.info("M1 phase 1 - manufactured_precision null -> 'unknown'")
    logger.info(f"Mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    logger.info(f"Started: {_iso_now()}")
    logger.info("=" * 72)

    try:
        client, db = connect()
    except (PyMongoError, RuntimeError) as exc:
        logger.error(f"Mongo connection failed: {exc}")
        return 1

    try:
        classification = scan(db)
        report(classification)

        total_safe = sum(
            len(info["safe"]) for info in classification.values()
        )
        total_anom = sum(
            len(info["anomalies"]) for info in classification.values()
        )

        if dry_run:
            logger.info("")
            logger.info(
                "Dry-run complete. Re-run with --apply to commit."
            )
            return 0

        if total_anom and not force_anomalies:
            logger.error("")
            logger.error(
                f"Refusing to apply: {total_anom} anomaly row(s) "
                "(precision=null with non-null manufactured_at) require "
                "manual review. Re-run with --force-anomalies after the "
                "anomalies are addressed if you want to apply the safe "
                "subset anyway."
            )
            return 2

        if not total_safe:
            logger.info("")
            logger.info("Nothing to apply (0 safe rows).")
            return 0

        modified = apply_backfill(db, classification)
        logger.info("")
        logger.info(f"DONE. Total modified: {modified}")
        return 0
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Backfill manufactured_precision = 'unknown' on legacy rows "
            "where precision and manufactured_at are both null."
        )
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes (default is dry-run)",
    )
    ap.add_argument(
        "--force-anomalies",
        action="store_true",
        help=(
            "Apply the safe subset even if anomaly rows exist "
            "(precision=null with a non-null manufactured_at). "
            "Anomaly rows themselves are never modified by this script."
        ),
    )
    args = ap.parse_args()
    return run(dry_run=not args.apply, force_anomalies=args.force_anomalies)


if __name__ == "__main__":
    sys.exit(main())
