#!/usr/bin/env python3.13
"""
The PDF passport summary of one component (spec section 7.8; decisions 8.44
c, 8.116 b, g): at most two A4 pages, English, generated with ReportLab, the
human-readable edition beside the machine-readable JSON (DIN SPEC 91484
section 8).

The builder is a pure function of ``PassportPdfData``: the passport body as
the caller may see it (people already stripped for an anonymous caller, only
published evidence) plus the few facts the body does not carry. It reads
nothing and decides nothing about visibility: the route does that, through the
passport's read path. ``member`` only controls what the body cannot: the
attachment names and the change-log line (8.13, 8.36).

A bundled Noto Sans (SIL Open Font License, ``licenses/NotoSans-OFL.txt``)
carries the characters outside Latin-1 that place and catalogue names hold; the
QR code is ReportLab's own (``reportlab.graphics.barcode.qr``). No system
library is used.
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import io
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse
from xml.sax.saxutils import escape

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# LOCAL IMPORTS ---------------------------------------------------------------
from apps.catalog.exports.cero import is_cero_material
from apps.catalog.vocab import (
    CONDITION_GRADE_LABELS,
    CONNECTION_TYPE_LABELS,
    CONSTRUCTION_METHOD_LABELS,
    DGNB_CLASS_LABELS,
    EVIDENCE_METHOD_LABELS,
    EXIT_KIND_LABELS,
    ORIGIN_KIND_LABELS,
    ORIGINAL_FUNCTION_LABELS,
    QUANTITY_BY_NAME,
    QUANTITY_LABELS,
    SHAPE_CLASS_LABELS,
)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
FONT = 'NotoSans'
FONT_BOLD = 'NotoSans-Bold'
MAX_PAGES = 2

INK = colors.HexColor('#1f2933')
MUTED = colors.HexColor('#616e7c')
RULE = colors.HexColor('#cbd2d9')
LINK = colors.HexColor('#0b5cad')

_VERIFICATION_LABEL = {
    'unverified': 'unverified', 'self_attested': 'self-attested',
    'reviewed': 'reviewed', 'accredited': 'accredited',
}
_VERIFICATION_RANK = ('unverified', 'self_attested', 'reviewed', 'accredited')


@dataclass
class PassportPdfData:
    body: Dict[str, Any]                  # {identity, snapshots[], evidence[]}
    dataset_name: str
    material_label: Optional[str]
    base: str                             # site base: /id/{uuid}
    api_base: str                         # backend base: the JSON editions
    generated_at: str
    member: bool = False                  # attachment names, change log
    parents: List[Dict[str, Any]] = field(default_factory=list)
    children: List[Dict[str, Any]] = field(default_factory=list)
    change_info: Optional[Dict[str, Any]] = None   # members: {count, last_at}
    preview: Optional[bytes] = None       # an image file (JPEG / PNG)


# FONTS -------------------------------------------------------------------------
def register_fonts() -> None:
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(FONT, os.path.join(
        FONT_DIR, 'NotoSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(
        FONT_DIR, 'NotoSans-Bold.ttf')))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD,
                                  italic=FONT, boldItalic=FONT_BOLD)


def _styles() -> Dict[str, ParagraphStyle]:
    base = dict(fontName=FONT, fontSize=8, leading=10.2, textColor=INK)
    return {
        'body': ParagraphStyle('body', **base),
        'muted': ParagraphStyle('muted', **{**base, 'textColor': MUTED}),
        'cell': ParagraphStyle('cell', **{**base, 'fontSize': 7.6,
                                          'leading': 9.4}),
        'head': ParagraphStyle('head', **{**base, 'fontName': FONT_BOLD,
                                          'fontSize': 7.4, 'leading': 9,
                                          'textColor': MUTED}),
        'section': ParagraphStyle('section', **{**base, 'fontName': FONT_BOLD,
                                                'fontSize': 9.6, 'leading': 12,
                                                'spaceBefore': 6,
                                                'spaceAfter': 2}),
        'title': ParagraphStyle('title', **{**base, 'fontName': FONT_BOLD,
                                            'fontSize': 15, 'leading': 18}),
        'sub': ParagraphStyle('sub', **{**base, 'fontSize': 9.4,
                                        'leading': 12}),
        'note': ParagraphStyle('note', **{**base, 'fontName': FONT_BOLD,
                                          'fontSize': 8.4, 'leading': 10.6,
                                          'textColor': colors.HexColor(
                                              '#7a3e00')}),
    }


# TEXT --------------------------------------------------------------------------
def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _link(url: str, label: Optional[str] = None) -> str:
    href = escape(url, {'"': '&quot;'})
    return (f'<link href="{href}" color="#0b5cad">'
            f'{escape(label or url)}</link>')


def fmt_ts(value: Optional[str], precision: Optional[str] = None) -> str:
    """A timestamp at the precision it was recorded with."""
    if not value:
        return ''
    text = str(value)
    if precision == 'year':
        return text[:4]
    if precision == 'month':
        return text[:7]
    if precision in ('day', None, 'unknown'):
        return text[:10]
    return text[:16].replace('T', ' ') + ' UTC'


def _number(value: Any) -> str:
    if isinstance(value, float):
        return f'{value:.6g}'
    return str(value)


def _dim(value: Any) -> str:
    return f'{float(value):.1f}'.rstrip('0').rstrip('.')


def fmt_range(rng: Sequence[Any], unit: Optional[str],
              quantity: Optional[str] = None) -> str:
    """A folded range, with its unit; a grade or a severity as its label."""
    if not rng:
        return ''
    q = QUANTITY_BY_NAME.get(quantity or '')
    if q is not None and q.kind == 'categorical':
        text = ', '.join(str(v) for v in rng)
    elif quantity == 'condition_grade':
        lo, hi = rng[0], rng[-1]
        text = (CONDITION_GRADE_LABELS.get(int(lo), str(lo)) if lo == hi else
                f'{CONDITION_GRADE_LABELS.get(int(lo), lo)} to '
                f'{CONDITION_GRADE_LABELS.get(int(hi), hi)}')
        return text
    elif q is not None and q.kind == 'ordinal':
        text = _number(rng[0]) if rng[0] == rng[-1] else \
            f'{_number(rng[0])} to {_number(rng[-1])}'
    elif len(rng) == 1 or rng[0] == rng[-1]:
        text = _number(rng[0])
    else:
        text = f'{_number(rng[0])} to {_number(rng[-1])}'
    shown = unit if unit and unit != '1' else ''
    return f'{text} {shown}'.strip()


def _result(record: Dict[str, Any]) -> str:
    """What a record says, in one line; a record without a result is a
    document (8.106)."""
    summary = record.get('summary')
    if summary:
        label = QUANTITY_LABELS.get(summary.get('quantity'),
                                    summary.get('quantity') or '')
        unit = summary.get('unit')
        if summary.get('value') not in (None, ''):
            value = f'{_number(summary["value"])} {unit or ""}'.strip() \
                if unit != '1' else _number(summary['value'])
        else:
            value = fmt_range(summary.get('range') or [], unit,
                              summary.get('quantity'))
        return f'{label}: {value}'
    derived = record.get('derived') or []
    if derived:
        first = derived[0]
        label = QUANTITY_LABELS.get(first.get('quantity'),
                                    first.get('quantity') or '')
        value = _number(first['value']) if first.get('value') is not None \
            else fmt_range(first.get('range') or [], first.get('unit'),
                           first.get('quantity'))
        more = f' (+{len(derived) - 1})' if len(derived) > 1 else ''
        return f'{label}: {value} {first.get("unit") or ""}'.rstrip() + more
    return 'a document'


def _host(url: str) -> str:
    return urlparse(url).netloc or url


# SECTIONS ----------------------------------------------------------------------
def _kv(rows: List[Tuple[str, Any]], st: Dict[str, ParagraphStyle],
        width: float, columns: int = 2) -> Optional[Table]:
    rows = [(k, v) for k, v in rows if v not in (None, '', [])]
    if not rows:
        return None
    cells = []
    for index in range(0, len(rows), columns):
        line = []
        for k, v in rows[index:index + columns]:
            line += [_p(k, st['head']),
                     v if isinstance(v, Paragraph) else _p(v, st['cell'])]
        while len(line) < columns * 2:
            line += ['', '']
        cells.append(line)
    label_w = 26 * mm if columns == 2 else 30 * mm
    value_w = (width - label_w * columns) / columns
    table = Table(cells, colWidths=[label_w, value_w] * columns)
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    return table


def _grid(header: List[str], rows: List[List[Any]], widths: List[float],
          st: Dict[str, ParagraphStyle]) -> Table:
    data = [[_p(h, st['head']) for h in header]]
    for row in rows:
        data.append([c if isinstance(c, Paragraph) else _p(c, st['cell'])
                     for c in row])
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, MUTED),
        ('LINEBELOW', (0, 1), (-1, -1), 0.25, RULE),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
    ]))
    return table


def _qr(url: str, size: float) -> Drawing:
    widget = QrCodeWidget(url)
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[
        size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    return drawing


def _image(data: bytes, max_w: float, max_h: float) -> Optional[Image]:
    try:
        image = Image(io.BytesIO(data))
        ratio = min(max_w / image.imageWidth, max_h / image.imageHeight)
        image.drawWidth = image.imageWidth * ratio
        image.drawHeight = image.imageHeight * ratio
        return image
    except Exception:       # a file that is no image: no preview
        return None


def _best_verification(ids: Sequence[str],
                       evidence: Dict[str, Dict[str, Any]]) -> str:
    best = -1
    for evidence_id in ids:
        state = ((evidence.get(evidence_id) or {}).get('verification')
                 or {}).get('state')
        if state in _VERIFICATION_RANK:
            best = max(best, _VERIFICATION_RANK.index(state))
    return _VERIFICATION_LABEL[_VERIFICATION_RANK[best]] if best >= 0 else ''


def _origin_rows(identity: Dict[str, Any]) -> List[Tuple[str, Any]]:
    origin = identity.get('origin') or {}
    work = origin.get('construction_work') or {}
    place = origin.get('place') or {}
    rows: List[Tuple[str, Any]] = []
    if origin.get('planned'):
        rows.append(('Status', 'In place'))
    kind = ORIGIN_KIND_LABELS.get(origin.get('kind'), origin.get('kind') or '')
    if origin.get('planned'):
        # in place: the deinstallation or demolition is still to come
        kind = {'deinstallation': 'Deinstallation planned',
                'demolition': 'Demolition planned'}.get(origin.get('kind'), kind)
    rows.append(('Origin', kind))
    rows.append(('Date', fmt_ts(origin.get('at'), origin.get('at_precision'))))
    rows.append(('Place', ', '.join(
        x for x in (place.get('name'), place.get('address')) if x)))
    works = ', '.join(x for x in (
        work.get('name'),
        f'built {work["year_built"]}' if work.get('year_built') else None,
        work.get('use'),
        CONSTRUCTION_METHOD_LABELS.get(work.get('construction_method'))
        if work.get('construction_method') not in (None, 'unknown') else None,
    ) if x)
    rows.append(('Works', works))
    rows.append(('Position', origin.get('position_in_work')))
    rows.append(('Connections', ', '.join(
        CONNECTION_TYPE_LABELS.get(c, c)
        for c in origin.get('connection_types') or [])))
    for key, label in (('detachability', 'Detachability'),
                       ('material_separability', 'Separability')):
        item = (origin if key == 'detachability' else identity).get(key)
        if item:
            text = DGNB_CLASS_LABELS.get(item.get('class'), item.get('class'))
            if item.get('note'):
                text = f'{text} ({item["note"]})'
            rows.append((label, text))
    rows.append(('Method', origin.get('method')))
    return rows


def _story(data: PassportPdfData, rows_cap: int, props_cap: int,
           st: Dict[str, ParagraphStyle], width: float) -> List[Any]:
    body = data.body
    identity = body['identity']
    snapshot = (body.get('snapshots') or [{}])[0]
    evidence = body.get('evidence') or []
    by_id = {r['_id']: r for r in evidence}
    iri = f'{data.base}/id/{identity["_id"]}'
    origin = identity.get('origin') or {}
    name = snapshot.get('name') or ORIGINAL_FUNCTION_LABELS.get(
        identity.get('original_function'), identity.get('original_function'))
    story: List[Any] = []

    # HEADER ----------------------------------------------------------------
    head_left = [
        _p('Component passport', st['muted']),
        _p(f'#{identity.get("catalog_number")}  {name}', st['title']),
        Spacer(1, 2),
        Paragraph(
            f'Dataset: {escape(data.dataset_name)}<br/>'
            f'Issued {escape(data.generated_at[:10])}'
            + (f' &#183; state v{snapshot["version"]}'
               if snapshot.get('version') is not None else '')
            + f'<br/>{_link(iri)}', st['sub']),
    ]
    header = Table([[head_left, _qr(iri, 26 * mm)]],
                   colWidths=[width - 30 * mm, 30 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, INK),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(header)
    if origin.get('planned'):
        date = fmt_ts(origin.get('at'), origin.get('at_precision'))
        story += [Spacer(1, 3), _p(
            'In place, deinstallation planned'
            + (f' {date}' if date else ' (date not set)'), st['note'])]

    # IDENTITY --------------------------------------------------------------
    story.append(_p('Identity', st['section']))
    function = identity.get('original_function')
    ifc = '' if function == 'CscDebris' else f' ({function})'
    table = _kv([
        ('Function', f'{ORIGINAL_FUNCTION_LABELS.get(function, function)}{ifc}'),
        ('Material', data.material_label or identity.get('material')),
        ('Waste class', identity.get('material_class')),
        ('Trade name', identity.get('trade_name')),
        ('Manufacturer', identity.get('manufacturer')),
        ('Manufactured', fmt_ts(identity.get('manufactured_at'),
                                identity.get('manufactured_precision'))),
    ], st, width)
    if table:
        story.append(table)

    # ORIGIN ----------------------------------------------------------------
    story.append(_p('Origin and DGNB items', st['section']))
    table = _kv(_origin_rows(identity), st, width)
    if table:
        story.append(table)
    if origin.get('kind') == 'deinstallation' and not origin.get('planned'):
        place = (origin.get('place') or {}).get('name') or \
            (origin.get('construction_work') or {}).get('name') or ''
        when = fmt_ts(origin.get('at'), origin.get('at_precision')) \
            or 'date not recorded'
        story += [Spacer(1, 2), Paragraph(
            '<b>CPR Annex V 1(h)</b>, date and place of the latest '
            f'deinstallation: {escape(when)}'
            f'{", " + escape(place) if place else ""}', st['body'])]

    # CURRENT STATE ---------------------------------------------------------
    story.append(_p('Current state', st['section']))
    props = {**(snapshot.get('properties') or {}),
             **(identity.get('properties') or {})}
    bbx = snapshot.get('bbx') or []
    quantity = snapshot.get('quantity') or 1
    remaining = identity.get('remaining')
    state_rows: List[Tuple[str, Any]] = [
        ('Dimensions', ' x '.join(_dim(x) for x in bbx) + ' mm'
         if len(bbx) == 3 else ''),
        ('Shape class', SHAPE_CLASS_LABELS.get(snapshot.get('shape_class'))),
        ('Mass', fmt_range((props.get('mass') or {}).get('range') or [],
                           (props.get('mass') or {}).get('unit'), 'mass')),
        ('Condition', fmt_range(
            (props.get('condition_grade') or {}).get('range') or [], None,
            'condition_grade')),
    ]
    if quantity > 1 or remaining is not None:
        drawn = quantity - remaining if remaining is not None else None
        line = f'{quantity} recorded'
        if drawn is not None:
            line += f', {drawn} drawn, {remaining} remaining'
        state_rows.append(('Batch', line))
    state_table = _kv(state_rows, st, width - 52 * mm, columns=1)
    picture = _image(data.preview, 48 * mm, 36 * mm) if data.preview else None
    if picture is not None:
        state = Table([[picture, state_table or '']],
                      colWidths=[52 * mm, width - 52 * mm])
        state.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        story.append(state)
    elif state_table:
        story.append(_kv(state_rows, st, width))

    # PROPERTIES ------------------------------------------------------------
    folded = [(n, p) for n, p in (identity.get('properties') or {}).items()]
    folded += [(n, p) for n, p in (snapshot.get('properties') or {}).items()
               if n not in (identity.get('properties') or {})]
    if folded:
        story.append(_p('Properties from the evidence', st['section']))
        rows = []
        for n, p in folded[:props_cap]:
            rows.append([
                QUANTITY_LABELS.get(n, n),
                fmt_range(p.get('range') or [], p.get('unit'), n),
                p.get('n'), p.get('source'),
                _best_verification(p.get('evidence_ids') or [], by_id)])
        story.append(_grid(['Quantity', 'Range', 'n', 'Source',
                            'Verification'], rows,
                           [52 * mm, 56 * mm, 10 * mm, 26 * mm,
                            width - 144 * mm], st))
        if len(folded) > props_cap:
            story.append(_p(f'... and {len(folded) - props_cap} more in the '
                            'JSON edition.', st['muted']))

    # EVIDENCE --------------------------------------------------------------
    if evidence:
        story.append(_p('Evidence', st['section']))
        ordered = sorted(evidence, key=lambda r: r.get('observed_at') or '',
                         reverse=True)
        rows = []
        for record in ordered[:rows_cap]:
            result = _result(record)
            document = (record.get('payload') or {}).get('document') or {}
            result_cell: Any = _p(result, st['cell'])
            if document.get('url'):
                title = document.get('title') or _host(document['url'])
                result_cell = Paragraph(
                    f'{escape(result)}<br/>{_link(document["url"], title)}',
                    st['cell'])
            files = [a for a in record.get('attachments') or []
                     if not a.get('removed')]
            if files:
                names = '; '.join(a.get('name') or 'file' for a in files) \
                    if data.member else f'{len(files)} file(s)'
            else:
                names = ''
            rows.append([
                EVIDENCE_METHOD_LABELS.get(record.get('method'),
                                           record.get('method')),
                fmt_ts(record.get('observed_at'),
                       record.get('observed_at_precision')),
                result_cell,
                _VERIFICATION_LABEL.get(
                    (record.get('verification') or {}).get('state'), ''),
                names])
        story.append(_grid(['Method', 'Date', 'Result', 'Verification',
                            'Files'], rows,
                           [34 * mm, 20 * mm, 66 * mm, 22 * mm,
                            width - 142 * mm], st))
        if len(ordered) > rows_cap:
            story.append(_p(f'... and {len(ordered) - rows_cap} more records '
                            'in the JSON edition.', st['muted']))

    # LINEAGE AND CIRCULATION -----------------------------------------------
    story.append(_p('Lineage and circulation', st['section']))

    def _refs(items: List[Dict[str, Any]]) -> Optional[Paragraph]:
        if not items:
            return None
        shown = items[:8]
        text = ', '.join(_link(
            f'{data.base}/id/{i["id"]}',
            f'#{i.get("catalog_number")}' if i.get('catalog_number')
            else i['id'][:8]) for i in shown)
        if len(items) > len(shown):
            text += f' and {len(items) - len(shown)} more'
        return Paragraph(text, st['cell'])

    exit_ = identity.get('exit') or {}
    cycles = identity.get('past_cycles') or []
    cycle_text = '; '.join(
        f'{ORIGIN_KIND_LABELS.get(((c.get("origin") or {}).get("kind")), "origin")} '
        f'{fmt_ts((c.get("origin") or {}).get("at"), (c.get("origin") or {}).get("at_precision"))}'
        f' to {EXIT_KIND_LABELS.get((c.get("exit") or {}).get("kind"), "exit")} '
        f'{fmt_ts((c.get("exit") or {}).get("at"), (c.get("exit") or {}).get("at_precision"))}'
        for c in cycles[:4])
    table = _kv([
        ('Parents', _refs(data.parents)),
        ('Children', _refs(data.children)),
        ('Exit', (f'{EXIT_KIND_LABELS.get(exit_.get("kind"), exit_.get("kind"))} '
                  f'{fmt_ts(exit_.get("at"), exit_.get("at_precision"))}')
         if exit_ else 'In circulation'),
        ('Earlier cycles', cycle_text),
    ], st, width)
    if table:
        story.append(table)

    # FOOTER LINKS ----------------------------------------------------------
    api = data.api_base.rstrip('/')
    compose = f'{api}/identities/{identity["_id"]}/compose'
    editions = [_link(compose, 'JSON'),
                _link(f'{compose}?format=jsonld', 'JSON-LD')]
    if is_cero_material(identity.get('material')):
        editions.append(_link(
            f'{api}/identities/{identity["_id"]}/export/cero', 'CERO'))
    parts = ['Machine-readable editions: ' + ', '.join(editions)]
    if data.member and data.change_info:
        parts.append(
            f'Change log: {data.change_info.get("count", 0)} entries'
            + (f', last change {escape(fmt_ts(data.change_info["last_at"], "exact"))}'
               if data.change_info.get('last_at') else ''))
    parts.append(f'Generated {escape(data.generated_at[:16].replace("T", " "))}'
                 ' UTC')
    story += [Spacer(1, 6), Paragraph('<br/>'.join(parts), st['muted'])]
    return story


def _render(data: PassportPdfData, rows_cap: int, props_cap: int
            ) -> Tuple[bytes, int]:
    register_fonts()
    st = _styles()
    buffer = io.BytesIO()
    page_w, _ = A4
    margin = 14 * mm
    width = page_w - 2 * margin
    identity = data.body['identity']
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=margin, rightMargin=margin,
        topMargin=12 * mm, bottomMargin=14 * mm,
        title=f'Component passport #{identity.get("catalog_number")}',
        author='CSC - Catalog of Second Chances',
        subject='Component passport summary')

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(margin, 8 * mm,
                          f'CSC component passport #{identity.get("catalog_number")}')
        canvas.drawRightString(page_w - margin, 8 * mm,
                               f'Page {document.page}')
        canvas.restoreState()

    doc.build(_story(data, rows_cap, props_cap, st, width),
              onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue(), doc.page


def _flowable_text(flowable: Any) -> List[str]:
    if isinstance(flowable, Paragraph):
        return [flowable.getPlainText()]
    cells = getattr(flowable, '_cellvalues', None)
    if cells is not None:
        out: List[str] = []
        for row in cells:
            for cell in row:
                out += _flowable_text(cell)
        return out
    if isinstance(flowable, (list, tuple)):
        return [t for item in flowable for t in _flowable_text(item)]
    return []


def story_text(data: PassportPdfData, rows_cap: int = 40,
               props_cap: int = 30) -> str:
    """The text the PDF holds, one line per paragraph (the fonts are
    subsets, so the file itself cannot be searched): for tests."""
    register_fonts()
    st = _styles()
    width = A4[0] - 28 * mm
    story = _story(data, rows_cap, props_cap, st, width)
    return '\n'.join(t for f in story for t in _flowable_text(f))


def build_pdf(data: PassportPdfData) -> bytes:
    """The PDF of ``data``: at most two pages. A long evidence list or
    property table is cut back, with a note that the rest is in the JSON
    edition, until it fits."""
    pdf = b''
    for rows_cap, props_cap in ((40, 30), (24, 20), (14, 14), (8, 8), (4, 4),
                                (2, 2)):
        pdf, pages = _render(data, rows_cap, props_cap)
        if pages <= MAX_PAGES:
            return pdf
    return pdf
