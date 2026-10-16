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
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recreate_common as common  # noqa: E402

# the checks and the download live in recreate_common (the EPFL fetch step uses them too); the names stay
# here for callers and tests
from recreate_common import (  # noqa: E402,F401
    ALLOWED_HOST, API, CHUNK, TIMEOUT, Opener, default_open, download, expected_md5, load_record, md5_of,
    safe_name, sync, url_problem)

RECORD_ID = '16809738'


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
