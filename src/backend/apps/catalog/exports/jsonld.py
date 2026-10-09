#!/usr/bin/env python3.13
"""
The JSON-LD view of a component passport (spec section 7.8; decisions 8.44
and 8.116 a, h).

``build_context`` is the versioned ``@context`` (served at
``/context/v1.jsonld``): the ontology prefixes, the terms that have a
standard counterpart and the typing of a few fields. It is generated from the
mapping columns of the vocabularies (``vocab.py``), so a new quantity row or
an IFC class needs no change here. Every other key expands to the CSC
namespace through ``@vocab``: nothing of the JSON is dropped.

``to_jsonld`` turns a passport body (the JSON of
``GET /identities/{id}/compose``, already stripped for the caller) into a
JSON-LD document: the same keys plus ``@context``, ``@id``
(``{FRONTEND_URL}/id/{uuid}``) and ``@type``, with the links written as
IRIs. Pure functions; the storage is unchanged (ontologies sit at the
boundary).

IRIs that were looked up (2026-10-06): the bSDD identifiers of the IFC 4.3
dictionary (``.../ifc/4.3/prop/<code>`` and ``.../class/<IfcClass>``, checked
against the bSDD API) and the CERO terms (``https://w3id.org/cero#``).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import copy
import hashlib
import json
from typing import Any, Dict, List, Optional

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.vocab import (
    EVIDENCE_METHOD_SOSA_TYPE,
    ORIGINAL_FUNCTION_IFC_CLASS,
    QUANTITIES,
    QUANTITY_BY_NAME,
)

CONTEXT_VERSION = 'v1'

BSDD_IFC = 'https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/'

PREFIXES: Dict[str, str] = {
    'xsd': 'http://www.w3.org/2001/XMLSchema#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
    'dcterms': 'http://purl.org/dc/terms/',
    'sosa': 'http://www.w3.org/ns/sosa/',
    'ssn': 'http://www.w3.org/ns/ssn/',
    'prov': 'http://www.w3.org/ns/prov#',
    'bot': 'https://w3id.org/bot#',
    'qudt': 'http://qudt.org/schema/qudt/',
    'unit': 'http://qudt.org/vocab/unit/',
    # an IFC class is named by its bSDD identifier, a property by its code
    'ifc': BSDD_IFC + 'class/',
    'bsdd': BSDD_IFC + 'prop/',
    'cero': 'https://w3id.org/cero#',
}

# keys whose value is a technical structure, kept as one JSON literal
JSON_KEYS = (
    'geometry', 'descriptors', 'derivation', 'frame', 'bbx', 'color',
    'payload', 'attributes', 'position', 'status_history',
    'mesh_ply_resolutions', 'context', 'verification', 'capture',
)

_DATETIME_TERMS = {
    'created': 'dcterms:created',
    'lastmodified': 'dcterms:modified',
    'effective_from': 'prov:generatedAtTime',
    'observed_at': 'sosa:resultTime',
    'derived_at': 'prov:generatedAtTime',
}


def site_base(request_base: Optional[str] = None) -> str:
    """The public base of the site: ``FRONTEND_URL`` (decision 8.116 h);
    the request's own base only where it is not set (tests, local use)."""
    import os
    base = (os.getenv('FRONTEND_URL') or request_base or '').rstrip('/')
    return base


def element_iri(base: str, identity_id: str) -> str:
    return f'{base}/id/{identity_id}'


def _urn(record_id: str) -> str:
    return f'urn:uuid:{record_id}'


def quantity_iris() -> Dict[str, str]:
    """The IRI of every quantity term: its bSDD property where there is
    one, else its CERO property, else its own CSC term. A counterpart that
    is taken already (two quantities share a bSDD code) is skipped for the
    next one, so two terms never merge: ``compressive_strength_in_situ``
    takes its CERO term, ``concreteCompressiveStrength``."""
    taken: Dict[str, str] = {}
    out: Dict[str, str] = {}
    for q in QUANTITIES:
        candidates = [f'bsdd:{q.bsdd}' if q.bsdd else None,
                      f'cero:{q.cero}' if q.cero else None,
                      f'csc:{q.name}']
        iri = next(c for c in candidates if c and c not in taken)
        taken[iri] = q.name
        out[q.name] = iri
    return out


