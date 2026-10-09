"""
Exports of a passport on the real routes (data model spec 7.8; decisions
8.44, 8.101, 8.116; plan P10): the JSON-LD context and edition, CERO, the PDF.
Visibility, status codes, ETags per viewer, and validation with standard
processors (pyld expands the JSON-LD, rdflib parses the Turtle).
"""
# flake8: noqa: F811  -- the `world` fixture is imported from test_inplace_batches

from __future__ import annotations

import json
import os
import re
from decimal import Decimal

import pytest
from pyld import jsonld as pyld
from rdflib import RDF, Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic

from apps.catalog.api import exports as exports_api
from apps.catalog.api.snapshot_images import photo_filename
from apps.catalog.exports.pdf import story_text
from evidence_samples import claim_body
from test_inplace_batches import (  # noqa: F401  (the fixture and helpers)
    BEAM, _new, _publish, _published, world)

CERO = Namespace('https://w3id.org/cero#')
BOT = Namespace('https://w3id.org/bot#')
BSDD_PROP = 'https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/'
BSDD_CLASS = 'https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/'
SITE = 'http://localhost:3000'
EXPORTS = ('/identities/{}/compose?format=jsonld', '/identities/{}/export/cero',
           '/identities/{}/export/pdf')


def pages(pdf: bytes) -> int:
    return len(re.findall(rb'/Type /Page\b(?!s)', pdf))


def _expand(world, document):
    """JSON-LD expansion by pyld; the context comes from the app itself."""
    api = world['api']

    def loader(url, options=None):
        path = '/' + url.split('/', 3)[3]
        response = api.get(path)
        assert response.status_code == 200, url
        return {'contentType': 'application/ld+json', 'contextUrl': None,
                'documentUrl': url, 'document': response.json()}

    return pyld.expand(document, {'documentLoader': loader})


def _evidence(w, identity_id, body):
    made = w['api'].post(f'/identities/{identity_id}/evidence', json=body,
                         headers=w['c'])
    assert made.status_code == 201, made.text
    record = made.json()
    submitted = w['api'].post(f"/evidence/{record['_id']}/submit",
                              headers=w['c'])
    assert submitted.status_code == 200, submitted.text
    done = w['api'].post(f"/evidence/{record['_id']}/publish",
                         headers=w['m'])
    assert done.status_code == 200, done.text
    return done.json()


def _document(**document):
    return {'method': 'archival_document', 'observed_at': '2022-03-01T00:00:00Z',
            'payload': {'document': {'title': 'Profile drawing',
                                     'kind': 'drawing', **document}}}


def _public(w, identity_id):
    w['db']['component_identities'].update_one(
        {'_id': identity_id}, {'$set': {'is_public': True}})


@pytest.fixture
def pdf_spy(monkeypatch):
    """The data every PDF is built from (the file's text is a font subset)."""
    seen = []
    real = exports_api.build_pdf

    def spy(data):
        seen.append(data)
        return real(data)

    exports_api.clear_pdf_cache()       # a cached PDF would hide the render
    monkeypatch.setattr(exports_api, 'build_pdf', spy)
    yield seen
    exports_api.clear_pdf_cache()


# CONTEXT ---------------------------------------------------------------------
def test_the_context_is_public_cacheable_and_versioned(world):
    api = world['api']
    first = api.get('/context/v1.jsonld')
    assert first.status_code == 200
    assert first.headers['content-type'].startswith('application/ld+json')
    assert 'public' in first.headers['cache-control']
    context = first.json()['@context']
    assert context['@vocab'] == f'{SITE}/vocab/v1#'
    assert context['bsdd'] == BSDD_PROP
    assert api.get('/context/v1.jsonld', headers={
        'If-None-Match': first.headers['etag']}).status_code == 304


