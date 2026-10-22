"""Backfill ``geo_current`` and ``geo_origin`` on ``component_identities``.

The near search (decision 8.170) reads two derived GeoJSON points on each
identity: ``geo_current`` from the ``location`` of the current snapshot and
``geo_origin`` from ``origin.place.location``. The API keeps them current from
release 0.6.4 on; this script fills them for records written before, and
afterwards reports any record whose points disagree with its documents, so it
doubles as the check.

Rules
-----
* ``geo_current`` is the point of ``location`` of the snapshot named by
  ``current_snapshot_id``; absent when there is none.
* ``geo_origin`` is the point of ``origin.place.location``; absent when there
  is none.
* A location outside the globe or without two numbers gives no point (the
  index would refuse it); such records are counted and listed.
* ``lastmodified``, ``etag`` and the change log are not touched: both fields
  are derived, never authored.

Safety
------
* **Dry-run by default.** Pass ``--apply`` to commit.
* Exit codes: 0 = nothing to do (every point agrees with its record), or the
  changes were applied and a second scan is clean; 1 = no connection;
  2 = no ``component_identities`` collection; 3 = after ``--apply`` points
  still disagree; **4 = a dry run found points to set, correct or remove**, so
  a dry run is the consistency check (non-zero means disagreement).
* Idempotent: re-running after a clean apply finds nothing to do.
* The ``2dsphere`` indexes themselves are created by the API at its start.

Mongo connection: ``MONGO_URI`` env or ``scripts/config/dbconfig.json``.

Usage
-----
::

    conda run -n csc python scripts/db_maintenance/backfill_geo_points.py
    conda run -n csc python scripts/db_maintenance/backfill_geo_points.py \\
        --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src" / "backend"))

from apps.catalog.geo import (  # noqa: E402
    GEO_CURRENT,
    GEO_ORIGIN,
    origin_point,
    point_of,
)

LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "backfill_geo_points.log"

IDENTITIES_COLLECTION = "component_identities"
SNAPSHOTS_COLLECTION = "component_snapshots"

LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("backfill_geo_points")
logger.setLevel(logging.INFO)
logger.handlers.clear()
_fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_fh)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_sh)


def load_mongo_config() -> Dict[str, str]:
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri:
        return {"uri": mongo_uri}

    candidate = REPO_ROOT / "scripts" / "config" / "dbconfig.json"
    if candidate.exists():
        with candidate.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        server, db = cfg.get("server"), cfg.get("db")
        user, pwd = cfg.get("user"), cfg.get("pwd")
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


def has_location(location: Any) -> bool:
    """True when a stored location holds anything (even an unusable value)."""
    return isinstance(location, dict) and (
        location.get("lat") is not None or location.get("lon") is not None
    )


def expected_points(
    identity: Dict[str, Any], current_location: Optional[Dict[str, Any]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    return {
        GEO_CURRENT: point_of(current_location),
        GEO_ORIGIN: origin_point(identity),
    }


def scan(db) -> Dict[str, Any]:
    identities = db[IDENTITIES_COLLECTION]
    snapshots = db[SNAPSHOTS_COLLECTION]

    locations: Dict[str, Optional[Dict[str, Any]]] = {
        doc["_id"]: doc.get("location")
        for doc in snapshots.find({}, {"location": 1})
    }

    stats: Dict[str, Any] = {
        "total": 0,
        "with_current": 0,
        "with_origin": 0,
        "to_set": 0,
        "to_remove": 0,
        "unusable": [],
        "updates": [],
    }
    for identity in identities.find({}):
        stats["total"] += 1
        current_location = locations.get(identity.get("current_snapshot_id"))
        origin_location = ((identity.get("origin") or {}).get("place") or {}
                           ).get("location")
        want = expected_points(identity, current_location)
        for field, raw in ((GEO_CURRENT, current_location),
                           (GEO_ORIGIN, origin_location)):
            if want[field] is None and has_location(raw):
                stats["unusable"].append((identity["_id"], field))
        stats["with_current"] += want[GEO_CURRENT] is not None
        stats["with_origin"] += want[GEO_ORIGIN] is not None

        operations: List[Any] = []
        for field in (GEO_CURRENT, GEO_ORIGIN):
            have = identity.get(field)
            if want[field] is not None and have != want[field]:
                operations.append(
                    UpdateOne({"_id": identity["_id"]},
                              {"$set": {field: want[field]}}))
                stats["to_set"] += 1
            elif want[field] is None and field in identity:
                operations.append(
                    UpdateOne({"_id": identity["_id"]},
                              {"$unset": {field: ""}}))
                stats["to_remove"] += 1
        stats["updates"].extend(operations)
    return stats


def report(stats: Dict[str, Any]) -> None:
    logger.info("")
    logger.info("=" * 72)
    logger.info("SCAN SUMMARY")
    logger.info("=" * 72)
    logger.info(f"identities total:            {stats['total']}")
    logger.info(f"with a current point:        {stats['with_current']}")
    logger.info(f"with an origin point:        {stats['with_origin']}")
    logger.info(f"points to set or correct:    {stats['to_set']}")
    logger.info(f"points to remove:            {stats['to_remove']}")
    logger.info(f"unusable locations:          {len(stats['unusable'])}")
    for identity_id, field in stats["unusable"][:10]:
        logger.info(f"  {identity_id}  {field}: not a point on the globe")


def apply(db, updates: List[Any]) -> int:
    if not updates:
        return 0
    try:
        result = db[IDENTITIES_COLLECTION].bulk_write(updates, ordered=False)
    except BulkWriteError as exc:
        logger.error(f"bulk_write failed: {exc.details}")
        raise
    logger.info(
        f"matched={result.matched_count}  modified={result.modified_count}  "
        f"(operations={len(updates)})"
    )
    return result.modified_count


def run(dry_run: bool) -> int:
    logger.info("=" * 72)
    logger.info("Backfill geo_current and geo_origin")
    logger.info(f"Mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    logger.info(f"Target collection: {IDENTITIES_COLLECTION}")
    logger.info("=" * 72)

    try:
        client, db = connect()
    except (PyMongoError, RuntimeError) as exc:
        logger.error(f"Mongo connection failed: {exc}")
        return 1

    try:
        if IDENTITIES_COLLECTION not in db.list_collection_names():
            logger.error(f"Collection '{IDENTITIES_COLLECTION}' does not exist.")
            return 2

        stats = scan(db)
        report(stats)

        if not stats["updates"]:
            logger.info("")
            logger.info("Nothing to do (every point agrees with its record).")
            return 0
        if dry_run:
            logger.info("")
            logger.info("Dry-run complete. Re-run with --apply to commit.")
            logger.info("Exit code 4: points disagree with their records.")
            return 4

        apply(db, stats["updates"])
        again = scan(db)
        if again["updates"]:
            logger.error("")
            logger.error(
                f"{len(again['updates'])} points still disagree after the "
                "write; investigate before done."
            )
            return 3
        logger.info("")
        logger.info("DONE. A second scan finds nothing left to do.")
        return 0
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Fill geo_current / geo_origin on component_identities from the "
            "current snapshot's location and origin.place.location "
            "(dry-run by default). Exit code 4: a dry run found points that "
            "disagree with their records; 0: all agree."
        )
    )
    ap.add_argument("--apply", action="store_true",
                    help="Commit changes (default is dry-run)")
    args = ap.parse_args()
    return run(dry_run=not args.apply)


if __name__ == "__main__":
    sys.exit(main())
