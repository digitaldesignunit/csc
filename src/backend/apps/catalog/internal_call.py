"""
A read of the REST API from inside the backend, as one account (decision 8.168,
the tools of the MCP layer).

The tools do not copy the loaders and serialisers of the routes: they call the
routes. A call goes through the whole application with a JWT of one minute made
for the owner of the token, so every route decides as it does for the web app
(visibility of datasets, withdrawn versions, redaction of people) and its limits
count that account's reads. The call carries the client ``mcp/<version>`` and
the ASGI scope key ``csc_internal``, which the client-header check lets pass
(there is no network hop and no header an outsider could set). Only GET.
"""

from typing import Any, Dict, Optional
from urllib.parse import urlencode

from csc_version import CSC_VERSION

CALL_MINUTES = 1


class InternalError(Exception):
    """A route answered with a status other than 200."""

    def __init__(self, status: int, detail: Any):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


async def rest_get(app, user, path: str,
                   params: Optional[Dict[str, Any]] = None) -> Any:
    """The JSON of ``GET path`` as ``user`` sees it; ``InternalError`` for any
    other status."""
    import json

    from apps.catalog.api.auth import create_access_token

    token = create_access_token(
        secret=app.state.jwt_secret, sub=user.id, role=user.role,
        minutes=CALL_MINUTES)
    query = urlencode([(k, v if not isinstance(v, bool) else str(v).lower())
                       for k, v in (params or {}).items()
                       if v is not None and v != ''])
    scope = {
        'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'method': 'GET', 'scheme': 'http', 'path': path,
        'raw_path': path.encode('ascii'), 'query_string': query.encode(),
        'root_path': '', 'server': ('internal', 80),
        'client': ('127.0.0.1', 0),
        'headers': [
            (b'host', b'internal'),
            (b'accept', b'application/json'),
            (b'authorization', b'Bearer ' + token.encode('ascii')),
            (b'x-csc-client', f'mcp/{CSC_VERSION}'.encode('ascii')),
        ],
        'csc_internal': True,
    }
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {'type': 'http.disconnect'}
        sent = True
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    status_code = 500
    chunks = []

    async def send(message):
        nonlocal status_code
        if message['type'] == 'http.response.start':
            status_code = message['status']
        elif message['type'] == 'http.response.body':
            chunks.append(message.get('body', b''))

    await app(scope, receive, send)
    raw = b''.join(chunks)
    try:
        body = json.loads(raw) if raw else None
    except ValueError:
        body = raw.decode('utf-8', 'replace')[:200]
    if status_code != 200:
        detail = body.get('detail') if isinstance(body, dict) else body
        raise InternalError(status_code, detail)
    return body
