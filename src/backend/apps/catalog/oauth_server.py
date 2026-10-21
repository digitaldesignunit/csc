"""
CSC as a small OAuth 2.0 authorization server for Claude's connectors
(decision 8.168), on the authorization-server routes of the MCP Python SDK with
our MongoDB behind them.

What lives where:

* ``oauth_clients``   a registered client (Dynamic Client Registration only).
  The TTL index is on ``expires_at``: a client that never completes a consent
  goes after 1 day; the first consent moves it to 30 days after its last use
  (``last_used`` pushes ``expires_at`` out, at most once an hour)
* ``oauth_requests``  an authorization request waiting for the consent of a
  signed-in account: the SDK has validated the client, the redirect URI and
  PKCE, ``authorize`` stores the request under the hash of a random id and
  sends the browser to the consent page of the web app with that id
  (``api/oauth_consent.py`` takes the account's answer); gone after 10 minutes
* ``oauth_codes``     an authorization code (hash only), good for 5 minutes and
  once; a second use ends the connection it made
* ``access_tokens``   one row of kind ``oauth`` per connection (see
  ``access_tokens.py``): the current access token (1 hour) and refresh token
  (30 days after its last use, rotated on every use, at most 90 days from the
  consent) as two hashes. The Grasshopper client signs in the same way with the
  fixed public client ``csc-grasshopper`` (no registration, loopback redirect
  on 127.0.0.1 only) and scope ``gh:client``, open to every verified account:
  its row is of kind ``device``, its refresh token is ``csc_dev_...`` and its
  access token is the normal CSC JWT of one hour, so every route the Session
  and the other components call keeps working (8.168 f)
* ``oauth_used_refresh`` the hashes of rotated refresh tokens, kept 91 days:
  the use of a dead one ends the whole connection

PKCE S256 is required by the SDK. Redirect URIs: exactly
``https://claude.ai/api/mcp/auth_callback``, and ``http://localhost/callback``
and ``http://127.0.0.1/callback`` with any port.
"""

import contextvars
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import urlsplit

