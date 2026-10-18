"""
Access tokens (PyJWT; T5 of 0.6.2.0).

One algorithm, ``HS256``: a token is accepted only when it names no other and
carries ``exp`` and ``sub``. The same secret and the same claims as before
the move from python-jose, so a token issued before the deploy stays valid.

A request is decoded once. The limiter key (``limiter.signed_in_or_ip``) and
the authentication dependency (``api.auth.lookup_user_from_token``) both ask
``verified_payload``; the first call checks the signature and keeps the
answer in ``request.state``, the second reads it. A payload is never taken
from a token whose signature was not checked.
"""

from typing import Any, Dict, Optional

import jwt
from fastapi import Request

from logging_setup import get_logger

log = get_logger(__name__)

JWT_ALGORITHM = 'HS256'
REQUIRED_CLAIMS = ('exp', 'sub')


def encode_token(secret: str, claims: Dict[str, Any]) -> str:
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_token(token: str, secret: str) -> Dict[str, Any]:
    """The claims of a token that holds, else ``jwt.InvalidTokenError``."""
    return jwt.decode(
        token, secret, algorithms=[JWT_ALGORITHM],
        options={'require': list(REQUIRED_CLAIMS), 'verify_aud': False})


def verified_payload(request: Request, token: str) -> Optional[Dict[str, Any]]:
    """The claims of ``token`` if its signature and times hold, else None.
    Decoded once per request."""
    checked = getattr(request.state, 'jwt_checked', None)
    if checked is not None and checked[0] == token:
        return checked[1]
    secret = getattr(request.app.state, 'jwt_secret', None)
    payload = None
    if secret and token:
        try:
            payload = decode_token(token, secret)
        except jwt.InvalidTokenError as exc:
            # the text names the check that failed, never the token
            log.info('JWT refused: %s', exc)
    request.state.jwt_checked = (token, payload)
    return payload
