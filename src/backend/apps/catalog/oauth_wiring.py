"""
Puts the OAuth server and the MCP endpoint into the application (decision
8.168). Off, with one log line, when ``CSC_PUBLIC_API_URL`` is not set: the
issuer and the resource of the metadata are that address, and a connector must
be given the same one (``https://<api host>/mcp``).

``install`` runs when the module of the app is imported: the routes at the root
of the API host

* ``/.well-known/oauth-protected-resource/mcp`` and
  ``/.well-known/oauth-authorization-server``   (discovery)
* ``/register`` (dynamic client registration), ``/authorize``, ``/token``,
  ``/revoke``                                   (the SDK's handlers)
* ``/mcp``                                      (the tools, behind the check)

``start`` runs in the lifespan, once the database is up: it makes the MCP server
and runs its session manager. The per-address limits of ``/register``,
``/authorize`` and ``/token`` count in the shared store like the sign-in's.
"""

from contextlib import AsyncExitStack
from typing import Optional

import anyio
from limits import parse
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.routes import (
    build_metadata,
    build_resource_metadata_url,
    cors_middleware,
    create_auth_routes,
    create_protected_resource_routes,
)
from mcp.server.auth.settings import (
    ClientRegistrationOptions,
    RevocationOptions,
)
from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

import limiter as lim
from apps.catalog.mcp_server import build_gate, build_mcp
from apps.catalog.oauth_server import SCOPE, CscOAuthProvider
from logging_setup import get_logger

log = get_logger(__name__)

# per address, like the sign-in; /register and /token are called from
# Anthropic's addresses, which many people share, so they are not tight
LIMITS = {'/register': '30/minute', '/authorize': '30/minute',
          '/token': '120/minute'}


class AddressLimit:
    """An ASGI wrapper: one count per client address and endpoint."""

    def __init__(self, inner, name: str, rate: str):
        self.inner = inner
        self.name = name
        self.item = parse(rate)

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and scope['method'] != 'OPTIONS':
            address = lim.client_ip(Request(scope))
            counter = lim.shared_limiter._limiter
            allowed = await anyio.to_thread.run_sync(
                counter.hit, self.item, 'oauth', self.name, address)
            if not allowed:
                response = JSONResponse(
                    {'error': 'rate_limited',
                     'error_description': 'Too many requests; wait a minute.'},
                    status_code=429, headers={'Retry-After': '60'})
                await response(scope, receive, send)
                return
        await self.inner(scope, receive, send)


class McpEndpoint:
    """``/mcp``: the gate built by ``start``; 503 before it exists."""

    async def __call__(self, scope, receive, send):
        gate = scope['app'].state.mcp_gate
        if gate is None:
            await JSONResponse(
                {'detail': 'The MCP endpoint is starting.'},
                status_code=503)(scope, receive, send)
            return
        await gate(scope, receive, send)


def install(app, settings) -> bool:
    api = (settings.csc_public_api_url or '').rstrip('/')
    app.state.oauth_provider = None
    app.state.mcp_gate = None
    if not api:
        log.info('MCP and OAuth are off: CSC_PUBLIC_API_URL is not set')
        return False
    resource = f'{api}/mcp'
    provider = CscOAuthProvider(app, settings.frontend_url, resource)
    app.state.oauth_provider = provider
    app.state.mcp_resource = resource
    issuer = AnyHttpUrl(api)
    registration = ClientRegistrationOptions(
        enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE])
    revocation = RevocationOptions(enabled=True)
    routes = []
    for route in create_auth_routes(
            provider, issuer, client_registration_options=registration,
            revocation_options=revocation):
        if route.path == '/.well-known/oauth-authorization-server':
            # a public client (Claude's) registers with auth method none
            metadata = build_metadata(issuer, None, registration, revocation)
            metadata.token_endpoint_auth_methods_supported = [
                'none', 'client_secret_post', 'client_secret_basic']
            route = Route(route.path, endpoint=cors_middleware(
                MetadataHandler(metadata).handle, ['GET', 'OPTIONS']),
                methods=['GET', 'OPTIONS'])
        elif route.path in LIMITS:
            route = Route(route.path, endpoint=AddressLimit(
                route.endpoint, route.path, LIMITS[route.path]),
                methods=sorted(route.methods or []))
        routes.append(route)
    routes += create_protected_resource_routes(
        AnyHttpUrl(resource), [issuer], scopes_supported=[SCOPE],
        resource_name='Catalog of Second Chances')
    routes.append(Route('/mcp', endpoint=McpEndpoint(),
                        methods=['GET', 'POST', 'DELETE', 'OPTIONS']))
    app.router.routes.extend(routes)
    log.info('MCP and OAuth are on: %s', resource)
    return True


async def start(app, settings, stack: AsyncExitStack) -> Optional[object]:
    """In the lifespan: the MCP server and its session manager; ``stack``
    stops it again."""
    provider: Optional[CscOAuthProvider] = app.state.oauth_provider
    if provider is None:
        return None
    mcp = build_mcp(app, settings.frontend_url)
    metadata_url = str(build_resource_metadata_url(
        AnyHttpUrl(app.state.mcp_resource)))
    gate, manager = build_gate(app, mcp, metadata_url)
    await stack.enter_async_context(manager.run())
    app.state.mcp_gate = gate
    return mcp
