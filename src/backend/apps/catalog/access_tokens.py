"""
Access tokens, the parts that need no request (decision 8.167).

One collection ``access_tokens`` holds three kinds: ``pat`` (a personal access
token for the MCP layer, scope ``read:catalog``), ``device`` (the Grasshopper
device sign-in, scope ``gh:client``; created by a later step, the model and the
check already know it) and ``oauth`` (one row per connection of a Claude
connector, 8.168: the row holds the current access token, ``csc_oat_``, and its
refresh token, ``csc_ort_``, as two hashes, so a refresh token can never pass
the access-token check). A token is a prefix plus 32 random bytes in base64url
(43 characters). Only its SHA-256 is stored: a random token
cannot be guessed, so no slow hash is needed and every call stays fast. The
list shows the first 8 characters after the prefix (``short_id``).

All timestamps are written by ``stamp`` with fixed width, so that a string
comparison in a query is a time comparison.
"""

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

PAT_PREFIX = 'csc_pat_'
DEVICE_PREFIX = 'csc_dev_'
OAUTH_ACCESS_PREFIX = 'csc_oat_'
OAUTH_REFRESH_PREFIX = 'csc_ort_'       # not in PREFIXES: never an access token
PREFIXES = (PAT_PREFIX, DEVICE_PREFIX, OAUTH_ACCESS_PREFIX)
PREFIX_OF_KIND = {'pat': PAT_PREFIX, 'device': DEVICE_PREFIX,
                  'oauth': OAUTH_ACCESS_PREFIX}
# kinds whose owner must still have a role of CSC_PAT_ROLES on every request
ROLE_CHECKED_KINDS = ('pat', 'oauth')

SCOPE_CATALOG = 'read:catalog'
SCOPE_GH = 'gh:client'
SCOPE_OF_KIND = {'pat': SCOPE_CATALOG, 'device': SCOPE_GH,
                 'oauth': SCOPE_CATALOG}

PAT_LIFETIME_DAYS = (30, 90, 365)
DEFAULT_PAT_DAYS = 90
MAX_ACTIVE_TOKENS = 10
LAST_USED_INTERVAL_SECONDS = 60
REQUESTS_PER_MINUTE = 120
RENEW_WITHIN_DAYS = 14
# a Claude connection (8.168): an access token of one hour, renewed through a
# refresh token that is good 30 days after its last use and is rotated on every
# use, and a hard limit of 90 days from the consent
OAUTH_ACCESS_SECONDS = 3600
OAUTH_REFRESH_DAYS = 30
OAUTH_GRANT_DAYS = 90


def now() -> datetime:
    return datetime.now(timezone.utc)


def stamp(moment: datetime) -> str:
    """``2026-10-20T10:00:00.000000Z``: always the same width."""
    return moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def parse_stamp(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + '+00:00')


def new_token(kind: str) -> str:
    """A new random token of ``kind``; shown once, never stored."""
    body = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=')
    return PREFIX_OF_KIND[kind] + body.decode('ascii')


def new_refresh_token() -> str:
    body = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=')
    return OAUTH_REFRESH_PREFIX + body.decode('ascii')


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def prefix_of(token: str) -> Optional[str]:
    return next((p for p in PREFIXES if token.startswith(p)), None)


def short_id_of(token: str) -> str:
    """The first 8 characters after the prefix."""
    prefix = prefix_of(token) or ''
    return token[len(prefix):][:8]


def expires_at(days: int, moment: Optional[datetime] = None) -> str:
    return stamp((moment or now()) + timedelta(days=days))


def status_of(doc: dict, moment: Optional[datetime] = None) -> str:
    """``revoked``, ``expired`` or ``active``."""
    if doc.get('revoked'):
        return 'revoked'
    if doc['expires'] <= stamp(moment or now()):
        return 'expired'
    return 'active'


def lifetime_days(doc: dict) -> int:
    """The lifetime a token was made with, as one of the offered choices;
    the default when it is none of them."""
    days = round((parse_stamp(doc['expires'])
                  - parse_stamp(doc['created'])).total_seconds() / 86400)
    return days if days in PAT_LIFETIME_DAYS else DEFAULT_PAT_DAYS
