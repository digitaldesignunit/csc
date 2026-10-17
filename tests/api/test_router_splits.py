"""The module splits of 0.6.2.0 (decision 8.160) moved routes between files and
changed nothing a client sees: the generated openapi.json and the route table
(path, method, name, tags, status, response model) are those of before the
splits, kept in tests/fixtures/openapi_before_splits.json, and two routes that
can match the same URL are still tried in the same order."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BEFORE = Path(__file__).resolve().parents[1] / 'fixtures' / 'openapi_before_splits.json'


def route_table(app):
    """The routes in matching order, as the splits captured them."""
    rows = []
    for route in app.router.routes:
        if type(route).__name__ != '_IncludedRouter':
            rows.append({'path': getattr(route, 'path', None), 'name': getattr(route, 'name', None)})
            continue
        for ctx in route.effective_route_contexts():
            rows.append({
                'path': ctx.path_format, 'methods': [], 'name': ctx.name,
                'endpoint': getattr(ctx.endpoint, '__qualname__', str(ctx.endpoint)),
                'tags': [str(t) for t in ctx.tags], 'status_code': ctx.status_code,
                'response_model': str(ctx.response_model),
                'operation_id': ctx.operation_id, 'unique_id': ctx.unique_id,
                'in_schema': ctx.include_in_schema, 'summary': ctx.summary,
                'deprecated': ctx.deprecated})
    return rows


def normalised(row):
    """The module path of a response model is where it is defined, which moves."""
    row = dict(row)
    if 'response_model' in row:
        row['response_model'] = re.sub(r"<class '(?:[\w]+\.)*([\w]+)'>", r"<class '\1'>", row['response_model'])
    return row


def overlap(a, b):
    """Two path templates that can match one URL (no path converters here)."""
    x, y = a.strip('/').split('/'), b.strip('/').split('/')
    if len(x) != len(y):
        return False
    return all(p == q or p.startswith('{') or q.startswith('{') for p, q in zip(x, y))


@pytest.fixture(scope='module')
def before():
    return json.loads(BEFORE.read_text(encoding='utf-8'))


def test_the_generated_openapi_is_the_one_before_the_splits(app, before):
    assert app.openapi() == before['openapi']


def test_every_route_is_still_there_once(app, before):
    now = sorted(json.dumps(normalised(r), sort_keys=True) for r in route_table(app))
    was = sorted(json.dumps(normalised(r), sort_keys=True) for r in before['routes'])
    assert now == was


def test_routes_that_can_match_one_url_keep_their_order(app, before):
    def key(row):
        return (row['path'], row.get('unique_id'))

    now = [key(r) for r in route_table(app)]
    was = [key(r) for r in before['routes']]
    assert sorted(now, key=str) == sorted(was, key=str)
    position = {k: i for i, k in enumerate(now)}
    problems = []
    checked = 0
    for i, first in enumerate(was):
        for second in was[i + 1:]:
            if first[0] and second[0] and overlap(first[0], second[0]) \
                    and position[first] > position[second]:
                problems.append((first, second))
            if first[0] and second[0] and overlap(first[0], second[0]):
                checked += 1
    assert not problems, problems[:5]
    assert checked > 50                       # the check looks at real pairs