from mcp.server.auth.provider import (
    AccessToken as SdkAccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import (
    InvalidRedirectUriError,
    OAuthClientInformationFull,
    OAuthToken,
)
from pydantic import AnyUrl

import read_only
from apps.catalog import access_tokens as tk
from apps.catalog.token_check import (
    TokenRefused,
    lookup_access_token,
    may_hold_pat,
    note_use,
)
from logging_setup import get_logger

log = get_logger(__name__)

SCOPE = tk.SCOPE_CATALOG
CLAUDE_CALLBACK = 'https://claude.ai/api/mcp/auth_callback'
LOOPBACK_HOSTS = ('localhost', '127.0.0.1')
LOOPBACK_PATH = '/callback'

CODE_SECONDS = 300
REQUEST_SECONDS = 600
CLIENT_UNCONSENTED_DAYS = 1       # a registration nobody consented to
CLIENT_UNUSED_DAYS = 30           # a client that was consented to, unused
USED_REFRESH_DAYS = tk.OAUTH_GRANT_DAYS + 1
CLIENT_NAME_MAX = 100

# the Grasshopper client (8.168 f): one fixed public client, no DCR row
GH_CLIENT_ID = 'csc-grasshopper'
GH_SCOPE = tk.SCOPE_GH
GH_CALLBACK = 'http://127.0.0.1/callback'
GH_ACCESS_TEXT = ('Grasshopper on this computer: act as you in the '
                  'Grasshopper interface')
COMPUTER_MAX = 60
# the computer name the client sends with /authorize (a query parameter the
# SDK does not read): the wrapper of the route sets it for provider.authorize
REQUEST_COMPUTER = contextvars.ContextVar('csc_request_computer', default=None)


def clean_computer(value) -> Optional[str]:
    """A computer name as text to show: printable, no markup, cut."""
    text = ''.join(ch for ch in str(value or '') if ch.isprintable()
                   and ch not in '<>"\'&\\')
    text = ' '.join(text.split())[:COMPUTER_MAX]
    return text or None


# REDIRECT URIS ---------------------------------------------------------------
def _loopback_parts(uri: str):
    """``(host, port)`` of an allowed loopback redirect URI, else None."""
    try:
        parts = urlsplit(uri)
        port = parts.port                      # may raise on a bad port
    except ValueError:
        return None
    if (parts.scheme != 'http' or parts.hostname not in LOOPBACK_HOSTS
            or parts.path != LOOPBACK_PATH or parts.query or parts.fragment
            or parts.username or parts.password):
        return None
    return parts.hostname, port


def redirect_allowed(uri: str) -> bool:
    """A redirect URI a client may register (8.168 d)."""
    return uri == CLAUDE_CALLBACK or _loopback_parts(uri) is not None


def redirect_matches(candidate: str, registered: List[str]) -> bool:
    """Exact, or a loopback URI of the same host and path on any port."""
    if candidate in registered:
        return True
    parts = _loopback_parts(candidate)
    if parts is None:
        return False
    return any((_loopback_parts(uri) or (None,))[0] == parts[0]
               for uri in registered)


def redirect_host(uri: str) -> str:
    """The host the consent page shows."""
    return urlsplit(uri).hostname or ''


class CscClient(OAuthClientInformationFull):
    """A registered client; the redirect check allows a loopback port."""

    def validate_redirect_uri(self, redirect_uri: Optional[AnyUrl]) -> AnyUrl:
        registered = [str(u) for u in (self.redirect_uris or [])]
        if redirect_uri is not None:
            if not redirect_matches(str(redirect_uri), registered):
                raise InvalidRedirectUriError(
                    f"Redirect URI '{redirect_uri}' not registered for "
                    'client')
            return redirect_uri
        if len(registered) == 1:
            return self.redirect_uris[0]
        raise InvalidRedirectUriError(
            'redirect_uri must be specified when client has multiple '
            'registered URIs')


class CscAuthorizationCode(AuthorizationCode):
    pass


class CscRefreshToken(RefreshToken):
    grant_id: str = ''


class CscAccessToken(SdkAccessToken):
    grant_id: str = ''


GH_CLIENT = CscClient(
    client_id=GH_CLIENT_ID, redirect_uris=[AnyUrl(GH_CALLBACK)],
    token_endpoint_auth_method='none',
    grant_types=['authorization_code', 'refresh_token'],
    response_types=['code'], scope=GH_SCOPE, client_name='Grasshopper')


def hash_secret(value: str) -> str:
    """The SHA-256 under which a request id, a code or a token is stored."""
    return tk.token_hash(value)


def _epoch(stamp_text: str) -> float:
    return tk.parse_stamp(stamp_text).timestamp()


# THE PROVIDER ----------------------------------------------------------------
class CscOAuthProvider:
    """The SDK's ``OAuthAuthorizationServerProvider`` over our collections.
    ``app`` carries the collection handles the lifespan sets up."""

    def __init__(self, app, frontend_url: str, resource: str):
        self.app = app
        self.frontend_url = frontend_url.rstrip('/')
        self.resource = resource.rstrip('/')

    # collections
    @property
    def clients(self):
        return self.app.mongodb_oauth_clients

    @property
    def requests(self):
        return self.app.mongodb_oauth_requests

    @property
    def codes(self):
        return self.app.mongodb_oauth_codes

    @property
    def used_refresh(self):
        return self.app.mongodb_oauth_used_refresh

    @property
    def tokens(self):
        return self.app.mongodb_access_tokens

    # clients -----------------------------------------------------------------
    async def get_client(self, client_id: str) -> Optional[CscClient]:
        if client_id == GH_CLIENT_ID:
            return GH_CLIENT
        doc = await self.clients.find_one({'_id': client_id})
        if doc is None:
            return None
        # a client that was consented to goes 30 days after its last use (TTL
        # on expires_at); a use moves that date, written at most once an hour.
        # An unconsented one is not extended: it goes after its first day.
        now = datetime.now(timezone.utc)
        await self.clients.update_one(
            {'_id': client_id, 'consented': True,
             'last_used': {'$lt': now - timedelta(hours=1)}},
            {'$set': {'last_used': now, 'expires_at': now + timedelta(
                days=CLIENT_UNUSED_DAYS)}})
        try:
            return CscClient.model_validate(doc['info'])
        except Exception:
            return None

    async def register_client(self, client_info: OAuthClientInformationFull
                              ) -> None:
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris or not all(redirect_allowed(u) for u in uris):
            raise RegistrationError(
                'invalid_redirect_uri',
                'Allowed redirect URIs: ' + CLAUDE_CALLBACK + ', '
                'http://localhost/callback and http://127.0.0.1/callback '
                '(any port)')
        if client_info.client_name:
            client_info.client_name = client_info.client_name.strip()[
                :CLIENT_NAME_MAX]
        client_info.scope = SCOPE
        info = client_info.model_dump(mode='json', exclude_none=True)
        now = datetime.now(timezone.utc)
        await self.clients.insert_one({
            '_id': client_info.client_id, 'info': info,
            'created': tk.stamp(tk.now()), 'last_used': now,
            'consented': False,
            'expires_at': now + timedelta(days=CLIENT_UNCONSENTED_DAYS)})

    async def client_consented(self, client_id: str) -> None:
        """The first granted consent: from now the client lives 30 days after
        its last use (the same TTL index, a later ``expires_at``)."""
        now = datetime.now(timezone.utc)
        await self.clients.update_one(
            {'_id': client_id},
            {'$set': {'consented': True, 'last_used': now,
                      'expires_at': now + timedelta(days=CLIENT_UNUSED_DAYS)}})

    # the authorization request -------------------------------------------------
    async def authorize(self, client: OAuthClientInformationFull,
                        params: AuthorizationParams) -> str:
        if read_only.is_on():
            # a new consent is a write: the maintenance flag refuses it
            raise AuthorizeError(
                'temporarily_unavailable',
                'The catalog is in maintenance; try again later.')
        gh = client.client_id == GH_CLIENT_ID
        if gh:
            if params.resource:
                raise AuthorizeError('invalid_request',
                                     'this client sends no resource')
            scopes = params.scopes or [GH_SCOPE]
            if scopes != [GH_SCOPE]:
                raise AuthorizeError('invalid_scope',
                                     f'only {GH_SCOPE} is offered')
        else:
            if params.resource and params.resource.rstrip('/') \
                    != self.resource:
                raise AuthorizeError('invalid_request',
                                     'resource is not this server')
            scopes = params.scopes or [SCOPE]
            if scopes != [SCOPE]:
                raise AuthorizeError('invalid_scope',
                                     f'only {SCOPE} is offered')
        request_id = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        await self.requests.insert_one({
            '_id': hash_secret(request_id), 'client_id': client.client_id,
            'redirect_uri': str(params.redirect_uri),
            'redirect_uri_provided_explicitly':
                params.redirect_uri_provided_explicitly,
            'code_challenge': params.code_challenge, 'state': params.state,
            'scopes': scopes, 'resource': params.resource,
            'computer': clean_computer(REQUEST_COMPUTER.get()) if gh else None,
            'created': tk.stamp(now), 'bound_user': None, 'decided': False,
            'expire_at': now + timedelta(seconds=REQUEST_SECONDS)})
        return f'{self.frontend_url}/oauth/consent?request={request_id}'

    # the code ---------------------------------------------------------------------
    async def create_code(self, request_doc: dict, user_id: str) -> str:
        """The code for a request the account allowed (``api/oauth_consent``)."""
        code = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        await self.codes.insert_one({
            '_id': hash_secret(code), 'client_id': request_doc['client_id'],
            'user_id': user_id, 'redirect_uri': request_doc['redirect_uri'],
            'redirect_uri_provided_explicitly':
                request_doc['redirect_uri_provided_explicitly'],
            'code_challenge': request_doc['code_challenge'],
            'scopes': request_doc['scopes'],
            'resource': request_doc.get('resource'),
            'computer': request_doc.get('computer'),
            'expires_at': now.timestamp() + CODE_SECONDS,
            'expire_at': now + timedelta(seconds=CODE_SECONDS + 3600),
            'used': False, 'grant_id': None})
        return code

    async def load_authorization_code(self, client, authorization_code: str
                                      ) -> Optional[CscAuthorizationCode]:
        doc = await self.codes.find_one({'_id': hash_secret(authorization_code)})
        if doc is None or doc['client_id'] != client.client_id:
            return None
        if doc.get('used'):
            # a code used twice: whoever holds the first result loses it
            if doc.get('grant_id'):
                await self._revoke_grant(doc['grant_id'], 'code reused')
            return None
        return CscAuthorizationCode(
            code=authorization_code, scopes=doc['scopes'],
            expires_at=doc['expires_at'], client_id=doc['client_id'],
            code_challenge=doc['code_challenge'],
            redirect_uri=AnyUrl(doc['redirect_uri']),
            redirect_uri_provided_explicitly=doc[
                'redirect_uri_provided_explicitly'],
            resource=doc.get('resource'), subject=doc['user_id'])

    async def exchange_authorization_code(self, client, authorization_code
                                          ) -> OAuthToken:
        h = hash_secret(authorization_code.code)
        claimed = await self.codes.update_one(
            {'_id': h, 'used': False}, {'$set': {'used': True}})
        if claimed.modified_count != 1:
            raise TokenError('invalid_grant', 'authorization code used')
        gh = GH_SCOPE in authorization_code.scopes
        owner = await self.app.mongodb_users.find_one(
            {'_id': authorization_code.subject})
        if not (self._owner_ok(owner) if gh else self._owner_may(owner)):
            raise TokenError('invalid_grant', 'authorization is no longer '
                             'possible for this account')
        now = tk.now()
        hard = now + timedelta(days=tk.OAUTH_GRANT_DAYS)
        grant_id = secrets.token_hex(16)
        host = redirect_host(str(authorization_code.redirect_uri))
        row = {
            '_id': grant_id, 'owner_user_id': authorization_code.subject,
            'short_id': grant_id[:8], 'created': tk.stamp(now),
            'expires': tk.stamp(hard), 'last_used': None, 'revoked': None,
            'refresh_expires': tk.stamp(
                min(now + timedelta(days=tk.OAUTH_REFRESH_DAYS), hard)),
            'client_id': client.client_id, 'redirect_host': host}
        if gh:
            # the Grasshopper client: the access token is the normal JWT of an
            # hour (every route keeps working), the row keeps only the refresh
            # token (csc_dev_...); token_sha256 holds the hash of a token nobody
            # has, so that no bearer can ever find this row as an access token
            code_doc = await self.codes.find_one({'_id': h}) or {}
            refresh = tk.new_token('device')
            access, seconds = self._gh_access_token(owner, now, hard)
            label = code_doc.get('computer') or 'an unnamed computer'
            row.update({
                'kind': 'device', 'scopes': [GH_SCOPE],
                'name': f'Grasshopper on {label}'[:80],
                'token_sha256': hash_secret(tk.new_token('device')),
                'refresh_sha256': hash_secret(refresh)})
            scope = GH_SCOPE
        else:
            access = tk.new_token('oauth')
            refresh = tk.new_refresh_token()
            label = (client.client_name or 'Unnamed client')
            seconds = tk.OAUTH_ACCESS_SECONDS
            row.update({
                'kind': 'oauth', 'scopes': [SCOPE],
                'name': f'{label} ({host})'[:80],
                'token_sha256': hash_secret(access),
                'access_expires': tk.stamp(min(
                    now + timedelta(seconds=seconds), hard)),
                'refresh_sha256': hash_secret(refresh)})
            scope = SCOPE
        await self.tokens.insert_one(row)
        await self.codes.update_one({'_id': h}, {'$set': {'grant_id': grant_id}})
        log.info('oauth connection made: %s (%s, %s)', grant_id[:8],
                 row['kind'], host)
        return OAuthToken(
            access_token=access, token_type='Bearer', expires_in=seconds,
            scope=scope, refresh_token=refresh)

    # refresh ---------------------------------------------------------------------------
    @staticmethod
    def _refresh_kind(token: str) -> Optional[str]:
        """The kind of grant a refresh token belongs to, by its prefix."""
        if token.startswith(tk.OAUTH_REFRESH_PREFIX):
            return 'oauth'
        if token.startswith(tk.DEVICE_PREFIX):
            return 'device'
        return None

    async def load_refresh_token(self, client, refresh_token: str
                                 ) -> Optional[CscRefreshToken]:
        kind = self._refresh_kind(refresh_token)
        if kind is None:
            return None
        h = hash_secret(refresh_token)
        doc = await self.tokens.find_one({'kind': kind, 'refresh_sha256': h})
        if doc is None:
            dead = await self.used_refresh.find_one({'_id': h})
            if dead is not None:
                # a rotated token shown again: it was copied; end the connection
                await self._revoke_grant(dead['grant_id'], 'refresh reused')
            return None
        if doc.get('revoked') or doc['client_id'] != client.client_id:
            return None
        now = tk.stamp(tk.now())
        if doc['expires'] <= now or doc['refresh_expires'] <= now:
            return None
        return CscRefreshToken(
            token=refresh_token, client_id=doc['client_id'],
            scopes=list(doc['scopes']),
            expires_at=int(_epoch(doc['refresh_expires'])),
            subject=doc['owner_user_id'], grant_id=doc['_id'])

    async def exchange_refresh_token(self, client, refresh_token, scopes
                                     ) -> OAuthToken:
        h = hash_secret(refresh_token.token)
        kind = self._refresh_kind(refresh_token.token) or 'oauth'
        gh = kind == 'device'
        owner = await self.app.mongodb_users.find_one(
            {'_id': refresh_token.subject})
        if not (self._owner_ok(owner) if gh else self._owner_may(owner)):
            raise TokenError('invalid_grant', 'the account may no longer '
                             'authorize')
        now = tk.now()
        stamp_now = tk.stamp(now)
        refresh = tk.new_token('device') if gh else tk.new_refresh_token()
        hard = tk.parse_stamp(
            (await self.tokens.find_one({'_id': refresh_token.grant_id},
                                        {'expires': 1}) or {}
             ).get('expires', stamp_now))
        changes = {
            'refresh_sha256': hash_secret(refresh),
            'refresh_expires': tk.stamp(
                min(now + timedelta(days=tk.OAUTH_REFRESH_DAYS), hard)),
            'last_used': stamp_now}
        if gh:
            access, seconds = self._gh_access_token(owner, now, hard)
        else:
            access = tk.new_token('oauth')
            access_expires = min(
                now + timedelta(seconds=tk.OAUTH_ACCESS_SECONDS), hard)
            seconds = max(1, int((access_expires - now).total_seconds()))
            changes.update({'token_sha256': hash_secret(access),
                            'access_expires': tk.stamp(access_expires)})
        claimed = await self.tokens.update_one(
            {'_id': refresh_token.grant_id, 'kind': kind,
             'refresh_sha256': h, 'revoked': None,
             'expires': {'$gt': stamp_now}},
            {'$set': changes})
        if claimed.modified_count != 1:
            # lost a race with another use of the same token, or revoked
            raise TokenError('invalid_grant', 'refresh token is not valid')
        await self.used_refresh.insert_one({
            '_id': h, 'grant_id': refresh_token.grant_id,
            'at': datetime.now(timezone.utc)})
        return OAuthToken(
            access_token=access, token_type='Bearer', expires_in=seconds,
            scope=GH_SCOPE if gh else SCOPE, refresh_token=refresh)

    def _gh_access_token(self, owner: dict, now: datetime, hard: datetime):
        """The normal CSC JWT for the Grasshopper client: an hour, never past
        the hard limit of the connection. ``(token, seconds)``."""
        from apps.catalog.api.auth import create_access_token
        seconds = max(60, min(tk.OAUTH_ACCESS_SECONDS,
                              int((hard - now).total_seconds())))
        token = create_access_token(
            secret=self.app.state.jwt_secret, sub=owner['_id'],
            role=owner.get('role', 'user'), minutes=seconds // 60)
        return token, seconds

    # access tokens and revocation -----------------------------------------------
    async def load_access_token(self, token: str) -> Optional[CscAccessToken]:
        if not token.startswith(tk.OAUTH_ACCESS_PREFIX):
            return None
        doc = await self.tokens.find_one({'kind': 'oauth',
                                          'token_sha256': hash_secret(token)})
        if doc is None or doc.get('revoked'):
            return None
        return CscAccessToken(
            token=token, client_id=doc['client_id'], scopes=list(doc['scopes']),
            expires_at=int(_epoch(doc['access_expires'])),
            subject=doc['owner_user_id'], grant_id=doc['_id'])

    async def revoke_token(self, token) -> None:
        """Revoking either token ends the connection (access and refresh)."""
        grant_id = getattr(token, 'grant_id', '')
        if grant_id:
            await self._revoke_grant(grant_id, 'revoked by the client')

    # helpers ----------------------------------------------------------------------------
    @staticmethod
    def _owner_ok(owner: Optional[dict]) -> bool:
        """An account that may sign Grasshopper in: it exists, is not
        disabled and has a verified address (no role needed, 8.167 e)."""
        return bool(owner and not owner.get('disabled')
                    and owner.get('email_verified', False))

    @staticmethod
    def _owner_may(owner: Optional[dict]) -> bool:
        return bool(owner and not owner.get('disabled')
                    and owner.get('email_verified', False)
                    and may_hold_pat(owner.get('role', 'user')))

    async def _revoke_grant(self, grant_id: str, why: str) -> None:
        done = await self.tokens.update_one(
            {'_id': grant_id, 'kind': {'$in': ['oauth', 'device']},
             'revoked': None},
            {'$set': {'revoked': tk.stamp(tk.now())}})
        if done.modified_count:
            log.warning('oauth connection ended: %s (%s)', grant_id[:8], why)


# THE TOKEN VERIFIER OF THE MCP LAYER ---------------------------------------------------
class AccessTokenVerifier:
    """The SDK's ``TokenVerifier`` over the lookup half of the access-token
    check: a PAT or an OAuth access token, scope ``read:catalog``. A refused
    token is ``None`` (the SDK answers its 401); a valid token over its rate
    limit raises ``RateLimited`` for the gate around ``/mcp`` to answer 429."""

    def __init__(self, app):
        self.app = app

    async def verify_token(self, token: str) -> Optional[SdkAccessToken]:
        try:
            doc, user = await lookup_access_token(self.app, token, SCOPE)
        except TokenRefused as refusal:
            log.info('access token refused: %s (%s)', refusal.reason,
                     refusal.short_id)
            return None
        await note_use(self.app, doc, '/mcp')
        ends = doc['expires']
        if doc['kind'] == 'oauth':
            ends = min(ends, doc['access_expires'])
        return SdkAccessToken(
            token=token, client_id=doc.get('client_id') or doc['kind'],
            scopes=list(doc['scopes']), expires_at=int(_epoch(ends)),
            subject=user.id)
