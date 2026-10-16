"""Paths, constants and readers shared by the EPFL stone import scripts (decision 8.146).

The scripts run with ``python -I`` (the data is untrusted), which leaves the script's own folder off
``sys.path``; each script inserts this folder and the folder of ``recreate_common`` itself before importing.
Defaults are the places of the local rehearsal (under the git-ignored ``.dev/``); every one is an argument
of the scripts. The shared guards (output paths, local database, sign-in, Zenodo checks) are the ones of
``scripts/import/recreate/recreate_common.py``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'recreate'))
import recreate_common as common  # noqa: E402

DEFAULT_DATA = common.DOT_DEV / 'open_datasets' / 'epfl_stacking' / 'zenodo-7180964'
DEFAULT_OUT = common.DOT_DEV / 'import_open' / 'epfl_stacking' / 'out'

RECORD_ID = '7180964'
DOI = '10.5281/zenodo.7180964'
DOI_URL = 'https://doi.org/' + DOI
GITHUB_URL = 'https://github.com/ibois-epfl/augmented-stacking-dataset/tree/v1'
TITLE = 'Dataset of mineral scraps for augmented stacking'
RELEASE_DATE = '2022-10-10'
RUN = 'epfl-stacking-2026-10-15'
DATASET_ID = 'epfl_stacking'
DATASET_NAME = 'EPFL: Mineral scraps for augmented stacking'
NAMESPACE = '5d2e7c1a-3b94-4f60-8a17-c9e04b6f2d38'

STONE_ID = re.compile(r'^[A-Z]\d+$')
MESH_NAME = re.compile(r'^remeshed_high_res_(?P<id>[A-Z]\d+)\.ply$')
CLOUD_NAME = re.compile(r'^pcd_high_res_(?P<id>[A-Z]\d+)\.ply$')
MM_RANGE = (20.0, 3000.0)          # the extents of a stone, mm; anything outside is flagged, never "fixed"


def find_root(data: Path) -> Path:
    """The folder that holds ``stones/``: ``data`` itself, ``data/unpacked`` or the one folder inside it
    (a GitHub archive unpacks into ``<owner>-<repo>-<commit>``)."""
    data = Path(data)
    for base in (data, data / 'unpacked'):
        if (base / 'stones').is_dir():
            return base
        if base.is_dir():
            inside = [p for p in sorted(base.iterdir()) if (p / 'stones').is_dir()]
            if len(inside) == 1:
                return inside[0]
    raise FileNotFoundError(f'no stones/ folder in {data}: run fetch.py first')


def stone_files(root: Path) -> Dict[str, Tuple[Path, Path]]:
    """``{stone id: (mesh file, cloud file)}`` of a dataset folder, in the order of the ids (letter, then
    number). A stone with only one of the two files is an error."""
    meshes = {m['id']: p for p in (Path(root) / 'stones' / 'mesh_high_res').glob('*.ply')
              if (m := MESH_NAME.match(p.name))}
    clouds = {m['id']: p for p in (Path(root) / 'stones' / 'pcd_high_res').glob('*.ply')
              if (m := CLOUD_NAME.match(p.name))}
    if set(meshes) != set(clouds):
        odd = sorted(set(meshes) ^ set(clouds))
        raise ValueError(f'stones with a mesh or a cloud but not both: {", ".join(odd[:10])}')
    return {sid: (meshes[sid], clouds[sid]) for sid in sorted(meshes, key=sort_key)}


def sort_key(stone_id: str):
    return stone_id[0], int(stone_id[1:])


def group_of(stone_id: str) -> str:
    return stone_id[0]


def bibtex_authors(readme: str) -> List[str]:
    """The ``author`` field of the BibTeX snippet of the dataset's README, as a list of names (read at run
    time: no name is written into this repository). BibTeX separates authors with ``and``; a value in
    braces or quotes may span lines. An empty list when there is no such field."""
    match = re.search(r'\bauthor\s*=\s*(?:\{(?P<b>[^}]*)\}|"(?P<q>[^"]*)")', readme, re.I)
    if not match:
        return []
    value = re.sub(r'\s+', ' ', match.group('b') if match.group('b') is not None else match.group('q'))
    authors = []
    for name in re.split(r'\s+and\s+', value.strip(), flags=re.I):
        name = name.strip()
        if ',' in name:                              # "Last, First" -> "First Last"
            last, _, first = name.partition(',')
            name = f'{first.strip()} {last.strip()}'.strip()
        if name:
            authors.append(name)
    return authors


def readme_of(root: Path) -> Optional[str]:
    path = Path(root) / 'README.md'
    return path.read_text(encoding='utf-8', errors='replace') if path.is_file() else None
