"""
Access tokens: the routes and the check (decision 8.167).

Routes (a signed-in account, JWT as everywhere):

* ``POST   /auth/access-tokens``              create a personal access token
  (name, 30 / 90 / 365 days); the plain token is in this answer only
* ``GET    /auth/access-tokens``              the caller's own tokens
* ``DELETE /auth/access-tokens/{id}``         revoke one of the caller's own
* ``POST   /auth/access-tokens/{id}/renew``   a new token, the old one revoked
* ``GET    /admin/access-tokens``             admin: every token (owner user
  name, no e-mail address)
* ``DELETE /admin/access-tokens/{id}``        admin: revoke any token
* ``GET    /auth/token-check``                with a token itself (scope
  ``read:catalog``): who owns it, its scope, its expiry

``access_token_user(scope)`` is the dependency a route puts in front of
itself to be reached with an access token (the MCP layer, the device
sign-in). It reads ``Authorization: Bearer csc_...``, hashes the token,
loads it from the database on every request (no cache) and checks, in this
order: not revoked, not expired, the scope asked for, the owner still exists,
is not disabled and has a verified address, and, for a personal access token,
still has a role of ``CSC_PAT_ROLES``. Any failure is the same 401 with the
same text, so the answer does not tell which check failed (the log does). A
JWT is refused here, and ``auth.lookup_user_from_token`` refuses ``csc_``
tokens. 120 requests a minute per token are allowed, counted per worker in
memory (8.152) after the token has proved itself.
"""

import time
import uuid
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from pydantic import BaseModel, ConfigDict, Field

import read_only
from apps.catalog import access_tokens as tk
from apps.catalog.documents import AccessToken
from apps.catalog.models import UserInDB
from logging_setup import get_logger
from settings import get_settings
from .auth import get_current_active_user, require_admin

log = get_logger(__name__)

router = APIRouter()

REFUSED = 'Invalid or expired access token'


# ROWS ------------------------------------------------------------------------
class TokenRow(BaseModel):
    """What a list shows of a token: never the token, never its hash."""
    id: str
    kind: str
    name: str
    scopes: List[str]
    short_id: str
    created: str
    expires: str
    last_used: Optional[str] = None
    revoked: Optional[str] = None
    status: str
    renew_due: bool = False


class TokenCreated(TokenRow):
    """The answer of a create or a renew: the plain token, once."""
    token: str


class AdminTokenRow(TokenRow):
    owner_id: str
    owner_username: Optional[str] = None


class CreatePayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    days: int = Field(tk.DEFAULT_PAT_DAYS)


class RenewPayload(BaseModel):
    days: Optional[int] = None


class Options(BaseModel):
    """What the settings page needs to draw its form."""
    can_create: bool
    lifetimes: List[int]
    default_days: int
    max_active: int


class TokenCheck(BaseModel):
    owner: str
    scope: str
    expires: str


def _row(doc: dict, moment=None) -> dict:
    moment = moment or tk.now()
    state = tk.status_of(doc, moment)
    left = tk.parse_stamp(doc['expires']) - moment
    return {
        'id': doc['_id'], 'kind': doc['kind'], 'name': doc['name'],
        'scopes': list(doc['scopes']), 'short_id': doc['short_id'],
        'created': doc['created'], 'expires': doc['expires'],
        'last_used': doc.get('last_used'), 'revoked': doc.get('revoked'),
        'status': state,
        'renew_due': state == 'active'
        and left.days < tk.RENEW_WITHIN_DAYS,
    }


def _tokens(request: Request):
    return request.app.mongodb_access_tokens


def _may_hold_pat(role: str) -> bool:
    return role in get_settings().pat_roles


async def _count_active(request: Request, user_id: str,
                        except_id: Optional[str] = None) -> int:
    query = {'owner_user_id': user_id, 'revoked': None,
             'expires': {'$gt': tk.stamp(tk.now())}}
    if except_id:
        query['_id'] = {'$ne': except_id}
    return await _tokens(request).count_documents(query)


async def _create(request: Request, user: UserInDB, name: str, days: int,
                  except_id: Optional[str] = None) -> dict:
    """Insert a personal access token for ``user``; the 10-token limit holds
    even for two requests at once (counted again after the insert)."""
    if await _count_active(request, user.id, except_id) \
            >= tk.MAX_ACTIVE_TOKENS:
        raise _too_many()
    token = tk.new_token('pat')
    moment = tk.now()
    doc = AccessToken(
        _id=uuid.uuid4().hex, kind='pat', owner_user_id=user.id,
        scopes=[tk.SCOPE_CATALOG], name=name.strip(),
        token_sha256=tk.token_hash(token), short_id=tk.short_id_of(token),
        created=tk.stamp(moment), expires=tk.expires_at(days, moment),
    ).model_dump(by_alias=True)
    await _tokens(request).insert_one(doc)
    if await _count_active(request, user.id, except_id) \
            > tk.MAX_ACTIVE_TOKENS:
        await _tokens(request).delete_one({'_id': doc['_id']})
        raise _too_many()
    return {**_row(doc, moment), 'token': token}


