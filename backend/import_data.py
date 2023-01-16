#!/usr/bin/env python

import csv
import sys
from fastapi.encoders import jsonable_encoder
import certifi

# dotenv environment variables
from dotenv import dotenv_values
from models import VenueBase, ClubBase, TeamBase

config = dotenv_values(".env")
collection = sys.argv[1]
filename = "../data/{}.csv".format(collection)

# read csv
with open(filename, encoding='utf-8') as f:
    csv_reader = csv.DictReader(f)
    name_records = list(csv_reader)

# Mongo db - we do not need Motor here
from pymongo import MongoClient
client = MongoClient()

client = MongoClient(config['DB_URL'], tlsCAFile=certifi.where())
db = client[config['DB_NAME']]
db_collection = db[collection]

match collection:

    case "venues":
        print("Delete all records in {}".format(collection))
        db_collection.delete_many({})
        for rec in name_records:
            try:
                rec['latitude'] = float(rec['latitude'])
                rec['longitude'] = float(rec['longitude'])
                rec['active'] = bool(rec['active'])
                rec['legacyId'] = int(rec['legacyId'])

                venue = jsonable_encoder(VenueBase(**rec))  
                print("Inserting: ", venue)
                db_collection.insert_one(venue)

            except ValueError as e:
                print("ERROR at ", rec['name'])
                print(e)
                exit()

    case "clubs":
        print("Delete all records in {}".format(collection))
        db_collection.delete_many({})
        for rec in name_records:
            try:
                rec['email'] = str(rec['email']) if rec['email'] else None
                rec['dateOfFoundation'] = str(rec['dateOfFoundation']) if rec['dateOfFoundation'] else None
                rec['website'] = str(rec['website']) if rec['website'] else None
                rec['ishdId'] = int(rec['ishdId']) if rec['ishdId'] else None
                rec['active'] = bool(rec['active'])
                rec['legacyId'] = int(rec['legacyId'])

                club = jsonable_encoder(ClubBase(**rec))  
                print("Inserting: ", club)
                db_collection.insert_one(club)

            except ValueError as e:
                print("ERROR at ", rec['name'])
                print(e)
                exit()
            
    case "teams":
        print("Delete all records in {}".format(collection))
        db_collection.delete_many({})
        for rec in name_records:
            try:
                rec['teamNumber'] = int(rec['teamNumber']) if rec['teamNumber'] else None
                rec['email'] = str(rec['email']) if rec['email'] else None
                rec['extern'] = bool(rec['extern'])
                rec['active'] = bool(rec['active'])
                rec['legacyId'] = int(rec['legacyId'])

                team = jsonable_encoder(TeamBase(**rec))  
                print("Inserting: ", team)
                db_collection.insert_one(team)

            except ValueError as e:
                print("ERROR at ", rec['name'])
                print(e)
                exit()

    case _:
        print("Unknown parameter value!")
    
print("SUCCESS")
