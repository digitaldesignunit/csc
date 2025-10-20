#!/usr/bin/env python3.9

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
import os
import sys
import json
from datetime import datetime, timedelta, timezone
import asyncio

# THIRD PARTY LIBRARY IMPORTS -------------------------------------------------
from pymongo import AsyncMongoClient

# LOCAL MODULE IMPORTS --------------------------------------------------------
try:
    from utility import create_logging_timestamp as logts
except ImportError:
    print('Import Error: utility module not found, '
          'continuing without logging...')


# CONFIGURATION ---------------------------------------------------------------

def load_db_config():
    """
    Load database configuration from config file.
    """
    # Get the backend directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(script_dir, '..', 'src', 'backend')
    config_file = os.path.join(backend_dir, 'config', 'dbconfig.json')

    if not os.path.exists(config_file):
        raise FileNotFoundError(f'Config file not found: {config_file}')

    with open(config_file, 'r', encoding='utf-8-sig') as f:
        config = json.load(f)

    return config


def get_connection_string(config):
    """
    Build MongoDB connection string from config.
    """
    user = config.get('user', '')
    password = config.get('password', '')
    host = config.get('host', 'localhost')
    port = config.get('port', 27017)

    if user and password:
        return f'mongodb://{user}:{password}@{host}:{port}'
    else:
        return f'mongodb://{host}:{port}'


# MAIN CLEANUP LOGIC ----------------------------------------------------------

async def cleanup_unverified_users(dry_run=False):
    """
    Remove unverified user accounts older than 7 days.

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
    config = load_db_config()
    connection_string = get_connection_string(config)

    client = AsyncMongoClient(
        connection_string,
        serverSelectionTimeoutMS=5000,
    )

    try:
        await client.aconnect()
        await client.admin.command('ping')
        print('[CLEANUP] Connected to MongoDB')

        db = client['csc']
        users = db['users']

        # Calculate cutoff date (7 days ago)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
        print(f'[CLEANUP] Cutoff date: {cutoff_date.isoformat()}')

        # Find unverified users with expired tokens older than 7 days
        # We check verification_token_expires to ensure we only delete accounts
        # where the verification period has definitely expired
        query = {
            'email_verified': False,
            'verification_token_expires': {'$lt': cutoff_date}
        }

        # Count matching users
        count = await users.count_documents(query)
        ts = logts()
        print(f'[CLEANUP] {ts} Found {count} unverified user(s) to delete')

        if count == 0:
            print(f'[CLEANUP] {ts} No users to delete.')
            return 0

        # Get details of users to be deleted (for logging)
        users_to_delete = []
        cursor = users.find(query)
        async for user in cursor:
            users_to_delete.append({
                'id': user.get('_id'),
                'username': user.get('username'),
                'email': user.get('email'),
                'verification_token_expires': user.get(
                    'verification_token_expires'
                )
            })

        # Log users to be deleted
        print('\n[CLEANUP] Users to be deleted:')
        for user in users_to_delete:
            print(f'  - ID: {user["id"]}')
            print(f'    Username: {user["username"]}')
            print(f'    Email: {user["email"]}')
            print(f'    Token expired: {user["verification_token_expires"]}')
            print()

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
        print(f'[CLEANUP] {ts} Error during cleanup: {str(e)}')
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
        print(f'[CLEANUP] FATAL ERROR: {str(e)}')
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
