"""
While the read-only flag is set, every write is refused (decision 8.154).

An ASGI middleware next to the body limit (``body_limit.py``), outside it, so
the 503 comes before any body is read: every request whose method is not GET,
HEAD or OPTIONS gets 503, ``Retry-After`` and ``{"detail": "read-only:
maintenance"}``. Registration, uploads and the Grasshopper writes are included.
The exceptions are the sign-in (``POST /auth/token``): it stays open for
checks and writes nothing while the flag is set (see ``auth.py``), and the MCP
layer (``POST /mcp``, ``POST /token``), which only reads the catalog. Added inside
CORS, so the refusal carries the CORS headers and the web app can read it.

``read_only.is_on()`` looks at the file on every request.
"""

from __future__ import annotations

import json

import read_only

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')
# the sign-in, and the MCP layer (8.168): every MCP call is a POST, and a
# refresh rotates a token (a token write, allowed); a new registration, a new
# consent and a revoke are not open and get the 503 like every write
OPEN_WRITES = (('POST', '/auth/token'), ('POST', '/mcp'), ('POST', '/token'))


class ReadOnlyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') in SAFE_METHODS:
            await self.app(scope, receive, send)
            return
        if (scope.get('method'), scope.get('path', '').rstrip('/')) in OPEN_WRITES \
                or not read_only.is_on():
            await self.app(scope, receive, send)
            return
        body = json.dumps({'detail': read_only.DETAIL}).encode('utf-8')
        await send({
            'type': 'http.response.start',
            'status': 503,
            'headers': [(b'content-type', b'application/json'),
                        (b'content-length', str(len(body)).encode()),
                        (b'retry-after', str(read_only.RETRY_AFTER_SECONDS).encode()),
                        (b'connection', b'close')],
        })
        await send({'type': 'http.response.body', 'body': body})
