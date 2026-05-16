#!/usr/bin/env python3
"""
M2 - Catalog number backfill (live DB)
=======================================

Implements milestone **M2** of the v0.5 migration track per
**ADR-004** (`catalog_number` policy) and the v0.5 implementation plan.

Rules (locked 2026-05-13)
-------------------------

* **Order:** legacy ``components`` and ``components_archive`` are read
  together and sorted ascending by **(``created``, ``_id``)**. Oldest
  ``created`` gets the **lowest** number; ``_id`` is the tie-breaker.
* **First value:** ``1``.
* **Allocation policy:** **monotonic forever** - numbers are never
  recycled. Deleting a doc retires its ``catalog_number`` permanently.
* **Counter doc:** ``counters._id = "catalog_number"`` with field
  ``next_value`` is initialised to ``max_assigned + 1`` so future
  allocations (e.g. AddComponent) use
  ``find_one_and_update({"_id": "catalog_number"},
  {"$inc": {"next_value": 1}}, return_document=BEFORE)``.

Idempotency
-----------

* If a doc already has a ``catalog_number`` that matches the deterministic
  computation for its row, it's left alone.
* If a doc already has a ``catalog_number`` that **disagrees** with the
  computation, the script logs a clear ``mismatch`` error and refuses to
  overwrite (operator must reconcile manually).
* The counter doc is created if missing; if present, it is moved
  **forward** to ``max(existing_next_value, max_assigned + 1)`` and never
  rolled back.

Safety
------

* **Dry-run by default.** Pass ``--apply`` to commit.
* Read-only Mongo access is sufficient for dry-run.
* Logs to ``logs/m2_catalog_number_backfill.log``.

Usage
-----

::

    # Preview (no writes)
    python scripts/db_maintenance/m2_catalog_number_backfill.py

    # Commit
    python scripts/db_maintenance/m2_catalog_number_backfill.py --apply
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


REPO_ROOT = Path(__file__).resolve().parents[2]
_LOG_DIR = REPO_ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_PATH = _LOG_DIR / "m2_catalog_number_backfill.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


COMPONENTS_COLLECTION = "components"
ARCHIVE_COLLECTION = "components_archive"
COUNTERS_COLLECTION = "counters"
CATALOG_COUNTER_ID = "catalog_number"


# ---------------------------------------------------------------------------
# Mongo connection (mirrors migrate_phase1 / m1_phase1_completion pattern)
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
# Core
# ---------------------------------------------------------------------------


def _normalize_created(value: Any) -> str:
    """Coerce a `created` value to an ISO-8601 string for stable sort.

    Accepts:
        - string: returned as-is (ISO-8601 sorts correctly lexicographically
          when terminator and precision are uniform).
        - datetime.datetime: rendered ISO-8601 UTC.
        - dict {"$date": "..."}: mongoexport extended JSON shape.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    if isinstance(value, dict):
        for k in ("$date", "date"):
            if k in value:
                return _normalize_created(value[k])
    raise TypeError(
        f"Cannot normalise `created` value of type {type(value).__name__}"
    )


def gather_rows(components, archive) -> List[Dict[str, Any]]:
    """Return all docs across both collections, each enriched with
    `_source_collection`. Skips docs missing `created` (logged warning)."""
    rows: List[Dict[str, Any]] = []
    for coll, label in (
        (components, COMPONENTS_COLLECTION),
        (archive, ARCHIVE_COLLECTION),
    ):
        for doc in coll.find(
            {},
            {"_id": 1, "created": 1, "catalog_number": 1},
        ):
            if "created" not in doc or doc["created"] is None:
                logger.warning(
                    f"[{label}] {doc.get('_id')}: missing `created` "
                    "- excluded from M2 ordering"
                )
                continue
            try:
                created_norm = _normalize_created(doc["created"])
            except TypeError as e:
                logger.warning(
                    f"[{label}] {doc.get('_id')}: cannot normalise "
                    f"`created`: {e}"
                )
                continue
            rows.append(
                {
                    "_id": str(doc["_id"]),
                    "_source_collection": label,
                    "created": created_norm,
                    "existing_catalog_number": doc.get("catalog_number"),
                }
            )
    return rows