def _too_many() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f'You already have {tk.MAX_ACTIVE_TOKENS} active access tokens: '
        'revoke one first.')


def _check_days(days: int) -> int:
    if days not in tk.PAT_LIFETIME_DAYS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            'days must be one of ' + ', '.join(
                str(d) for d in tk.PAT_LIFETIME_DAYS))
    return days


def _check_role(user: UserInDB) -> None:
    if not _may_hold_pat(user.role):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            'Personal access tokens are not available for your role.')


async def _load_own(request: Request, user: UserInDB, token_id: str) -> dict:
    doc = await _tokens(request).find_one(
        {'_id': token_id, 'owner_user_id': user.id})
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'No such token')
    return doc


async def _revoke(request: Request, doc: dict) -> dict:
    if not doc.get('revoked'):
        revoked = tk.stamp(tk.now())
        await _tokens(request).update_one(
            {'_id': doc['_id'], 'revoked': None},
            {'$set': {'revoked': revoked}})
        doc = {**doc, 'revoked': revoked}
    return doc


# OWN TOKENS ------------------------------------------------------------------
def _no_store(response: Response) -> None:
    """A page that holds a token is never cached."""
    response.headers['Cache-Control'] = 'no-store'


@router.get('/auth/access-tokens/options', response_model=Options,
            summary='Whether the caller may create a token, and the choices')
async def access_token_options(
    user: UserInDB = Depends(get_current_active_user),
):
    return {'can_create': _may_hold_pat(user.role),
            'lifetimes': list(tk.PAT_LIFETIME_DAYS),
            'default_days': tk.DEFAULT_PAT_DAYS,
            'max_active': tk.MAX_ACTIVE_TOKENS}


@router.post('/auth/access-tokens', response_model=TokenCreated,
             status_code=status.HTTP_201_CREATED,
             summary='Create a personal access token (shown once)')
async def create_access_token_route(
    request: Request,
    response: Response,
    payload: CreatePayload,
    user: UserInDB = Depends(get_current_active_user),
):
    _check_role(user)
    _check_days(payload.days)
    _no_store(response)
    created = await _create(request, user, payload.name, payload.days)
    log.info('access token created: %s', created['short_id'])
    return created


@router.get('/auth/access-tokens', response_model=List[TokenRow],
            summary='The caller\'s own access tokens')
async def list_own_access_tokens(
    request: Request,
    user: UserInDB = Depends(get_current_active_user),
):
    cursor = _tokens(request).find(
        {'owner_user_id': user.id, 'revoked': None}).sort('created', -1)
    moment = tk.now()
    return [_row(doc, moment) async for doc in cursor]


@router.delete('/auth/access-tokens/{token_id}', response_model=TokenRow,
               summary='Revoke one of the caller\'s own access tokens')
async def revoke_own_access_token(
    request: Request,
    token_id: str,
    user: UserInDB = Depends(get_current_active_user),
):
    doc = await _revoke(request, await _load_own(request, user, token_id))
    log.info('access token revoked: %s', doc['short_id'])
    return _row(doc)


@router.post('/auth/access-tokens/{token_id}/renew',
             response_model=TokenCreated, status_code=status.HTTP_201_CREATED,
             summary='A new token with the old one\'s name; the old is revoked')
async def renew_access_token(
    request: Request,
    response: Response,
    token_id: str,
    payload: Optional[RenewPayload] = None,
    user: UserInDB = Depends(get_current_active_user),
):
    old = await _load_own(request, user, token_id)
    if old['kind'] != 'pat':
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'No such token')
    if old.get('revoked'):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            'This token is revoked and cannot be renewed.')
    _check_role(user)
    days = _check_days((payload.days if payload and payload.days else None)
                       or tk.lifetime_days(old))
    _no_store(response)
    # the old token does not count: it is replaced
    created = await _create(request, user, old['name'], days,
                            except_id=old['_id'])
    await _revoke(request, old)
    log.info('access token renewed: %s -> %s', old['short_id'],
             created['short_id'])
    return created


# ADMIN -----------------------------------------------------------------------
@router.get('/admin/access-tokens', response_model=List[AdminTokenRow],
            summary='Admin: every access token')
