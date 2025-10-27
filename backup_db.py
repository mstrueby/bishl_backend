#!/usr/bin/env python
import argparse
import json
import os
from datetime import datetime

import certifi
from pymongo import MongoClient

parser = argparse.ArgumentParser(description="Backup MongoDB collections")
parser.add_argument("--prod", action="store_true", help="Backup production database")
args = parser.parse_args()

# Database configuration
if args.prod:
    DB_URL = os.environ["DB_URL_PROD"]
    DB_NAME = "bishl"
    backup_prefix = "prod"
else:
    DB_URL = os.environ["DB_URL"]
    DB_NAME = "bishl_dev"
    backup_prefix = "dev"

# Connect to MongoDB
client = MongoClient(DB_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]

# Create backup directory
backup_dir = f"backups/{backup_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
os.makedirs(backup_dir, exist_ok=True)

# Collections to backup
collections = db.list_collection_names()

print(f"Starting backup for {DB_NAME}...")
for collection_name in collections:
    print(f"Backing up {collection_name}...")
    collection = db[collection_name]

    # Export to JSON
    documents = list(collection.find())

    # Convert ObjectId to string for JSON serialization
    for doc in documents:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])

    backup_file = f"{backup_dir}/{collection_name}.json"
    with open(backup_file, "w") as f:
        json.dump(documents, f, indent=2, default=str)

    print(f"  → Saved {len(documents)} documents to {backup_file}")

print(f"\nBackup completed successfully in {backup_dir}")
print(f"Total collections backed up: {len(collections)}")

# Create metadata file
metadata = {
    "backup_date": datetime.now().isoformat(),
    "database": DB_NAME,
    "environment": backup_prefix,
    "collections": collections,
    "total_collections": len(collections),
}

with open(f"{backup_dir}/_metadata.json", "w") as f:
    json.dump(metadata, f, indent=2)

print("\nTo restore, use: python restore_db.py --backup <backup_dir>")
