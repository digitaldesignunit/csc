"""Backfill ``added_by_*`` and ``quantity`` on ``component_snapshots``.

New snapshot fields (see ``ComponentSnapshot`` in ``models.py``):

* ``added_by_user_id`` / ``added_by_username`` — who created the catalog
  entry (set on initial add). Legacy rows migrated before this field existed
  have neither; they are attributed to the shared **ddu** service account.
* ``quantity`` — count of identical physical items (default ``1``).

Rules
-----
* **added_by:** set when ``added_by_user_id`` is missing, ``null``, or empty.
  Existing non-empty values are left unchanged.
* **quantity:** set to ``1`` when the field is missing, ``null``, not a
  positive integer, or ``< 1``. Existing valid quantities are left unchanged.

Each updated snapshot gets a fresh ``etag`` (same sha256 recipe as the API
and M3 backfill). ``lastmodified`` is not touched.

Safety
------
* **Dry-run by default.** Pass ``--apply`` to commit.
* Idempotent: re-running after a clean apply finds nothing to do.

Mongo connection: ``MONGO_URI`` env or ``scripts/config/dbconfig.json``.

Usage
-----
::

    conda run -n csc python \\
        scripts/db_maintenance/backfill_snapshot_added_by_quantity.py
    conda run -n csc python \\
        scripts/db_maintenance/backfill_snapshot_added_by_quantity.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.backend.apps.catalog.models import ComponentSnapshot  # noqa: E402


def compute_snapshot_etag(snapshot_doc: Dict[str, Any]) -> str:
    """sha256 over canonical snapshot JSON, excluding etag and lastmodified."""
    payload = {
        k: v for k, v in snapshot_doc.items()
        if k not in ("etag", "lastmodified")
    }
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "backfill_snapshot_added_by_quantity.log"

SNAPSHOTS_COLLECTION = "component_snapshots"

DDU_USER_ID = "98e7e459-a8f4-4def-9360-21ec8cb7ed8d"
DDU_USERNAME = "ddu"
DEFAULT_QUANTITY = 1

LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("backfill_snapshot_added_by_quantity")
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


def _missing_added_by(doc: Dict[str, Any]) -> bool:
    user_id = doc.get("added_by_user_id")
    if user_id is None:
        return True
    if isinstance(user_id, str) and not user_id.strip():
        return True
    return False


def _missing_quantity(doc: Dict[str, Any]) -> bool:
    quantity = doc.get("quantity")
    if quantity is None:
        return True
    if isinstance(quantity, bool):
        return True
    if not isinstance(quantity, int):
        return True
    return quantity < 1


def classify_doc(doc: Dict[str, Any]) -> Tuple[bool, bool]:
    return _missing_added_by(doc), _missing_quantity(doc)


def build_update(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return fields to $set, including a recomputed etag, or {} if unchanged."""
    updates: Dict[str, Any] = {}
    if _missing_added_by(doc):
        updates["added_by_user_id"] = DDU_USER_ID
        updates["added_by_username"] = DDU_USERNAME
    if _missing_quantity(doc):
        updates["quantity"] = DEFAULT_QUANTITY
    if not updates:
        return {}
    merged = {**doc, **updates}
    updates["etag"] = compute_snapshot_etag(merged)
    return updates


def scan(db) -> Dict[str, Any]:
    collection = db[SNAPSHOTS_COLLECTION]
    total = collection.count_documents({})

    stats = {
        "total": total,
        "needs_added_by": 0,
        "needs_quantity": 0,
        "needs_both": 0,
        "already_complete": 0,
        "to_update": 0,
        "updates": [],
    }

    for doc in collection.find({}):
        miss_added_by, miss_quantity = classify_doc(doc)
        if miss_added_by:
            stats["needs_added_by"] += 1
        if miss_quantity:
            stats["needs_quantity"] += 1
        if miss_added_by and miss_quantity:
            stats["needs_both"] += 1
        if not miss_added_by and not miss_quantity:
            stats["already_complete"] += 1
            continue

        updates = build_update(doc)
        if updates:
            stats["updates"].append({"_id": doc["_id"], "set": updates})

    stats["to_update"] = len(stats["updates"])
    return stats


