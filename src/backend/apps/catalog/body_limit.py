"""
Request bodies are capped before a route reads them (decision 8.163).

Starlette spools a whole multipart body to a temporary file before the route
runs, and a JSON body had no cap at all. This ASGI middleware sits in front of
every route and gives each route group its cap from the settings:

* the mesh and point cloud uploads: ``GEOMETRY_UPLOAD_LIMIT_MB``
* the evidence attachments: ``EVIDENCE_UPLOAD_LIMIT_MB``
* the photos: ``SNAPSHOT_PHOTO_UPLOAD_LIMIT_MB``
  (each plus ``MULTIPART_OVERHEAD_BYTES`` for the multipart framing)
* the result route of the remote runner: no cap here, it has its own limits
  (``geometry_remote.py``)
* every other route: ``CSC_JSON_BODY_LIMIT_MB``

A ``Content-Length`` above the cap is answered 413 without reading a byte. A
body without one (chunked) is counted as it arrives, and the answer is 413 as
soon as the cap is passed. ``read_upload_limited`` stays as the second check
of the file size itself. Added inside CORS, so the refusal carries the CORS
headers and reaches the browser as 413.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

from settings import get_settings

MULTIPART_OVERHEAD_BYTES = 1024 * 1024
MB = 1024 * 1024
BODY_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE')

# (method, path pattern, setting that holds the cap in MB; None: no cap here)
_GROUPS: List[Tuple[str, 're.Pattern', Optional[str]]] = [
    ('PUT', re.compile(r'^/snapshots/[^/]+/meshes/'), 'geometry_upload_limit_mb'),
    ('PUT', re.compile(r'^/snapshots/[^/]+/point_clouds/'),
     'geometry_upload_limit_mb'),
    ('POST', re.compile(r'^/evidence/attachments/?$'),
     'evidence_upload_limit_mb'),
    ('PUT', re.compile(r'^/snapshots/[^/]+/photos/'),
     'snapshot_photo_upload_limit_mb'),
    ('POST', re.compile(r'^/geometry/results/'), None),
]
_FILE_GROUPS = {'geometry_upload_limit_mb', 'evidence_upload_limit_mb',
                'snapshot_photo_upload_limit_mb'}


def body_cap(method: str, path: str) -> Optional[int]:
    """The largest body in bytes that ``method path`` takes, or None."""
    settings = get_settings()
    for group_method, pattern, name in _GROUPS:
        if method == group_method and pattern.match(path):
            if name is None:
                return None
            return getattr(settings, name) * MB + (
                MULTIPART_OVERHEAD_BYTES if name in _FILE_GROUPS else 0)
    return settings.csc_json_body_limit_mb * MB


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in BODY_METHODS:
            await self.app(scope, receive, send)
            return
        cap = body_cap(scope['method'], scope.get('path', ''))
        if cap is None:
            await self.app(scope, receive, send)
            return
        for key, value in scope.get('headers', []):
            if key == b'content-length':
                try:
                    declared = int(value)
                except ValueError:
                    declared = 0
                if declared > cap:
                    await self._refuse(send, cap)
                    return
                break

        # The count cannot raise: FastAPI turns any error of reading the body
        # into a 400. Past the cap the app is told the client is gone, and
        # whatever it answers is replaced by the 413.
        received = 0
        exceeded = refused = started = False

        async def counted_receive():
            nonlocal received, exceeded
            if exceeded:
                return {'type': 'http.disconnect'}
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > cap:
                    exceeded = True
                    return {'type': 'http.disconnect'}
            return message

        async def watched_send(message):
            nonlocal refused, started
            if exceeded and not started:
                if not refused:
                    refused = True
                    await self._refuse(send, cap)
                return
            if message['type'] == 'http.response.start':
                started = True
            await send(message)

        await self.app(scope, counted_receive, watched_send)
        if exceeded and not refused and not started:
            await self._refuse(send, cap)

    @staticmethod
    async def _refuse(send, cap: int) -> None:
        limit = max(1, round(cap / MB))
        body = json.dumps({
            'detail': f'The request is too large; the limit here is '
                      f'{limit} MB.'}).encode('utf-8')
        await send({
            'type': 'http.response.start',
            'status': 413,
            'headers': [(b'content-type', b'application/json'),
                        (b'content-length', str(len(body)).encode()),
                        (b'connection', b'close')],
        })
        await send({'type': 'http.response.body', 'body': body})
