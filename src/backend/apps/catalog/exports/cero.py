#!/usr/bin/env python3.13
"""
The CERO exporter (spec section 7.8; decisions 8.44 and 8.116 c, d).

CERO (Concrete Element Reuse Ontology, v0.1, ``https://w3id.org/cero``) puts
one literal value per property directly on a ``bot:Element``: no time, no
source, no range. CSC keeps evidence, so the export is lossy by design: each
folded property becomes one literal, the conservative bound of its range
(``bound.py``), and the provenance stays behind ``rdfs:seeAlso`` links to the
CSC record and to the cited documents.

Only concrete and autoclaved aerated concrete elements: CERO describes
concrete elements. Units are not written on a value; the unit sits on the CERO
property, and the CSC unit of every exported quantity is the one CERO declares
(MPa, mm, %, GPa, kg/m3; ``weight`` has none declared, CSC gives kg). The
Turtle is written here by hand, no RDF library is needed on the server.

Identity and state fields exported (one literal each, left out when unknown):
``identifier`` (the permanent id), ``elementType`` (the IFC class),
``initialFunction`` and ``initialProject`` (the construction work's use and
name), ``origin`` (kind, date and place as one string), ``location``
(``lat, lon``), ``shapeCategory``, ``color`` (``#rrggbb``) and ``length`` /
``width`` / ``height`` (the extents along the snapshot frame's x, y, z in m).
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.exports.bound import conservative_value
from apps.catalog.exports.jsonld import element_iri
from apps.catalog.vocab import QUANTITIES

CERO = 'https://w3id.org/cero#'
CERO_MATERIALS = ('concrete', 'autoclaved_aerated_concrete')
NOT_CONCRETE = 'CERO covers concrete elements only'

# CERO declares these two as strings, all other exported scalars as decimals
_STRING_RANGE = ('chlorideContent',)

PREFIXES = {
    'cero': CERO,
    'bot': 'https://w3id.org/bot#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
    'xsd': 'http://www.w3.org/2001/XMLSchema#',
}


@dataclass
class CeroLiteral:
    name: str                  # CERO property, local name
    value: Any
    datatype: str              # 'xsd:decimal' | 'xsd:string'


@dataclass
class CeroElement:
    subject: str
    literals: List[CeroLiteral] = field(default_factory=list)
    see_also: List[str] = field(default_factory=list)


def is_cero_material(material: Optional[str]) -> bool:
    return material in CERO_MATERIALS


def _decimal(value: float) -> str:
    text = f'{float(value):.10f}'.rstrip('0').rstrip('.')
    return text or '0'


def _literal(name: str, value: Any, *, scalar: bool) -> CeroLiteral:
    if scalar and name not in _STRING_RANGE:
        return CeroLiteral(name, _decimal(value), 'xsd:decimal')
    if isinstance(value, float):
        value = _decimal(value)
    return CeroLiteral(name, str(value), 'xsd:string')


def _origin_text(origin: Dict[str, Any]) -> Optional[str]:
    if not origin:
        return None
    parts = []
    if origin.get('planned'):
        parts.append('in place, deinstallation planned')
    else:
        parts.append(str(origin.get('kind') or 'origin'))
    if origin.get('at'):
        precision = origin.get('at_precision')
        at = str(origin['at'])
        parts.append(at[:4] if precision == 'year' else
                     at[:7] if precision == 'month' else at[:10])
    place = (origin.get('place') or {}).get('name')
    if place:
        parts.append(place)
    return ', '.join(parts)


def _hex(color: Optional[List[int]]) -> Optional[str]:
    if not color or len(color) != 3:
        return None
    return '#' + ''.join(f'{int(c):02x}' for c in color)


def cero_element(body: Dict[str, Any], *, base: str) -> CeroElement:
    """The CERO view of a passport body (identity, the current snapshot,
    evidence); the caller has checked the material."""
    identity = body['identity']
    snapshots = body.get('snapshots') or []
    snapshot = snapshots[0] if snapshots else {}
    iri = element_iri(base, identity['_id'])
    out = CeroElement(subject=f'{iri}#cero', see_also=[iri])

    def add(name: str, value: Any, *, scalar: bool = False) -> None:
        if value is not None and value != '':
            out.literals.append(_literal(name, value, scalar=scalar))

    work = (identity.get('origin') or {}).get('construction_work') or {}
    location = snapshot.get('location') or {}
    bbx = snapshot.get('bbx') or []
    add('identifier', identity['_id'])
    add('elementType', identity.get('original_function'))
    add('initialFunction', work.get('use'))
    add('initialProject', work.get('name'))
    add('origin', _origin_text(identity.get('origin') or {}))
    if location.get('lat') is not None and location.get('lon') is not None:
        add('location', f'{location["lat"]}, {location["lon"]}')
    add('shapeCategory', snapshot.get('shape_class'))
    add('color', _hex(snapshot.get('color')))
    if len(bbx) == 3:
        for name, extent in zip(('length', 'width', 'height'), bbx):
            add(name, round(float(extent) / 1000.0, 4), scalar=True)

    properties = {**(snapshot.get('properties') or {}),
                  **(identity.get('properties') or {})}
    for quantity in QUANTITIES:
        if not quantity.cero or quantity.name not in properties:
            continue
        value = conservative_value(quantity, properties[quantity.name])
        if value is not None:
            add(quantity.cero, value, scalar=quantity.kind == 'scalar')

    seen = set(out.see_also)
    for record in body.get('evidence') or []:
        url = ((record.get('payload') or {}).get('document') or {}).get('url')
        if url and url not in seen:
            seen.add(url)
            out.see_also.append(url)
    return out


# TURTLE ------------------------------------------------------------------------
def _escape(text: str) -> str:
    return (text.replace('\\', '\\\\').replace('"', '\\"')
            .replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t'))


def _iri(value: str) -> str:
    """An IRI for Turtle's ``<...>``: spaces and the characters a Turtle IRI
    may not hold are percent-encoded."""
    return f'<{quote(value, safe=":/?#[]@!$&()*+,;=%-._~")}>'


def to_turtle(element: CeroElement) -> str:
    lines = [
        '# CERO (https://w3id.org/cero, v0.1) export of a CSC component:',
        '# one literal per property, the conservative bound of its folded',
        '# range. Lossy by design; the evidence stays behind rdfs:seeAlso.',
    ]
    lines += [f'@prefix {p}: <{iri}> .' for p, iri in PREFIXES.items()]
    lines.append('')
    statements = ['a bot:Element']
    for literal in element.literals:
        statements.append(
            f'cero:{literal.name} "{_escape(literal.value)}"^^{literal.datatype}')
    if element.see_also:
        statements.append('rdfs:seeAlso ' + ', '.join(
            _iri(u) for u in element.see_also))
    lines.append(_iri(element.subject) + '\n    ' + ' ;\n    '.join(statements)
                 + ' .')
    return '\n'.join(lines) + '\n'


def to_jsonld(element: CeroElement) -> Dict[str, Any]:
    node: Dict[str, Any] = {
        '@context': dict(PREFIXES),
        '@id': element.subject,
        '@type': 'bot:Element',
    }
    for literal in element.literals:
        node[f'cero:{literal.name}'] = {'@value': literal.value,
                                        '@type': literal.datatype}
    node['rdfs:seeAlso'] = [{'@id': u} for u in element.see_also]
    return node
