"""Run the EPFL stone import plan against a CSC backend over its HTTP API (decision 8.146).

    python run.py --dry-run                              validate every body offline, touch nothing
    python run.py --server URL --username NAME [--only A0,B7] [--limit N]

Run in an environment with the backend's packages (the `csc` conda environment): the dry run imports the
backend's request models. `--out` is the folder `prepare.py` and `plan.py` wrote (`plan.json` and
`stones/<ID>/...`).

Sign-in as in the ReCreate import: with `--username` the password is asked on the terminal (no echo) and
exchanged at `POST /auth/token`; or put a bearer token into CSC_IMPORT_TOKEN. `--config FILE` (optional,
never committed) holds defaults for `server` and `username`. The account must be an admin: the plan fixes
the dataset id, and only an admin may state a slug.

Per stone, as the Grasshopper client does it (decision 8.95): the identity is created with the inline
preview mesh and the inline point cloud; the `reduced` and `detailed` mesh files go up through
`PUT /snapshots/{id}/meshes/0/<level>` (a level the snapshot already lists in `mesh_ply_resolutions` is not
sent again), the full cloud through `PUT /snapshots/{id}/point_clouds/0.ply` (not sent again when the
snapshot lists the cloud in `point_cloud_files`, the marker the upload route sets); then the version is submitted
and published (`publish?promote=1`). Resumable: fixed identity ids (uuid5 of `epfl_stacking:<ID>`); a stone
that exists and is published is left alone (a published version is frozen), one that stopped in `draft`,
`rejected` or `pending` goes on from where it was. A second run creates nothing. The dataset is created
private (members only). Writes `<out>/run-<time>.log`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import epfl_common as epfl  # noqa: E402

common = epfl.common
REPO = common.REPO


def read_preview(out: Path, item) -> dict:
    return json.loads((out / item['files']['preview']).read_text(encoding='utf-8'))


def identity_body(item, preview) -> dict:
    snapshot = dict(item['snapshot'])
    snapshot['geometry'] = {'meshes': [preview['mesh']],
                            'point_clouds': [preview['cloud']] if preview.get('cloud') else [],
                            'proxies': []}
    return {**item['identity'], 'snapshot': snapshot}


# VALIDATION (dry run) ---------------------------------------------------------
def validate(out: Path, items):
    """Every body of every stone against the backend's own models, as the routes would read them."""
    sys.path.insert(0, str(REPO / 'src' / 'backend'))
    from apps.catalog.api.identity_edit import IdentityCreateBody
    from apps.catalog.api.snapshot_lifecycle import SnapshotDraftBody
    problems = []
    for item in items:
        try:
            body = identity_body(item, read_preview(out, item))
            IdentityCreateBody.model_validate(body)
            SnapshotDraftBody.model_validate(body['snapshot'])
            for level in ('reduced', 'detailed', 'cloud'):
                if level in item['files'] and not (out / item['files'][level]).is_file():
                    raise ValueError(f'the file {item["files"][level]} is missing')
        except Exception as error:     # noqa: BLE001 - report, keep going
            problems.append((item['key'], str(error).splitlines()[0][:300]))
    return problems


# ONE STONE ----------------------------------------------------------------------
def cloud_is_there(current) -> bool:
    """True when the snapshot already holds its full cloud as a file: the upload route lists the index in
    ``point_cloud_files`` once the file is written (a version uploaded before 0.6.2 has no marker: its cloud
    goes up again, which replaces the file)."""
    return 0 in (current.get('point_cloud_files') or [])


