"""Fetch the EPFL augmented-stacking stone dataset from Zenodo, check it and unpack it.

    python fetch.py [--dest <folder>] [--unpack-to <folder>] [--record 7180964] [--record-file record.json]

Downloads the release archive of the Zenodo record (631 MB) into `--dest` (default: the local rehearsal's
data folder), checks its MD5 sum against the record (a mismatching file is refused and deleted, exit code
1) and unpacks it into `--unpack-to` (default `<dest>/unpacked`) by a checked extraction: a member with an
absolute path, a drive letter, a `..` part, a backslash or a name that would land outside the folder is
refused and nothing is extracted from an archive that holds one. The bytes actually written are counted as
they are written and the extraction stops (the partial member is deleted, exit code 1) when they pass the
limit, whatever sizes the archive declares. A second run downloads nothing (the sum
matches) and extracts only what is missing or of another size. Standard library only; the data is never
committed to the repository (decision 8.146).

Source: "Dataset of mineral scraps for augmented stacking", IBOIS / EESD, EPFL, release v1,
https://doi.org/10.5281/zenodo.7180964, MIT licence.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import epfl_common as epfl  # noqa: E402

common = epfl.common

MAX_MEMBERS = 5000
MAX_UNPACKED_BYTES = 4 << 30                   # the archive is 631 MB; a bomb is not
CHUNK = 1 << 20


def flat_name(key: str) -> str:
    """The file name under ``--dest`` of a key of the record: the record keys the archive with its folder
    (``<owner>/<file>.zip``); each part must be a plain name, and the file lands in ``--dest`` itself."""
    parts = str(key).split('/')
    for part in parts:
        common.safe_name(part)
    return parts[-1]


def member_problem(name: str) -> str:
    """Why an archive member must not be extracted, or '' when its name is fine."""
    if not name or '\x00' in name:
        return 'empty or unprintable name'
    if '\\' in name:
        return 'backslash in the name'
    if name.startswith('/') or PurePosixPath(name).is_absolute():
        return 'absolute path'
    if PureWindowsPath(name).drive or PureWindowsPath(name).anchor:
        return 'drive letter or rooted path'
    if any(part == '..' for part in name.split('/')):
        return 'parent folder (..) in the path'
    return ''


def check_archive(archive: zipfile.ZipFile) -> List[str]:
    """Every problem of the archive's names and sizes, one line each; empty when it may be extracted."""
    problems = []
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS:
        problems.append(f'{len(infos)} members (more than {MAX_MEMBERS})')
    if sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
        problems.append(f'more than {MAX_UNPACKED_BYTES >> 30} GB unpacked')
    for info in infos:
        why = member_problem(info.filename)
        if why:
            problems.append(f'{info.filename!r}: {why}')
    return problems


def extract(zip_path: Path, target: Path, log: Callable[[str], None] = print) -> Dict[str, int]:
    """Unpack ``zip_path`` into ``target``: every name is checked first (nothing is written when one is
    refused), every file goes to a path that is resolved and must stay under ``target``. The bytes written
    are counted in the write loop, across the whole archive: when the total passes ``MAX_UNPACKED_BYTES`` the
    partial member is deleted and the extraction stops with a ``ValueError``, whatever the central directory
    declared. Files already there with the right size are left alone, so the call is idempotent. Returns
    counts."""
    target = Path(target)
    root = target.resolve()
    counts = {'written': 0, 'present': 0, 'folders': 0}
    total = 0
    with zipfile.ZipFile(zip_path) as archive:
        problems = check_archive(archive)
        if problems:
            raise ValueError('refusing to extract ' + Path(zip_path).name + ': ' + '; '.join(problems[:5]))
        target.mkdir(parents=True, exist_ok=True)
        for info in archive.infolist():
            path = (root / info.filename).resolve()
            if root != path and root not in path.parents:        # belt and braces after the name check
                raise ValueError(f'refusing to extract {info.filename!r}: it would land outside {root}')
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                counts['folders'] += 1
                continue
            if path.is_file() and path.stat().st_size == info.file_size:
                counts['present'] += 1
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            too_much = False
            with archive.open(info) as source, open(path, 'wb') as handle:
                for block in iter(lambda: source.read(CHUNK), b''):
                    total += len(block)
                    if total > MAX_UNPACKED_BYTES:
                        too_much = True
                        break
                    handle.write(block)
            if too_much:
                path.unlink(missing_ok=True)                 # the partial member is never kept
                raise ValueError(f'refusing to go on with {Path(zip_path).name}: more than '
                                 f'{MAX_UNPACKED_BYTES} bytes written (at {info.filename!r}); the partial '
                                 f'file is deleted')
            counts['written'] += 1
    log(f'  unpacked: {counts["written"]} written, {counts["present"]} already there, '
        f'{counts["folders"]} folders -> {target}')
    return counts


def main(argv=None, opener: common.Opener = common.default_open) -> int:
    parser = argparse.ArgumentParser(description='Fetch the EPFL stone dataset from Zenodo and unpack it.')
    parser.add_argument('--dest', type=Path, default=epfl.DEFAULT_DATA,
                        help='folder for the archive (default: the local rehearsal); record.json goes beside it')
    parser.add_argument('--unpack-to', type=Path, help='folder for the unpacked files (default: <dest>/unpacked)')
    parser.add_argument('--record', default=epfl.RECORD_ID, help='Zenodo record id (default: %(default)s)')
    parser.add_argument('--record-file', type=Path,
                        help='read the record metadata from this JSON file instead of the Zenodo API')
    args = parser.parse_args(argv)
    dest = common.out_dir(args.dest, create=False)
    unpack = common.out_dir(args.unpack_to or dest / 'unpacked', create=False)
    record = common.load_record(args.record, args.record_file, opener)
    metadata = record.get('metadata') or {}
    print(f'{record.get("doi", args.record)}: {len(record["files"])} file(s), '
          f'licence of the record: {(metadata.get("license") or {}).get("id")} (the README says MIT)')
    done = common.sync(record, dest, opener, local_name=flat_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    (dest.parent / 'record.json').write_text(json.dumps(record, indent=1, ensure_ascii=True), encoding='utf-8')
    print(f'{len(done["fetched"])} fetched, {len(done["skipped"])} already there, '
          f'{len(done["refused"])} refused -> {dest}')
    if done['refused']:
        return 1
    for name in done['fetched'] + done['skipped']:
        if name.lower().endswith('.zip'):
            try:
                extract(dest / name, unpack)
            except (ValueError, zipfile.BadZipFile) as error:
                print(f'  REFUSED {name}: {error}')
                return 1
    print('Attribution (MIT licence): IBOIS / EESD, EPFL, https://doi.org/' + epfl.DOI)
    return 0


if __name__ == '__main__':
    sys.exit(main())