# JSON-LD ---------------------------------------------------------------------
def test_the_passport_as_json_ld_expands_with_a_standard_processor(world):
    api = world['api']
    record = _evidence(world, BEAM, claim_body())
    got = api.get(f'/identities/{BEAM}/compose',
                  params={'format': 'jsonld', 'include': 'evidence'},
                  headers=world['m'])
    assert got.status_code == 200, got.text
    assert got.headers['content-type'].startswith('application/ld+json')
    document = got.json()
    assert document['@id'] == f'{SITE}/id/{BEAM}'
    assert document['@context'].endswith('/context/v1.jsonld')
    # the same body as the plain JSON, plus the linked-data keys
    plain = api.get(f'/identities/{BEAM}/compose',
                    params={'include': 'evidence'}, headers=world['m']).json()
    assert document['identity']['catalog_number'] == \
        plain['identity']['catalog_number']
    assert len(document['evidence']) == len(plain['evidence'])
    expanded = _expand(world, document)
    assert len(expanded) == 1
    node = expanded[0]
    assert node['@id'] == f'{SITE}/id/{BEAM}'
    assert set(node['@type']) == {'https://w3id.org/bot#Element',
                                  BSDD_CLASS + 'IfcBeam'}
    # nothing of the identity is dropped: a key without a standard IRI lands
    # in the CSC namespace, one with a bSDD counterpart under its IRI
    assert f'{SITE}/vocab/v1#catalog_number' in node
    assert f'{SITE}/vocab/v1#originalFunction' in node
    props = node[f'{SITE}/vocab/v1#properties'][0]
    assert BSDD_PROP + 'CompressiveStrength' in props
    assert BSDD_PROP + 'CompressiveStrength' in json.dumps(props)
    evidence = node[f'{SITE}/vocab/v1#evidence']
    assert {e['@id'] for e in evidence} == {
        f"urn:uuid:{e['_id']}" for e in plain['evidence']}
    assert f"urn:uuid:{record['_id']}" in {e['@id'] for e in evidence}


def test_a_batch_has_quantity_and_remaining_and_a_document_has_a_link(world):
    api = world['api']
    batch = _published(world, planned=True, quantity=5)
    _evidence(world, batch, _document(url='https://example.org/f/profile.pdf',
                                      retrieved_at='2026-10-05'))
    got = api.get(f'/identities/{batch}/compose', headers=world['m'],
                  params={'format': 'jsonld', 'include': 'evidence'})
    assert got.status_code == 200, got.text
    document = got.json()
    assert document['identity']['remaining'] == 5
    assert document['snapshots'][0]['quantity'] == 5
    node = _expand(world, document)[0]
    assert node[f'{SITE}/vocab/v1#remaining'] == [{'@value': 5}]
    record = node[f'{SITE}/vocab/v1#evidence'][0]
    link = record[f'{SITE}/vocab/v1#document'][0]
    # the document's url is a link (an IRI), its retrieval date a value
    assert link[f'{SITE}/vocab/v1#url'] == [
        {'@id': 'https://example.org/f/profile.pdf'}]
    assert link[f'{SITE}/vocab/v1#retrievedAt'] == [{'@value': '2026-10-05'}]


def test_a_cut_piece_links_to_its_parent(world):
    api, w = world['api'], world
    parent = _published(w, quantity=1)
    created = api.post('/identities', headers=w['c'], json={
        'dataset': 'dbu_zirkus', 'parent_identities': [parent],
        'snapshot': {'geometry': {'proxies': [{
            'primitive': 'box', 'role': 'primary', 'params': {'size': [1, 1, 1]},
            'placement': {'o': [0, 0, 0], 'x': [1, 0, 0], 'y': [0, 1, 0],
                          'z': [0, 0, 1]}, 'fit': {'method': 'authored'}}]}}})
    assert created.status_code == 201, created.text
    child = created.json()['identity']['_id']
    _publish(w, created.json())
    got = api.get(f'/identities/{child}/compose', headers=w['m'],
                  params={'format': 'jsonld'})
    assert got.status_code == 200, got.text
    assert got.json()['identity']['parent_identities'] == \
        [f'{SITE}/id/{parent}']
    node = _expand(w, got.json())[0]
    assert node['http://www.w3.org/ns/prov#wasDerivedFrom'] == [
        {'@id': f'{SITE}/id/{parent}'}]
    for template in EXPORTS:
        assert api.get(template.format(child),
                       headers=w['m']).status_code == 200