def report(stats: Dict[str, Any]) -> None:
    logger.info("")
    logger.info("=" * 72)
    logger.info("SCAN SUMMARY")
    logger.info("=" * 72)
    logger.info(f"snapshots total:              {stats['total']}")
    logger.info(f"missing added_by_user_id:     {stats['needs_added_by']}")
    logger.info(f"missing/invalid quantity:     {stats['needs_quantity']}")
    logger.info(f"need both fields:             {stats['needs_both']}")
    logger.info(f"already complete:             {stats['already_complete']}")
    logger.info(f"documents to update:          {stats['to_update']}")

    sample = stats["updates"][:5]
    if sample:
        logger.info("")
        logger.info("Sample updates (first 5):")
        for item in sample:
            fields = ", ".join(
                k for k in item["set"] if k != "etag"
            )
            logger.info(f"  _id={item['_id']}  set: {fields}")


def validate_samples(db, sample_ids: List[Any]) -> bool:
    snapshots = db[SNAPSHOTS_COLLECTION]
    ok = True
    for _id in sample_ids:
        doc = snapshots.find_one({"_id": _id})
        if doc is None:
            logger.error(f"FAIL  sample {_id} missing after write")
            ok = False
            continue
        try:
            ComponentSnapshot.model_validate(doc)
        except Exception as exc:
            logger.error(f"FAIL  sample {_id} validation: {exc}")
            ok = False
            continue
        if _missing_added_by(doc):
            logger.error(f"FAIL  sample {_id} still missing added_by_user_id")
            ok = False
        if _missing_quantity(doc):
            logger.error(f"FAIL  sample {_id} still missing/invalid quantity")
            ok = False
    if ok and sample_ids:
        logger.info(
            f"OK    {len(sample_ids)} post-write samples pass validation"
        )
    return ok


def apply(db, updates: List[Dict[str, Any]]) -> int:
    if not updates:
        return 0

    logger.info("")
    logger.info("=" * 72)
    logger.info("APPLY")
    logger.info("=" * 72)

    ops = [
        UpdateOne({"_id": item["_id"]}, {"$set": item["set"]})
        for item in updates
    ]
    try:
        result = db[SNAPSHOTS_COLLECTION].bulk_write(ops, ordered=False)
    except BulkWriteError as exc:
        logger.error(f"bulk_write failed: {exc.details}")
        raise

    modified = result.modified_count
    logger.info(
        f"matched={result.matched_count}  modified={modified}  "
        f"(expected={len(updates)})"
    )
    return modified


def run(dry_run: bool) -> int:
    logger.info("=" * 72)
    logger.info("Backfill snapshot added_by + quantity")
    logger.info(f"Mode: {'DRY-RUN' if dry_run else 'APPLY'}")
    logger.info(f"Target collection: {SNAPSHOTS_COLLECTION}")
    logger.info(
        f"added_by default: {DDU_USERNAME} ({DDU_USER_ID})"
    )
    logger.info(f"quantity default: {DEFAULT_QUANTITY}")
    logger.info("=" * 72)

    try:
        client, db = connect()
    except (PyMongoError, RuntimeError) as exc:
        logger.error(f"Mongo connection failed: {exc}")
        return 1

    try:
        if SNAPSHOTS_COLLECTION not in db.list_collection_names():
            logger.error(
                f"Collection '{SNAPSHOTS_COLLECTION}' does not exist; "
                "nothing to backfill."
            )
            return 2

        stats = scan(db)
        report(stats)

        if not stats["updates"]:
            logger.info("")
            logger.info("Nothing to do (all snapshots already complete).")
            return 0

        if dry_run:
            logger.info("")
            logger.info("Dry-run complete. Re-run with --apply to commit.")
            return 0

        modified = apply(db, stats["updates"])

        sample_ids = [item["_id"] for item in stats["updates"][:10]]
        ok = validate_samples(db, sample_ids)
        if not ok:
            logger.error("")
            logger.error("Post-write validation failed; investigate before done.")
            return 3

        logger.info("")
        logger.info(f"DONE. Total modified: {modified}")
        return 0
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Backfill added_by_user_id / added_by_username (ddu user) and "
            "quantity=1 on component_snapshots (dry-run by default)."
        )
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes (default is dry-run)",
    )
    args = ap.parse_args()
    return run(dry_run=not args.apply)


if __name__ == "__main__":
    sys.exit(main())
