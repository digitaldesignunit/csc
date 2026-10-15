"""Plan the import of the ReCreate pilot element data (README decisions 1--4).

    python -I -X utf8 plan.py [--out <out folder>]

Input: `<out>/parsed.json` (parse.py) and `<out>/geometry.json` (geometry.py). Output: `<out>/plan.json`
(every record the runner writes, as plain JSON; the mesh as a path to its PLY) and `<out>/report.md`. Nothing
is written to a server here. Standard library only.

Reinforcement, per the data collection guidelines (sections 3.3.2--3.3.3):
- longitudinal layer: the first bar runs from (h1, v1) to (h2, v2) in the zone plane (XZ: h = x, v = z; YZ:
  h = y, v = z; XY: h = x, v = y); `Layer Position [Start]` is its coordinate on the remaining axis; the
  `Num. Bars` bars of the layer follow at `Bar Spacing` along that axis (centre to centre);
- transverse bars: the bent shape in its plane (two of x, y, z per point), closed for a closed stirrup,
  repeated along the span axis from start to end at the spacing;
- HCS strands: straight along the slab length x at (y, z) = the strand's section coordinates.
Hooks, hairpins (zone anchorage) and connection bars are not drawn; the accuracy note says so. A mirrored
product's bars are mirrored with its mesh (x -> x0 + x1 - x).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recreate_common as common  # noqa: E402

RUN = 'recreate-2026-10-15'
RETRIEVED = '2026-10-15'
PUBLISHED = '2025-08-12'
DOI_URL = 'https://doi.org/10.5281/zenodo.16809738'
NAMESPACE = uuid.UUID('3c1f0a52-8e64-4b9e-9d35-1f6a2b7c4e90')
DECONSTRUCTED = '2023-01-01T00:00:00Z'
OBSERVED = PUBLISHED + 'T00:00:00Z'
RECREATE_ORG = {'kind': 'organization',
                'organization': 'ReCreate project (EU H2020, grant 958200)'}
COLOR = [168, 168, 162]

PILOTS = {
    'Dutch': ('recreate_nl', 'NL'), 'German': ('recreate_de', 'DE'), 'Finnish': ('recreate_fi', 'FI')}
ATTRIBUTION = (
    'Source: ReCreate (EU Horizon 2020, grant agreement 958200), "Reclaimed Precast Concrete Elements: Data '
    'Collection Guidelines, Templates, & Pilot Element Data", v1, 2025-08-12, https://doi.org/10.5281/'
    'zenodo.16809738, licensed CC BY 4.0. Imported unchanged in substance; geometry computed from the published '
    'cross-section views and reinforcement drawn from the published layer tables (see each version\'s capture '
    'notes). State as published in 2025, not the present state of the elements.')
FUNCTION = {'Wall': 'IfcWall', 'HCS': 'IfcSlab', 'Slab': 'IfcSlab', 'Beam': 'IfcBeam', 'Column': 'IfcColumn'}
TRADE = {'HCS': 'Precast hollow-core slab', 'Slab': 'Precast solid slab', 'Beam': 'Precast beam',
         'Column': 'Precast column'}
CONNECTION = {'BOLTED': 'bolted'}
EXPOSURE = {'X0', 'XC1', 'XC2', 'XC3', 'XC4', 'XD1', 'XD2', 'XD3', 'XS1', 'XS2', 'XS3',
            'XF1', 'XF2', 'XF3', 'XF4', 'XA1', 'XA2', 'XA3'}


def uid(key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, 'csc-import/' + key))


def get(rec, *names):
    """A value by the last part of its header; the first name that is present wins."""
    for name in names:
        for key, value in rec.items():
            if not key.endswith(' []') and key.split(' / ')[-1] == name and value is not None:
                return value
    return None


def column(rec, *names):
    for name in names:
        for key in rec:
            if key.endswith(' []') and key[:-3].split(' / ')[-1] == name:
                return rec[key]
        value = get(rec, name)
        if value is not None:
            return [value]
    return []


def num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(',', '.'))
    except ValueError:
        return None


def grade(text):
    """'NL_FeB500' -> 'FeB500' (the pilot prefix of the dataset)."""
    return re.sub(r'^[A-Z]{2}_', '', str(text)) if text else None


# German and French letters of the data's names, written out (the code stays ASCII)
ASCII_LETTERS = {chr(0xE7): 'c', chr(0xF6): 'oe', chr(0xE4): 'ae', chr(0xFC): 'ue', chr(0xDF): 'ss'}


def ascii_text(text):
    if text is None:
        return None
    out = str(text)
    for letter, plain in ASCII_LETTERS.items():
        out = out.replace(letter, plain)
    return out


# REINFORCEMENT ----------------------------------------------------------------
AXES = {'XZ': ('x', 'z', 'y'), 'YZ': ('y', 'z', 'x'), 'XY': ('x', 'y', 'z')}


def point(values: dict):
    return [round(values['x'], 2), round(values['y'], 2), round(values['z'], 2)]


def long_bars(rows, skips):
    bars = []
    for r in rows:
        plane = (get(r, 'Zone Plane') or 'XZ').upper()
        if plane not in AXES:
            skips.append(f'layer {get(r, "Zone ID")}/{get(r, "Layer ID")}: zone plane {plane!r}')
            continue
        h, v, w = AXES[plane]
        h1 = num(get(r, 'Layer Coord [Start] h1', 'Layer Coord [Start] x1'))
        h2 = num(get(r, 'Layer Coord [End] h2', 'Layer Coord [End] x2'))
        v1 = num(get(r, 'Layer Coord [Start] v1', 'Layer Coord [Start] z1'))
        v2 = num(get(r, 'Layer Coord [End] v2', 'Layer Coord [End] z2'))
        pos = num(get(r, 'Layer Position [Start]', 'Layer Coord [Start] y1'))
        count = int(num(get(r, 'Num. Bars')) or 0)
        spacing = num(get(r, 'Bar Spacing (mm)')) or 0.0
        diameter = num(get(r, 'Bar Diameter (mm)'))
        if None in (h1, h2, v1, v2, pos) or not count or not diameter:
            skips.append(f'layer {get(r, "Zone ID")}/{get(r, "Layer ID")}: incomplete row {r.get("_row")}')
            continue
        for i in range(count):
            third = pos + i * spacing
            a = {h: h1, v: v1, w: third}
            b = {h: h2, v: v2, w: third}
            bars.append({'spec': grade(get(r, 'Steel Grade')), 'diameter_mm': diameter,
                         'diameter_known': True, 'points': [point(a), point(b)],
                         '_cover': [num(get(r, 'X')), num(get(r, 'Z')), num(get(r, 'Y'))],
                         '_confidence': num(get(r, 'Confidence (+- mm)'))})
    return bars


def transverse_bars(groups, skips):
    bars = []
    for g in groups:
        plane = (get(g, 'Bent Plane') or '').upper()
        axis = (get(g, 'Axis') or '').lower()
        diameter = num(get(g, 'Diameter (mm)'))
        if plane not in AXES or axis not in ('x', 'y', 'z') or not diameter:
            skips.append(f'transverse {get(g, "Zone ID")} row {g.get("_row")}: plane {plane!r}, axis {axis!r}')
            continue
        a, b, _ = AXES[plane]
        ua = [num(v) for v in column(g, a.upper())]
        ub = [num(v) for v in column(g, b.upper())]
        n = min(len([u for u in ua if u is not None]), len([u for u in ub if u is not None]))
        shape = [(ua[i], ub[i]) for i in range(n) if ua[i] is not None and ub[i] is not None]
        if len(shape) < 2:
            skips.append(f'transverse {get(g, "Zone ID")} row {g.get("_row")}: fewer than 2 shape points')
            continue
        if 'closed' in str(get(g, 'Description') or '').lower():
            shape.append(shape[0])
        start, end = num(get(g, 'Start')), num(get(g, 'End'))
        spacing = num(get(g, 'Spacing (mm)')) or 0.0
        if start is None:
            skips.append(f'transverse {get(g, "Zone ID")} row {g.get("_row")}: no span start')
            continue
        positions = [start]
        if spacing > 0 and end is not None:
            k = 1
            while start + k * spacing <= end + 1e-6:
                positions.append(start + k * spacing)
                k += 1
        for p in positions:
            pts = []
            for ca, cb in shape:
                pts.append(point({a: ca, b: cb, axis: p}))
            bars.append({'spec': grade(get(g, 'Steel Grade')), 'diameter_mm': diameter,
                         'diameter_known': True, 'points': pts})
    return bars


def strand_bars(rows, length):
    bars = []
    for r in rows:
        y, z, d = num(get(r, 'x')), num(get(r, 'y')), num(get(r, 'Strand Diameter (mm)'))
        if None in (y, z, d):
            continue
        bars.append({'spec': grade(get(r, 'Steel Grade')), 'diameter_mm': d, 'diameter_known': True,
                     'points': [[0.0, round(y, 2), round(z, 2)], [round(length, 2), round(y, 2), round(z, 2)]]})
    return bars


def pid_of(product):
    return get(product, 'Product ID')


def mirror(bars, x0, x1):
    for bar in bars:
        bar['points'] = [[round(x0 + x1 - p[0], 2), p[1], p[2]] for p in bar['points']]
    return bars


# PLAN -------------------------------------------------------------------------
class Planner:
    def __init__(self, parsed, geometry):
        self.parsed = parsed
        self.meshes = {(g['file'], g['product']): g for g in geometry['products']}
        self.buildings = {get(b, 'Building ID'): b for b in parsed['buildings']}
        self.items, self.skips, self.notes = [], [], []
        self.layout_checks = Counter()

    def dataset_entries(self):
        out = []
        for pilot, (slug, code) in PILOTS.items():
            b = next((x for x in self.parsed['buildings'] if x['_pilot'] == pilot), None)
            if b is None:
                continue
            name = ascii_text(get(b, 'Name'))
            city = ascii_text(get(b, 'City'))
            out.append({'id': slug, 'name': f'ReCreate Pilot {code}: {get(b, "Building Type")}, {city} '
                                          f'({get(b, "Construction Year")})',
                        'description': (f'Reclaimed precast concrete elements of the donor building "{name}" '
                                        f'({city}, {get(b, "Country")}; built {get(b, "Construction Year")}, '
                                        f'deconstructed {get(b, "Deconstruction Year")}), from the ReCreate '
                                        f'pilot data. ' + ATTRIBUTION)})
        return out

    def run(self):
        for entry in self.parsed['element_files']:
            self.plan_file(entry)

    def plan_file(self, entry):
        sheets = entry['sheets']
        products = {get(r, 'Product ID'): r for r in sheets['Geometry']['records']}
        longs = defaultdict(list)
        for r in sheets.get('Long Reinf', {}).get('records', []):
            longs[get(r, 'Reinf ID', 'Reinf_ID')].append(r)
        transv = defaultdict(list)
        for r in sheets.get('Transv Reinf', {}).get('records', []):
            transv[get(r, 'Reinf ID')].append(r)
        strands = defaultdict(list)
        for r in sheets.get('Prestressing', {}).get('records', []):
            strands[get(r, 'Reinf ID')].append(r)
        slug, code = PILOTS[entry['pilot']]
        id_name = {'Wall': 'Wall ID', 'HCS': 'Slab ID', 'Slab': 'Slab ID', 'Beam': 'Beam ID',
                   'Column': 'Column ID'}[entry['type']]
        for el in sheets['elements']['records']:
            eid = get(el, id_name)
            key = f'recreate:{code}:{eid}'
            pid = get(el, 'Product ID')
            product = products.get(pid)
            mesh = self.meshes.get((entry['file'], pid))
            if product is None or mesh is None:
                self.skips.append({'dataset': slug, 'element': eid,
                                   'reason': f'product {pid!r} has no geometry'})
                continue
            building = self.buildings.get(get(el, 'Building ID'))
            if building is None:
                self.skips.append({'dataset': slug, 'element': eid, 'reason': 'unknown building'})
                continue
            reinf = get(el, 'Reinf ID') or get(product, 'Reinf ID')
            self.items.append(self.item(entry, el, eid, key, slug, product, mesh, building, reinf,
                                        longs.get(reinf, []), transv.get(reinf, []),
                                        strands.get(reinf, [])))

    def item(self, entry, el, eid, key, slug, product, mesh, building, reinf, longs, transv, strands):
        etype = entry['type']
        pid = get(product, 'Product ID')
        mirrored = bool(get(product, 'Mirrored', 'Mirrored [boolean]'))
        # identity -----------------------------------------------------------
        if etype == 'Wall':
            trade = 'Precast ' + ascii_text(str(get(el, 'Wall Type') or 'wall')).replace('_', ' ').lower()
            if 'wall' not in trade and 'facade' not in trade:
                trade += ' wall'
        else:
            trade = TRADE[etype]
        place_bits = [get(el, 'Wing') and f'wing {get(el, "Wing")}',
                      get(el, 'Floor Num') is not None and f'floor {get(el, "Floor Num")}',
                      get(el, 'Grid Position') and f'grid {get(el, "Grid Position")}',
                      get(el, 'Orientation') and f'facing {get(el, "Orientation")}']
        connections = sorted({CONNECTION.get(str(c).upper(), 'other')
                              for c in column(product, 'Connection Type') if c})
        work = {'name': ascii_text(get(building, 'Name')).strip(),
                'identifier': get(building, 'Building ID'),
                'construction_method': 'prefabricated'}
        if num(get(building, 'Construction Year')):
            work['year_built'] = int(num(get(building, 'Construction Year')))
        if get(building, 'Building Type'):
            work['use'] = get(building, 'Building Type')
        origin = {'kind': 'deinstallation', 'planned': False, 'at': DECONSTRUCTED, 'at_precision': 'year',
                  'construction_work': work,
                  'place': {'name': f'{ascii_text(get(building, "City")).strip()}, {get(building, "Country")}',
                            'location': {'lat': num(get(building, 'Latitude')),
                                         'lon': num(get(building, 'Longitude'))}},
                  'position_in_work': ', '.join(b for b in place_bits if b)}
        if connections:
            origin['connection_types'] = connections
        if get(building, 'Deconstruction Company'):
            origin['performed_by'] = [{'kind': 'organization',
                                       'organization': ascii_text(get(building, 'Deconstruction Company'))}]
        if num(get(building, 'Deconstruction Year')) and int(num(get(building, 'Deconstruction Year'))) != 2023:
            origin['at'] = f'{int(num(get(building, "Deconstruction Year")))}-01-01T00:00:00Z'
        attributes = {'recreate': {
            'run': RUN, 'doi': DOI_URL.removeprefix('https://doi.org/'), 'file': entry['file'],
            'row': el['_row'], 'element_id': eid, 'building_id': get(el, 'Building ID'),
            'product_id': pid, 'reinf_id': reinf, 'mirrored': mirrored,
            'status': get(el, 'Status'), 'intervention_class': get(el, 'Intervention Class'),
            'has_tests': get(el, 'Has Tests'), 'has_damage': get(el, 'Has Damage'),
            'coating_layer': get(el, 'Coating Layer')}}
        identity = {'id': uid(key), 'dataset': slug, 'original_function': FUNCTION[etype],
                    'material': 'concrete', 'trade_name': trade, 'is_public': False, 'origin': origin,
                    'attributes': attributes}
        # snapshot -----------------------------------------------------------
        lat = num(get(el, 'Storage Lat', 'Storgage Lat'))
        lon = num(get(el, 'Storage Long'))
        product_notes = get(product, 'Notes')
        capture_notes = (f'Mesh computed by the CSC ReCreate import from the published cross-section views of '
                         f'product {pid} (front, side and plan intersected; voids subtracted; corbels added; '
                         f'hollow-core slabs from their parameters), mm, origin as in the dataset.')
        if mesh['notes']:
            capture_notes += ' ' + '; '.join(mesh['notes']) + '.'
        if product_notes:
            capture_notes += f' Product note: {product_notes}'
        snapshot = {'name': f'{trade} {pid}', 'quantity': 1, 'effective_from': DECONSTRUCTED,
                    'effective_from_precision': 'year', 'color': COLOR,
                    'capture': {'method': 'manual', 'software': 'CSC ReCreate import (manifold3d)',
                                'notes': capture_notes[:2000]}}
        if lat is not None and lon is not None:
            snapshot['location'] = {'lat': lat, 'lon': lon}
        else:
            self.notes.append(f'{eid}: no storage location')
        if get(el, 'Notes'):
            snapshot['notes'] = str(get(el, 'Notes'))
        # evidence -----------------------------------------------------------
        evidence = self.archival(entry, el, eid, product, building, longs, strands)
        layout = self.layout(entry, eid, product, mesh, mirrored, reinf, longs, transv, strands)
        if layout:
            evidence.append(layout)
            if layout['payload']['bars']:
                cover = self.cover_record(eid, layout, reinf)
                if cover:
                    evidence.append(cover)
        for record in evidence:
            if record['method'] == 'reinforcement_layout':
                record['payload']['bars'] = [{k: v for k, v in b.items() if not k.startswith('_')}
                                             for b in record['payload']['bars']]
        return {'key': key, 'dataset': slug, 'type': etype, 'element_id': eid, 'product': pid,
                'mesh_ply': mesh['ply'], 'identity': identity, 'snapshot': snapshot, 'evidence': evidence}

    # evidence helpers ----------------------------------------------------------
    def document(self, entry, eid, what):
        return {'title': f'ReCreate pilot element data, {entry["file"]}', 'date': PUBLISHED,
                'kind': 'report', 'reference': f'recreate:{eid}:{what}', 'url': DOI_URL,
                'retrieved_at': RETRIEVED}

    def claim_record(self, entry, eid, what, claim, interpretation, summary):
        payload = {'document': self.document(entry, eid, what), 'claim': {'text': claim}}
        if interpretation:
            payload['claim']['interpretation'] = interpretation
        return {'method': 'archival_document', 'observed_at': OBSERVED, 'observed_at_precision': 'day',
                'performed_by': [RECREATE_ORG], 'payload': payload, 'summary': summary}

    def archival(self, entry, el, eid, product, building, longs, strands):
        out = []
        cls = get(product, 'Concrete Strength Class')
        note = str(get(product, 'Notes') or '')
        if cls:
            raw = str(cls)
            equal = re.search(r'equivalent to EN 206-1 class (C\d+/\d+)', note)
            value = equal.group(1) if equal else grade(raw)
            interpretation = (f'{grade(raw)} is equivalent to EN 206-1 {equal.group(1)} (note of the dataset)'
                              if equal else None)
            out.append(self.claim_record(entry, eid, 'concrete_class', f'Concrete Strength Class: {raw}',
                                         interpretation,
                                         {'quantity': 'concrete_class', 'value': value, 'kind': 'claimed'}))
        mean = re.search(r'[Mm]ean compression strength = (\d+(?:[.,]\d+)?) N/mm2', note) or \
            re.search(r'[Aa]verage compressive strength[^.]*? was (\d+(?:[.,]\d+)?) MPa', note)
        if mean:
            value = float(mean.group(1).replace(',', '.'))
            sentence = next((s.strip() for s in re.split(r'(?<=\.)\s+', note) if mean.group(1) in s), note)
            out.append(self.claim_record(entry, eid, 'compressive_strength_in_situ', sentence,
                                         'mean of the tests reported for this product type',
                                         {'quantity': 'compressive_strength_in_situ', 'value': value,
                                          'unit': 'MPa', 'kind': 'claimed'}))
        grades = Counter(grade(get(r, 'Steel Grade')) for r in longs + strands if get(r, 'Steel Grade'))
        if grades:
            main, _ = grades.most_common(1)[0]
            raw = sorted({str(get(r, 'Steel Grade')) for r in longs + strands if get(r, 'Steel Grade')})
            out.append(self.claim_record(entry, eid, 'rebar_spec', 'Steel Grade: ' + ', '.join(raw),
                                         None if len(grades) == 1 else f'most frequent: {main}',
                                         {'quantity': 'rebar_spec', 'value': main, 'kind': 'claimed'}))
        exposure = str(get(building, 'Exposure Class') or '').strip().upper()
        if exposure in EXPOSURE:
            out.append(self.claim_record(entry, eid, 'exposure_class',
                                         f'Exposure Class of the donor building: {exposure}', None,
                                         {'quantity': 'exposure_class', 'value': exposure, 'kind': 'claimed'}))
        return out

    def cover_record(self, eid, layout, reinf):
        covers = [c for b in layout['payload']['bars'] for c in (b.get('_cover') or []) if c]
        if not covers:
            return None
        confidence = {b.get('_confidence') for b in layout['payload']['bars'] if b.get('_confidence')}
        entry = {'file': layout['payload']['document']['title'].split(', ', 1)[1]}
        record = self.claim_record(entry, eid, 'cover_depth',
                                   f'Concrete cover (x, z, y) of reinforcement type {reinf}: smallest '
                                   f'{min(covers):g} mm' + (f', confidence +-{max(confidence):g} mm'
                                                            if confidence else ''),
                                   'the smallest cover of all layers', {
                                       'quantity': 'cover_depth', 'value': min(covers), 'unit': 'mm',
                                       'kind': 'claimed'})
        return record

    def layout(self, entry, eid, product, mesh, mirrored, reinf, longs, transv, strands):
        if not (longs or transv or strands):
            return None
        skips = []
        bars = long_bars(longs, skips) + transverse_bars(transv, skips)
        if strands:
            bars += strand_bars(strands, num(get(product, 'Length (mm)')) or mesh['bbox_mm'][0])
        if mirrored:
            x0 = mesh['origin_mm'][0]
            mirror(bars, x0, x0 + mesh['bbox_mm'][0])
        for s in skips:
            self.notes.append(f'{entry["file"]} {reinf}: {s}')
        if not bars:
            return None
        # a bar outside the element's bounding box (+ 1 mm) belongs to a part this element does not have:
        # a corbel the product lacks (G03.3: "assumed that there is no corbel"), the full width of a cut
        # hollow-core slab, or a mistyped coordinate; it is left out and counted
        lo = mesh['origin_mm']
        hi = [lo[i] + mesh['bbox_mm'][i] for i in range(3)]
        kept = [b for b in bars if all(lo[i] - 1 <= p[i] <= hi[i] + 1
                                       for p in b['points'] for i in range(3))]
        dropped = len(bars) - len(kept)
        self.layout_checks['bars'] += len(bars)
        self.layout_checks['dropped'] += dropped
        if dropped:
            self.layout_checks[f'dropped in {pid_of(product)}'] += dropped
        bars = kept
        if not bars:
            return None
        confidence = max((b.get('_confidence') or 0 for b in bars), default=0)
        accuracy = ('Bars drawn as centre lines from the published layer tables of reinforcement type '
                    f'{reinf}' + (f'; cover confidence +-{confidence:g} mm' if confidence else '') +
                    '. Hooks, hairpins (zone anchorage) and connection bars are not drawn.')
        if mirrored:
            accuracy += ' Mirrored with the element (x -> L - x).'
        if dropped:
            accuracy += (f' {dropped} bar(s) of the published type lie outside this element (a corbel it does '
                         f'not have, the cut-off width of a hollow-core slab, or a coordinate error) and are '
                         f'left out.')
        return {'method': 'reinforcement_layout', 'observed_at': OBSERVED, 'observed_at_precision': 'day',
                'performed_by': [RECREATE_ORG],
                'position': {'kind': 'none', 'snapshot_id': None,
                             'description': 'Whole element; bars in the stored coordinates of this version'},
                'payload': {'basis': 'drawing',
                            'document': {'title': f'ReCreate pilot element data, {entry["file"]}, '
                                                  f'reinforcement type {reinf}',
                                         'date': PUBLISHED, 'reference': f'recreate:{eid}:layout',
                                         'url': DOI_URL, 'retrieved_at': RETRIEVED},
                            'accuracy_note': accuracy, 'bars': bars}}


def report(planner, datasets) -> str:
    lines = ['# ReCreate import plan', '', f'Run `{RUN}`; source {DOI_URL}.', '', '## Datasets', '']
    for d in datasets:
        lines.append(f'- `{d["id"]}`: {d["name"]}')
    lines += ['', '## Elements and records', '',
              '| dataset | type | elements | archival records | layouts | bars |', '|---|---|---|---|---|---|']
    agg = defaultdict(lambda: [0, 0, 0, 0])
    for item in planner.items:
        a = agg[(item['dataset'], item['type'])]
        a[0] += 1
        a[1] += sum(r['method'] == 'archival_document' for r in item['evidence'])
        lay = [r for r in item['evidence'] if r['method'] == 'reinforcement_layout']
        a[2] += len(lay)
        a[3] += sum(len(r['payload']['bars']) for r in lay)
    for (ds, t), (n, arch, lay, bars) in sorted(agg.items()):
        lines.append(f'| {ds} | {t} | {n} | {arch} | {lay} | {bars} |')
    total = len(planner.items)
    records = sum(len(i['evidence']) for i in planner.items)
    lines += ['', f'Total: {total} components, {records} evidence records.', '']
    q = Counter(r['summary']['quantity'] for i in planner.items for r in i['evidence'] if r.get('summary'))
    lines += ['## Archival values', ''] + [f'- {k}: {v}' for k, v in sorted(q.items())]
    vals = Counter((r['summary']['quantity'], str(r['summary']['value'])) for i in planner.items
                   for r in i['evidence'] if r.get('summary'))
    lines += [''] + [f'  - {k[0]} = {k[1]}: {v}' for k, v in sorted(vals.items())]
    lines += ['', '## Reinforcement check', '',
              f'- bars computed: {planner.layout_checks["bars"]}; left out because outside the element '
              f'(bounding box +-1 mm): {planner.layout_checks["dropped"]}']
    lines += [f'  - {k}: {v}' for k, v in sorted(planner.layout_checks.items()) if k.startswith('dropped in')]
    lines += ['', '## Skipped elements', ''] + ([f'- {s["dataset"]} {s["element"]}: {s["reason"]}'
                                                 for s in planner.skips] or ['- none'])
    notes = Counter(planner.notes)
    lines += ['', '## Notes', ''] + ([f'- {n}' + (f' (x{c})' if c > 1 else '') for n, c in notes.items()]
                                     or ['- none'])
    return '\n'.join(lines) + '\n'


def main(out: Path) -> int:
    parsed = json.loads((out / 'parsed.json').read_text(encoding='utf-8'))
    geometry = json.loads((out / 'geometry.json').read_text(encoding='utf-8'))
    planner = Planner(parsed, geometry)
    planner.run()
    datasets = planner.dataset_entries()
    plan = {'run': RUN, 'source': DOI_URL, 'datasets': datasets, 'items': planner.items}
    (out / 'plan.json').write_text(json.dumps(plan, ensure_ascii=True), encoding='utf-8')
    (out / 'report.md').write_text(report(planner, datasets), encoding='ascii', errors='replace')
    print(f'{len(planner.items)} items, {len(planner.skips)} skipped, '
          f'{sum(len(i["evidence"]) for i in planner.items)} evidence records')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plan the import of the ReCreate pilot element data.')
    parser.add_argument('--out', type=Path, default=common.DEFAULT_OUT,
                        help='folder with parsed.json and geometry.json; plan.json and report.md go here')
    args = parser.parse_args()
    out = common.out_dir(args.out)
    for name in ('parsed.json', 'geometry.json'):
        if not (out / name).is_file():
            sys.exit(f'no {name} in {out}: run parse.py and geometry.py first')
    sys.exit(main(out))
