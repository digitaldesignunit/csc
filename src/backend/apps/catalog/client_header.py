"""
Client identification through the ``X-CSC-Client`` request header.

Every client names itself as ``<client>/<version>``, e.g.
``gh-userobjects/0.6.0.0`` or ``web/0.6.0.0`` (data model spec section 7.4).
Every request is logged. Enforcement (decision 8.11) is on when
``CSC_MIN_CLIENT_VERSIONS`` is set: writes and logged-in requests need a
known client at or above its minimum version, anonymous GETs may omit the
header, and a known client below its minimum always gets 426.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import re
from typing import Dict, Optional, Tuple

CLIENT_HEADER = 'X-CSC-Client'
_HEADER_KEY = CLIENT_HEADER.lower().encode('latin-1')
_CLIENT_RE = re.compile(r'^([a-z][a-z0-9-]{0,39})/(\d+(?:\.\d+){0,3})$')

client_logger = logging.getLogger('csc.clients')


def parse_client_header(value: Optional[str]) -> Optional[Tuple[str, str]]:
    """Return ``(client, version)`` for a well-formed header, else None."""
    if not value:
        return None
    match = _CLIENT_RE.match(value.strip())
    if match is None:
        return None
    return match.group(1), match.group(2)


def describe_client(
    header_value: Optional[str],
    user_agent: Optional[str],
) -> str:
    """One log field naming the caller; falls back to the user agent."""
    parsed = parse_client_header(header_value)
    if parsed is not None:
        return f'client={parsed[0]} version={parsed[1]}'
    if header_value:
        return f'client=invalid raw={header_value[:60]!r}'
    return f'client=unknown agent={(user_agent or "")[:80]!r}'


def configure_client_log(path: str) -> None:
    """Send ``csc.clients`` records to a size-capped file (idempotent)."""
    path = os.path.abspath(path)
    for handler in client_logger.handlers:
        if getattr(handler, 'baseFilename', None) == path:
            return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8',
    )
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    client_logger.addHandler(handler)
    client_logger.setLevel(logging.INFO)
    client_logger.propagate = False


class ClientHeaderLogMiddleware:
    """
    Log one line per HTTP request: caller, method, path, status.

    Pure ASGI so streamed file responses (PLY downloads) pass through
    untouched. Never rejects a request.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        header_value = None
        user_agent = None
        for key, value in scope.get('headers', []):
            if key == _HEADER_KEY:
                header_value = value.decode('latin-1')
            elif key == b'user-agent':
                user_agent = value.decode('latin-1')

        status_holder = {'status': 0}

        async def send_wrapper(message):
            if message['type'] == 'http.response.start':
                status_holder['status'] = message['status']
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            client_logger.info(
                '%s %s %s %s',
                describe_client(header_value, user_agent),
                scope.get('method', '-'),
                scope.get('path', '-'),
                status_holder['status'],
            )


# ENFORCEMENT (decision 8.11) -------------------------------------------------
MIN_VERSIONS_ENV = 'CSC_MIN_CLIENT_VERSIONS'
# the updater must reach everything under /ghinterface/, even when outdated
EXEMPT_PREFIXES: Tuple[str, ...] = (
    '/ghinterface/', '/docs', '/redoc', '/openapi.json', '/health',
    '/version',
)
ANONYMOUS_READ_METHODS: Tuple[str, ...] = ('GET', 'HEAD')
_UPDATE_HINT: Dict[str, str] = {
    'gh-userobjects': 'update the Grasshopper UserObjects via CSC_Update',
    'web': 'reload the page to get the current web app',
}


def version_tuple(version: str) -> Tuple[int, ...]:
    """'0.6.0.0' -> (0, 6, 0, 0); shorter versions are padded with zeros."""
    parts = tuple(int(p) for p in version.split('.'))
    return parts + (0,) * (4 - len(parts))


def parse_min_versions(value: Optional[str]) -> Dict[str, Tuple[int, ...]]:
    """``'gh-userobjects=0.6.0.0,web=0.6.0.0'`` -> minimum per client."""
    table: Dict[str, Tuple[int, ...]] = {}
    for item in (value or '').split(','):
        item = item.strip()
        if not item:
            continue
        client, _, version = item.partition('=')
        if not client.strip() or not version.strip():
            raise ValueError(f'{MIN_VERSIONS_ENV}: bad entry {item!r}')
        table[client.strip()] = version_tuple(version.strip())
    return table


def rejection(
    method: str,
    path: str,
    header_value: Optional[str],
    authenticated: bool,
    min_versions: Dict[str, Tuple[int, ...]],
) -> Optional[str]:
    """
    Why this request is refused with 426, or None when it may pass.

    Without a minimum-version table nothing is refused (log only).
    """
    if not min_versions or method == 'OPTIONS':
        return None
    if any(path == p.rstrip('/') or path.startswith(p)
           for p in EXEMPT_PREFIXES):
        return None
    header_optional = not authenticated and method in ANONYMOUS_READ_METHODS
    parsed = parse_client_header(header_value)
    if parsed is None:
        if header_optional:
            return None
        return ('this request needs an X-CSC-Client header naming a '
                'supported client and its version')
    client, version = parsed
    minimum = min_versions.get(client)
    if minimum is None:
        if header_optional:
            return None
        return f'unknown client {client!r}'
    if version_tuple(version) < minimum:
        hint = _UPDATE_HINT.get(client, 'update the client')
        needed = '.'.join(str(n) for n in minimum)
        return (f'{client} {version} is older than the minimum {needed}: '
                f'{hint}')
    return None


class ClientHeaderEnforcementMiddleware:
    """
    Refuse outdated or unidentified clients with 426 (decision 8.11).

    Reads the minimum-version table from ``app.state.min_client_versions``
    (set at startup from ``CSC_MIN_CLIENT_VERSIONS``). Added inside CORS so
    a refusal still carries CORS headers and reaches the browser as 426.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        state = getattr(scope.get('app'), 'state', None)
        table = getattr(state, 'min_client_versions', None) or {}
        header_value = None
        authenticated = False
        for key, value in scope.get('headers', []):
            if key == _HEADER_KEY:
                header_value = value.decode('latin-1')
            elif key == b'authorization' and value.strip():
                authenticated = True
        reason = rejection(scope.get('method', 'GET'),
                           scope.get('path', ''), header_value,
                           authenticated, table)
        if reason is None:
            await self.app(scope, receive, send)
            return
        body = json.dumps({'detail': reason}).encode('utf-8')
        await send({
            'type': 'http.response.start',
            'status': 426,
            'headers': [(b'content-type', b'application/json'),
                        (b'content-length', str(len(body)).encode())],
        })
        await send({'type': 'http.response.body', 'body': body})
