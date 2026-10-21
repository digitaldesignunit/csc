"""
Clean-up of access tokens and OAuth rows (0.6.3.1).

* ``remove_tokens_of``: the account is gone, so its access tokens and its
  OAuth rows go with it (a Claude connection and a Grasshopper sign-in are rows
  of ``access_tokens``; the rest are the pending authorization codes and
  requests of the account and the used refresh tokens of its connections).
  Called wherever an account is deleted (``usermaintenance``).
* ``backfill_purge_dates``: the TTL index on ``purge_at`` deletes a row 90
  days after it was revoked or expired; rows made by an earlier build have no
  such date yet and get it once, when the API starts.
"""

from typing import Dict, Iterable

import read_only
from apps.catalog import access_tokens as tk
from logging_setup import get_logger

log = get_logger(__name__)


async def remove_tokens_of(db, user_ids: Iterable[str]) -> Dict[str, int]:
    """Delete the access tokens and OAuth rows of the accounts ``user_ids``;
    ``db`` is the database handle. Returns how many rows went per collection."""
    ids = list(user_ids)
    if not ids:
        return {}
    grants = [row['_id'] async for row in db['access_tokens'].find(
        {'owner_user_id': {'$in': ids}, 'kind': {'$in': ['oauth', 'device']}},
        {'_id': 1})]
    counts = {
        'oauth_used_refresh': (await db['oauth_used_refresh'].delete_many(
            {'grant_id': {'$in': grants}})).deleted_count if grants else 0,
        'oauth_codes': (await db['oauth_codes'].delete_many(
            {'user_id': {'$in': ids}})).deleted_count,
        'oauth_requests': (await db['oauth_requests'].delete_many(
            {'bound_user': {'$in': ids}})).deleted_count,
        'access_tokens': (await db['access_tokens'].delete_many(
            {'owner_user_id': {'$in': ids}})).deleted_count,
    }
    log.info('tokens of deleted accounts removed: %s', counts)
    return counts


async def backfill_purge_dates(tokens) -> int:
    """Give every row without a ``purge_at`` its date; returns how many. The
    condition is in the update, so two workers starting together do no harm.
    Nothing is written while the read-only flag is set."""
    if read_only.is_on():
        return 0
    done = 0
    async for doc in tokens.find({'purge_at': {'$exists': False}}):
        result = await tokens.update_one(
            {'_id': doc['_id'], 'purge_at': {'$exists': False}},
            {'$set': {'purge_at': tk.purge_at(doc)}})
        done += result.modified_count
    if done:
        log.info('purge dates added to access token rows: %d', done)
    return done
