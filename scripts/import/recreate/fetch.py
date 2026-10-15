"""Fetch the ReCreate pilot element data from Zenodo and check it.

    python fetch.py [--dest <folder>] [--record 16809738] [--record-file record.json]

Downloads every file of the Zenodo record into `--dest` (default: the local rehearsal's data folder) and
writes the record's metadata as `record.json` next to that folder. Each file is checked against the MD5
sum of the record: a file that does not match is refused and deleted, and the command exits with 1. A file
already there whose sum matches is not fetched again, so the command can be run any number of times.
Standard library only; the data is never committed to the repository (decision 8.145).

Source: ReCreate (EU Horizon 2020, grant agreement 958200), "Reclaimed Precast Concrete Elements: Data
Collection Guidelines, Templates, & Pilot Element Data", https://doi.org/10.5281/zenodo.16809738, CC BY 4.0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List
from urllib.parse import urlsplit
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recreate_common as common  # noqa: E402

RECORD_ID = '16809738'
API = 'https://zenodo.org/api/records/{record}'
CHUNK = 1 << 20
TIMEOUT = 120

Opener = Callable[[str], object]       # url -> a binary file-like object (context manager)


def default_open(url: str):
    return urlopen(url, timeout=TIMEOUT)             # noqa: S310 -- https, the Zenodo API


def expected_md5(checksum: str) -> str:
    """``md5:<hex>`` of the record, as a bare lower-case hex string. Whitespace and carriage returns are
    stripped: a list read on Windows carries them (the first version of this check failed on them)."""
    kind, _, digest = str(checksum).strip().partition(':')
    if kind.strip().lower() != 'md5' or not digest.strip():
        raise ValueError(f'not an md5 checksum: {checksum!r}')
    return digest.strip().lower()


def md5_of(path: Path) -> str:
    digest = hashlib.md5()                           # noqa: S324 -- the record's own sum, not security
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


ALLOWED_HOST = 'zenodo.org'


def url_problem(url: str) -> str:
    """Why a file URL of the record is not fetched, or '' when it may be: only https, and only from
    zenodo.org (or a sub-domain of it). A record is data from the network; it must not be able to send
    this tool to a local file, a plain-http server or another site."""
    parts = urlsplit(str(url))
    host = (parts.hostname or '').lower()
    if parts.scheme != 'https':
        return f'the URL is not https ({parts.scheme or "no scheme"})'
    if host != ALLOWED_HOST and not host.endswith('.' + ALLOWED_HOST):
        return f'the host is not {ALLOWED_HOST} ({host or "none"})'
    return ''


def safe_name(key: str) -> str:
    """A file name of the record that cannot leave the destination folder."""
    if not key or key in ('.', '..') or '/' in key or '\\' in key or '\x00' in key:
        raise ValueError(f'unsafe file name in the record: {key!r}')
    return key


def load_record(record: str, record_file: Path = None, opener: Opener = default_open) -> Dict:
    """The record metadata: from a local JSON file (offline, tests) or from the Zenodo API."""
    if record_file is not None:
        return json.loads(Path(record_file).read_text(encoding='utf-8'))
    with opener(API.format(record=record)) as response:
        return json.loads(response.read().decode('utf-8'))


def download(url: str, target: Path, opener: Opener = default_open) -> str:
    """Download ``url`` to ``target`` through a temporary name; returns the MD5 of what arrived."""
    part = target.with_name(target.name + '.part')
    digest = hashlib.md5()                           # noqa: S324
    try:
        with opener(url) as response, open(part, 'wb') as handle:
            for block in iter(lambda: response.read(CHUNK), b''):
                digest.update(block)
                handle.write(block)
        part.replace(target)
    finally:
        part.unlink(missing_ok=True)
    return digest.hexdigest()


def sync(record: Dict, dest: Path, opener: Opener = default_open, log=print) -> Dict[str, List[str]]:
    """Bring ``dest`` in line with the record. Returns the names ``fetched``, ``skipped`` (already there
    with the right sum) and ``refused`` (the sum did not match; the file is deleted)."""
    dest.mkdir(parents=True, exist_ok=True)
    done: Dict[str, List[str]] = {'fetched': [], 'skipped': [], 'refused': []}
    for entry in record['files']:
        name = safe_name(entry['key'])
        want = expected_md5(entry['checksum'])
        target = dest / name
        if target.is_file() and md5_of(target) == want:
            log(f'  ok      {name}')
            done['skipped'].append(name)
            continue
        problem = url_problem(entry['links']['self'])
        if problem:
            log(f'  REFUSED {name}: {problem}; not fetched')
            done['refused'].append(name)
            continue
        got = download(entry['links']['self'], target, opener)
        if got != want:
            target.unlink(missing_ok=True)           # a wrong file is never kept
            log(f'  REFUSED {name}: md5 {got}, the record says {want}; deleted')
            done['refused'].append(name)
        else:
            log(f'  fetched {name}')
            done['fetched'].append(name)
    return done


def main(argv=None, opener: Opener = default_open) -> int:
    parser = argparse.ArgumentParser(description='Fetch the ReCreate pilot element data from Zenodo.')
    parser.add_argument('--dest', type=Path, default=common.DEFAULT_DATA,
                        help='folder for the files (default: the local rehearsal); record.json goes beside it')
    parser.add_argument('--record', default=RECORD_ID, help='Zenodo record id (default: %(default)s)')
    parser.add_argument('--record-file', type=Path,
                        help='read the record metadata from this JSON file instead of the Zenodo API')
    args = parser.parse_args(argv)
    dest = common.out_dir(args.dest, create=False)
    record = load_record(args.record, args.record_file, opener)
    licence = ((record.get('metadata') or {}).get('license') or {}).get('id')
    print(f'{record.get("doi", args.record)}: {len(record["files"])} files, licence {licence}')
    if licence != 'cc-by-4.0':
        print(f'warning: the licence is {licence!r}, not cc-by-4.0: read it before you use the data')
    done = sync(record, dest, opener)
    dest.parent.mkdir(parents=True, exist_ok=True)
    (dest.parent / 'record.json').write_text(json.dumps(record, indent=1, ensure_ascii=True),
                                             encoding='utf-8')
    print(f'{len(done["fetched"])} fetched, {len(done["skipped"])} already there, '
          f'{len(done["refused"])} refused -> {dest}')
    if done['refused']:
        return 1
    print('Attribution (CC BY 4.0): ReCreate, https://doi.org/10.5281/zenodo.16809738')
    return 0


if __name__ == '__main__':
    sys.exit(main())