# VISIBILITY, PEOPLE, ETAGS ---------------------------------------------------
@pytest.mark.parametrize('template', EXPORTS)
def test_an_export_answers_as_compose_does_for_a_caller_who_may_not_read(
        world, auth_headers, template):
    api = world['api']
    compose = api.get(f'/identities/{BEAM}/compose')
    assert compose.status_code == 401
    assert api.get(template.format(BEAM)).status_code == 401
    outsider = auth_headers('user')
    expected = api.get(f'/identities/{BEAM}/compose', headers=outsider)
    assert api.get(template.format(BEAM), headers=outsider).status_code == \
        expected.status_code


@pytest.mark.parametrize('template', EXPORTS)
def test_a_public_viewer_gets_no_person_and_a_viewer_specific_etag(
        world, template):
    api = world['api']
    _public(world, BEAM)
    member = api.get(template.format(BEAM), headers=world['m'])
    public = api.get(template.format(BEAM))
    assert member.status_code == public.status_code == 200
    assert 'Authorization' in public.headers['vary']
    assert 'public' in public.headers['cache-control']
    assert public.headers['etag'] != member.headers['etag']
    # a 304 only for the viewer the ETag was made for
    assert api.get(template.format(BEAM), headers={
        'If-None-Match': public.headers['etag']}).status_code == 304
    assert api.get(template.format(BEAM), headers={
        'If-None-Match': member.headers['etag']}).status_code == 200
    assert api.get(template.format(BEAM), headers={
        **world['m'],
        'If-None-Match': member.headers['etag']}).status_code == 304
    if 'pdf' in template:
        return
    # the stored recorder of the seeded records is a person: members see
    # them in the JSON-LD (CERO carries no person at all), the public does not
    if 'jsonld' in template:
        assert 'u-ddu' in member.text
    assert 'u-ddu' not in public.text
    assert '"ddu"' not in public.text and 'ddu@' not in public.text


def test_a_public_pdf_is_built_without_people_and_member_data(world, pdf_spy):
    api = world['api']
    _public(world, BEAM)
    got = api.get(f'/identities/{BEAM}/export/pdf')
    assert got.status_code == 200
    data = pdf_spy[-1]
    assert data.member is False and data.change_info is None
    dump = json.dumps(data.body)
    assert 'ddu' not in dump
    assert 'added_by' not in dump and 'recorded_by' not in dump
    member = api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
    assert member.status_code == 200
    assert pdf_spy[-1].member is True
    assert pdf_spy[-1].change_info is not None


# CERO ------------------------------------------------------------------------
def _turtle(world, identity_id, headers=None):
    got = world['api'].get(f'/identities/{identity_id}/export/cero',
                           headers=headers or world['m'])
    assert got.status_code == 200, got.text
    assert got.headers['content-type'].startswith('text/turtle')
    graph = Graph()
    graph.parse(data=got.text, format='turtle')           # it parses
    return graph


def test_cero_has_one_literal_per_property_with_the_conservative_bound(world):
    _evidence(world, BEAM, claim_body(rng=(18, 28)))
    _evidence(world, BEAM, claim_body(rng=(24, 34),
                                      observed_at='2026-03-02T00:00:00Z'))
    graph = _turtle(world, BEAM)
    subject = URIRef(f'{SITE}/id/{BEAM}#cero')
    assert (subject, RDF.type, BOT.Element) in graph
    strength = list(graph.objects(subject, CERO.compressiveStrength))
    assert len(strength) == 1                      # one literal, lower bound
    assert strength[0].toPython() == Decimal('18')
    assert strength[0].datatype == URIRef(
        'http://www.w3.org/2001/XMLSchema#decimal')
    assert Literal('IfcBeam') in set(graph.objects(subject, CERO.elementType)) \
        or str(next(graph.objects(subject, CERO.elementType))) == 'IfcBeam'
    # every property once
    predicates = [p for _, p, _ in graph if str(p).startswith(str(CERO))]
    assert len(predicates) == len(set(predicates))
    # the record behind it
    links = {str(o) for o in graph.objects(
        subject, URIRef('http://www.w3.org/2000/01/rdf-schema#seeAlso'))}
    assert f'{SITE}/id/{BEAM}' in links


