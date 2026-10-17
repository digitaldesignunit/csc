"""
The store of the rate limit counters (decision 8.152).

The counters of slowapi and of the failed sign-ins (``signin_limit.py``) live
in MongoDB, so that every gunicorn worker counts the same requests; with an
in-process store each worker would allow the limit again. One collection,
``rate_limit_counters``, in the database of the API; every counter carries
``expireAt`` and a TTL index removes it when the window is over. The
collection and the index are created on first use.

``CSC_RATE_LIMIT_STORAGE`` selects the store: unset, it is the MongoDB URI of
the API; ``memory://`` keeps the counters in the process (tests, local runs).

The store fails open: when MongoDB does not answer, the request passes
uncounted, one log line says so (no address, no URI, nothing about the
request), and for ``COOLDOWN_SECONDS`` the store is not asked again, so a down
database costs one short wait per half minute and not one per request. The
calls are synchronous (the ``limits`` library has no async client) and short:
one round trip each.
"""

import threading
import time
from typing import Any, Optional

from limits.storage import MemoryStorage
from limits.storage.mongodb import MongoDBStorageBase

from logging_setup import get_logger

log = get_logger(__name__)

COLLECTION = 'rate_limit_counters'
COOLDOWN_SECONDS = 30
# a store that does not answer must not hold a request for the default 30 s
CLIENT_OPTIONS = {
    'maxPoolSize': 20,
    'serverSelectionTimeoutMS': 1000,
    'connectTimeoutMS': 1000,
    'socketTimeoutMS': 2000,
}


class GuardedMongoStorage(MongoDBStorageBase):
    """Fixed-window counters in one MongoDB collection; never raises."""

    def __init__(self, uri: str, database_name: str, **options: Any) -> None:
        super().__init__(
            uri, database_name=database_name,
            counter_collection_name=COLLECTION,
            window_collection_name=COLLECTION,
            **{**CLIENT_OPTIONS, **options})
        self._down_until = 0.0
        self._lock = threading.Lock()

    def _init_mongo_client(self, uri, **options):
        return self.lib.MongoClient(uri, **options)

    @property
    def storage(self):
        """The client, with the TTL index in place (the base class would
        also make a second collection for moving windows)."""
        if self._storage is None:
            client = self._init_mongo_client(self._storage_uri,
                                             **self._storage_options)
            try:
                client[self._database_name][COLLECTION].create_index(
                    'expireAt', expireAfterSeconds=0)
            except Exception:
                client.close()
                raise
            self._storage = client
        return self._storage

    def __del__(self) -> None:
        # the base class would open a client just to close it
        if getattr(self, '_storage', None) is not None:
            self._storage.close()

    # THE GUARD ---------------------------------------------------------------
    def _guard(self, call, otherwise):
        """``call()``, or ``otherwise`` while the store does not answer."""
        if time.monotonic() < self._down_until:
            return otherwise
        try:
            result = call()
        except Exception as exc:
            with self._lock:
                first = time.monotonic() >= self._down_until
                self._down_until = time.monotonic() + COOLDOWN_SECONDS
            if first:
                log.warning(
                    'rate limit store unreachable (%s): requests pass '
                    'uncounted for %d s', type(exc).__name__,
                    COOLDOWN_SECONDS)
            return otherwise
        return result

    def incr(self, key: str, expiry: int, amount: int = 1) -> int:
        return self._guard(
            lambda: MongoDBStorageBase.incr(self, key, expiry, amount), 0)

    def get(self, key: str) -> int:
        return self._guard(lambda: MongoDBStorageBase.get(self, key), 0)

    def get_expiry(self, key: str) -> float:
        return self._guard(
            lambda: MongoDBStorageBase.get_expiry(self, key), time.time())

    def check(self) -> bool:
        return self._guard(lambda: MongoDBStorageBase.check(self), False)

    def clear(self, key: str) -> None:
        self._guard(lambda: self.counters.delete_one({'_id': key}), None)

    def reset(self) -> Optional[int]:
        return self._guard(lambda: self._drop(), 0)

    def _drop(self) -> int:
        # not drop(): that would take the TTL index with it
        return self.counters.delete_many({}).deleted_count


def make_store(uri: str, database_name: str):
    """The store for ``uri``: ``memory://`` or a MongoDB URI."""
    if uri.startswith('memory://'):
        return MemoryStorage()
    return GuardedMongoStorage(uri, database_name)
