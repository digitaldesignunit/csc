"""Run the ReCreate import plan against a CSC backend over its HTTP API.

    python run.py --dry-run                              validate every body offline, touch nothing
    python run.py --server URL --username NAME [--dataset recreate_nl] [--only recreate:NL:] [--limit N]

Run in an environment with the backend's packages (the `csc` conda environment): it imports the backend's
request models for the dry run and the Grasshopper client's mesh rules, and needs `numpy` and `requests`.
`--out` is the folder `plan.py` wrote (`plan.json` and the meshes).

Sign-in: with `--username` the password is asked on the terminal (no echo) and exchanged at `POST
/auth/token`; or put a bearer token into the environment variable CSC_IMPORT_TOKEN. Neither is stored or
printed. `--config FILE` (optional, never committed) is a JSON object with defaults for `server` and
`username`, for a local rehearsal. The account becomes moderator and contributor of the datasets it creates.

Meshes follow the Grasshopper client's rules (csc_gh.build.mesh_levels, decision 8.95): the mesh is the
inline geometry, and a mesh above 500 faces also goes up as `detailed.ply`. Resumable: fixed identity ids
(uuid5 of `recreate:<pilot>:<element id>`), evidence found again by its document reference; a second run
creates nothing. Writes `<out>/run-<time>.log`. Datasets are created private (members only); making them
public is a separate, deliberate step.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import recreate_common as common  # noqa: E402

REPO = common.REPO
sys.path.insert(0, str(REPO / 'grasshopper_lib'))
import numpy as np  # noqa: E402
import requests  # noqa: E402
from csc_gh.build import mesh_levels  # noqa: E402
from csc_gh.ply import write_ply_mesh  # noqa: E402

CLIENT = common.CLIENT


def read_ply(path: Path):
    """Vertices and triangles of a binary little-endian PLY written by trimesh."""
    data = path.read_bytes()
    end = data.index(b'end_header\n') + len(b'end_header\n')
    header = data[:end].decode('ascii').splitlines()
    nv = int(next(h for h in header if h.startswith('element vertex')).split()[-1])
    nf = int(next(h for h in header if h.startswith('element face')).split()[-1])
    vertex_fields = []
    for h in header:
        if h.startswith('element face'):
            break
        if h.startswith('property') and 'list' not in h:
            kind, name = h.split()[1], h.split()[2]
            vertex_fields.append((name, {'float': '<f4', 'double': '<f8', 'uchar': 'u1',
                                         'int': '<i4'}[kind]))
    vtype = np.dtype(vertex_fields)
    verts = np.frombuffer(data, dtype=vtype, count=nv, offset=end)
    faces = np.frombuffer(data, dtype=np.dtype([('n', 'u1'), ('i', '<i4', (3,))]), count=nf,
                          offset=end + nv * vtype.itemsize)
    xyz = np.stack([verts['x'], verts['y'], verts['z']], axis=1).astype(float)
    return xyz, faces['i'].astype(int)


def inline_mesh(out: Path, item):
    xyz, tri = read_ply(out / item['mesh_ply'])
    return {'vertices': [[round(float(c), 2) for c in v] for v in xyz],
            'faces': [[int(i) for i in f] for f in tri]}, xyz, tri


class Api:
    def __init__(self, server, token, renew=None):
        self.server = server.rstrip('/')
        self.token = token
        self.renew = renew
        self.http = requests.Session()
        self.calls = 0

    def request(self, method, path, **kw):
        for attempt in (1, 2):
            headers = {'Authorization': 'Bearer ' + self.token, 'X-CSC-Client': CLIENT}
            self.calls += 1
            response = self.http.request(method, self.server + path, headers=headers, timeout=300, **kw)
            if response.status_code == 401 and attempt == 1 and self.renew:
                self.token = self.renew()          # the token ran out during a long run
                continue
            return response

    def json(self, method, path, ok=(200, 201), **kw):
        response = self.request(method, path, **kw)
        if response.status_code not in ok:
            raise RuntimeError(f'{method} {path} -> {response.status_code}: {response.text[:400]}')
        return response.json() if response.content else None


def user_id_of(token):
    payload = token.split('.')[1]
    payload += '=' * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))['sub']


def identity_body(item, mesh):
    snapshot = dict(item['snapshot'])
    snapshot['geometry'] = {'meshes': [mesh], 'point_clouds': [], 'proxies': []}
    return {**item['identity'], 'snapshot': snapshot}


def records_of(item, snapshot_id):
    out = []
    for record in item['evidence']:
        body = json.loads(json.dumps(record))
        if body.get('position') is not None:
            body['position']['snapshot_id'] = snapshot_id
        body['identity_id'] = item['identity']['id']
        out.append((body['payload']['document']['reference'], body))
    return out


# VALIDATION (dry run) ---------------------------------------------------------
def validate(out: Path, items):
    """Every body of every item against the backend's own models, as the routes would read them."""
    sys.path.insert(0, str(REPO / 'src' / 'backend'))
    from apps.catalog.api.evidence_service import EvidenceBulkItem
    from apps.catalog.api.identity_edit import IdentityCreateBody
    from apps.catalog.api.snapshot_lifecycle import SnapshotDraftBody
    from apps.catalog.evidence.registry import EvidenceInvalid, prepare_record
    problems = []
    meshes = {}
    for item in items:
        try:
            if item['mesh_ply'] not in meshes:
                meshes[item['mesh_ply']] = inline_mesh(out, item)[0]
            body = identity_body(item, meshes[item['mesh_ply']])
            IdentityCreateBody.model_validate(body)
            SnapshotDraftBody.model_validate(body['snapshot'])
            for _, record in records_of(item, '00000000-0000-4000-8000-000000000000'):
                EvidenceBulkItem.model_validate(record)
                try:
                    prepare_record({k: v for k, v in record.items()
                                    if k not in ('identity_id', 'performed_by', 'notes', 'self_attested')})
                except EvidenceInvalid as exc:
                    raise ValueError(f'{record["method"]}: {exc}') from exc
        except Exception as error:     # noqa: BLE001 - report, keep going
            problems.append((item['key'], str(error).splitlines()[0][:300]))
    return problems


