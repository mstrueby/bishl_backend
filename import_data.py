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
from models.tournaments import TournamentBase, SeasonBase, RoundBase, MatchdayBase, MatchBase
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
        team_id = ObjectId()
        rec['teamNumber'] = int(rec['teamNumber'])
        rec['active'] = bool(rec['active'])
        rec['external'] = bool(rec['external'])
        rec['legacyId'] = int(rec['legacyId'])
        rec['_id'] = team_id

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
        season_id = ObjectId()
        season = SeasonBase(**rec)
        db_collection = db["tournaments"]
        filter= {'tinyName': rec['t_tinyName']}
        new_values = { 
          "$push" : {
            "seasons": jsonable_encoder(season)
          }
        }
        
        print("Inserting Season: ", filter, '/', new_values)
        db_collection.update_one(filter, new_values)

      except ValueError as e:
        print("ERROR at ", rec['t_tinyName'], '/', rec['name'])
        print(e)
        exit()

    # add ROUNDS
    with open("data/data_rounds.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        #round_id = ObjectId()
        #rec['seasonYear'] = int(rec['seasonYear'])
        #rec['_id'] = str(round_id)
        rec['createStandings'] = bool(rec['createStandings'])
        rec['createStats'] = bool(rec['createStats'])
        rec['published'] = bool(rec['published'])
        rec['startDate'] = parse_datetime(rec['startDate']) if rec['startDate'] else None
        rec['endDate'] = parse_datetime(rec['endDate' ]) if rec['endDate'] else None
        
        print(rec)
        
        round = RoundBase(**rec)
        db_collection=db["tournaments"]
        filter= {'tinyName': rec['t_tinyName']}
        new_value={"$push" : { "seasons.$[s].rounds" : my_jsonable_encoder(round) } }
        array_filters=[{"s.alias" : rec['s_alias']}]
        
        print("Inserting Round: ", filter, '/', new_value)
        db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)
      except ValueError as e:
        print("ERROR at ", rec['t_tinyName'], '/', rec['s_alias'], '/', rec['name'])
        print(e)
        exit()

    # add MATCHDAYS
    with open("data/data_matchdays.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        matchday_id = ObjectId()
        #rec['seasonYear'] = int(rec['seasonYear'])
        rec['createStandings'] = bool(rec['createStandings'])
        rec['createStats'] = bool(rec['createStats'])
        rec['published'] = bool(rec['published'])
        rec['startDate'] = parse_datetime(rec['startDate']) if rec['startDate'] else None
        rec['endDate'] = parse_datetime(rec['endDate']) if rec['endDate'] else None

        matchday = MatchdayBase(**rec)
        db_collection=db["tournaments"]
        filter= {'tinyName': rec['t_tinyName']}
        new_value={"$push" : { "seasons.$[y].rounds.$[r].matchdays" : my_jsonable_encoder(matchday) } }
        array_filters=[{"y.alias" : rec['s_alias']}, {"r.name" : rec['r_name']}]
        
        print("Inserting Matchday: ", filter, '/', new_value)
        db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)

      except ValueError as e:
        print("ERROR at ", rec['t_tinyName'], '/', rec['s_alias'], '/', rec['r_name'], '/', rec['name'])
        print(e)
        exit()

    # add MATCHES
    with open("data/data_matches.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        match_id = ObjectId()
        #rec['seasonYear'] = int(rec['seasonYear'])
        rec['homeScore'] = int(rec['homeScore'])
        rec['awayScore'] = int(rec['awayScore'])
        rec['overtime'] = bool(rec['overtime'])
        rec['shootout'] = bool(rec['shootout'])
        rec['published'] = bool(rec['published'])
        rec['startTime'] = parse_datetime(rec['startTime']) if rec['startTime'] else None

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

        match = MatchBase(**rec)
        db_collection=db["tournaments"]
        filter= {'tinyName': rec['t_tinyName']}
        new_value={"$push" : { "seasons.$[y].rounds.$[r].matchdays.$[md].matches" : my_jsonable_encoder(match)}  }
        array_filters=[{"y.alias" : rec['s_alias']}, {"r.name" : rec['r_name']}, {"md.name" : rec['md_name']}]
        
        #print("Inserting Matches: ", filter, '/', rec['matchId'])
        #db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)
        
        #print("Match: ", match)
        #exit()
        
      except ValueError as e:
        print("ERROR at ", rec['t_tinyName'], '/', rec['s_alias'], '/', rec['r_name'], '/', rec['md_name'], '/', rec['match_id'])
        print(e)
        exit()
        
  case _:
    print("Unknown parameter value!")
    
print("SUCCESS")

