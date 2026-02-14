#!/bin/bash

# Configuration
# DB_URL_PROD and DB_URL (demo) should be set in environment variables/secrets
SOURCE_URI="${DB_URL_PROD}"
TARGET_URI="${DB_URL_DEMO}"
DB_NAME="bishl"
DEMO_DB_NAME="bishl_demo"

if [ -z "$SOURCE_URI" ] || [ -z "$TARGET_URI" ]; then
    echo "Error: DB_URL_PROD and DB_URL environment variables must be set."
    exit 1
fi

echo "Starting database sync from $DB_NAME to $DEMO_DB_NAME..."

# 1. Create a temporary dump directory
DUMP_DIR="temp_mongodb_dump"
mkdir -p "$DUMP_DIR"

# 2. Dump the production database
echo "Dumping production database..."
mongodump --uri="$SOURCE_URI" --db="$DB_NAME" --out="$DUMP_DIR"

# 3. Clean up the target database (bishl_demo)
# We need to drop all collections except 'users'
echo "Cleaning up target database collections (except users)..."
# Get all collection names except 'users' and drop them
mongosh "$TARGET_URI/$DEMO_DB_NAME" --eval "db.getCollectionNames().filter(c => c !== 'users' && !c.startsWith('system.')).forEach(c => db.getCollection(c).drop())"

# 4. Restore to bishl_demo, excluding the 'users' collection from the dump
echo "Restoring collections (excluding users)..."
mongorestore --uri="$TARGET_URI" --nsInclude="$DB_NAME.*" --nsFrom="$DB_NAME.*" --nsTo="$DEMO_DB_NAME.*" --nsExclude="$DB_NAME.users" "$DUMP_DIR/$DB_NAME"

# 5. Cleanup
rm -rf "$DUMP_DIR"

echo "Database sync completed successfully."