def test_cero_links_the_documents(world):
    _evidence(world, BEAM, _document(url='https://example.org/f/layout.pdf',
                                     retrieved_at='2026-10-05'))
    graph = _turtle(world, BEAM)
    links = {str(o) for o in graph.objects(
        URIRef(f'{SITE}/id/{BEAM}#cero'),
        URIRef('http://www.w3.org/2000/01/rdf-schema#seeAlso'))}
    assert 'https://example.org/f/layout.pdf' in links


def test_cero_json_ld_is_the_same_graph_as_the_turtle(world):
    _evidence(world, BEAM, claim_body())
    turtle = _turtle(world, BEAM)
    got = world['api'].get(f'/identities/{BEAM}/export/cero',
                           params={'format': 'jsonld'}, headers=world['m'])
    assert got.status_code == 200
    assert got.headers['content-type'].startswith('application/ld+json')
    expanded = pyld.expand(got.json())            # a standard processor
    assert expanded[0]['@id'] == f'{SITE}/id/{BEAM}#cero'
    graph = Graph()
    graph.parse(data=got.text, format='json-ld')
    assert isomorphic(graph, turtle)


def test_cero_covers_concrete_only(world):
    api = world['api']
    steel = _published(world, material='steel')
    got = api.get(f'/identities/{steel}/export/cero', headers=world['m'])
    assert got.status_code == 409
    assert got.json()['detail'] == 'CERO covers concrete elements only'
    # the other exports of the same piece are fine
    assert api.get(f'/identities/{steel}/export/pdf',
                   headers=world['m']).status_code == 200
    assert api.get(f'/identities/{steel}/compose', headers=world['m'],
                   params={'format': 'jsonld'}).status_code == 200
    aerated = _published(world, material='autoclaved_aerated_concrete')
    assert api.get(f'/identities/{aerated}/export/cero',
                   headers=world['m']).status_code == 200
    # the read check comes first: nobody learns the material of a piece
    # they may not read
    assert api.get(f'/identities/{steel}/export/cero').status_code == 401


def test_cero_is_not_found_for_an_unknown_piece(world):
    unknown = '99999999-9999-4999-8999-999999999999'
    for template in EXPORTS:
        assert world['api'].get(template.format(unknown),
                                headers=world['m']).status_code == 404


# PDF -------------------------------------------------------------------------
def test_the_pdf_opens_and_has_at_most_two_pages(world, pdf_spy):
    api = world['api']
    got = api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
    assert got.status_code == 200
    assert got.headers['content-type'] == 'application/pdf'
    assert got.content.startswith(b'%PDF-') and pages(got.content) <= 2
    assert 'csc-passport-' in got.headers['content-disposition']
    data = pdf_spy[-1]
    assert data.dataset_name == 'ZirKuS'
    assert data.material_label == 'Concrete'
    text = story_text(data)
    assert 'Component passport' in text
    assert 'CPR Annex V 1(h)' in text               # deinstalled, not planned
    again = api.get(f'/identities/{BEAM}/export/pdf', headers={
        **world['m'], 'If-None-Match': got.headers['etag']})
    assert again.status_code == 304


def test_an_in_place_batch_has_the_planned_line_and_no_1h(world, pdf_spy):
    batch = _published(world, planned=True, quantity=356,
                       origin={'at': '2031-05-01T00:00:00Z',
                               'at_precision': 'month'})
    got = world['api'].get(f'/identities/{batch}/export/pdf',
                           headers=world['m'])
    assert got.status_code == 200
    text = story_text(pdf_spy[-1])
    assert 'In place, deinstallation planned 2031-05' in text
    assert '356 recorded, 0 drawn, 356 remaining' in text
    assert 'CPR Annex V 1(h)' not in text
    # a draw changes the batch line
    drawn = world['api'].post('/identities', headers=world['c'], json={
        'dataset': 'dbu_zirkus', 'parent_identities': [batch],
        'snapshot': {'quantity': 6}})
    assert drawn.status_code == 201, drawn.text
    _publish(world, drawn.json())
    world['api'].get(f'/identities/{batch}/export/pdf', headers=world['m'])
    assert '356 recorded, 6 drawn, 350 remaining' in \
        story_text(pdf_spy[-1])
    # CERO of a concrete batch is fine
    assert world['api'].get(f'/identities/{batch}/export/cero',
                            headers=world['m']).status_code == 200


