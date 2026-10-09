"""
Exports of a passport (data model spec 7.8; decisions 8.44, 8.116; plan P10):
the conservative bound, the JSON-LD context and document, the CERO exporter
and the PDF, as pure functions over a passport body. The routes are in
tests/api/test_exports_routes.py.
"""

from __future__ import annotations

import io

import pytest

from apps.catalog import vocab
from apps.catalog.exports import cero, jsonld
from apps.catalog.exports.bound import conservative_value
from apps.catalog.exports.pdf import PassportPdfData, build_pdf, story_text

BASE = 'https://csc.example.org'
IID = '11111111-1111-4111-8111-111111111111'
SID = '22222222-2222-4222-8222-222222222222'
EID = '33333333-3333-4333-8333-333333333333'


def prop(rng, unit=None):
    return {'range': rng, 'unit': unit, 'confidence': 0.5,
            'source': 'archival', 'n': 1, 'evidence_ids': [EID],
            'inherited_from': None, 'derived_at': '2026-10-06T10:00:00Z'}


def body(**identity):
    ident = {
        '_id': IID, 'catalog_number': 7, 'original_function': 'IfcBeam',
        'material': 'concrete', 'material_class': '17 01 01',
        'trade_name': None, 'manufacturer': None, 'dataset': 'dbu_zirkus',
        'manufactured_at': None, 'manufactured_precision': 'unknown',
        'origin': {
            'kind': 'deinstallation', 'planned': False,
            'at': '2022-05-01T00:00:00Z', 'at_precision': 'month',
            'place': {'name': 'Werdh\u00f6lzli', 'address': None},
            'construction_work': {'name': 'Hall 7', 'year_built': 1969,
                                  'use': 'warehouse'},
            'connection_types': ['welded'], 'performed_by': []},
        'parent_identities': None, 'exit': None, 'past_cycles': [],
        'properties': {
            'compressive_strength': prop([25.0, 35.0], 'MPa'),
            'density': prop([2300.0, 2400.0], 'kg/m3'),
            'chloride_content': prop([0.02, 0.05], '%'),
            'exposure_class': prop(['XC3', 'XC4']),
            'concrete_class': prop(['C25/30']),
            'rebar_diameter': prop([8.0, 12.0], 'mm')},
        'remaining': None}
    ident.update(identity)
    snap = {'_id': SID, 'identity_id': IID, 'version': 1, 'name': 'beam',
            'quantity': 1, 'bbx': [6000.0, 300.0, 200.0],
            'shape_class': 'linear', 'color': [128, 128, 128],
            'location': {'lat': 49.87, 'lon': 8.65},
            'properties': {'mass': prop([900.0, 1100.0], 'kg')}}
    record = {
        '_id': EID, 'identity_id': IID, 'method': 'archival_document',
        'observed_at': '2022-03-01T00:00:00Z',
        'observed_at_precision': 'day', 'summary': None, 'derived': [],
        'performed_by': [{'kind': 'organization', 'organization': 'ACME'}],
        'attachments': [{'index': 0, 'name': 'drawing.pdf', 'removed': None}],
        'verification': {'state': 'reviewed'},
        'payload': {'document': {
            'title': 'Plan 1969', 'kind': 'drawing',
            'url': 'https://example.org/files/plan.pdf',
            'retrieved_at': '2026-10-05'}}}
    return {'identity': ident, 'snapshots': [snap], 'evidence': [record]}


# THE BOUND (8.116 c) ------------------------------------------------------------
Q = vocab.QUANTITY_BY_NAME


@pytest.mark.parametrize('name, rng, expected', [
    ('compressive_strength', [25.0, 35.0], 25.0),        # low
    ('compressive_strength_in_situ', [20.0, 30.0], 20.0),
    ('density', [2300.0, 2400.0], 2300.0),
    ('elastic_modulus', [28.0, 34.0], 28.0),
    ('cover_depth', [20.0, 35.0], 20.0),
    ('chloride_content', [0.02, 0.05], 0.05),             # high
    ('carbonation_depth', [4.0, 9.0], 9.0),
    ('crack_width', [0.1, 0.4], 0.4),
    ('mass', [900.0, 1100.0], 1100.0),
    ('rebar_diameter', [8.0, 12.0], None),                # no bound: none
    ('rebar_diameter', [8.0, 8.0], 8.0),                  # a single value
    ('moisture_content', [3.0, 5.0], None),
    ('exposure_class', ['XC3'], 'XC3'),                   # unambiguous
    ('exposure_class', ['XC3', 'XC4'], None),
    ('steel_grade', ['S235', 'S355'], None),
    ('spalling', [1, 3], 3),                              # worst severity
    ('corrosion', [0, 2], 2),
    ('condition_grade', [1, 3], 1),                       # worst grade
])
def test_the_conservative_bound(name, rng, expected):
    assert conservative_value(Q[name], {'range': rng}) == expected