async def list_all_access_tokens(
    request: Request,
    admin: UserInDB = Depends(require_admin),
):
    docs = [doc async for doc in _tokens(request).find({}).sort(
        'created', -1).limit(1000)]
    owners = {}
    ids = list({doc['owner_user_id'] for doc in docs})
    if ids:
        async for user in request.app.mongodb_users.find(
                {'_id': {'$in': ids}}, {'username': 1}):
            owners[user['_id']] = user.get('username')
    moment = tk.now()
    return [{**_row(doc, moment), 'owner_id': doc['owner_user_id'],
             'owner_username': owners.get(doc['owner_user_id'])}
            for doc in docs]


@router.delete('/admin/access-tokens/{token_id}', response_model=TokenRow,
               summary='Admin: revoke any access token')
async def revoke_any_access_token(
    request: Request,
    token_id: str,
    admin: UserInDB = Depends(require_admin),
):
    doc = await _tokens(request).find_one({'_id': token_id})
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'No such token')
    doc = await _revoke(request, doc)
    log.info('access token revoked by an admin: %s', doc['short_id'])
    return _row(doc)


# THE CHECK -------------------------------------------------------------------
_counters = FixedWindowRateLimiter(MemoryStorage())


def _refuse(reason: str, short_id: str = '-') -> HTTPException:
    """The one answer for every failed check; the log has the reason."""
    log.info('access token refused: %s (%s)', reason, short_id)
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, REFUSED,
        headers={'WWW-Authenticate': 'Bearer'})


def _bearer(request: Request) -> str:
    scheme, _, token = (request.headers.get('authorization') or '') \
        .partition(' ')
    return token.strip() if scheme.lower() == 'bearer' else ''


async def _touch(request: Request, doc: dict) -> None:
    """``last_used``, at most once a minute per token and never while the
    read-only flag is set. The condition is in the update, so two workers do
    not both write."""
    if read_only.is_on():
        return
    moment = tk.now()
    due = tk.stamp(moment - timedelta(
        seconds=tk.LAST_USED_INTERVAL_SECONDS))
    await _tokens(request).update_one(
        {'_id': doc['_id'], '$or': [{'last_used': None},
                                    {'last_used': {'$lt': due}}]},
        {'$set': {'last_used': tk.stamp(moment)}})


def _within_rate(short_id: str) -> Optional[int]:
    """None when the token may go on, else the seconds to wait."""
    item = parse(f'{tk.REQUESTS_PER_MINUTE}/minute')
    if _counters.hit(item, short_id):
        return None
    reset = _counters.get_window_stats(item, short_id).reset_time
    return max(1, int(reset - time.time()) + 1)


def access_token_user(scope: str):
    """A dependency: the user an access token of ``scope`` belongs to."""

    async def dependency(request: Request) -> UserInDB:
        token = _bearer(request)
        if not token or tk.prefix_of(token) is None:
            raise _refuse('not an access token')      # a JWT lands here
        doc = await _tokens(request).find_one(
            {'token_sha256': tk.token_hash(token)})
        if doc is None:
            raise _refuse('unknown token')
        short = doc['short_id']
        if doc.get('revoked'):
            raise _refuse('revoked', short)
        if doc['expires'] <= tk.stamp(tk.now()):
            raise _refuse('expired', short)
        if scope not in doc.get('scopes', ()):
            raise _refuse('wrong scope', short)
        owner = await request.app.mongodb_users.find_one(
            {'_id': doc['owner_user_id']})
        if not owner or owner.get('disabled') \
                or not owner.get('email_verified', False):
            raise _refuse('owner missing, disabled or unverified', short)
        if doc['kind'] == 'pat' and not _may_hold_pat(
                owner.get('role', 'user')):
            raise _refuse('owner has lost the role', short)
        try:
            user = UserInDB(**owner)
        except Exception:
            raise _refuse('owner record unreadable', short)
        wait = _within_rate(short)
        if wait is not None:
            log.info('access token over its rate limit: %s', short)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                'Too many requests for this access token.',
                headers={'Retry-After': str(wait)})
        await _touch(request, doc)
        route = getattr(request.scope.get('route'), 'path', '-')
        log.info('access token used: %s %s', short, route)
        request.state.access_token = doc
        return user

    return dependency


@router.get('/auth/token-check', response_model=TokenCheck,
            summary='Test an access token: owner, scope, expiry')
async def token_check(
    request: Request,
    user: UserInDB = Depends(access_token_user(tk.SCOPE_CATALOG)),
):
    doc = request.state.access_token
    return {'owner': user.username, 'scope': tk.SCOPE_CATALOG,
            'expires': doc['expires']}