def test_a_deinstalled_steel_piece_has_1h_and_no_cero(world, pdf_spy):
    piece = _published(world, planned=False, material='steel',
                       origin={'at': '2022-03-01T00:00:00Z',
                               'at_precision': 'month'})
    got = world['api'].get(f'/identities/{piece}/export/pdf',
                           headers=world['m'])
    assert got.status_code == 200
    text = story_text(pdf_spy[-1])
    assert 'CPR Annex V 1(h)' in text
    assert 'deinstallation: 2022-03' in text
    assert 'In place, deinstallation planned' not in text
    assert 'CERO' not in text                      # no edition for steel
    assert world['api'].get(f'/identities/{piece}/export/cero',
                            headers=world['m']).status_code == 409


def test_the_preview_is_the_state_preview_else_the_first_photo(
        world, pdf_spy):
    from PIL import Image
    api = world['api']
    snapshot_id = world['db']['component_identities'].find_one(
        {'_id': BEAM})['current_snapshot_id']
    app = api.app
    api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
    assert pdf_spy[-1].preview is None
    photo_dir = os.path.join(app.snapshot_photos_dir, snapshot_id)
    os.makedirs(photo_dir, exist_ok=True)
    photo = os.path.join(photo_dir, photo_filename(0))
    Image.new('RGB', (40, 30), (200, 0, 0)).save(photo, format='JPEG')
    os.makedirs(app.snapshot_preview_dir, exist_ok=True)
    preview = os.path.join(app.snapshot_preview_dir, f'{snapshot_id}.webp')
    try:
        api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
        assert pdf_spy[-1].preview is not None     # the photo
        photo_bytes = pdf_spy[-1].preview
        Image.new('RGB', (40, 30), (0, 0, 200)).save(preview, format='WEBP')
        api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
        assert pdf_spy[-1].preview not in (None, photo_bytes)   # the preview
    finally:
        for path in (photo, preview):
            if os.path.exists(path):
                os.remove(path)


def test_attachment_names_are_for_members_only(world, pdf_spy, member_headers):
    api = world['api']
    from evidence_samples import PDF
    record = _evidence(world, BEAM, _document())
    uploaded = api.post('/evidence/attachments', headers=world['m'],
                        data={'record_ids': [record['_id']]},
                        files={'file': ('secret-report.pdf', PDF,
                                        'application/pdf')})
    assert uploaded.status_code == 201, uploaded.text
    _public(world, BEAM)
    api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
    assert 'secret-report.pdf' in story_text(pdf_spy[-1])
    api.get(f'/identities/{BEAM}/export/pdf')
    assert 'secret-report.pdf' not in story_text(pdf_spy[-1])
    # a signed-in caller outside the dataset is no member either
    outsider, _ = member_headers({'schoenes_neues_feld': ['contributor']})
    got = api.get(f'/identities/{BEAM}/export/pdf', headers=outsider)
    assert got.status_code == 200
    assert pdf_spy[-1].member is False
    assert 'secret-report.pdf' not in story_text(pdf_spy[-1])


# CACHE, ETAG OF THE PICTURE, FILE NAME, RATE (P10 review) -----------------------
def test_a_repeated_request_does_not_render_again(world, pdf_spy):
    api = world['api']
    _public(world, BEAM)
    first = api.get(f'/identities/{BEAM}/export/pdf')
    second = api.get(f'/identities/{BEAM}/export/pdf')
    assert first.status_code == second.status_code == 200
    assert len(pdf_spy) == 1                       # the second came from the cache
    assert second.content == first.content
    assert second.headers['etag'] == first.headers['etag']
    assert second.headers['content-disposition'] ==         first.headers['content-disposition']
    # a changed record is another ETag: rendered again
    _evidence(world, BEAM, _document(url='https://example.org/f/new.pdf',
                                     retrieved_at='2026-10-06'))
    third = api.get(f'/identities/{BEAM}/export/pdf')
    assert third.headers['etag'] != first.headers['etag']
    assert len(pdf_spy) == 2
    # another viewer has its own entry, not the public one
    api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
    assert len(pdf_spy) == 3