def test_no_range_gives_no_value():
    assert conservative_value(Q['density'], {'range': []}) is None


def test_the_bound_column_follows_8_116_c():
    low = {q.name for q in vocab.QUANTITIES if q.conservative == 'low'}
    high = {q.name for q in vocab.QUANTITIES if q.conservative == 'high'}
    assert low == {'compressive_strength', 'compressive_strength_in_situ',
                   'density', 'elastic_modulus', 'cover_depth'}
    assert high == {'chloride_content', 'carbonation_depth', 'crack_width',
                    'mass'}
    # a bound only for a scalar
    assert all(Q[n].kind == 'scalar' for n in low | high)


def test_steel_grade_has_the_ifc_4_3_mapping():
    q = Q['steel_grade']
    assert q.ifc_property == 'Pset_MaterialSteel.StructuralGrade'
    assert q.bsdd == 'StructuralGrade'


# THE CONTEXT -------------------------------------------------------------------
def test_the_context_is_generated_from_the_mapping_columns():
    context = jsonld.build_context(BASE)['@context']
    assert context['@version'] == 1.1
    assert context['@vocab'] == f'{BASE}/vocab/v1#'
    assert context['ifc'].endswith('/ifc/4.3/class/')
    assert context['bsdd'].endswith('/ifc/4.3/prop/')
    assert context['IfcBeam'] == 'ifc:IfcBeam'
    assert 'CscDebris' not in context          # no IFC counterpart
    assert context['compressive_strength'] == {
        '@id': 'bsdd:CompressiveStrength'}
    # two quantities never share an IRI
    iris = jsonld.quantity_iris()
    # its bSDD code is taken: its CERO term comes before its own CSC term
    assert iris['compressive_strength'] == 'bsdd:CompressiveStrength'
    assert iris['compressive_strength_in_situ'] == \
        'cero:concreteCompressiveStrength'
    # a quantity with neither a bSDD nor a CERO property has its own term
    assert iris['rebound_number'] == 'csc:rebound_number'
    assert len(set(iris.values())) == len(iris)
    assert iris['steel_grade'] == 'bsdd:StructuralGrade'
    assert iris['chloride_content'] == 'cero:chlorideContent'


def test_the_context_etag_is_stable_and_follows_the_content():
    one = jsonld.build_context(BASE)
    assert jsonld.context_etag(one) == jsonld.context_etag(
        jsonld.build_context(BASE))
    assert jsonld.context_etag(one) != jsonld.context_etag(
        jsonld.build_context('https://other.example.org'))


def test_the_document_has_id_type_and_links_and_keeps_the_body():
    source = body(parent_identities=[SID], remaining=3)
    doc = jsonld.to_jsonld(source, base=BASE,
                           context_url=f'{BASE}/context/v1.jsonld')
    assert doc['@id'] == f'{BASE}/id/{IID}'
    assert doc['@type'] == ['bot:Element', 'ifc:IfcBeam']
    assert doc['identity']['parent_identities'] == [f'{BASE}/id/{SID}']
    assert doc['identity']['remaining'] == 3        # the batch line (8.116 b)
    assert doc['identity']['origin']['construction_work']['@type'] == \
        'bot:Building'
    prop_ = doc['identity']['properties']['compressive_strength']
    assert prop_['qudt_unit'] == 'unit:MegaPA'
    assert prop_['ifc_property'] == \
        'Pset_MaterialConcrete.CompressiveStrength'
    assert prop_['evidence_ids'] == [f'urn:uuid:{EID}']
    snapshot = doc['snapshots'][0]
    assert snapshot['@id'] == f'urn:uuid:{SID}'
    assert snapshot['prov:specializationOf'] == {'@id': f'{BASE}/id/{IID}'}
    evidence = doc['evidence'][0]
    assert evidence['@type'] == 'sosa:Observation'
    assert evidence['document'] == {
        'title': 'Plan 1969', 'kind': 'drawing',
        'url': 'https://example.org/files/plan.pdf',
        'retrieved_at': '2026-10-05'}
    assert evidence['performed_by'][0]['@type'] == 'prov:Agent'
    # the source body is untouched
    assert 'qudt_unit' not in source['identity']['properties'][
        'compressive_strength']


def test_a_core_is_also_a_sample():
    source = body()
    source['evidence'][0]['method'] = 'core_compression'
    doc = jsonld.to_jsonld(source, base=BASE, context_url='x')
    assert doc['evidence'][0]['@type'] == 'sosa:Sample'


def test_a_piece_without_ifc_counterpart_is_only_an_element():
    doc = jsonld.to_jsonld(body(original_function='CscDebris'), base=BASE,
                           context_url='x')
    assert doc['@type'] == ['bot:Element']


