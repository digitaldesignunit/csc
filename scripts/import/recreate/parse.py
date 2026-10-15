"""Parse the ReCreate pilot element data as published on Zenodo.

    python -I -X utf8 parse.py [--data <zenodo folder>] [--out <out folder>]

Reads the folder (fetch.py puts it there) exactly as published at https://doi.org/10.5281/zenodo.16809738
(`<Type> Data - <Pilot>.xlsx`, `Site Metadata - <Pilot>.xlsx`, the
`<Type> Template.xlsx` files) and writes `parsed.json` plus `structure.md`.
Columns are found by their header text (three header rows: section, field,
sub-field), never by position: the pilot files differ from the templates
(e.g. the Dutch HCS sheet has no density column). Nothing is interpreted
here beyond grouping; the planner maps the result to CSC records.

Untrusted input: run with `python -I`, the data folder is only read. Needs openpyxl
(requirements-import.txt).
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import openpyxl  # noqa: E402
import recreate_common as common  # noqa: E402

ZENODO = {'record': '16809738', 'doi': '10.5281/zenodo.16809738',
          'url': 'https://doi.org/10.5281/zenodo.16809738',
          'licence': 'CC-BY-4.0'}
DATA_FILE = re.compile(r'^(?P<type>Wall|HCS|Slab|Beam|Column) Data - (?P<pilot>\w+)\.xlsx$')
SITE_FILE = re.compile(r'^Site Metadata - (?P<pilot>\w+)\.xlsx$')
TEMPLATE_FILE = re.compile(r'^(?P<type>Wall|HCS|Slab|Beam|Column|Site Metadata) Template\.xlsx$')
ID_SHEETS = ('Wall ID', 'Wall IDs', 'Slab ID', 'Beam ID', 'Column ID')
# sheets whose rows continue a record on the following rows (point lists)
GROUPED = {'Geometry': 'Product ID', 'Extra Panels': 'Product ID',
           'Connections': 'Product ID', 'Transv Reinf': 'Reinf ID'}


# the data's headers carry a plus-minus sign, a theta and a c-cedilla; the code stays ASCII
PLUS_MINUS, THETA, C_CEDILLA = chr(0xB1), chr(0x3B8), chr(0xE7)


def norm(text) -> str:
    text = str(text or '').replace(PLUS_MINUS, '+-').replace(THETA, 'theta')
    text = text.replace(C_CEDILLA, 'c')
    return re.sub(r'\s+', ' ', text).strip()


def value(v):
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, str):
        v = v.strip()
        if v.upper() in ('TRUE', 'FALSE'):
            return v.upper() == 'TRUE'
        return v or None
    return v


def rows_of(ws):
    out = []
    for i, r in enumerate(ws.iter_rows(values_only=True), 1):
        cells = [value(c) for c in r]
        if any(c is not None for c in cells):
            out.append((i, cells))
    return out


def header_keys(header_rows, width):
    """Column keys from up to three header rows; a merged section or field
    carries over the empty cells to its right."""
    keys, carry = [], [''] * len(header_rows)
    for col in range(width):
        parts = []
        for level, (_, cells) in enumerate(header_rows):
            text = norm(cells[col]) if col < len(cells) else ''
            if text:
                carry[level] = text
                for deeper in range(level + 1, len(header_rows)):
                    carry[deeper] = ''
            elif level == len(header_rows) - 1:
                carry[level] = ''
            parts.append(carry[level])
        keys.append(' / '.join(p for p in parts if p))
    return keys


def header_depth(rows):
    """Leading header rows: the first row, then every row whose first cell is
    empty or a label (no digit, no underscore); data rows start with an id."""
    depth = 1
    for _, cells in rows[1:4]:
        first = cells[0]
        if first is None or not re.search(r'\d|_', str(first)):
            depth += 1
        else:
            break
    return depth


def table(ws):
    rows = rows_of(ws)
    if not rows:
        return [], []
    depth = header_depth(rows)
    width = max(len(c) for _, c in rows)
    keys = header_keys(rows[:depth], width)
    return keys, rows[depth:]


def records(ws):
    """One dict per data row (flat sheets)."""
    keys, data = table(ws)
    out = []
    for row, cells in data:
        rec = {k: cells[i] for i, k in enumerate(keys)
               if k and i < len(cells) and cells[i] is not None}
        rec['_row'] = row
        out.append(rec)
    return keys, out


def grouped(ws, id_key):
    """Records that continue on the next rows: scalars from the first row,
    every column also as the list of its values down the group."""
    keys, data = table(ws)
    id_col = next((i for i, k in enumerate(keys) if k.split(' / ')[0] == id_key), 0)
    groups = []
    for row, cells in data:
        if cells[id_col] is not None:
            groups.append({'_row': row, '_rows': []})
        if not groups:
            continue
        groups[-1]['_rows'].append(cells)
    out = []
    for g in groups:
        rec = {'_row': g['_row']}
        first = g['_rows'][0]
        for i, k in enumerate(keys):
            if not k:
                continue
            column = [r[i] if i < len(r) else None for r in g['_rows']]
            head = first[i] if i < len(first) else None
            if head is not None:
                rec[k] = head
            if sum(v is not None for v in column) > 1:
                rec[k + ' []'] = column
        out.append(rec)
    return keys, out


def site(ws):
    """Building rows; the rows below a building with an empty id are its
    wings (Wing ID, storeys, floor areas)."""
    keys, data = table(ws)
    buildings = []
    for row, cells in data:
        rec = {k: cells[i] for i, k in enumerate(keys)
               if k and i < len(cells) and cells[i] is not None}
        if rec.get('BUILDING DATA / Building ID'):
            rec['_row'] = row
            rec['wings'] = []
            buildings.append(rec)
        if buildings:
            wing = {k.split(' / ')[-1]: v for k, v in rec.items()
                    if k.startswith('STRUCTURAL FRAME')}
            if wing:
                buildings[-1]['wings'].append(wing)
    return keys, buildings


def main(src: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    parsed = {'source': ZENODO, 'files': [], 'buildings': [], 'element_files': [],
              'templates': {}}
    notes = []
    for path in sorted(src.glob('*.xlsx')):
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        parsed['files'].append(path.name)
        if m := TEMPLATE_FILE.match(path.name):
            parsed['templates'][m['type']] = {
                ws.title: [k for k in table(ws)[0] if k] for ws in wb.worksheets}
        elif m := SITE_FILE.match(path.name):
            ws = wb['Building Data']
            keys, buildings = site(ws)
            for b in buildings:
                b['_pilot'] = m['pilot']
                b['_file'] = path.name
            parsed['buildings'].extend(buildings)
        elif m := DATA_FILE.match(path.name):
            entry = {'file': path.name, 'type': m['type'], 'pilot': m['pilot'],
                     'sheets': {}}
            for ws in wb.worksheets:
                if ws.title in ID_SHEETS:
                    keys, recs = records(ws)
                    entry['sheets']['elements'] = {'title': ws.title, 'keys': keys,
                                                   'records': recs}
                elif ws.title in GROUPED:
                    keys, recs = grouped(ws, GROUPED[ws.title])
                    entry['sheets'][ws.title] = {'keys': keys, 'records': recs}
                else:
                    keys, recs = records(ws)
                    entry['sheets'][ws.title] = {'keys': keys, 'records': recs}
            parsed['element_files'].append(entry)
        else:
            notes.append(f'unrecognised file: {path.name}')
    (out / 'parsed.json').write_text(json.dumps(parsed, ensure_ascii=True, indent=1),
                                     encoding='utf-8')
    (out / 'structure.md').write_text(structure(parsed, notes), encoding='ascii',
                                      errors='replace')
    print(f'parsed {len(parsed["files"])} files -> {out}')
    return 0


def structure(parsed, notes) -> str:
    lines = ['# ReCreate pilot data: structure as parsed', '',
             f'Source: {parsed["source"]["url"]} ({parsed["source"]["licence"]}).', '']
    lines += ['## Donor buildings', '']
    for b in parsed['buildings']:
        g = lambda k: b.get('BUILDING DATA / ' + k)
        lines.append(f'- `{g("Building ID")}` ({b["_pilot"]}): {g("Building Type")}, '
                     f'{g("City")}, {g("Country")}; built {g("Construction Year")}, '
                     f'deconstructed {g("Deconstruction Year")}; {len(b["wings"])} wing rows')
    lines += ['', '## Element files', '',
              '| file | elements | products | sheets (records) |', '|---|---|---|---|']
    total = 0
    for e in parsed['element_files']:
        els = e['sheets'].get('elements', {}).get('records', [])
        total += len(els)
        prods = {r.get('Product ID') for r in els}
        sheets = ', '.join(f'{k} ({len(v["records"])})' for k, v in e['sheets'].items()
                           if k != 'elements')
        lines.append(f'| {e["file"]} | {len(els)} | {len(prods)} | {sheets} |')
    lines += ['', f'Total elements: {total}.', '']
    lines += ['## Value distributions (element sheets)', '']
    for e in parsed['element_files']:
        els = e['sheets'].get('elements', {}).get('records', [])
        lines.append(f'### {e["file"]}')
        for key in sorted({k for r in els for k in r if not k.startswith('_')}):
            c = Counter(str(r.get(key)) for r in els)
            if len(c) <= 8:
                lines.append(f'- {key}: ' + ', '.join(f'{v} x{n}' for v, n in c.most_common()))
            else:
                lines.append(f'- {key}: {len(c)} distinct')
        lines.append('')
    lines += ['## Differences to the templates', '']
    for e in parsed['element_files']:
        tpl = parsed['templates'].get(e['type'], {})
        for sheet, body in e['sheets'].items():
            title = body.get('title', sheet)
            want = set(tpl.get(title, tpl.get('Wall IDs' if title == 'Wall ID' else title, [])))
            have = {k for k in body['keys'] if k}
            if want and want != have:
                lines.append(f'- {e["file"]} / {title}: missing {sorted(want - have)}; '
                             f'extra {sorted(have - want)}')
    lines += [''] + [f'- {n}' for n in notes]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse the ReCreate pilot element data.')
    parser.add_argument('--data', type=Path, default=common.DEFAULT_DATA,
                        help='folder of the Zenodo files, as fetch.py wrote it (default: the local rehearsal)')
    parser.add_argument('--out', type=Path, default=common.DEFAULT_OUT,
                        help='folder for parsed.json and structure.md (default: the local rehearsal)')
    args = parser.parse_args()
    if not args.data.is_dir():
        sys.exit(f'no data folder {args.data}: run fetch.py first')
    sys.exit(main(args.data, common.out_dir(args.out)))