def upload(api, out: Path, item, snapshot_id, current, stats):
    """The files of a draft version that the snapshot does not have yet."""
    have = (current.get('mesh_ply_resolutions') or {}).get('0', [])
    for level in ('reduced', 'detailed'):
        if level in item['files'] and level not in have:
            data = (out / item['files'][level]).read_bytes()
            api.json('PUT', f'/snapshots/{snapshot_id}/meshes/0/{level}',
                     files={'mesh_file': (f'{level}.ply', data, 'application/octet-stream')})
            stats['ply'] += 1
    if 'cloud' in item['files']:
        path = out / item['files']['cloud']
        if not cloud_is_there(current):
            api.json('PUT', f'/snapshots/{snapshot_id}/point_clouds/0.ply',
                     files={'point_cloud_file': ('cloud.ply', path.read_bytes(), 'application/octet-stream')})
            stats['clouds'] += 1


def run_item(api, out: Path, item, stats, log):
    identity_id = item['identity']['id']
    found = api.request('GET', f'/identities/{identity_id}?expand=none')
    if found.status_code == 404:
        created = api.json('POST', '/identities', ok=(201,),
                           json=identity_body(item, read_preview(out, item)))
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
        upload(api, out, item, snapshot_id, current, stats)
        api.json('POST', f'/snapshots/{snapshot_id}/submit')
        api.json('POST', f'/snapshots/{snapshot_id}/publish?promote=1')
        stats['published'] += 1
    elif current.get('status') == 'pending':
        api.json('POST', f'/snapshots/{snapshot_id}/publish?promote=1')
        stats['published'] += 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Write the EPFL stone import plan through the CSC API.')
    parser.add_argument('--out', type=Path, default=epfl.DEFAULT_OUT,
                        help='folder with plan.json and stones/ (prepare.py, plan.py); the log goes here')
    parser.add_argument('--dry-run', action='store_true',
                        help='validate every body against the backend models and stop')
    parser.add_argument('--server', help='base URL of the CSC backend')
    parser.add_argument('--username', help='account to sign in with; the password is asked')
    parser.add_argument('--config', type=Path,
                        help='JSON with defaults for server and username (local rehearsal; never commit it)')
    parser.add_argument('--limit', type=int, help='only the first N stones')
    parser.add_argument('--only', help='comma-separated stone ids, e.g. A0,B7')
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
        sys.exit(f'no plan.json in {out}: run prepare.py and plan.py first')
    plan = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
    wanted = {s.strip() for s in (args.only or '').split(',') if s.strip()}
    items = [i for i in plan['items'] if not wanted or i['stone'] in wanted]
    if args.limit:
        items = items[:args.limit]
    logfile = out / f'run-{time.strftime("%Y%m%d-%H%M%S")}{"-dry" if args.dry_run else ""}.log'

    def log(text):
        line = f'{time.strftime("%H:%M:%S")} {text}'
        print(line, flush=True)
        with open(logfile, 'a', encoding='utf-8') as handle:
            handle.write(line + '\n')

    problems = validate(out, items)
    log(f'{len(items)} stones; {len(problems)} refused by the models')
    for key, message in problems[:30]:
        log(f'  refused {key}: {message}')
    if args.dry_run:
        return 1 if problems else 0
    if problems:
        sys.exit('fix the plan first (see the log)')
    if not args.server:
        sys.exit('--server is required (or a --config file with "server")')
    token, renew = common.get_token(args.server, args.username)
    api = common.Api(args.server, token, renew)
    owner_id = common.user_id_of(api.token)
    common.ensure_datasets(api, plan, owner_id, log, {i['dataset'] for i in items})
    stats = dict(identities=0, existing=0, published=0, ply=0, clouds=0)
    for number, item in enumerate(items, 1):
        try:
            run_item(api, out, item, stats, log)
        except Exception as error:   # noqa: BLE001 - one stone must not stop the run
            log(f'{item["key"]}: FAILED {error}')
            stats['failed'] = stats.get('failed', 0) + 1
            continue
        if number % 25 == 0:
            log(f'{number}/{len(items)} {stats} ({api.calls} calls)')
    log(f'done: {stats} ({api.calls} calls)')
    return 0 if not stats.get('failed') else 1


if __name__ == '__main__':
    sys.exit(main())
