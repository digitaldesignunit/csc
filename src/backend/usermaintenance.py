#!/usr/bin/env python3.13

"""
Cleanup script for unverified user accounts.

This script removes user accounts that:
1. Have not verified their email (email_verified = False)
2. Were created more than 7 days ago
3. Have an expired verification token

Run this script as a cron job (e.g., daily at 2 AM):
0 2 * * * /path/to/python /path/to/cleanup_unverified_users.py
"""

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import sys
from datetime import datetime, timedelta, timezone
import asyncio

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pymongo import AsyncMongoClient

# LOCAL MODULE IMPORTS --------------------------------------------------------
from logging_setup import configure as configure_logging, get_logger
from settings import get_settings
from utility import (
    get_database_name,
    get_db_connectionstring,
)

log = get_logger(__name__)


# MAIN CLEANUP LOGIC ----------------------------------------------------------

def unverified_query(cutoff: datetime) -> dict:
    """The accounts to remove: not verified, and the verification period ended
    before ``cutoff``. The expiry is a date in the accounts the API creates and
    an ISO text in accounts that went through an import or an older version; a
    comparison matches only values of its own type, so both are asked for."""
    return {
        'email_verified': False,
        '$or': [
            {'verification_token_expires': {'$lt': cutoff}},
            {'verification_token_expires': {
                '$lt': cutoff.strftime('%Y-%m-%dT%H:%M:%S')}},
        ],
    }


async def cleanup_unverified_users(dry_run=False):
    """
    Remove unverified user accounts older than 7 days.

    The log holds counts and account ids only: no user name, no e-mail
    address, no database error text (decision 8.144 h).

    Args:
        dry_run: If True, only print what would be deleted without
        actually deleting.

    Returns:
        Number of users deleted (or would be deleted in dry run).
    """
    log.info('Starting unverified user cleanup (%s)',
             'DRY RUN' if dry_run else 'LIVE')

    # Load config and connect to MongoDB
    connection_string = get_db_connectionstring()

    client = AsyncMongoClient(
        connection_string,
        serverSelectionTimeoutMS=5000,
        maxPoolSize=20,
    )

    try:
        await client.aconnect()
        await client.admin.command('ping')
        log.info('Connected to MongoDB')

        db = client[get_database_name()]
        users = db['users']

        # Calculate cutoff date (7 days ago)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
        log.info('Cutoff date: %s', cutoff_date.isoformat())

        query = unverified_query(cutoff_date)

        # Count matching users
        count = await users.count_documents(query)
        log.info('Found %d unverified user(s) to delete', count)

        if count == 0:
            log.info('No users to delete')
            return 0

        ids = [user['_id'] async for user in users.find(query, {'_id': 1})]
        log.info('Account ids: %s', ', '.join(str(i) for i in ids))

        if dry_run:
            log.info('DRY RUN: no users were actually deleted')
        else:
            # Delete the users
            result = await users.delete_many(query)
            log.info('Deleted %d user(s)', result.deleted_count)

        log.info('Cleanup completed successfully')

        return count

    except Exception as e:
        # the type only: a database error text can name accounts (8.144 h)
        log.error('Error during cleanup: %s', type(e).__name__)
        raise

    finally:
        await client.close()
        log.info('MongoDB connection closed')


# MAIN ENTRY POINT ------------------------------------------------------------

async def main():
    """
    Main entry point for the cleanup script.
    """
    configure_logging(get_settings())
    # Check for dry-run flag
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv

    try:
        deleted_count = await cleanup_unverified_users(dry_run=dry_run)

        log.info('Summary: users processed %d, mode %s', deleted_count,
                 'DRY RUN' if dry_run else 'LIVE')

        return 0

    except Exception as e:
        log.error('FATAL ERROR: %s', type(e).__name__)
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
