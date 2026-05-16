"""M3 — verifier for the new identity / snapshot collections.

Re-runnable read-only sanity check against live MongoDB. Verifies that
`component_identities`, `component_snapshots`, and the `catalog_number`
counter all hold together per the invariants locked in ADR-003 / ADR-004 /
ADR-011 / ADR-015 (and Appendix A).

Run any time after M3.2 has applied. Exits ``0`` if every check passes,
non-zero if any check fails. Writes a detailed log to
``logs/m3_verify.log``.

Usage
-----
::

    conda run -n csc python scripts/db_maintenance/m3_verify.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from pymongo import MongoClient
from pymongo.errors import PyMongoError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.backend.apps.catalog.models import (  # noqa: E402
    ComponentIdentity,
    ComponentSnapshot,
)

LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "m3_verify.log"

TARGET_IDENTITIES = "component_identities"
TARGET_SNAPSHOTS = "component_snapshots"
COUNTERS = "counters"
COUNTER_DOC_ID = "catalog_number"

REQUIRED_IDENTITY_INDEXES = [
    "catalog_number_unique",
    "parent_identities_sparse",
    "consumed_at_sparse",
]
REQUIRED_SNAPSHOT_INDEXES = ["identity_version_unique"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("m3_verify")
logger.setLevel(logging.INFO)
logger.handlers.clear()
_fh = logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_fh)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_sh)


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
# Check helpers
# ---------------------------------------------------------------------------
class CheckResult:
    """Lightweight container so the orchestrator can tally results."""

    __slots__ = ("name", "passed", "message")

    def __init__(
        self, name: str, passed: bool, message: str = ""
    ) -> None:
        self.name = name
        self.passed = passed
        self.message = message


def _emit(result: CheckResult) -> None:
    if result.passed:
        logger.info(f"OK    {result.name}  {result.message}".rstrip())
    else:
        logger.error(f"FAIL  {result.name}  {result.message}".rstrip())


# ---------------------------------------------------------------------------
# Group A - structure
# ---------------------------------------------------------------------------
def check_populated(
    identities: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
) -> List[CheckResult]:
    out: List[CheckResult] = []
    out.append(CheckResult(
        "A.1 identities populated",
        len(identities) >= 1,
        f"({len(identities)} docs)",
    ))
    out.append(CheckResult(
        "A.2 snapshots populated",
        len(snapshots) >= len(identities),
        f"({len(snapshots)} snapshots vs {len(identities)} identities)",
    ))
    return out


# ---------------------------------------------------------------------------
# Group B - referential integrity
# ---------------------------------------------------------------------------
def check_referential_integrity(
    identities: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
) -> List[CheckResult]:
    out: List[CheckResult] = []
    snap_by_id = {s["_id"]: s for s in snapshots}
    ident_by_id = {i["_id"]: i for i in identities}

    bad_current: List[str] = []
    bad_roundtrip: List[str] = []
    for ident in identities:
        snap_id = ident.get("current_snapshot_id")
        if snap_id is None or snap_id not in snap_by_id:
            bad_current.append(str(ident["_id"]))
            continue
        snap = snap_by_id[snap_id]
        if snap.get("identity_id") != ident["_id"]:
            bad_roundtrip.append(str(ident["_id"]))

    out.append(CheckResult(
        "B.1 current_snapshot_id resolves",
        not bad_current,
        f"({len(bad_current)} identity(s) with dangling current_snapshot_id)",
    ))
    out.append(CheckResult(
        "B.2 current snapshot round-trips to its identity",
        not bad_roundtrip,
        f"({len(bad_roundtrip)} identity(s) whose current snapshot points "
        "at a different identity_id)",
    ))

    orphan_snaps: List[str] = []
    for snap in snapshots:
        if snap.get("identity_id") not in ident_by_id:
            orphan_snaps.append(str(snap["_id"]))
    out.append(CheckResult(
        "B.3 snapshots reference a known identity",
        not orphan_snaps,
        f"({len(orphan_snaps)} orphan snapshot(s))",
    ))

    bad_parents: List[str] = []
    for ident in identities:
        for pid in ident.get("parent_identities") or []:
            if pid not in ident_by_id:
                bad_parents.append(
                    f"identity {ident['_id']} -> missing parent {pid}"
                )
    out.append(CheckResult(
        "B.4 parent_identities resolve",
        not bad_parents,
        f"({len(bad_parents)} dangling parent reference(s))",
    ))

    if bad_current:
        for _id in bad_current[:10]:
            logger.error(f"      bad current_snapshot_id on {_id}")
    if bad_roundtrip:
        for _id in bad_roundtrip[:10]:
            logger.error(f"      current snapshot round-trip mismatch: {_id}")
    if orphan_snaps:
        for _id in orphan_snaps[:10]:
            logger.error(f"      orphan snapshot: {_id}")
    if bad_parents:
        for msg in bad_parents[:10]:
            logger.error(f"      {msg}")

    return out


# ---------------------------------------------------------------------------
# Group C - uniqueness
# ---------------------------------------------------------------------------
def check_uniqueness(
    identities: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
) -> List[CheckResult]:
    out: List[CheckResult] = []
    ident_ids = [i["_id"] for i in identities]
    snap_ids = [s["_id"] for s in snapshots]
    catalog_numbers = [i.get("catalog_number") for i in identities]
    iv_pairs = [(s.get("identity_id"), s.get("version")) for s in snapshots]

    out.append(CheckResult(
        "C.1 identity._id unique",
        len(set(ident_ids)) == len(ident_ids),
        f"(unique={len(set(ident_ids))} of {len(ident_ids)})",
    ))
    out.append(CheckResult(
        "C.2 snapshot._id unique",
        len(set(snap_ids)) == len(snap_ids),
        f"(unique={len(set(snap_ids))} of {len(snap_ids)})",
    ))
    out.append(CheckResult(
        "C.3 catalog_number unique",
        len(set(catalog_numbers)) == len(catalog_numbers),
        f"(unique={len(set(catalog_numbers))} of {len(catalog_numbers)})",
    ))
    out.append(CheckResult(
        "C.4 (identity_id, version) unique",
        len(set(iv_pairs)) == len(iv_pairs),
        f"(unique={len(set(iv_pairs))} of {len(iv_pairs)})",
    ))
    return out


# ---------------------------------------------------------------------------
# Group D - counter doc
# ---------------------------------------------------------------------------
def check_counter(
    db, identities: List[Dict[str, Any]]
) -> List[CheckResult]:
    out: List[CheckResult] = []
    doc = db[COUNTERS].find_one({"_id": COUNTER_DOC_ID})
    if doc is None:
        out.append(CheckResult(
            "D.1 counter doc exists",
            False,
            f"(counters._id == '{COUNTER_DOC_ID}' is missing)",
        ))
        return out
    out.append(CheckResult(
        "D.1 counter doc exists",
        True,
        f"(next_value={doc.get('next_value')!r})",
    ))
    nv = doc.get("next_value")
    cns = [
        i["catalog_number"] for i in identities
        if isinstance(i.get("catalog_number"), int)
    ]
    if not cns:
        out.append(CheckResult(
            "D.2 counter next_value > max(catalog_number)",
            True,
            "(no catalog numbers to compare)",
        ))
        return out
    max_cn = max(cns)
    out.append(CheckResult(
        "D.2 counter next_value > max(catalog_number)",
        isinstance(nv, int) and nv > max_cn,
        f"(next_value={nv}, max={max_cn})",
    ))
    return out


# ---------------------------------------------------------------------------
# Group E - consumed_at semantics
# ---------------------------------------------------------------------------
def check_consumed_at(
    db, identities: List[Dict[str, Any]]
) -> List[CheckResult]:
    out: List[CheckResult] = []
    expected_active = sum(
        1 for i in identities if i.get("consumed_at") is None
    )
    queried_active = db[TARGET_IDENTITIES].count_documents(
        {"consumed_at": None}
    )
    out.append(CheckResult(
        "E.1 default-filter (consumed_at = null) count matches",
        expected_active == queried_active,
        f"(query={queried_active} build={expected_active})",
    ))

    bad_consumed_types: List[str] = []
    for ident in identities:
        c = ident.get("consumed_at")
        if c is None:
            continue
        if not isinstance(c, str):
            bad_consumed_types.append(str(ident["_id"]))
    out.append(CheckResult(
        "E.2 consumed_at values are ISO-8601 strings (or null)",
        not bad_consumed_types,
        f"({len(bad_consumed_types)} identity(s) with non-string consumed_at)",
    ))
    if bad_consumed_types:
        for _id in bad_consumed_types[:10]:
            logger.error(f"      bad consumed_at type on {_id}")
    return out


# ---------------------------------------------------------------------------
# Group F - Pydantic re-validation
# ---------------------------------------------------------------------------
def check_pydantic(
    identities: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
) -> List[CheckResult]:
    out: List[CheckResult] = []
    ident_errors: List[Tuple[str, str]] = []
    snap_errors: List[Tuple[str, str]] = []
    for doc in identities:
        try:
            ComponentIdentity.model_validate(doc)
        except Exception as exc:
            ident_errors.append((str(doc.get("_id")), str(exc)[:300]))
    for doc in snapshots:
        try:
            ComponentSnapshot.model_validate(doc)
        except Exception as exc:
            snap_errors.append((str(doc.get("_id")), str(exc)[:300]))

    out.append(CheckResult(
        "F.1 every identity passes ComponentIdentity validation",
        not ident_errors,
        f"({len(ident_errors)} failure(s))",
    ))
    out.append(CheckResult(
        "F.2 every snapshot passes ComponentSnapshot validation",
        not snap_errors,
        f"({len(snap_errors)} failure(s))",
    ))
    for _id, err in ident_errors[:10]:
        logger.error(f"      identity {_id}: {err}")
    for _id, err in snap_errors[:10]:
        logger.error(f"      snapshot {_id}: {err}")
    return out


# ---------------------------------------------------------------------------
# Group G - indexes
# ---------------------------------------------------------------------------
def check_indexes(db) -> List[CheckResult]:
    out: List[CheckResult] = []
    ident_index_names = set(db[TARGET_IDENTITIES].index_information().keys())
    snap_index_names = set(db[TARGET_SNAPSHOTS].index_information().keys())

    missing_ident = [
        n for n in REQUIRED_IDENTITY_INDEXES if n not in ident_index_names
    ]
    missing_snap = [
        n for n in REQUIRED_SNAPSHOT_INDEXES if n not in snap_index_names
    ]
    out.append(CheckResult(
        "G.1 required indexes on component_identities present",
        not missing_ident,
        f"(missing: {missing_ident})" if missing_ident else "",
    ))
    out.append(CheckResult(
        "G.2 required indexes on component_snapshots present",
        not missing_snap,
        f"(missing: {missing_snap})" if missing_snap else "",
    ))
    return out


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run() -> int:
    logger.info("=" * 72)
    logger.info("M3 verifier - component_identities / component_snapshots")
    logger.info("=" * 72)

    try:
        client, db = connect()
    except (PyMongoError, RuntimeError) as exc:
        logger.error(f"Mongo connection failed: {exc}")
        return 1

    try:
        identities = list(db[TARGET_IDENTITIES].find({}))
        snapshots = list(db[TARGET_SNAPSHOTS].find({}))
        logger.info(
            f"Loaded identities={len(identities)}  "
            f"snapshots={len(snapshots)}"
        )

        results: List[CheckResult] = []
        results += check_populated(identities, snapshots)
        results += check_referential_integrity(identities, snapshots)
        results += check_uniqueness(identities, snapshots)
        results += check_counter(db, identities)
        results += check_consumed_at(db, identities)
        results += check_indexes(db)
        results += check_pydantic(identities, snapshots)

        logger.info("")
        logger.info("=" * 72)
        logger.info("RESULTS")
        logger.info("=" * 72)
        for r in results:
            _emit(r)

        failed = [r for r in results if not r.passed]
        logger.info("")
        logger.info("=" * 72)
        if failed:
            logger.error(
                f"VERIFICATION FAILED ({len(failed)}/{len(results)} checks)"
            )
            return 2
        logger.info(f"VERIFICATION OK ({len(results)}/{len(results)} checks)")
        return 0
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Re-runnable verifier for component_identities + "
            "component_snapshots invariants (ADR-003 / ADR-011 / ADR-015)."
        )
    )
    ap.parse_args()
    return run()


if __name__ == "__main__":
    sys.exit(main())