# ONE ITEM ---------------------------------------------------------------------
def run_item(api, out, item, stats, log):
    identity_id = item['identity']['id']
    mesh, xyz, tri = inline_mesh(out, item)
    found = api.request('GET', f'/identities/{identity_id}?expand=none')
    if found.status_code == 404:
        created = api.json('POST', '/identities', ok=(201,), json=identity_body(item, mesh))
        snapshot_id = created['snapshot']['_id']
        stats['identities'] += 1
    elif found.status_code == 200:
        passport = api.json('GET', f'/identities/{identity_id}/compose?snapshots=all')
        snapshot_id = passport['snapshots'][0]['_id']
        stats['existing'] += 1
    else:
        raise RuntimeError(f'GET {identity_id} -> {found.status_code}')
    current = api.json('GET', f'/snapshots/{snapshot_id}')
    if current.get('status') in ('rejected', 'withdrawn'):
        log(f'{item["key"]}: snapshot {snapshot_id} is {current["status"]}')
    if current.get('status') in ('draft', 'rejected'):
        if mesh_levels(len(tri))['save_original'] and 'detailed' not in (
                current.get('mesh_ply_resolutions') or {}).get('0', []):
            ply = write_ply_mesh(xyz, tri, item['snapshot']['color'])
            api.json('PUT', f'/snapshots/{snapshot_id}/meshes/0/detailed',
                     files={'mesh_file': ('detailed.ply', ply, 'application/octet-stream')})
            stats['ply'] += 1
        api.json('POST', f'/snapshots/{snapshot_id}/submit')
        api.json('POST', f'/snapshots/{snapshot_id}/publish?promote=1')
        stats['published'] += 1
    elif current.get('status') == 'pending':
        api.json('POST', f'/snapshots/{snapshot_id}/publish?promote=1')
        stats['published'] += 1
    have = {}
    for record in api.json('GET', f'/identities/{identity_id}/evidence?status=all&include=superseded') or []:
        ref = ((record.get('payload') or {}).get('document') or {}).get('reference')
        if ref:
            have[ref] = record
    fresh = [(ref, body) for ref, body in records_of(item, snapshot_id) if ref not in have]
    if fresh:
        result = api.json('POST', '/evidence/bulk', ok=(201,),
                          json={'records': [b for _, b in fresh], 'submit': True})
        for created in result['records']:
            api.json('POST', f'/evidence/{created["_id"]}/publish')
        stats['evidence'] += len(fresh)
    for record in have.values():
        if record.get('status') in ('rejected', 'withdrawn'):
            log(f'{item["key"]}: evidence record {record.get("_id")} is {record["status"]}')
    for record in have.values():           # an earlier run that stopped before publishing
        if record.get('status') == 'pending':
            api.json('POST', f'/evidence/{record["_id"]}/publish')
        elif record.get('status') == 'draft':
            api.json('POST', f'/evidence/{record["_id"]}/submit')
            api.json('POST', f'/evidence/{record["_id"]}/publish')


