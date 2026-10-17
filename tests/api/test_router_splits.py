"""The routes of the live app (decision 8.160): every method and path is
registered once, and no route is shadowed by an earlier one with a parameter
where it has a literal segment (`/users/{id}` before `/users/me`). The module
splits of 0.6.2.0 were proven against a capture of the generated openapi.json
and the route table taken before the splits; the capture is gone, these two
checks stay."""

from __future__ import annotations

from collections import Counter


def live_routes(app):
    """``(method, path, name)`` of every route in matching order."""
    rows = []
    for route in app.router.routes:
        if type(route).__name__ != '_IncludedRouter':
            continue
        for ctx in route.effective_route_contexts():
            method = ctx.unique_id.rsplit('_', 1)[-1].upper()
            rows.append((method, ctx.path_format, ctx.name))
    return rows


def segments(path):
    return path.strip('/').split('/')


def shadows(first, second):
    """``first`` (earlier) catches every URL of ``second`` and more: same
    length, and wherever they differ ``first`` has the parameter."""
    x, y = segments(first), segments(second)
    if len(x) != len(y) or x == y:
        return False
    return all(p == q or p.startswith('{') for p, q in zip(x, y))


def test_every_method_and_path_is_registered_once(app):
    routes = live_routes(app)
    assert len(routes) > 100
    twice = [key for key, n in Counter((m, p) for m, p, _ in routes).items() if n > 1]
    assert not twice, twice


def test_no_route_is_shadowed_by_an_earlier_one(app):
    routes = live_routes(app)
    shadowed = [(a, b) for i, a in enumerate(routes) for b in routes[i + 1:]
                if a[0] == b[0] and shadows(a[1], b[1])]
    assert not shadowed, shadowed[:5]