def build_context(base: str) -> Dict[str, Any]:
    """The ``@context`` document. ``base`` is the site base: the CSC terms
    live under ``{base}/vocab/v1#``."""
    ctx: Dict[str, Any] = {
        '@version': 1.1,
        '@vocab': f'{base}/vocab/{CONTEXT_VERSION}#',
        'csc': f'{base}/vocab/{CONTEXT_VERSION}#',
        **PREFIXES,
    }
    ctx['identity'] = '@nest'
    ctx['snapshots'] = {'@id': 'csc:snapshot', '@container': '@set'}
    ctx['evidence'] = {'@id': 'csc:evidence', '@container': '@set'}
    ctx['_id'] = 'csc:uuid'
    ctx['original_function'] = {'@id': 'csc:originalFunction',
                                '@type': '@vocab'}
    for ifc_class in sorted({c for c in ORIGINAL_FUNCTION_IFC_CLASS.values()
                             if c}):
        ctx[ifc_class] = f'ifc:{ifc_class}'
    ctx['parent_identities'] = {'@id': 'prov:wasDerivedFrom',
                                '@type': '@id', '@container': '@set'}
    ctx['construction_work'] = {'@id': 'csc:constructionWork'}
    ctx['performed_by'] = {'@id': 'prov:wasAttributedTo',
                           '@container': '@set'}
    for key, iri in _DATETIME_TERMS.items():
        ctx[key] = {'@id': iri, '@type': 'xsd:dateTime'}
    ctx['range'] = {'@id': 'csc:range', '@container': '@list'}
    ctx['evidence_ids'] = {'@id': 'prov:wasDerivedFrom', '@type': '@id',
                           '@container': '@set'}
    ctx['qudt_unit'] = {'@id': 'qudt:hasUnit', '@type': '@vocab'}
    ctx['ifc_property'] = 'csc:ifcProperty'
    ctx['url'] = {'@id': 'csc:url', '@type': '@id'}
    ctx['retrieved_at'] = 'csc:retrievedAt'
    ctx['document'] = {'@id': 'csc:document'}
    ctx['title'] = 'dcterms:title'
    ctx['quantity'] = {'@id': 'csc:quantity'}
    ctx['remaining'] = {'@id': 'csc:remaining'}
    for key in JSON_KEYS:
        ctx[key] = {'@id': f'csc:{key}', '@type': '@json'}
    # a key that is a quantity name (under ``properties``): its IRI
    for name, iri in quantity_iris().items():
        if name not in ctx:
            ctx[name] = {'@id': iri}
    return {'@context': ctx}


def context_etag(context: Dict[str, Any]) -> str:
    payload = json.dumps(context, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


# THE DOCUMENT ------------------------------------------------------------------
def _types(identity: Dict[str, Any]) -> List[str]:
    types = ['bot:Element']
    ifc = ORIGINAL_FUNCTION_IFC_CLASS.get(identity.get('original_function'))
    if ifc:
        types.append(f'ifc:{ifc}')
    return types


def _agents(actors: Any) -> Any:
    if not isinstance(actors, list):
        return actors
    return [{'@type': 'prov:Agent', **a} if isinstance(a, dict) else a
            for a in actors]


def _property(name: str, prop: Dict[str, Any]) -> Dict[str, Any]:
    node = dict(prop)
    node['evidence_ids'] = [_urn(e) for e in prop.get('evidence_ids') or []]
    quantity = QUANTITY_BY_NAME.get(name)
    if quantity is not None:
        if quantity.qudt_unit:
            node['qudt_unit'] = quantity.qudt_unit
        if quantity.ifc_property:
            node['ifc_property'] = quantity.ifc_property
    return node


def _identity_node(identity: Dict[str, Any], base: str) -> Dict[str, Any]:
    node = copy.deepcopy(identity)
    if node.get('parent_identities'):
        node['parent_identities'] = [
            element_iri(base, p) for p in node['parent_identities']]
    origin = node.get('origin')
    if isinstance(origin, dict):
        work = origin.get('construction_work')
        if isinstance(work, dict):
            origin['construction_work'] = {'@type': 'bot:Building', **work}
        origin['performed_by'] = _agents(origin.get('performed_by'))
    node['properties'] = {name: _property(name, prop)
                          for name, prop in (node.get('properties')
                                             or {}).items()}
    return node


def _snapshot_node(snapshot: Dict[str, Any], base: str) -> Dict[str, Any]:
    node = copy.deepcopy(snapshot)
    node['@id'] = _urn(snapshot['_id'])
    node['@type'] = ['csc:Snapshot', 'prov:Entity']
    node['prov:specializationOf'] = {
        '@id': element_iri(base, snapshot['identity_id'])}
    node['properties'] = {name: _property(name, prop)
                          for name, prop in (node.get('properties')
                                             or {}).items()}
    return node


def _evidence_node(record: Dict[str, Any], base: str) -> Dict[str, Any]:
    node = copy.deepcopy(record)
    node['@id'] = _urn(record['_id'])
    node['@type'] = EVIDENCE_METHOD_SOSA_TYPE.get(
        record.get('method'), 'sosa:Observation')
    node['sosa:hasFeatureOfInterest'] = {
        '@id': element_iri(base, record['identity_id'])}
    node['performed_by'] = _agents(record.get('performed_by'))
    document = (record.get('payload') or {}).get('document')
    if isinstance(document, dict):
        # the source document of a record, as a link (8.116 b)
        node['document'] = {key: document[key] for key in (
            'title', 'kind', 'url', 'retrieved_at', 'reference')
            if document.get(key)}
    return node


def to_jsonld(body: Dict[str, Any], *, base: str,
              context_url: str) -> Dict[str, Any]:
    """The passport ``body`` as a JSON-LD document."""
    identity = body['identity']
    doc: Dict[str, Any] = {
        '@context': context_url,
        '@id': element_iri(base, identity['_id']),
        '@type': _types(identity),
        'identity': _identity_node(identity, base),
        'snapshots': [_snapshot_node(s, base)
                      for s in body.get('snapshots') or []],
    }
    if 'evidence' in body:
        doc['evidence'] = [_evidence_node(r, base)
                           for r in body['evidence'] or []]
    return doc