# CERO ----------------------------------------------------------------------------
def literals(source):
    element = cero.cero_element(source, base=BASE)
    return {lit.name: lit for lit in element.literals}, element


def test_cero_takes_the_conservative_bound_per_property():
    lits, element = literals(body())
    assert lits['compressiveStrength'].value == '25'
    assert lits['compressiveStrength'].datatype == 'xsd:decimal'
    assert lits['density'].value == '2300'
    assert lits['weight'].value == '1100'               # mass: high
    # CERO declares the chloride content a string
    assert (lits['chlorideContent'].value, lits['chlorideContent'].datatype) \
        == ('0.05', 'xsd:string')
    # an ambiguous categorical and a quantity without CERO property: absent
    assert 'exposureClass' not in lits
    assert 'rebarDiameter' not in lits
    assert element.subject == f'{BASE}/id/{IID}#cero'


def test_cero_identity_and_state_fields():
    lits, element = literals(body())
    assert lits['identifier'].value == IID
    assert lits['elementType'].value == 'IfcBeam'
    assert lits['initialProject'].value == 'Hall 7'
    assert lits['initialFunction'].value == 'warehouse'
    assert lits['origin'].value == 'deinstallation, 2022-05, Werdh\u00f6lzli'
    assert lits['location'].value == '49.87, 8.65'
    assert lits['shapeCategory'].value == 'linear'
    assert lits['color'].value == '#808080'
    assert (lits['length'].value, lits['width'].value,
            lits['height'].value) == ('6', '0.3', '0.2')


def test_cero_links_back_to_the_record_and_to_the_documents():
    _, element = literals(body())
    assert element.see_also == [f'{BASE}/id/{IID}',
                                'https://example.org/files/plan.pdf']


def test_cero_says_in_place_for_a_planned_origin():
    source = body()
    source['identity']['origin']['planned'] = True
    lits, _ = literals(source)
    assert lits['origin'].value.startswith('in place, deinstallation planned')


def test_cero_materials():
    assert cero.is_cero_material('concrete')
    assert cero.is_cero_material('autoclaved_aerated_concrete')
    assert not cero.is_cero_material('steel')
    assert not cero.is_cero_material(None)


def test_the_turtle_escapes_and_encodes():
    source = body()
    source['identity']['origin']['construction_work']['name'] = \
        'The "big" hall\nwest\\east'
    source['evidence'][0]['payload']['document']['url'] = \
        'https://example.org/a b/\u00e4.pdf'
    _, element = literals(source)
    turtle = cero.to_turtle(element)
    assert 'cero:initialProject "The \\"big\\" hall\\nwest\\\\east"' in turtle
    assert '<https://example.org/a%20b/%C3%A4.pdf>' in turtle
    assert turtle.rstrip().endswith('.')


def test_the_cero_json_ld_has_typed_values():
    node = cero.to_jsonld(cero.cero_element(body(), base=BASE))
    assert node['@type'] == 'bot:Element'
    assert node['cero:compressiveStrength'] == {
        '@value': '25', '@type': 'xsd:decimal'}
    assert {'@id': f'{BASE}/id/{IID}'} in node['rdfs:seeAlso']


# THE PDF -------------------------------------------------------------------------
def pdf_data(source=None, **over):
    fields = dict(
        body=source or body(), dataset_name='ZirKuS',
        material_label='Concrete', base=BASE, api_base='https://api.example.org',
        generated_at='2026-10-06T10:00:00Z')
    fields.update(over)
    return PassportPdfData(**fields)


def pages(pdf: bytes) -> int:
    import re
    return len(re.findall(rb'/Type /Page\b(?!s)', pdf))


def test_the_pdf_is_a_pdf_of_at_most_two_pages():
    pdf = build_pdf(pdf_data())
    assert pdf.startswith(b'%PDF-')
    assert pages(pdf) == 1


def test_the_pdf_holds_the_spec_7_8_contents():
    text = story_text(pdf_data(
        parents=[{'id': SID, 'catalog_number': 3}],
        children=[{'id': EID, 'catalog_number': 9}],
        member=True, change_info={'count': 4, 'last_at': '2026-10-01T09:00:00Z'}))
    for needle in ('Component passport', '#7 beam', 'Dataset: ZirKuS',
                   'state v1', 'Beam (IfcBeam)', 'Concrete', '17 01 01',
                   'Deinstalled', '2022-05', 'Werdh\u00f6lzli',
                   'Hall 7', 'built 1969', 'Welded',
                   '6000 x 300 x 200 mm', 'Linear', 'Mass',
                   'Compressive strength', 'Plan 1969', 'drawing.pdf',
                   '#3', '#9', 'In circulation',
                   'Machine-readable editions', 'JSON-LD', 'CERO',
                   'Change log: 4 entries'):
        assert needle in text, needle


