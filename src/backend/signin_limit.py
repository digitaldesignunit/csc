"""
Failed sign-ins per account (decision 8.162).

The per-address limit of ``POST /auth/token`` stops one client; a password
guess spread over many addresses is stopped here: an identifier (e-mail
address or username) that has had ``MAX_FAILED`` failed sign-ins in
``WINDOW_SECONDS`` is answered 429 with ``Retry-After`` until the window is
over. Only failures count; a success does not reset or add. An identifier no
account has is counted and answered like one that has, so the answer does not
tell which exist.

The counter key is an HMAC-SHA256 of the lowercase identifier under a key
derived from ``JWT_SECRET``: the store (MongoDB, shared by the workers, see
``rate_store.py``) holds no address and no username in plain text.
"""

import hashlib
import hmac
import math
import time
from typing import Optional

from limiter import store

MAX_FAILED = 10
WINDOW_SECONDS = 15 * 60
LOCKED_DETAIL = ('Too many failed sign-ins for this account. Try again '
                 'later, or reset the password.')


def counter_key(secret: str, identifier: str) -> str:
    derived = hashlib.sha256(b'csc-failed-signin:' + secret.encode()).digest()
    mac = hmac.new(derived, identifier.strip().lower().encode(),
                   hashlib.sha256)
    return f'signin-failed:{mac.hexdigest()}'


def seconds_until_open(key: str) -> Optional[int]:
    """Whole seconds the account stays locked, or None when it is open."""
    counters = store()
    if counters.get(key) < MAX_FAILED:
        return None
    return max(1, math.ceil(counters.get_expiry(key) - time.time()))


def record_failure(key: str) -> None:
    store().incr(key, WINDOW_SECONDS)
