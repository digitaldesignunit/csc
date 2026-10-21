"""
The check of an access token, without HTTP (decisions 8.167, 8.168).

``lookup_access_token`` is the lookup half: it hashes the token, loads it from
the database on every request (no cache) and checks, in this order: not
revoked, not expired (for a Claude connection: the access token and the hard
limit of the connection), the scope asked for, the owner exists, is not
disabled and has a verified address, and, for a personal access token or a
Claude connection, still has a role of ``CSC_PAT_ROLES``. Any failure raises
``TokenRefused``; the HTTP half (``api.access_tokens.access_token_user``) and
the token verifier of the MCP layer (``oauth.verifier``) both turn it into one
and the same 401, so the answer does not tell which check failed (the log
does).

``note_use`` is the rest of a successful check: the rate limit (120 a minute
per token, counted per worker in memory), ``last_used`` (at most once a minute,
never while the read-only flag is set) and the log line of the use.
"""

import time
from datetime import timedelta
from typing import Optional, Tuple

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

import read_only
from apps.catalog import access_tokens as tk
from apps.catalog.models import UserInDB
from logging_setup import get_logger
from settings import get_settings

log = get_logger(__name__)


class TokenRefused(Exception):
    """The token does not pass; ``reason`` is for the log only."""

    def __init__(self, reason: str, short_id: str = '-'):
        super().__init__(reason)
        self.reason = reason
        self.short_id = short_id


class RateLimited(Exception):
    """A valid token over its limit; ``wait`` seconds to the next window."""

    def __init__(self, wait: int, short_id: str):
        super().__init__('rate limited')
        self.wait = wait
        self.short_id = short_id


def may_hold_pat(role: str) -> bool:
    return role in get_settings().pat_roles


async def lookup_access_token(app, token: str, scope: str
                              ) -> Tuple[dict, UserInDB]:
    """The token document and its owner, or ``TokenRefused``."""
    if not token or tk.prefix_of(token) is None:
        raise TokenRefused('not an access token')      # a JWT lands here
    doc = await app.mongodb_access_tokens.find_one(
        {'token_sha256': tk.token_hash(token)})
    if doc is None:
        raise TokenRefused('unknown token')
    short = doc['short_id']
    stamp_now = tk.stamp(tk.now())
    if doc.get('revoked'):
        raise TokenRefused('revoked', short)
    if doc['expires'] <= stamp_now:
        raise TokenRefused('expired', short)
    if doc['kind'] == 'oauth' \
            and (doc.get('access_expires') or '') <= stamp_now:
        raise TokenRefused('access token expired', short)
    if scope not in doc.get('scopes', ()):
        raise TokenRefused('wrong scope', short)
    owner = await app.mongodb_users.find_one({'_id': doc['owner_user_id']})
    if not owner or owner.get('disabled') \
            or not owner.get('email_verified', False):
        raise TokenRefused('owner missing, disabled or unverified', short)
    if doc['kind'] in tk.ROLE_CHECKED_KINDS \
            and not may_hold_pat(owner.get('role', 'user')):
        raise TokenRefused('owner has lost the role', short)
    try:
        user = UserInDB(**owner)
    except Exception:
        raise TokenRefused('owner record unreadable', short)
    return doc, user


# a private store: the counters are per worker and never touch the database
_counters = FixedWindowRateLimiter(MemoryStorage())


def _within_rate(short_id: str) -> Optional[int]:
    """None when the token may go on, else the seconds to wait."""
    item = parse(f'{tk.REQUESTS_PER_MINUTE}/minute')
    if _counters.hit(item, short_id):
        return None
    reset = _counters.get_window_stats(item, short_id).reset_time
    return max(1, int(reset - time.time()) + 1)


async def touch(app, doc: dict) -> None:
    """``last_used``, at most once a minute per token and never while the
    read-only flag is set. The condition is in the update, so two workers do
    not both write."""
    if read_only.is_on():
        return
    moment = tk.now()
    due = tk.stamp(moment - timedelta(
        seconds=tk.LAST_USED_INTERVAL_SECONDS))
    await app.mongodb_access_tokens.update_one(
        {'_id': doc['_id'], '$or': [{'last_used': None},
                                    {'last_used': {'$lt': due}}]},
        {'$set': {'last_used': tk.stamp(moment)}})


async def note_use(app, doc: dict, route: str) -> None:
    """Rate limit, last used and the log line; ``RateLimited`` when over."""
    short = doc['short_id']
    wait = _within_rate(short)
    if wait is not None:
        log.info('access token over its rate limit: %s', short)
        raise RateLimited(wait, short)
    await touch(app, doc)
    log.info('access token used: %s %s', short, route)
