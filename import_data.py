#!/usr/bin/env python

import csv
import sys
import os
import json
from datetime import datetime
from fastapi.encoders import jsonable_encoder
import certifi
from urllib.parse import urlparse
from bson import ObjectId

# dotenv environment variables
from dotenv import dotenv_values
from models.clubs import ClubBase
from models.venues import VenueBase
from models.teams import TeamBase
from models.tournaments import TournamentBase

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
        rec['teamNumber'] = int(rec['teamNumber'])
        rec['active'] = bool(rec['active'])
        rec['external'] = bool(rec['external'])
        rec['legacyId'] = int(rec['legacyId'])
        
        db_collection=db["clubs"]
        filter= {'alias': rec['clubAlias']}
        new_values = { "$push" : {  "teams" : { "name": rec['name'], "alias": rec['alias'], "fullName": rec['fullName'], "shortName": rec['shortName'], "tinyName": rec['tinyName'], "ageGroup": rec['ageGroup'], "teamNumber": rec['teamNumber'], "active" : rec['active'], "external" : rec['external'], "ishdid": rec['ishdId'], "legacyId": rec['legacyId'] } } }

        print("Inserting Team: ", filter, '/', new_values)
        db_collection.update_one(filter, new_values)

      except ValueError as e:
        print("ERROR at ", rec['clubAlias'], '/', rec['name'])
        print(e)
        exit()


  case "teams":
    print("Delete all records in {}".format(collection))
    db_collection.delete_many({})
    for rec in name_records:
      try:
        rec['teamNumber'] = int(rec['teamNumber']) if rec['teamNumber'] else None
        #rec['email'] = str(rec['email']) if rec['email'] else None
        rec['extern'] = bool(rec['external'])
        rec['active'] = bool(rec['active'])
        rec['legacyId'] = int(rec['legacyId'])

        team = jsonable_encoder(TeamBase(**rec))  
        print("Inserting: ", team)
        db_collection.insert_one(team)

      except ValueError as e:
        print("ERROR at ", rec['name'])
        print(e)
        exit()
          
  case "tournaments":
    print("Delete all records in {}".format(collection))
    db_collection.delete_many({})
    for rec in name_records:
      try:
        rec['published'] = bool(rec['published'])
        rec['active'] = bool(rec['active'])
        rec['external'] = bool(rec['external'])
        rec['legacyId'] = int(rec['legacyId'])
        rec['seasons'] = list(rec['seasons']) if rec['seasons'] else []
        
        tournament = jsonable_encoder(TournamentBase(**rec))
        print("Inserting: ", tournament)
        db_collection.insert_one(tournament)

      except ValueError as e:
        print("ERROR at ", rec['name'])
        print(e)
        exit()
      
    # add SEASONS
    with open("data/data_seasons.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
    
    for rec in name_records:
      try:
        rec['seasonYear'] = int(rec['seasonYear'])
        season_id = ObjectId()
        db_collection=db["tournaments"]
        filter= {'tinyName': rec['t_tinyName']}
        new_values = { "$push" : {  "seasons" : { "_id": str(season_id), "year": rec['seasonYear'], "published" : True } } }
        
        print("Inserting Season: ", filter, '/', new_values)
        db_collection.update_one(filter, new_values)

      except ValueError as e:
        print("ERROR at ", rec['t_tinyName'], '/', rec['seasonYear'])
        print(e)
        exit()

    # add ROUNDS
    with open("data/data_rounds.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        rec['seasonYear'] = int(rec['seasonYear'])
        rec['createStandings'] = bool(rec['createStandings'])
        rec['createStats'] = bool(rec['createStats'])
        rec['published'] = bool(rec['published'])
        rec['startDate'] = datetime.strptime(rec['startDate'], '%Y-%m-%d') if rec['startDate'] else None
        rec['endDate'] = datetime.strptime(rec['endDate'], '%Y-%m-%d') if rec['endDate'] else None

        db_collection=db["tournaments"]
        filter= {'tinyName': rec['t_tinyName']}
        new_value={"$push" : { "seasons.$[year].rounds" : { "name" : rec['name'], "createStandings" : rec['createStandings'], "createStats" : rec['createStats'], "published" : rec['published'], "startDate" : rec['startDate'], "endDate" : rec['endDate'], "matchdaysType" : rec['matchdaysType'], "matchdaysSortedBy" : rec['matchdaysSortedBy'] } } }
        array_filters=[{"year.year" : rec['seasonYear']}]
        
        print("Inserting Round: ", filter, '/', new_value)
        db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)

      except ValueError as e:
        print("ERROR at ", rec['t_tinyName'], '/', rec['seasonYear'], '/', rec['name'])
        print(e)
        exit()

    # add MATCHDAYS
    with open("data/data_matchdays.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        rec['seasonYear'] = int(rec['seasonYear'])
        rec['createStandings'] = bool(rec['createStandings'])
        rec['createStats'] = bool(rec['createStats'])
        rec['published'] = bool(rec['published'])
        rec['startDate'] = datetime.strptime(rec['startDate'], '%Y-%m-%d') if rec['startDate'] else None
        rec['endDate'] = datetime.strptime(rec['endDate'], '%Y-%m-%d') if rec['endDate'] else None

        db_collection=db["tournaments"]
        filter= {'tinyName': rec['t_tinyName']}
        new_value={"$push" : { "seasons.$[y].rounds.$[r].matchdays" : { "name" : rec['name'], "type": rec['type'], "startDate": rec['startDate'], "endDate": rec['endDate'], "createStandings" : rec['createStandings'], "createStats" : rec['createStats'], "published" : rec['published'] } } }
        array_filters=[{"y.year" : rec['seasonYear']}, {"r.name" : rec['r_name']}]
        
        print("Inserting Matchday: ", filter, '/', new_value)
        db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)

      except ValueError as e:
        print("ERROR at ", rec['t_tinyName'], '/', rec['seasonYear'], '/', rec['r_name'], '/', rec['name'])
        print(e)
        exit()

    # add MATCHES
    with open("data/data_matches.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        rec['seasonYear'] = int(rec['seasonYear'])
        rec['homeScore'] = int(rec['homeScore'])
        rec['awayScore'] = int(rec['awayScore'])
        rec['overtime'] = bool(rec['overtime'])
        rec['shootout'] = bool(rec['shootout'])
        rec['published'] = bool(rec['published'])
        rec['startTime'] = datetime.strptime(rec['startTime'], '%Y-%m-%d %H:%M:%S') if rec['startTime'] else None
        if isinstance(rec['homeTeam'], str):
          try:
              rec['homeTeam'] = json.loads(rec['homeTeam'].replace("'", "\""))
          except json.JSONDecodeError as e:
              print("ERROR: homeTeam cannot be decoded into dictionary for matchId", rec['matchId'])
              print(e)
              continue 
        # Check that `homeTeam` is now a dict
        if not isinstance(rec['homeTeam'], dict):
            print("ERROR: homeTeam is not a dictionary for matchId", rec['matchId'])
            continue  # Skip to the next record or handle error as needed

        if isinstance(rec['awayTeam'], str):
          try:
              rec['awayTeam'] = json.loads(rec['awayTeam'].replace("'", "\""))
          except json.JSONDecodeError as e:
              print("ERROR: awayTeam cannot be decoded into dictionary for matchId", rec['matchId'])
              print(e)
              continue 
        # Check that `awayTeam` is now a dict
        if not isinstance(rec['awayTeam'], dict):
            print("ERROR: awayTeam is not a dictionary for matchId", rec['matchId'])
            continue  # Skip to the next record or handle error as needed

        
        db_collection=db["tournaments"]
        filter= {'tinyName': rec['t_tinyName']}
        new_value={"$push" : { "seasons.$[y].rounds.$[r].matchdays.$[md].matches" : { "matchId" : rec['matchId'], "homeTeam": rec['homeTeam'], "awayTeam": rec['awayTeam'], "status": rec['status'], "venue": rec['venue'], "homeScore": rec['homeScore'], "awayScore": rec['awayScore'], "overtime": rec['overtime'], "shootout": rec['shootout'],  "startTime": rec['startTime'], "published" : rec['published'] } } }
        array_filters=[{"y.year" : rec['seasonYear']}, {"r.name" : rec['r_name']}, {"md.name" : rec['md_name']}]
        
        print("Inserting Matches: ", filter, '/', new_value)
        db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)

      except ValueError as e:
        print("ERROR at ", rec['t_tinyName'], '/', rec['seasonYear'], '/', rec['r_name'], '/', rec['md_name'], '/', rec['match_id'])
        print(e)
        exit()
        
  case _:
    print("Unknown parameter value!")
    
print("SUCCESS")

