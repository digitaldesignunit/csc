#!/usr/bin/env python3
"""
Escape hatch: remove every component of the given datasets without a trace.

Hard-deletes the identities of the datasets with all their snapshots and
evidence records, their change history, their files (previews, photos,
meshes, point clouds, deviation maps, capture fixtures, evidence
attachments), any purge stubs and pending id transmissions for them, so the
ids are free again (no 410 stub, decision 6.4 d does not apply here), and
resets the catalogue-number counter to continue after the highest remaining
number. The component map cache is cleared (run ``main_component_map.py``
afterwards). With ``--drop-datasets`` the dataset documents and their
invitations go too.

This bypasses every rule of the API (I15, 8.17, 6.4): use it only for data
that must leave the catalogue completely, e.g. an import without consent.
Nothing is written without ``--apply`` and a ``--confirm`` that repeats the
dataset slugs. Refused when a component outside the datasets names one of
them as a parent, or a record outside them points at one of their records.

Mongo connection: ``--uri``, else ``MONGODB_URI``; database ``--db``, else
``MONGODB_DB``, else ``csc``. Files: the ``SNAPSHOT_*_DIR`` and
``EVIDENCE_ATTACHMENTS_DIR`` variables (as the backend reads them), or
``--no-files``.

Usage::

    python scripts/db_maintenance/purge_datasets.py --dataset <slug> \\
        --dataset <slug>                       # dry run: counts only
    python scripts/db_maintenance/purge_datasets.py --dataset <slug> \\
        --apply --confirm <slug>               # writes
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from typing import Dict, Iterable, List, Optional, Set

from pymongo import MongoClient

SNAPSHOT_DIRS = {
    # env variable: how a snapshot's files sit below it
    'SNAPSHOT_PREVIEW_DIR': 'file',        # <sid>.webp
    'SNAPSHOT_PHOTOS_DIR': 'folder',       # <sid>/
    'SNAPSHOT_MESHES_DIR': 'folder',
    'SNAPSHOT_POINT_CLOUDS_DIR': 'folder',
    'SNAPSHOT_PROXIES_DIR': 'folder',      # <sid>/<proxy>/<face>.png
    'SNAPSHOT_CAPTURE_DIR': 'folder',      # <sid>/fixtures/
}
EVIDENCE_DIR = 'EVIDENCE_ATTACHMENTS_DIR'  # <eid>/


def ids_of(collection, query: dict) -> List[str]:
    return [doc['_id'] for doc in collection.find(query, {'_id': 1})]


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def file_targets(snapshot_ids: Iterable[str], evidence_ids: Iterable[str],
                 env: Dict[str, str]) -> List[str]:
    """Existing paths to remove; only uuid names below the configured
    roots (a malformed id never reaches the file system)."""
    paths: List[str] = []
    for var, kind in SNAPSHOT_DIRS.items():
        root = env.get(var)
        if not root:
            continue
        for sid in snapshot_ids:
            if not is_uuid(sid):
                continue
            path = os.path.join(root, f'{sid}.webp' if kind == 'file' else sid)
            if os.path.exists(path):
                paths.append(path)
    root = env.get(EVIDENCE_DIR)
    if root:
        for eid in evidence_ids:
            path = os.path.join(root, eid)
            if is_uuid(eid) and os.path.exists(path):
                paths.append(path)
    return paths


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--dataset', action='append', required=True,
                        help='dataset slug whose components go (repeatable)')
    parser.add_argument('--uri', help='MongoDB URI (else MONGODB_URI)')
    parser.add_argument('--db', help='database (else MONGODB_DB, else csc)')
    parser.add_argument('--drop-datasets', action='store_true',
                        help='also delete the dataset documents and their '
                             'invitations')
    parser.add_argument('--no-files', action='store_true',
                        help='leave the files alone (database only)')
    parser.add_argument('--apply', action='store_true',
                        help='write; without it the run only reports')
    parser.add_argument('--confirm', action='append', default=[],
                        help='repeat every --dataset slug to allow --apply')
    args = parser.parse_args(argv)

    slugs = sorted(set(args.dataset))
    if args.apply and sorted(set(args.confirm)) != slugs:
        raise SystemExit('--apply needs --confirm for exactly these datasets: '
                         + ' '.join(slugs))
    uri = args.uri or os.environ.get('MONGODB_URI')
    if not uri:
        raise SystemExit('no MongoDB URI: --uri or MONGODB_URI')
    db = MongoClient(uri)[args.db or os.environ.get('MONGODB_DB') or 'csc']
    identities = db['component_identities']
    snapshots = db['component_snapshots']
    evidence = db['component_evidence']

    known = set(ids_of(db['datasets'], {'_id': {'$in': slugs}}))
    missing = [s for s in slugs if s not in known]
    if missing:
        print(f'note: no dataset document for {", ".join(missing)}')

    identity_ids = ids_of(identities, {'dataset': {'$in': slugs}})
    id_set: Set[str] = set(identity_ids)
    snapshot_ids = ids_of(snapshots, {'identity_id': {'$in': identity_ids}})
    evidence_ids = ids_of(evidence, {'identity_id': {'$in': identity_ids}})
    all_ids = [*identity_ids, *snapshot_ids, *evidence_ids]

    # links from outside the datasets would point into nothing afterwards
    outside_children = ids_of(identities, {
        'dataset': {'$nin': slugs},
        'parent_identities': {'$in': identity_ids}})
    outside_pairs = ids_of(evidence, {
        'identity_id': {'$nin': identity_ids},
        'payload.sampling.paired_rebound_id': {'$in': evidence_ids}})
    stray_snapshots = ids_of(snapshots, {
        '_id': {'$in': [i['current_snapshot_id'] for i in identities.find(
            {'_id': {'$in': identity_ids}}, {'current_snapshot_id': 1})
            if i.get('current_snapshot_id')]},
        'identity_id': {'$nin': identity_ids}})

    numbers = [i.get('catalog_number') for i in identities.find(
        {'_id': {'$in': identity_ids}}, {'catalog_number': 1})]
    numbers = sorted(n for n in numbers if isinstance(n, int))
    highest_left = identities.find_one(
        {'dataset': {'$nin': slugs}, 'catalog_number': {'$type': 'number'}},
        sort=[('catalog_number', -1)], projection={'catalog_number': 1})
    next_value = int(highest_left['catalog_number']) + 1 if highest_left else 1
    counter = db['counters'].find_one({'_id': 'catalog_number'}) or {}

    env = {} if args.no_files else {
        var: os.environ[var] for var in [*SNAPSHOT_DIRS, EVIDENCE_DIR]
        if os.environ.get(var)}
    files = file_targets(snapshot_ids, evidence_ids, env)

    print(f'datasets: {", ".join(slugs)}')
    print(f'  identities {len(identity_ids)}, snapshots {len(snapshot_ids)}, '
          f'evidence {len(evidence_ids)}')
    print('  change log entries '
          + str(db['change_log'].count_documents(
              {'$or': [{'identity_id': {'$in': identity_ids}},
                       {'record_id': {'$in': all_ids}}]})))
    print('  purge stubs ' + str(db['purged_records'].count_documents(
        {'_id': {'$in': all_ids}})))
    print('  pending id transmissions ' + str(
        db['component_id_transmission'].count_documents(
            {'identity_id': {'$in': identity_ids}})))
    if numbers:
        print(f'  catalogue numbers {numbers[0]}..{numbers[-1]} '
              f'({len(numbers)})')
    print(f'  counter next_value {counter.get("next_value")} -> {next_value}'
          + ('' if not numbers or numbers[-1] < next_value or
             numbers[0] >= next_value else
             ' (numbers below the highest remaining stay unused gaps)'))
    if args.no_files:
        print('  files: left alone (--no-files)')
    else:
        unset = [v for v in [*SNAPSHOT_DIRS, EVIDENCE_DIR] if v not in env]
        print(f'  files to remove {len(files)}'
              + (f' (not configured: {", ".join(unset)})' if unset else ''))
    if args.drop_datasets:
        print(f'  dataset documents {len(known)}, invitations '
              + str(db['invitations'].count_documents(
                  {'dataset': {'$in': slugs}})))

    problems = []
    if outside_children:
        problems.append(f'{len(outside_children)} components outside the '
                        f'datasets name one of them as a parent')
    if outside_pairs:
        problems.append(f'{len(outside_pairs)} records outside the datasets '
                        f'are paired with one of their records')
    if stray_snapshots:
        problems.append('a current snapshot belongs to another component')
    if problems:
        for problem in problems:
            print('REFUSED: ' + problem)
        return 2
    if not args.apply:
        print('dry run: nothing written (--apply --confirm ... to write)')
        return 0

    # order: records first, then the identities, then the bookkeeping
    print('deleting ...')
    print('  evidence', evidence.delete_many(
        {'_id': {'$in': evidence_ids}}).deleted_count)
    print('  snapshots', snapshots.delete_many(
        {'_id': {'$in': snapshot_ids}}).deleted_count)
    print('  identities', identities.delete_many(
        {'_id': {'$in': identity_ids}}).deleted_count)
    print('  change log', db['change_log'].delete_many(
        {'$or': [{'identity_id': {'$in': identity_ids}},
                 {'record_id': {'$in': all_ids}}]}).deleted_count)
    print('  purge stubs', db['purged_records'].delete_many(
        {'_id': {'$in': all_ids}}).deleted_count)
    print('  id transmissions', db['component_id_transmission'].delete_many(
        {'identity_id': {'$in': identity_ids}}).deleted_count)
    print('  map cache', db['component_map_cache'].delete_many({})
          .deleted_count, '(run main_component_map.py)')
    db['counters'].update_one({'_id': 'catalog_number'},
                              {'$set': {'next_value': next_value}},
                              upsert=True)
    print(f'  counter next_value = {next_value}')
    if args.drop_datasets:
        print('  invitations', db['invitations'].delete_many(
            {'dataset': {'$in': slugs}}).deleted_count)
        print('  datasets', db['datasets'].delete_many(
            {'_id': {'$in': slugs}}).deleted_count)
    removed = 0
    for path in files:
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            removed += 1
        except OSError as exc:
            print(f'  WARNING: {path}: {exc}')
    print(f'  files removed {removed} of {len(files)}')
    print('done. Restart the backend (dataset cache) and rebuild the map.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
