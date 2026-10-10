#!/usr/bin/env python3
"""
Copy the provenance (``origin``) of one component and the capture details of
its first version (v0) to every other component of a dataset, through the API.

Going through the API keeps every rule of a web edit: validation, the change
log (8.36), lineage propagation to inheriting children (8.31) and the freeze
of published capture fields (a published v0 only gets fields that are still
empty, once, 8.123 a; a field that already holds another value is reported,
never overwritten).

What is copied:

* ``origin`` of the source identity, except ``place`` and
  ``position_in_work``: those stay as each target has them (set per piece).
* with ``--contractor`` (and ``--contractor-url``): the organisation that
  performed the deinstallation is first added to the source's
  ``origin.performed_by`` (its website into ``origin.notes``, since an actor
  has no link field), then copied with the rest.
* from the source's v0 capture: ``--capture-fields`` (default ``method``,
  ``device``, ``software``, ``coordinate_system``). ``markers`` and
  ``fixtures`` are never copied: they belong to one scan.
* ``--set-capture FIELD=VALUE`` (repeatable) sets a v0 capture field to a
  given value on every component, the source included; like a copy it fills
  only empty fields.

v0 is the snapshot with ``version`` 0, or the correction that replaced it.
Withdrawn components and the source itself are skipped. Without ``--apply``
nothing is written: the run prints what it would change.

Sign-in: ``CSC_TOKEN`` (a bearer token, e.g. from ``POST /auth/token``), else
the script asks for username and password. The account must moderate the
dataset (or be an admin).

Usage::

    python scripts/db_maintenance/copy_provenance_capture.py \\
        --server https://api.2ndchances.build --dataset dbu_zirkus \\
        --source <identity id> \\
        --contractor "<company>" --contractor-url https://...
    # the same with --apply to write
"""

from __future__ import annotations

import argparse
import copy
import getpass
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

CLIENT = 'catalog-import/0.1'   # a client the server knows (8.11)
DEFAULT_CAPTURE = ('method', 'device', 'software', 'coordinate_system')
NEVER_CAPTURE = ('markers', 'fixtures')
KEEP_FROM_TARGET = ('place', 'position_in_work')


class Api:
    def __init__(self, server: str, token: str):
        self.server = server.rstrip('/')
        self.http = requests.Session()
        self.http.headers.update({'Authorization': f'Bearer {token}',
                                  'X-CSC-Client': CLIENT})

    def call(self, method: str, path: str, **kwargs) -> requests.Response:
        for attempt in range(5):
            try:
                response = self.http.request(
                    method, self.server + path, timeout=120, **kwargs)
            except requests.ConnectionError as exc:
                print(f'  connection problem ({exc}); retrying')
                time.sleep(2 + 2 * attempt)
                continue
            if response.status_code == 429:
                wait = float(response.headers.get('Retry-After') or 10)
                print(f'  rate limited; waiting {wait:.0f} s')
                time.sleep(wait)
                continue
            return response
        raise SystemExit(f'giving up on {method} {path}')

    def get(self, path: str, **params) -> Any:
        response = self.call('GET', path, params=params)
        if response.status_code != 200:
            raise SystemExit(f'GET {path}: {response.status_code} '
                             f'{response.text[:300]}')
        return response.json()

    def patch(self, path: str, body: Dict[str, Any]) -> Tuple[bool, str]:
        response = self.call('PATCH', path, json=body)
        if response.status_code == 200:
            return True, 'ok'
        return False, f'{response.status_code} {response.text[:300]}'


def sign_in(server: str) -> str:
    token = os.environ.get('CSC_TOKEN')
    if token:
        return token
    username = input('username: ').strip()
    password = getpass.getpass('password: ')
    response = requests.post(
        server.rstrip('/') + '/auth/token',
        data={'username': username, 'password': password},
        headers={'X-CSC-Client': CLIENT}, timeout=60)
    if response.status_code != 200:
        raise SystemExit(f'sign-in failed: {response.status_code}')
    return response.json()['access_token']


