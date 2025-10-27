#!/usr/bin/env python
import argparse
import asyncio
import os
from collections import defaultdict
from datetime import datetime

import motor.motor_asyncio


async def check_password_migration_status(is_prod: bool = False):
    """
    Check the status of password migration from bcrypt to argon2.
    Shows statistics and lists users who still need migration.
    """
    # Connect to database
    if is_prod:
        DB_URL = os.environ.get('DB_URL_PROD')
        DB_NAME = 'bishl'
    else:
        DB_URL = os.environ.get('DB_URL')
        DB_NAME = os.environ.get('DB_NAME')

    if not DB_URL or not DB_NAME:
        print("Error: DB_URL and DB_NAME environment variables must be set")
        return

    client = motor.motor_asyncio.AsyncIOMotorClient(DB_URL)
    db = client[DB_NAME]

    try:
        # Fetch all users
        users = await db["users"].find({}).to_list(length=None)

        if not users:
            print("No users found in database")
            return

        # Analyze password types
        stats = {
            'total': len(users),
            'argon2': 0,
            'bcrypt': 0,
            'other': 0
        }

        users_by_type = defaultdict(list)

        for user in users:
            password_hash = user.get('password', '')
            user_info = {
                'id': user.get('_id'),
                'email': user.get('email'),
                'firstName': user.get('firstName'),
                'lastName': user.get('lastName'),
                'roles': user.get('roles', [])
            }

            if password_hash.startswith('$argon2'):
                stats['argon2'] += 1
                users_by_type['argon2'].append(user_info)
            elif password_hash.startswith('$2b$') or password_hash.startswith('$2a$') or password_hash.startswith('$2y$'):
                stats['bcrypt'] += 1
                users_by_type['bcrypt'].append(user_info)
            else:
                stats['other'] += 1
                users_by_type['other'].append(user_info)

        # Print results
        print("="*80)
        print(f"PASSWORD MIGRATION STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Database: {DB_NAME}")
        print("="*80)

        print("\n📊 STATISTICS:")
        print(f"  Total users: {stats['total']}")
        print(f"  ✅ Argon2 (migrated): {stats['argon2']} ({stats['argon2']/stats['total']*100:.1f}%)")
        print(f"  ⏳ Bcrypt (needs migration): {stats['bcrypt']} ({stats['bcrypt']/stats['total']*100:.1f}%)")
        if stats['other'] > 0:
            print(f"  ⚠️  Other/Unknown: {stats['other']}")

        # Show bcrypt users (need migration)
        if users_by_type['bcrypt']:
            print("\n⏳ USERS STILL ON BCRYPT (need to login to auto-migrate):")
            print("-" * 80)
            for i, user in enumerate(users_by_type['bcrypt'], 1):
                roles_str = ', '.join(user['roles']) if user['roles'] else 'No roles'
                print(f"{i:3d}. {user['email']:40s} | {user['firstName']} {user['lastName']:20s} | {roles_str}")

        # Show argon2 users
        if users_by_type['argon2']:
            print("\n✅ USERS ON ARGON2 (migrated):")
            print("-" * 80)
            for i, user in enumerate(users_by_type['argon2'], 1):
                roles_str = ', '.join(user['roles']) if user['roles'] else 'No roles'
                print(f"{i:3d}. {user['email']:40s} | {user['firstName']} {user['lastName']:20s} | {roles_str}")

        # Show other/unknown
        if users_by_type['other']:
            print("\n⚠️  USERS WITH OTHER/UNKNOWN PASSWORD FORMAT:")
            print("-" * 80)
            for i, user in enumerate(users_by_type['other'], 1):
                print(f"{i:3d}. {user['email']:40s} | {user['firstName']} {user['lastName']}")

        print("\n" + "="*80)
        print("ℹ️  MIGRATION NOTES:")
        print("  - Bcrypt passwords are automatically upgraded to Argon2 when users login")
        print("  - No manual migration is needed - users will be upgraded on next login")
        print("  - Inactive users will remain on bcrypt until they login")
        print("  - Both bcrypt and argon2 passwords work for authentication")
        print("="*80)

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        raise
    finally:
        client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Check password migration status')
    parser.add_argument('--prod', action='store_true', help='Use production database')
    args = parser.parse_args()

    asyncio.run(check_password_migration_status(is_prod=args.prod))
