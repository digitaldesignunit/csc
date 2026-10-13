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
from utility import (
    get_database_name,
    get_db_connectionstring,
    create_logging_timestamp as logts
)


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
    ts = logts()
    print(f'[CLEANUP] {ts} Starting unverified user cleanup...')
    print(f'[CLEANUP] Mode: {"DRY RUN" if dry_run else "LIVE"}')
    print('-' * 80)

    # Load config and connect to MongoDB
    connection_string = get_db_connectionstring()

    client = AsyncMongoClient(
        connection_string,
        serverSelectionTimeoutMS=5000,
    )

    try:
        await client.aconnect()
        await client.admin.command('ping')
        print('[CLEANUP] Connected to MongoDB')

        db = client[get_database_name()]
        users = db['users']

        # Calculate cutoff date (7 days ago)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
        print(f'[CLEANUP] Cutoff date: {cutoff_date.isoformat()}')

        query = unverified_query(cutoff_date)

        # Count matching users
        count = await users.count_documents(query)
        ts = logts()
        print(f'[CLEANUP] {ts} Found {count} unverified user(s) to delete')

        if count == 0:
            print(f'[CLEANUP] {ts} No users to delete.')
            return 0

        ids = [user['_id'] async for user in users.find(query, {'_id': 1})]
        print(f'[CLEANUP] Account ids: {", ".join(str(i) for i in ids)}')

        if dry_run:
            print('[CLEANUP] DRY RUN - No users were actually deleted.')
        else:
            # Delete the users
            result = await users.delete_many(query)
            ts = logts()
            print(f'[CLEANUP] {ts} Deleted {result.deleted_count} user(s)')

        print('-' * 80)
        ts = logts()
        print(f'[CLEANUP] {ts} Cleanup completed successfully')

        return count

    except Exception as e:
        ts = logts()
        print(f'[CLEANUP] {ts} Error during cleanup: {type(e).__name__}')
        raise

    finally:
        await client.close()
        ts = logts()
        print(f'[CLEANUP] {ts} MongoDB connection closed')


# MAIN ENTRY POINT ------------------------------------------------------------

async def main():
    """
    Main entry point for the cleanup script.
    """
    # Check for dry-run flag
    dry_run = '--dry-run' in sys.argv or '-d' in sys.argv

    try:
        deleted_count = await cleanup_unverified_users(dry_run=dry_run)

        print()
        print('[CLEANUP] Summary:')
        print(f'  Users processed: {deleted_count}')
        print(f'  Mode: {"DRY RUN" if dry_run else "LIVE"}')

        return 0

    except Exception as e:
        print(f'[CLEANUP] FATAL ERROR: {type(e).__name__}')
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
