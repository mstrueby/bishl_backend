#!/usr/bin/env python

import csv
import sys
import os
import json
from datetime import date, datetime, timezone
from fastapi.encoders import jsonable_encoder
import certifi
from urllib.parse import urlparse
from bson import ObjectId

# dotenv environment variables
from dotenv import dotenv_values
from models.clubs import ClubBase, TeamBase
from models.venues import VenueBase
from utils import my_jsonable_encoder, parse_datetime

def is_valid_url(url):
  try:
      result = urlparse(url)
      # Checking if the URL has the scheme and netloc attributes which are part of a valid URL.
      return all([result.scheme, result.netloc])
  except Exception:
      return False

#config = dotenv_values(".env")
collection = sys.argv[1]
filename = "data/data_{}.csv".format(collection)

# read csv
with open(filename, encoding='utf-8') as f:
  csv_reader = csv.DictReader(f)
  name_records = list(csv_reader)

# Mongo db - we do not need Motor here
from pymongo import MongoClient
client = MongoClient()

client = MongoClient(os.environ['DB_URL'], tlsCAFile=certifi.where())
db = client[os.environ['DB_NAME']]
db_collection = db[collection]

match collection:
  case "venues":
    print("Delete all records in {}".format(collection))
    db_collection.delete_many({})
    for rec in name_records:
      try:
        #rec['latitude'] = float(rec['latitude'])
        #rec['longitude'] = float(rec['longitude'])
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
        #rec['dateOfFoundation'] = datetime.strptime(rec['dateOfFoundation'], '%Y-%m-%d') if rec['dateOfFoundation'] else None
        rec['yearOfFoundation'] = int(rec['yearOfFoundation']) if rec['yearOfFoundation'] else None

        #rec['website'] = is_valid_url(rec['website']) if rec['website'] else None
        rec['website'] = str(rec['website']) if rec['website'] else None
        rec['ishdId'] = int(rec['ishdId']) if rec['ishdId'] else None
        rec['active'] = bool(rec['active'])
        rec['legacyId'] = int(rec['legacyId'])
        rec['teams'] = list(rec['teams']) if rec['teams'] else []

        club = jsonable_encoder(ClubBase(**rec))  
        print("Inserting: ", club)
        db_collection.insert_one(club)

      except ValueError as e:
        print("ERROR at ", rec['name'])
        print(e)
        exit()

    # add teams
    with open("data/data_teams.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)

    for rec in name_records:
      try:
        #team_id = ObjectId()
        rec['_id'] = rec['teamId']
        rec['teamNumber'] = int(rec['teamNumber'])
        rec['active'] = bool(rec['active'])
        rec['external'] = bool(rec['external'])
        rec['legacyId'] = int(rec['legacyId'])

        team = TeamBase(**rec)
        print(team)
        
        db_collection=db["clubs"]
        filter= {'alias': rec['clubAlias']}
        new_values = {
          "$push": {
            "teams": jsonable_encoder(team)
          }
        }

        print("Inserting Team: ", filter, '/', new_values)
        db_collection.update_one(filter, new_values)

      except ValueError as e:
        print("ERROR at ", rec['clubAlias'], '/', rec['name'])
        print(e)
        exit()
          

        
  case _:
    print("Unknown parameter value!")
    
print("SUCCESS")

