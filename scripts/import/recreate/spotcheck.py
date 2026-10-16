"""Spot-check the imported ReCreate data on a test instance against the plan.

    python spotcheck.py [--out DIR] [--server URL] [--mongo-uri URI] [--db csc] [--username NAME]

Per dataset: the number of identities in the database equals the plan; per element type one sample: the
API passport (function, origin, location, version status) and its evidence (methods, values, bar count)
equal the plan. Reads the database for the counts (a host other than this machine is refused) and the HTTP
API for the samples. Sign-in as in run.py (CSC_IMPORT_TOKEN, or --username and the password asked).
Run in the `csc` environment (requests, pymongo).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recreate_common as common  # noqa: E402
import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Compare an instance with the ReCreate import plan.')
    parser.add_argument('--out', type=Path, default=common.DEFAULT_OUT, help='folder with plan.json')
    parser.add_argument('--server', default=common.DEFAULT_SERVER, help='base URL of the backend')
    parser.add_argument('--mongo-uri', default=common.DEFAULT_MONGO_URI, help='the local test database')
    parser.add_argument('--db', default='csc')
    parser.add_argument('--username', help='account to sign in with; the password is asked')
    args = parser.parse_args(argv)
    common.require_local(args.mongo_uri)
    plan = json.loads((args.out.resolve() / 'plan.json').read_text(encoding='utf-8'))
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
        samples.setdefault((item['dataset'], item['type']), item)
    for (dataset, etype), item in sorted(samples.items()):
        iid = item['identity']['id']
        passport = requests.get(f'{server}/identities/{iid}/compose?snapshots=all', headers=headers).json()
        ident, snap = passport['identity'], passport['snapshots'][0]
        evidence = requests.get(f'{server}/identities/{iid}/evidence?status=all', headers=headers).json()
        checks = {
            'function': ident['original_function'] == item['identity']['original_function'],
            'origin building': ident['origin']['construction_work']['identifier']
            == item['identity']['origin']['construction_work']['identifier'],
            'published': snap['status'] == 'published',
            'location': snap.get('location') == item['snapshot'].get('location'),
            'records': len(evidence) == len(item['evidence']),
            'all published': all(r['status'] == 'published' for r in evidence),
        }
        bars_plan = sum(len(r['payload']['bars']) for r in item['evidence']
                        if r['method'] == 'reinforcement_layout')
        bars_db = sum(len((r.get('payload') or {}).get('bars') or []) for r in evidence
                      if r['method'] == 'reinforcement_layout')
        checks['bars'] = bars_plan == bars_db
        bad = [k for k, v in checks.items() if not v]
        print(f'{dataset} {etype} #{ident["catalog_number"]} {item["element_id"]}: '
              f'{len(evidence)} records, {bars_db} bars, frame {"yes" if snap.get("frame") else "no"}, '
              f'shape {snap.get("shape_class")}: {"ok" if not bad else "FAILED " + ", ".join(bad)}')
        if bad:
            problems.append(item['key'])
    print('spot check:', 'ok' if not problems else f'{len(problems)} problem(s)')
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