def test_the_pdf_cache_is_bounded_and_keeps_the_recently_used(world):
    exports_api.clear_pdf_cache()
    size = exports_api.PDF_CACHE_SIZE
    for n in range(size):
        exports_api._remember_pdf(f'etag-{n}', b'%PDF-' + bytes([n % 256]))
    assert exports_api._cached_pdf('etag-0') is not None    # used: kept
    exports_api._remember_pdf('etag-new', b'%PDF-new')
    assert len(exports_api._PDF_CACHE) == size
    assert exports_api._cached_pdf('etag-0') is not None
    assert exports_api._cached_pdf('etag-1') is None        # the oldest went
    assert exports_api._cached_pdf('etag-new') == b'%PDF-new'
    exports_api.clear_pdf_cache()


def _snapshot_of(world, identity_id):
    return world['db']['component_identities'].find_one(
        {'_id': identity_id})['current_snapshot_id']


def test_a_replaced_preview_changes_the_pdf_etag(world, pdf_spy):
    from PIL import Image
    api = world['api']
    snapshot_id = _snapshot_of(world, BEAM)
    app = api.app
    os.makedirs(app.snapshot_preview_dir, exist_ok=True)
    preview = os.path.join(app.snapshot_preview_dir, f'{snapshot_id}.webp')
    etags = [api.get(f'/identities/{BEAM}/export/pdf',
                     headers=world['m']).headers['etag']]
    try:
        Image.new('RGB', (40, 30), (0, 0, 200)).save(preview, format='WEBP')
        etags.append(api.get(f'/identities/{BEAM}/export/pdf',
                             headers=world['m']).headers['etag'])
        # the same file name, other content and time: a new picture
        Image.new('RGB', (80, 60), (200, 0, 0)).save(preview, format='WEBP')
        later = os.stat(preview).st_mtime + 30
        os.utime(preview, (later, later))
        etags.append(api.get(f'/identities/{BEAM}/export/pdf',
                             headers=world['m']).headers['etag'])
        again = api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
        assert again.headers['etag'] == etags[-1]            # unchanged: same
    finally:
        if os.path.exists(preview):
            os.remove(preview)
    assert len(set(etags)) == 3
    assert len(pdf_spy) == 3


def test_a_replaced_stand_in_photo_changes_the_pdf_etag(world, pdf_spy):
    from PIL import Image
    api = world['api']
    snapshot_id = _snapshot_of(world, BEAM)
    photo_dir = os.path.join(api.app.snapshot_photos_dir, snapshot_id)
    os.makedirs(photo_dir, exist_ok=True)
    photo = os.path.join(photo_dir, photo_filename(0))
    try:
        Image.new('RGB', (40, 30), (200, 0, 0)).save(photo, format='JPEG')
        first = api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
        Image.new('RGB', (90, 70), (0, 200, 0)).save(photo, format='JPEG')
        later = os.stat(photo).st_mtime + 30
        os.utime(photo, (later, later))
        second = api.get(f'/identities/{BEAM}/export/pdf', headers=world['m'])
    finally:
        if os.path.exists(photo):
            os.remove(photo)
    assert first.headers['etag'] != second.headers['etag']
    assert pdf_spy[-1].preview is not None


def test_the_file_name_falls_back_to_the_identity_id():
    assert exports_api.pdf_filename(
        {'_id': BEAM, 'catalog_number': 12}) == 'csc-passport-12.pdf'
    assert exports_api.pdf_filename(
        {'_id': BEAM, 'catalog_number': None}) == f'csc-passport-{BEAM}.pdf'
    assert exports_api.pdf_filename({'_id': BEAM}) ==         f'csc-passport-{BEAM}.pdf'


