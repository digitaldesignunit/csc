"""Spot-check the imported EPFL stones on a test instance against the plan.

    python spotcheck.py [--out DIR] [--server URL] [--mongo-uri URI] [--db csc] [--username NAME]

The number of identities of the dataset in the database equals the plan (452); per group (A to E) one stone:
the API passport (published, location none, origin offcut, material natural stone, the inline preview mesh
and cloud), the files the snapshot lists (`reduced`, `detailed`), and the staged cloud as the API serves it
(the same size as the prepared `cloud.ply`, not the inline fallback). Reads the database for the count (a host
other than this machine is refused) and the HTTP API for the samples. Sign-in as in run.py (CSC_IMPORT_TOKEN,
or --username and the password asked). Run in the `csc` environment (requests, pymongo).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import epfl_common as epfl  # noqa: E402

common = epfl.common
import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Compare an instance with the EPFL stone import plan.')
    parser.add_argument('--out', type=Path, default=epfl.DEFAULT_OUT, help='folder with plan.json and stones/')
    parser.add_argument('--server', default=common.DEFAULT_SERVER, help='base URL of the backend')
    parser.add_argument('--mongo-uri', default=common.DEFAULT_MONGO_URI, help='the local test database')
    parser.add_argument('--db', default='csc')
    parser.add_argument('--username', help='account to sign in with; the password is asked')
    args = parser.parse_args(argv)
    common.require_local(args.mongo_uri)
    out = args.out.resolve()
    plan = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
    db = MongoClient(args.mongo_uri)[args.db]
    token, _ = common.get_token(args.server, args.username)
    headers = {'Authorization': 'Bearer ' + token, 'X-CSC-Client': common.CLIENT}
    server = args.server.rstrip('/')
    problems = []
    want = Counter(i['dataset'] for i in plan['items'])
    for dataset, n in sorted(want.items()):
        have = db['component_identities'].count_documents({'dataset': dataset})
        status = 'ok' if have == n else 'MISMATCH'
        print(f'{dataset}: {have} identities (plan {n}) {status}')
        if have != n:
            problems.append(dataset)
    samples = {}
    for item in plan['items']:
        samples.setdefault(item['group'], item)
    for group, item in sorted(samples.items()):
        iid = item['identity']['id']
        passport = requests.get(f'{server}/identities/{iid}/compose?snapshots=all', headers=headers).json()
        ident, snap = passport['identity'], passport['snapshots'][0]
        meshes = (snap.get('geometry') or {}).get('meshes') or []
        clouds = (snap.get('geometry') or {}).get('point_clouds') or []
        resolutions = (snap.get('mesh_ply_resolutions') or {}).get('0', [])
        checks = {
            'published': snap['status'] == 'published',
            'location none': not snap.get('location'),
            'origin offcut': (ident.get('origin') or {}).get('kind') == 'offcut',
            'material': ident.get('material') == 'natural_stone',
            'preview mesh': bool(meshes) and bool(meshes[0].get('vertices')),
            'inline cloud': bool(clouds) and len(clouds[0].get('points') or []) == item['cloud_inline'],
            'mesh levels': all(level in resolutions for level in ('reduced', 'detailed') if level in item['files']),
        }
        if 'cloud' in item['files']:
            checks['cloud marker'] = 0 in (snap.get('point_cloud_files') or [])
            reply = requests.get(f'{server}/snapshots/{snap["_id"]}/point_clouds/0.ply', headers=headers)
            checks['staged cloud'] = reply.status_code == 200 and \
                len(reply.content) == (out / item['files']['cloud']).stat().st_size
        bad = [k for k, v in checks.items() if not v]
        print(f'{item["dataset"]} group {group} #{ident["catalog_number"]} {item["stone"]}: '
              f'{len(meshes[0]["faces"]) if meshes else 0} preview faces, levels {resolutions}, '
              f'frame {"yes" if snap.get("frame") else "no"}, shape {snap.get("shape_class")}: '
              f'{"ok" if not bad else "FAILED " + ", ".join(bad)}')
        if bad:
            problems.append(item['key'])
    print('spot check:', 'ok' if not problems else f'{len(problems)} problem(s)')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