def test_annex_v_1h_only_for_a_deinstalled_piece_that_is_not_planned():
    deinstalled = story_text(pdf_data())
    assert 'CPR Annex V 1(h)' in deinstalled
    assert 'date and place of the latest deinstallation: 2022-05, ' \
        'Werdh\u00f6lzli' in deinstalled
    planned = body()
    planned['identity']['origin']['planned'] = True
    planned['identity']['origin']['at'] = None
    text = story_text(pdf_data(planned))
    assert 'CPR Annex V 1(h)' not in text
    assert 'In place, deinstallation planned (date not set)' in text
    other = body()
    other['identity']['origin']['kind'] = 'offcut'
    other['identity']['origin']['construction_work'] = None
    other['identity']['origin']['connection_types'] = []
    assert 'CPR Annex V 1(h)' not in story_text(pdf_data(other))


def test_a_planned_date_is_named_and_the_batch_line_is_there():
    source = body(remaining=300)
    source['identity']['origin']['planned'] = True
    source['identity']['origin']['at'] = '2031-05-01T00:00:00Z'
    source['snapshots'][0]['quantity'] = 356
    text = story_text(pdf_data(source))
    assert 'In place, deinstallation planned 2031-05' in text
    assert '356 recorded, 56 drawn, 300 remaining' in text
    assert 'CPR Annex V 1(h)' not in text


def test_attachment_names_are_for_members_only():
    assert 'drawing.pdf' in story_text(pdf_data(member=True))
    other = story_text(pdf_data(member=False))
    assert 'drawing.pdf' not in other
    assert '1 file(s)' in other
    assert 'Change log' not in other


def test_the_pdf_links_documents_and_editions():
    text = story_text(pdf_data())
    assert 'Plan 1969' in text
    pdf = build_pdf(pdf_data())
    assert b'https://example.org/files/plan.pdf' in pdf
    assert b'https://api.example.org/identities/' + IID.encode() + \
        b'/compose?format=jsonld' in pdf
    assert b'/export/cero' in pdf
    steel = body(material='steel')
    assert b'/export/cero' not in build_pdf(pdf_data(steel))


def test_a_long_evidence_list_is_cut_to_two_pages():
    source = body()
    template = source['evidence'][0]
    source['evidence'] = [
        {**template, '_id': f'{i:08d}-0000-4000-8000-000000000000',
         'observed_at': f'2022-03-{(i % 28) + 1:02d}T00:00:00Z',
         'attachments': [{'index': 0, 'name': f'file-{i}.pdf',
                          'removed': None}]} for i in range(300)]
    pdf = build_pdf(pdf_data(source, member=True))
    assert pages(pdf) <= 2


def test_the_pdf_takes_a_preview_image():
    from PIL import Image
    buffer = io.BytesIO()
    Image.new('RGB', (80, 60), (10, 120, 200)).save(buffer, format='JPEG')
    with_image = build_pdf(pdf_data(preview=buffer.getvalue()))
    without = build_pdf(pdf_data())
    assert b'/Subtype /Image' in with_image
    assert b'/Subtype /Image' not in without
    # a file that is no image is no preview, not an error
    assert pages(build_pdf(pdf_data(preview=b'not an image'))) == 1


def test_a_piece_without_state_still_gets_a_passport():
    source = body()
    source['snapshots'] = []
    source['evidence'] = []
    pdf = build_pdf(pdf_data(source))
    assert pages(pdf) == 1


def test_characters_outside_latin_1_reach_the_pdf_through_noto_sans():
    from reportlab import rl_config
    text = 'Zagreb \u010d, Pozna\u0144, \u0141\u00f3d\u017a, \u0160umava'
    source = body()
    source['identity']['origin']['place']['name'] = text
    assert text in story_text(pdf_data(source))
    previous = rl_config.pageCompression
    rl_config.pageCompression = 0       # the ToUnicode map is then readable
    try:
        pdf = build_pdf(pdf_data(source))
    finally:
        rl_config.pageCompression = previous
    assert pdf.startswith(b'%PDF-') and pages(pdf) == 1
    assert b'/FontFile2' in pdf          # the bundled font is embedded
    for char in '\u010d\u0144\u0141\u017a\u0160':
        assert f'<{ord(char):04X}>'.encode() in pdf, char


def test_the_bundled_font_has_the_glyphs():
    import os

    from reportlab.pdfbase.ttfonts import TTFont

    from apps.catalog.exports.pdf import FONT_DIR
    for name in ('NotoSans-Regular.ttf', 'NotoSans-Bold.ttf'):
        face = TTFont('probe-' + name, os.path.join(FONT_DIR, name)).face
        for char in '\u010d\u0144\u0141\u017a\u0160\u00df':
            assert ord(char) in face.charToGlyph, (name, char)
