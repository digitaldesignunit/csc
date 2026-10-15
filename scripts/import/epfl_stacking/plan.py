"""Plan the import of the EPFL stones (decision 8.146): one component per stone, no evidence.

    python -I -X utf8 plan.py [--out <out folder>] [--data <dataset folder>]

Input: `<out>/prepare.json` (prepare.py) and the dataset's README (for the authors of its citation, read at
run time: no name is written into this repository). Output: `<out>/plan.json` (the records `run.py` writes,
as plain JSON; the meshes and the cloud as paths into `<out>/stones/<ID>/`) and `<out>/report.md`. Nothing is
written to a server. Standard library only.

Per stone: key `epfl_stacking:<ID>`, a uuid5 id (so a run is resumable), dataset `epfl_stacking`, material
`natural_stone`, the original function `IfcBuildingElementProxy` (the data names none; the backend requires one
for a component without parents, and this is the vocabulary's "unknown"), origin `offcut` (quarry extraction, no date), the group and file names
in `attributes.epfl_stacking`; version 0 named "Stone <ID>", effective from the publication date of the
dataset (day precision; the capture notes say it is not the scan date), the colour of the stone is the mean of
its scan; no capture method (the vocabulary has none for a Rhino export of a scan), the software and the
source in the capture notes.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import epfl_common as epfl  # noqa: E402

common = epfl.common
NAMESPACE = uuid.UUID(epfl.NAMESPACE)
EFFECTIVE = epfl.RELEASE_DATE + 'T00:00:00Z'
# the data names no function; a component without parents needs one: the generic one (shown as "Unknown")
ORIGINAL_FUNCTION = 'IfcBuildingElementProxy'
SOFTWARE = ('Rhino 7 export; Poisson remesh (Cockroach_MeshPoisson) of the scanned cloud, per the dataset\'s '
            'util/rh_pcd_2_mesh.py')


def uid(key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, 'csc-import/' + key))


def attribution(authors) -> str:
    who = ', '.join(authors[:-1]) + (' and ' if len(authors) > 1 else '') + authors[-1] if authors else ''
    return (f'Source: "{epfl.TITLE}", {who}, IBOIS and EESD, EPFL, release v1, {epfl.RELEASE_DATE}, '
            f'{epfl.DOI_URL} (GitHub ibois-epfl/augmented-stacking-dataset, {epfl.GITHUB_URL}), licensed '
            f'under the MIT licence. Mineral scraps from quarry extraction: a scanned point cloud and a '
            f'Poisson mesh of each stone. Imported unchanged in substance: the meshes are reduced to the '
            f'levels of the Grasshopper client (the original is kept), the point clouds are multiplied by '
            f'1000 (metres to millimetres, to match the meshes). The date of each version is the '
            f'publication date of the dataset, not the date of the scan.')


def dataset_entry(authors, count: int) -> dict:
    if not authors:
        raise ValueError('no authors: the dataset\'s README holds no BibTeX author field')
    return {'id': epfl.DATASET_ID, 'name': epfl.DATASET_NAME,
            'description': f'{count} stones of the augmented-stacking inventory. ' + attribution(authors)}


def capture_notes(meta) -> str:
    notes = (f'Source: {epfl.TITLE}, release v1 (published {epfl.RELEASE_DATE}), {epfl.DOI_URL}. Mesh '
             f'{meta["mesh_file"]} ({meta["faces"]} faces, mm, centred at the origin) and point cloud '
             f'{meta["cloud_file"]} ({meta["cloud"]["points"]} points). The version is dated with the '
             f'publication date of the dataset, not the scan date.')
    levels = meta['levels']
    if levels['reduced_faces'] or levels['preview_faces'] != meta['faces']:
        notes += (f' Reductions by quadric decimation, colours of the nearest original vertex: preview '
                  f'{levels["preview_faces"]} faces' +
                  (f', reduced {levels["reduced_faces"]} faces' if levels['reduced_faces'] else '') +
                  '; the original mesh is kept.')
    factor = meta['cloud'].get('scale_to_mesh_unit')
    if factor and factor != 1.0:
        notes += f' The point cloud is in metres in the source files and multiplied by {factor:g} here.'
    if not meta['watertight']:
        notes += ' The mesh is not watertight (kept as published).'
    return notes[:2000]


def item(meta) -> dict:
    stone_id = meta['id']
    key = f'{epfl.DATASET_ID}:{stone_id}'
    folder = f'stones/{stone_id}/'
    files = {'preview': folder + 'preview.json'}
    for name in ('reduced', 'detailed'):
        if name + '.ply' in meta['files']:
            files[name] = folder + name + '.ply'
    if 'cloud.ply' in meta['files']:
        files['cloud'] = folder + 'cloud.ply'
    identity = {
        'id': uid(key), 'dataset': epfl.DATASET_ID, 'original_function': ORIGINAL_FUNCTION,
        'material': 'natural_stone', 'is_public': False,
        'origin': {'kind': 'offcut', 'planned': False, 'at_precision': 'unknown',
                   'notes': 'Quarry extraction offcut'},
        'attributes': {epfl.DATASET_ID: {
            'run': epfl.RUN, 'id': stone_id, 'group': meta['group'], 'mesh_file': meta['mesh_file'],
            'cloud_file': meta['cloud_file'], 'doi': epfl.DOI, 'faces': meta['faces'],
            'watertight': meta['watertight']}}}
    snapshot = {
        'name': f'Stone {stone_id}', 'quantity': 1, 'effective_from': EFFECTIVE,
        'effective_from_precision': 'day',
        'capture': {'software': SOFTWARE, 'notes': capture_notes(meta)}}
    if meta.get('mean_color'):
        snapshot['color'] = meta['mean_color']
    return {'key': key, 'dataset': epfl.DATASET_ID, 'group': meta['group'], 'stone': stone_id,
            'files': files, 'cloud_inline': meta['cloud']['inline_points'], 'watertight': meta['watertight'],
            'faces': meta['faces'], 'identity': identity, 'snapshot': snapshot}


def report(items, dataset, skipped) -> str:
    groups = Counter(i['group'] for i in items)
    lines = ['# EPFL stones: import plan', '', f'Run `{epfl.RUN}`; source {epfl.DOI_URL}.', '',
             f'Dataset `{dataset["id"]}`: {dataset["name"]}', '',
             f'{len(items)} components (no evidence records): ' +
             ', '.join(f'{g} {n}' for g, n in sorted(groups.items())) + '.', '',
             f'Not watertight: {sum(not i["watertight"] for i in items)}; with a reduced file: '
             f'{sum("reduced" in i["files"] for i in items)}; with a detailed file: '
             f'{sum("detailed" in i["files"] for i in items)}; with a full cloud file: '
             f'{sum("cloud" in i["files"] for i in items)}.', '', '## Notes', '']
    lines += [f'- {s}' for s in skipped] or ['- none']
    return '\n'.join(lines) + '\n'


def main(out: Path, data: Path) -> int:
    prepared = json.loads((out / 'prepare.json').read_text(encoding='utf-8'))
    readme = epfl.readme_of(epfl.find_root(data))
    if readme is None:
        sys.exit(f'no README.md in the dataset folder {data}: run fetch.py first')
    authors = epfl.bibtex_authors(readme)
    stones = [m for m in prepared['stones'] if 'error' not in m]
    dataset = dataset_entry(authors, len(stones))
    items, skipped = [], [f'{m["id"]}: failed to prepare' for m in prepared['stones'] if 'error' in m]
    for meta in stones:
        if meta['cloud'].get('scale_to_mesh_unit') is None:
            skipped.append(f'{meta["id"]}: imported without its cloud (it does not match the mesh in size)')
        items.append(item(meta))
    plan = {'run': epfl.RUN, 'source': epfl.DOI_URL, 'datasets': [dataset], 'items': items}
    (out / 'plan.json').write_text(json.dumps(plan, ensure_ascii=True), encoding='utf-8')
    (out / 'plan-report.md').write_text(report(items, dataset, skipped), encoding='ascii', errors='replace')
    print(f'{len(items)} items, {len(skipped)} skipped')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plan the import of the EPFL stones.')
    parser.add_argument('--out', type=Path, default=epfl.DEFAULT_OUT, help='folder with prepare.json')
    parser.add_argument('--data', type=Path, default=epfl.DEFAULT_DATA,
                        help='the dataset folder (for the README\'s citation)')
    args = parser.parse_args()
    out = common.out_dir(args.out)
    if not (out / 'prepare.json').is_file():
        sys.exit(f'no prepare.json in {out}: run prepare.py first')
    sys.exit(main(out, args.data))
