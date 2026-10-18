"""
Two limiters (src/backend/limiter.py): the shared one counts in the MongoDB
store, the local one in the process. Every limited route is in exactly one
group, and the shared group is the list below.
"""

from __future__ import annotations

import limiter as lim

SHARED = {
    'apps.catalog.api.auth.login_for_access_token',
    'apps.catalog.api.auth.register_user',
    'apps.catalog.api.auth.resend_verification',
    'apps.catalog.api.auth.request_password_reset',
    'apps.catalog.api.auth.confirm_password_reset',
    'apps.catalog.api.invitations.preview_invitation',
    'apps.catalog.api.invitations.accept_invitation',
}


def live_endpoints(app):
    names = {}
    for route in app.router.routes:
        if type(route).__name__ != '_IncludedRouter':
            continue
        for ctx in route.effective_route_contexts():
            endpoint = getattr(ctx, 'endpoint', None)
            if endpoint is not None:
                key = f'{endpoint.__module__}.{endpoint.__name__}'
                names.setdefault(key, []).append((ctx.unique_id, ctx.path_format))
    return names


def test_the_shared_group_is_the_list(app):
    assert set(lim.shared_limiter._route_limits) == SHARED


def test_no_route_is_in_both_groups():
    both = set(lim.shared_limiter._route_limits) & set(lim.local_limiter._route_limits)
    assert not both, both


def test_every_limited_function_is_a_route_of_the_app(app):
    live = live_endpoints(app)
    limited = set(lim.shared_limiter._route_limits) | set(lim.local_limiter._route_limits)
    assert len(limited) > len(SHARED)
    for name in limited:
        assert live.get(name), name


def test_only_the_shared_limiter_has_a_shared_store(app):
    from limits.storage import MemoryStorage
    assert isinstance(lim.local_limiter._storage, MemoryStorage)
    assert lim.local_limiter._storage is not lim.shared_limiter._storage
    assert app.state.limiter is lim.shared_limiter


def test_a_local_route_does_not_touch_the_shared_store(api, auth_headers, monkeypatch):
    headers = auth_headers('user')
    lim.store().reset()
    for each in (lim.local_limiter, lim.shared_limiter):
        monkeypatch.setattr(each, 'enabled', True)
    try:
        calls = []
        real = lim.store().incr
        monkeypatch.setattr(lim.store(), 'incr',
                            lambda *a, **k: calls.append(a) or real(*a, **k))
        assert api.get('/identities/count', headers=headers).status_code == 200
        assert not calls
    finally:
        for each in (lim.local_limiter, lim.shared_limiter):
            each.enabled = False
            each.reset()
