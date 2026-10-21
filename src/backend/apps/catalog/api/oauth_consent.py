"""
The consent of a Claude connection: the two routes the web page ``/oauth/consent``
uses (decision 8.168 b). The browser arrives from ``/authorize`` with the id of a
pending authorization request (``oauth_server.py``), signs in if needed, and:

* ``GET  /oauth/requests/{id}``           what the page shows: the host the
  connection will return to, the client's own name (secondary), the access, and
  whether the signed-in account may allow it. The first account to ask binds the
  request to itself; another account gets the same answer as for an unknown id.
* ``POST /oauth/requests/{id}/decision``  ``{"allow": true | false}``: the answer
  is the URL to send the browser to, built here from the redirect URI that the
  SDK validated against the client's registration (never from anything the page
  sends): the code and the ``state`` of the client on Allow, ``access_denied``
  on Deny. A request is answered once; it ends after 10 minutes.

Only a role of ``CSC_PAT_ROLES`` may allow a connection of a tool that reads the
catalog (scope ``read:catalog``); the Grasshopper client (scope ``gh:client``,
8.168 f) may be allowed by every signed-in account with a verified address, and
its page says what that is: Grasshopper on this computer acting as you, with
the loopback host large and the computer name the client sent as unchecked
text. Nothing is remembered, so every connection asks again. Both are signed-in JWT routes; the POST is a write and
gets the 503 of the read-only flag like every write.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from mcp.server.auth.provider import construct_redirect_uri
from pydantic import BaseModel

from apps.catalog.models import UserInDB
from apps.catalog.oauth_server import (
    GH_ACCESS_TEXT,
    GH_SCOPE,
    CscOAuthProvider,
    hash_secret,
    redirect_host,
)
from apps.catalog.token_check import may_hold_pat
from logging_setup import get_logger
from .auth import get_current_active_user

log = get_logger(__name__)

router = APIRouter()

GONE = ('This connection request is no longer valid. Start the connection '
        'again in Claude.')
REFUSED_ROLE = ('Your account may not connect tools to the catalog. Ask an '
                'administrator.')
REFUSED_UNVERIFIED = 'Your e-mail address is not verified yet.'
ACCESS_TEXT = 'Read access to the catalog, as you see it'


class ConsentView(BaseModel):
    redirect_host: str
    redirect_is_loopback: bool
    client_name: Optional[str] = None
    # what is asked: read:catalog (a tool such as Claude) or gh:client
    # (Grasshopper on this computer); `computer` is the name the Grasshopper
    # client sent, shown as unchecked text
    scope: str = 'read:catalog'
    computer: Optional[str] = None
    access: str = ACCESS_TEXT
    can_allow: bool
    refusal: Optional[str] = None


class Decision(BaseModel):
    allow: bool


class DecisionResult(BaseModel):
    redirect_to: str


def _may_allow(user: UserInDB, gh: bool):
    """``(allowed, refusal text)``: a tool that reads the catalog needs a role
    of ``CSC_PAT_ROLES``; the Grasshopper client only a verified account."""
    if gh:
        if user.email_verified:
            return True, None
        return False, REFUSED_UNVERIFIED
    if may_hold_pat(user.role):
        return True, None
    return False, REFUSED_ROLE


def _provider(request: Request) -> CscOAuthProvider:
    provider = getattr(request.app.state, 'oauth_provider', None)
    if provider is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    return provider


async def _own_request(request: Request, request_id: str, user: UserInDB
                       ) -> dict:
    """The pending request, bound to ``user`` (or already theirs); anything
    else is the same 404."""
    provider = _provider(request)
    key = hash_secret(request_id)
    now = datetime.now(timezone.utc)
    doc = await provider.requests.find_one({'_id': key})
    if doc is None or doc['decided'] or doc['expire_at'].replace(
            tzinfo=timezone.utc) <= now:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    if doc['bound_user'] is None:
        await provider.requests.update_one(
            {'_id': key, 'bound_user': None}, {'$set': {'bound_user': user.id}})
        doc = await provider.requests.find_one({'_id': key}) or {}
    if doc.get('bound_user') != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    return doc


@router.get('/oauth/requests/{request_id}', response_model=ConsentView,
            summary='What the consent page shows')
async def get_consent_request(
    request: Request,
    response: Response,
    request_id: str,
    user: UserInDB = Depends(get_current_active_user),
):
    response.headers['Cache-Control'] = 'no-store'
    provider = _provider(request)
    doc = await _own_request(request, request_id, user)
    client = await provider.get_client(doc['client_id'])
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    host = redirect_host(doc['redirect_uri'])
    gh = GH_SCOPE in doc['scopes']
    allowed, refusal = _may_allow(user, gh)
    return {
        'redirect_host': host,
        'redirect_is_loopback': host in ('localhost', '127.0.0.1'),
        'client_name': None if gh else client.client_name,
        'scope': GH_SCOPE if gh else 'read:catalog',
        'computer': doc.get('computer') if gh else None,
        'access': GH_ACCESS_TEXT if gh else ACCESS_TEXT,
        'can_allow': allowed,
        'refusal': refusal,
    }


@router.post('/oauth/requests/{request_id}/decision',
             response_model=DecisionResult,
             summary='Allow or deny a connection; the answer is where to go')
async def decide_consent_request(
    request: Request,
    response: Response,
    request_id: str,
    decision: Decision,
    user: UserInDB = Depends(get_current_active_user),
):
    response.headers['Cache-Control'] = 'no-store'
    provider = _provider(request)
    doc = await _own_request(request, request_id, user)
    if decision.allow:
        allowed, refusal = _may_allow(user, GH_SCOPE in doc['scopes'])
        if not allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, refusal)
    # answered once: the claim is the update
    claimed = await provider.requests.update_one(
        {'_id': hash_secret(request_id), 'bound_user': user.id, 'decided': False},
        {'$set': {'decided': True,
                  'decision': 'allow' if decision.allow else 'deny'}})
    if claimed.modified_count != 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, GONE)
    if decision.allow:
        code = await provider.create_code(doc, user.id)
        await provider.client_consented(doc['client_id'])
        target = construct_redirect_uri(doc['redirect_uri'], code=code,
                                        state=doc.get('state'))
        log.info('oauth consent allowed (%s)', redirect_host(doc['redirect_uri']))
    else:
        target = construct_redirect_uri(
            doc['redirect_uri'], error='access_denied',
            error_description='The user denied the request',
            state=doc.get('state'))
        log.info('oauth consent denied (%s)', redirect_host(doc['redirect_uri']))
    return {'redirect_to': target}
