"""
Client identification through the ``X-CSC-Client`` request header.

Every client names itself as ``<client>/<version>``, e.g.
``gh-userobjects/0.5.1.0`` or ``web/0.5.1.0`` (data model spec section 7.4).
0.5.1.0 only logs the header so that old clients can be identified before
the 0.6 cutover; 0.6 rejects clients below a minimum version.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
from typing import Optional, Tuple

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