def first_version(api: Api, identity_id: str) -> Optional[Dict[str, Any]]:
    """v0, or the correction that took its place (follows superseded_by)."""
    rows = api.get(f'/identities/{identity_id}/snapshots')
    by_id = {row['_id']: row for row in rows}
    v0 = next((row for row in rows if row.get('version') == 0), None)
    seen = set()
    while v0 is not None and v0.get('superseded_by') \
            and v0['superseded_by'] in by_id and v0['_id'] not in seen:
        seen.add(v0['_id'])
        v0 = by_id[v0['superseded_by']]
    if v0 is None:
        return None
    return api.get(f'/snapshots/{v0["_id"]}')


def label(identity: Dict[str, Any]) -> str:
    number = identity.get('catalog_number')
    name = identity.get('name') or ''
    return f'#{number} {name} ({identity["_id"]})'.replace('  ', ' ')


def merged_origin(source: Dict[str, Any],
                  target: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = copy.deepcopy(source)
    for key in KEEP_FROM_TARGET:
        # the target's own value, also when empty (the copy never fills it)
        out[key] = copy.deepcopy(target.get(key)) if target else None
    return out


def with_contractor(origin: Dict[str, Any], name: str,
                    url: Optional[str]) -> Dict[str, Any]:
    """``origin`` with the organisation among its performers (once) and,
    with ``url``, a line naming its website in the notes (once)."""
    out = copy.deepcopy(origin)
    performers = list(out.get('performed_by') or [])
    if not any(p.get('kind') == 'organization'
               and p.get('organization') == name for p in performers):
        performers.append({'kind': 'organization', 'organization': name,
                           'role': 'operator'})
    out['performed_by'] = performers
    if url:
        line = f'Deinstallation by {name}: {url}'
        notes = out.get('notes') or ''
        if url not in notes:
            out['notes'] = f'{notes}\n{line}'.strip() if notes else line
    return out


def parse_set_capture(items: List[str]) -> Dict[str, Any]:
    """``FIELD=VALUE`` pairs; a ``captured_at`` date becomes its midnight
    in UTC (a day-precise instant, 8.91 b)."""
    out: Dict[str, Any] = {}
    for item in items:
        field, sep, value = item.partition('=')
        field = field.strip()
        if not sep or not field:
            raise SystemExit(f'--set-capture needs FIELD=VALUE, got {item!r}')
        if field == 'captured_at':
            try:
                day = datetime.strptime(value.strip(), '%Y-%m-%d')
            except ValueError:
                raise SystemExit('captured_at takes a date, YYYY-MM-DD')
            value = day.strftime('%Y-%m-%dT00:00:00Z')
        out[field] = value
    return out


def empty(value: Any) -> bool:
    return value in (None, '', [], {})


def normal(value: Any) -> Any:
    """``value`` without empty members, so a stored (dumped) block and the
    same block built here compare equal."""
    if isinstance(value, dict):
        return {k: normal(v) for k, v in value.items() if not empty(v)}
    if isinstance(value, list):
        return [normal(v) for v in value]
    return value


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--server', required=True)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--source', required=True,
                        help='identity id of the component to copy from')
    parser.add_argument('--capture-fields', default=','.join(DEFAULT_CAPTURE),
                        help='v0 capture fields to copy (comma list; '
                             'markers and fixtures are never copied)')
    parser.add_argument('--no-origin', action='store_true',
                        help='copy the capture fields only')
    parser.add_argument('--contractor',
                        help='organisation that performed the deinstallation:'
                             ' added to origin.performed_by (role operator) '
                             'of the source first, then copied with it')
    parser.add_argument('--contractor-url',
                        help='its website; an actor has no link field, so it '
                             'goes into origin.notes')
    parser.add_argument('--set-capture', action='append', default=[],
                        metavar='FIELD=VALUE',
                        help='set a v0 capture field to this value on every '
                             'component, the source included (repeatable; '
                             'captured_at takes a date, YYYY-MM-DD)')
    parser.add_argument('--apply', action='store_true',
                        help='write; without it the run only reports')
    args = parser.parse_args(argv)

    capture_fields = [f.strip() for f in args.capture_fields.split(',')
                      if f.strip()]
    set_capture = parse_set_capture(args.set_capture)
    bad = [f for f in [*capture_fields, *set_capture] if f in NEVER_CAPTURE]
    if bad:
        raise SystemExit(f'never copied (one scan only): {", ".join(bad)}')

    api = Api(args.server, sign_in(args.server))
    source = api.get(f'/identities/{args.source}', expand='none')
    if source.get('dataset') != args.dataset:
        raise SystemExit(f'the source is in dataset {source.get("dataset")!r}'
                         f', not {args.dataset!r}')
    source_origin = source.get('origin')
    if not args.no_origin and not source_origin:
        raise SystemExit('the source has no provenance (origin) to copy')
    if args.contractor and not args.no_origin:
        updated = with_contractor(source_origin, args.contractor,
                                  args.contractor_url)
        if normal(updated) != normal(source_origin):
            print(f'source origin: add {args.contractor} as performer')
            if args.apply:
                ok, message = api.patch(f'/identities/{args.source}',
                                        {'origin': updated})
                if not ok:
                    raise SystemExit(f'source origin FAILED: {message}')
            source_origin = updated
    source_v0 = first_version(api, args.source)
    source_capture = (source_v0 or {}).get('capture') or {}
    wanted_capture = {f: source_capture[f] for f in capture_fields
                      if not empty(source_capture.get(f))}
    wanted_capture.update(set_capture)
    print(f'source {label(source)}')
    if not args.no_origin:
        shown = {k: v for k, v in source_origin.items()
                 if k not in KEEP_FROM_TARGET}
        print('  origin (without place, position_in_work):')
        print('   ', json.dumps(shown, ensure_ascii=True)[:600])
    print('  v0 capture:', json.dumps(wanted_capture, ensure_ascii=True)
          if wanted_capture else '(none of the chosen fields is set)')

    targets = api.get('/identities', dataset=args.dataset, expand='none',
                      page=0, size=0)
    if not set_capture:
        # a copy leaves the source alone; set values go to every v0
        targets = [t for t in targets if t['_id'] != args.source]
    print(f'{len(targets)} components in {args.dataset}'
          f'{"" if args.apply else " (dry run)"}\n')

    counts = {'origin': 0, 'capture': 0, 'conflicts': 0, 'skipped': 0,
              'failed': 0}
    for target in sorted(targets, key=lambda t: t.get('catalog_number') or 0):
        print(label(target))
        if target.get('withdrawn'):
            print('  withdrawn: skipped')
            counts['skipped'] += 1
            continue

        if not args.no_origin:
            new = merged_origin(source_origin, target.get('origin'))
            if normal(new) == normal(target.get('origin')):
                print('  origin: already the same')
            else:
                if 'origin' in (target.get('inherited_fields') or []):
                    print('  origin: inherited from a parent today; the '
                          'copy makes it the component\'s own')
                print('  origin: set'
                      + ('' if target.get('origin') else ' (was empty)'))
                if args.apply:
                    ok, message = api.patch(f'/identities/{target["_id"]}',
                                            {'origin': new})
                    if not ok:
                        print(f'  origin FAILED: {message}')
                        counts['failed'] += 1
                    else:
                        counts['origin'] += 1
                else:
                    counts['origin'] += 1

        if not wanted_capture:
            continue
        v0 = first_version(api, target['_id'])
        if v0 is None:
            print('  v0: none')
            continue
        have = v0.get('capture') or {}
        fill, conflicts = {}, []
        for field, value in wanted_capture.items():
            if empty(have.get(field)):
                fill[field] = value
            elif have.get(field) != value:
                conflicts.append(field)
        for field in conflicts:
            print(f'  v0 capture.{field}: holds another value, left as it is '
                  f'({json.dumps(have.get(field), ensure_ascii=True)[:120]})')
        counts['conflicts'] += len(conflicts)
        if not fill:
            if not conflicts:
                print('  v0 capture: already the same')
            continue
        print(f'  v0 capture: fill {", ".join(sorted(fill))} '
              f'(snapshot {v0["_id"]}, {v0.get("status")})')
        if args.apply:
            ok, message = api.patch(f'/snapshots/{v0["_id"]}',
                                    {'capture': fill})
            if not ok:
                print(f'  v0 capture FAILED: {message}')
                counts['failed'] += 1
            else:
                counts['capture'] += 1
        else:
            counts['capture'] += 1

    verb = 'changed' if args.apply else 'would change'
    print(f'\n{verb}: origin {counts["origin"]}, v0 capture {counts["capture"]}'
          f'; capture conflicts {counts["conflicts"]}, skipped '
          f'{counts["skipped"]}, failed {counts["failed"]}')
    return 1 if counts['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