def assign_catalog_numbers(
    rows: List[Dict[str, Any]],
    start_from: int = 1,
) -> List[Dict[str, Any]]:
    """Sort rows by (created, _id) ascending and assign incrementing numbers
    starting from `start_from`."""
    rows_sorted = sorted(rows, key=lambda r: (r["created"], r["_id"]))
    for i, row in enumerate(rows_sorted, start=start_from):
        row["expected_catalog_number"] = i
    return rows_sorted


def reconcile(
    rows_sorted: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Categorise each row as match / mismatch / new. Returns counters
    and adds `action` to each row (`set` | `keep` | `mismatch`)."""
    counters = {"set": 0, "keep": 0, "mismatch": 0}
    for row in rows_sorted:
        cur = row["existing_catalog_number"]
        expected = row["expected_catalog_number"]
        if cur is None:
            row["action"] = "set"
            counters["set"] += 1
        elif int(cur) == expected:
            row["action"] = "keep"
            counters["keep"] += 1
        else:
            row["action"] = "mismatch"
            counters["mismatch"] += 1
            logger.error(
                f"[{row['_source_collection']}] {row['_id']}: catalog "
                f"mismatch - existing={cur}, deterministic={expected}"
            )
    return counters


def apply_writes(
    components,
    archive,
    rows_sorted: List[Dict[str, Any]],
    dry_run: bool,
) -> Dict[str, int]:
    counters = {"updated": 0, "skipped": 0, "errors": 0}
    coll_for = {
        COMPONENTS_COLLECTION: components,
        ARCHIVE_COLLECTION: archive,
    }
    for row in rows_sorted:
        if row["action"] != "set":
            counters["skipped"] += 1
            continue
        coll = coll_for[row["_source_collection"]]
        if dry_run:
            logger.info(
                f"  DRY RUN: [{row['_source_collection']}] {row['_id']}"
                f" -> catalog_number = {row['expected_catalog_number']}"
            )
            counters["updated"] += 1
            continue
        try:
            res = coll.update_one(
                {"_id": row["_id"]},
                {"$set": {
                    "catalog_number": int(
                        row["expected_catalog_number"]
                    )
                }},
            )
            if res.modified_count == 1:
                counters["updated"] += 1
        except PyMongoError as e:
            logger.error(
                f"[{row['_source_collection']}] {row['_id']}: "
                f"update error: {e}"
            )
            counters["errors"] += 1
    return counters


def ensure_counter(
    counters_coll,
    target_next_value: int,
    dry_run: bool,
) -> Dict[str, Any]:
    """Ensure `counters._id = "catalog_number"` exists with
    `next_value >= target_next_value`. Never rolls a counter backwards.
    Returns metadata about the action taken."""
    existing = counters_coll.find_one({"_id": CATALOG_COUNTER_ID})
    if existing is None:
        action = "create"
        chosen = target_next_value
    else:
        cur = int(existing.get("next_value", 0))
        if cur >= target_next_value:
            action = "keep"
            chosen = cur
        else:
            action = "advance"
            chosen = target_next_value

    logger.info(
        f"[counters] action={action} next_value -> {chosen} "
        f"(target_next_value={target_next_value})"
    )

    if dry_run:
        return {"action": action, "next_value": chosen, "applied": False}

    if action == "create":
        counters_coll.insert_one(
            {"_id": CATALOG_COUNTER_ID, "next_value": chosen}
        )
    elif action == "advance":
        counters_coll.update_one(
            {"_id": CATALOG_COUNTER_ID},
            {"$set": {"next_value": chosen}},
        )
    return {"action": action, "next_value": chosen, "applied": True}


def verify(components, archive, counters_coll, rows_sorted) -> bool:
    """Post-apply sanity checks."""
    failed = False

    # Every doc carries catalog_number
    for coll, label in (
        (components, COMPONENTS_COLLECTION),
        (archive, ARCHIVE_COLLECTION),
    ):
        n_missing = coll.count_documents(
            {"catalog_number": {"$exists": False}}
        )
        if n_missing > 0:
            logger.error(
                f"[{label}] {n_missing} doc(s) still missing "
                "catalog_number"
            )
            failed = True
        else:
            logger.info(
                f"[{label}] OK: catalog_number present on all docs"
            )

    # Cross-collection uniqueness
    all_nums = []
    for coll in (components, archive):
        for d in coll.find(
            {"catalog_number": {"$exists": True}},
            {"_id": 1, "catalog_number": 1},
        ):
            all_nums.append(int(d["catalog_number"]))
    if len(all_nums) != len(set(all_nums)):
        dup_counts: Dict[int, int] = {}
        for n in all_nums:
            dup_counts[n] = dup_counts.get(n, 0) + 1
        dups = [n for n, c in dup_counts.items() if c > 1]
        logger.error(
            f"catalog_number collisions across collections: "
            f"{sorted(dups)[:20]}{' ...' if len(dups) > 20 else ''}"
        )
        failed = True
    else:
        logger.info(
            "OK: catalog_number unique across components + "
            "components_archive"
        )

    # Counter is ahead of max
    if all_nums:
        max_num = max(all_nums)
        counter_doc = counters_coll.find_one({"_id": CATALOG_COUNTER_ID})
        if counter_doc is None:
            logger.error("counters._id='catalog_number' missing")
            failed = True
        else:
            nv = int(counter_doc.get("next_value", 0))
            if nv <= max_num:
                logger.error(
                    f"counter next_value={nv} <= max_assigned={max_num}"
                )
                failed = True
            else:
                logger.info(
                    f"OK: counter next_value={nv} > "
                    f"max_assigned={max_num}"
                )

    return not failed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(dry_run: bool) -> int:
    mode = "DRY RUN" if dry_run else "APPLY"
    logger.info(f"=== M2 catalog_number backfill ({mode}) ===")

    client, db = connect()
    try:
        components = db[COMPONENTS_COLLECTION]
        archive = db[ARCHIVE_COLLECTION]
        counters_coll = db[COUNTERS_COLLECTION]

        rows = gather_rows(components, archive)
        logger.info(
            f"Collected {len(rows)} doc(s) across "
            f"{COMPONENTS_COLLECTION} + {ARCHIVE_COLLECTION}"
        )
        rows_sorted = assign_catalog_numbers(rows, start_from=1)

        recon = reconcile(rows_sorted)
        logger.info(
            f"Reconcile: set={recon['set']} keep={recon['keep']} "
            f"mismatch={recon['mismatch']}"
        )

        if recon["mismatch"] > 0:
            logger.error(
                "Refusing to write: existing catalog_number values "
                "disagree with the deterministic computation. "
                "Resolve mismatches before re-running."
            )
            return 1

        # Apply writes (skipped if dry_run)
        w = apply_writes(components, archive, rows_sorted, dry_run)
        logger.info(
            f"Writes: updated={w['updated']} skipped={w['skipped']} "
            f"errors={w['errors']}"
        )

        # Counter
        max_assigned = max(
            (r["expected_catalog_number"] for r in rows_sorted),
            default=0,
        )
        ensure_counter(counters_coll, max_assigned + 1, dry_run)

        if dry_run:
            logger.info(
                "DRY RUN complete - no writes were made. "
                "Re-run with --apply to commit."
            )
            return 0

        # Verification
        logger.info("--- Verification ---")
        ok = verify(components, archive, counters_coll, rows_sorted)
        return 0 if ok else 1
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "M2 catalog_number backfill (live DB; idempotent; "
            "monotonic-forever)"
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