def test_the_export_routes_are_rate_limited(world):
    from limiter import limiter
    api = world['api']
    _public(world, BEAM)
    limiter.reset()
    limiter.enabled = True              # the fixtures switch it off
    try:
        codes = [api.get(f'/identities/{BEAM}/export/pdf').status_code
                 for _ in range(21)]
        assert codes[:20] == [200] * 20 and codes[20] == 429
        codes = [api.get(f'/identities/{BEAM}/export/cero').status_code
                 for _ in range(61)]
        assert codes[:60] == [200] * 60 and codes[60] == 429
    finally:
        limiter.enabled = False
        limiter.reset()


# WHO A LIMIT COUNTS FOR (P10 review, 8.117 e) --------------------------------
@pytest.fixture
def limits_on():
    from limiter import limiter
    limiter.reset()
    limiter.enabled = True              # the fixtures switch it off
    yield
    limiter.enabled = False
    limiter.reset()


@pytest.fixture
def web_server(world):
    """The test client with the web server on loopback as its peer: a
    trusted proxy (the transport decides the peer address of a request)."""
    transport = world['api']._transport
    previous = transport.client
    transport.client = ('127.0.0.1', 50001)
    yield world['api']
    transport.client = previous


def _pdf_codes(client, count, **kwargs):
    return [client.get(f'/identities/{BEAM}/export/pdf', **kwargs).status_code
            for _ in range(count)]


def test_two_signed_in_users_do_not_share_a_bucket(world, member_headers,
                                                   limits_on):
    api = world['api']
    _public(world, BEAM)
    other, _ = member_headers({'dbu_zirkus': ['contributor']})
    first = _pdf_codes(api, 21, headers=world['m'])
    assert first[:20] == [200] * 20 and first[20] == 429
    # the other user, the public and the same piece: not touched
    assert _pdf_codes(api, 1, headers=other) == [200]
    assert _pdf_codes(api, 1) == [200]
    assert _pdf_codes(api, 1, headers=world['m']) == [429]


def test_a_spoofed_forwarded_for_from_an_untrusted_peer_changes_nothing(
        world, limits_on):
    api = world['api']
    _public(world, BEAM)
    codes = [api.get(f'/identities/{BEAM}/export/pdf',
                     headers={'X-Forwarded-For': f'203.0.113.{n}'}).status_code
             for n in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_behind_the_trusted_proxy_each_visitor_has_a_bucket(world, limits_on,
                                                            web_server):
    _public(world, BEAM)
    web = web_server
    # the web server tells who asks; what the visitor wrote on the left of
    # the chain is never read
    spoofed = {'X-Forwarded-For': '6.6.6.6, 203.0.113.9'}
    codes = _pdf_codes(web, 21, headers=spoofed)
    assert codes[:20] == [200] * 20 and codes[20] == 429
    # another visitor of the same web server is not touched
    assert _pdf_codes(web, 1, headers={
        'X-Forwarded-For': '203.0.113.10'}) == [200]
    # nor is a visitor who only changes the part the caller controls
    assert _pdf_codes(web, 1, headers={
        'X-Forwarded-For': '1.2.3.4, 203.0.113.9'}) == [429]


def test_the_login_limit_counts_per_client_address(world, limits_on,
                                                   web_server):
    web = web_server

    def attempt(client_address):
        return web.post('/auth/token',
                        data={'username': 'nobody', 'password': 'wrong'},
                        headers={'X-Forwarded-For': client_address}
                        ).status_code

    codes = [attempt('203.0.113.50') for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    assert attempt('203.0.113.51') == 401            # another visitor
    # a caller who is not behind the proxy cannot move to a new bucket
    web_server._transport.client = ('198.51.100.7', 50002)
    direct = web_server
    spoof = [direct.post('/auth/token',
                         data={'username': 'nobody', 'password': 'wrong'},
                         headers={'X-Forwarded-For': f'198.51.100.{n}'}
                         ).status_code for n in range(11)]
    assert spoof[:10] == [401] * 10 and spoof[10] == 429