def ensure_datasets(api, plan, owner_id, log, wanted):
    have = {d['_id'] for d in api.json('GET', '/datasets')}
    for dataset in plan['datasets']:
        if dataset['id'] not in wanted:
            continue
        if dataset['id'] not in have:
            api.json('POST', '/datasets', ok=(201,), json={
                'id': dataset['id'], 'name': dataset['name'],
                'description': dataset['description'], 'visibility': 'members'})
            log(f'dataset {dataset["id"]} created')
        api.json('PUT', f'/datasets/{dataset["id"]}/members/{owner_id}',
                 json={'roles': ['moderator', 'contributor']})


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Write the ReCreate import plan through the CSC API.')
    parser.add_argument('--out', type=Path, default=common.DEFAULT_OUT,
                        help='folder with plan.json and the meshes (plan.py); the log goes here')
    parser.add_argument('--dry-run', action='store_true',
                        help='validate every body against the backend models and stop')
    parser.add_argument('--server', help='base URL of the CSC backend')
    parser.add_argument('--username', help='account to sign in with; the password is asked')
    parser.add_argument('--config', type=Path,
                        help='JSON with defaults for server and username (local rehearsal; never commit it)')
    parser.add_argument('--limit', type=int, help='only the first N elements')
    parser.add_argument('--only', help='key prefix, e.g. recreate:NL:')
    parser.add_argument('--dataset', help='only this dataset, e.g. recreate_nl')
    args = parser.parse_args(argv)
    if args.config:
        config = json.loads(args.config.read_text(encoding='utf-8'))
        args.server = args.server or config.get('server')
        args.username = args.username or config.get('username')
    return args


def main(argv=None):
    args = parse_args(argv)
    out = common.out_dir(args.out)
    if not (out / 'plan.json').is_file():
        sys.exit(f'no plan.json in {out}: run plan.py first')
    plan = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
    items = [i for i in plan['items'] if (not args.only or i['key'].startswith(args.only))
             and (not args.dataset or i['dataset'] == args.dataset)]
    if args.limit:
        items = items[:args.limit]
    logfile = out / f'run-{time.strftime("%Y%m%d-%H%M%S")}{"-dry" if args.dry_run else ""}.log'

    def log(text):
        line = f'{time.strftime("%H:%M:%S")} {text}'
        print(line, flush=True)
        with open(logfile, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    problems = validate(out, items)
    log(f'{len(items)} identities, {sum(len(i["evidence"]) for i in items)} evidence records; '
        f'{len(problems)} refused by the models')
    for key, message in problems[:30]:
        log(f'  refused {key}: {message}')
    if args.dry_run:
        return 1 if problems else 0
    if problems:
        sys.exit('fix the plan first (see the log)')
    if not args.server:
        sys.exit('--server is required (or a --config file with "server")')
    token, renew = common.get_token(args.server, args.username)
    api = Api(args.server, token, renew)
    owner_id = user_id_of(api.token)
    ensure_datasets(api, plan, owner_id, log, {i['dataset'] for i in items})
    stats = dict(identities=0, existing=0, published=0, ply=0, evidence=0)
    for number, item in enumerate(items, 1):
        try:
            run_item(api, out, item, stats, log)
        except Exception as error:   # noqa: BLE001 - one item must not stop the run
            log(f'{item["key"]}: FAILED {error}')
            stats['failed'] = stats.get('failed', 0) + 1
            continue
        if number % 50 == 0:
            log(f'{number}/{len(items)} {stats} ({api.calls} calls)')
    log(f'done: {stats} ({api.calls} calls)')
    return 0 if not stats.get('failed') else 1


if __name__ == '__main__':
    sys.exit(main())
