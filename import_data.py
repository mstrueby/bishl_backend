#!/usr/bin/env python

import csv
import sys
import os
from datetime import datetime
from fastapi.encoders import jsonable_encoder
import certifi

# dotenv environment variables
from dotenv import dotenv_values
from models.clubs import ClubBase
from models.venues import VenueBase
from models.teams import TeamBase
from models.tournaments import TournamentBase

config = dotenv_values(".env")
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
          
  case "tournaments":
    print("Delete all records in {}".format(collection))
    db_collection.delete_many({})
    for rec in name_records:
      try:
        rec['published'] = bool(rec['published'])
        rec['active'] = bool(rec['active'])
        rec['external'] = bool(rec['external'])
        rec['legacy_id'] = int(rec['legacy_id'])
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
        rec['season_year'] = int(rec['season_year'])

        db_collection=db["tournaments"]
        filter= {'tiny_name': rec['t_tiny_name']}
        new_values = { "$push" : {  "seasons" : { "year": rec['season_year'], "published" : True } } }
        
        print("Inserting Season: ", filter, '/', new_values)
        db_collection.update_one(filter, new_values)

      except ValueError as e:
        print("ERROR at ", rec['t_tiny_name'], '/', rec['season_year'])
        print(e)
        exit()

    # add ROUNDS
    with open("data/data_rounds.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        rec['season_year'] = int(rec['season_year'])
        rec['create_standings'] = bool(rec['create_standings'])
        rec['create_stats'] = bool(rec['create_stats'])
        rec['published'] = bool(rec['published'])
        rec['start_date'] = datetime.strptime(rec['start_date'], '%Y-%m-%d') if rec['start_date'] else None
        rec['end_date'] = datetime.strptime(rec['end_date'], '%Y-%m-%d') if rec['end_date'] else None

        db_collection=db["tournaments"]
        filter= {'tiny_name': rec['t_tiny_name']}
        new_value={"$push" : { "seasons.$[year].rounds" : { "name" : rec['name'], "create_standings" : rec['create_standings'], "create_stats" : rec['create_stats'], "published" : rec['published'], "start_date" : rec['start_date'], "end_date" : rec['end_date'], "matchdays_type" : rec['matchdays_type'], "matchdays_sorted_by" : rec['matchdays_sorted_by'] } } }
        array_filters=[{"year.year" : rec['season_year']}]
        
        print("Inserting Round: ", filter, '/', new_value)
        db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)

      except ValueError as e:
        print("ERROR at ", rec['t_tiny_name'], '/', rec['season_year'], '/', rec['name'])
        print(e)
        exit()

    # add MATCHDAYS
    with open("data/data_matchdays.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        rec['season_year'] = int(rec['season_year'])
        rec['create_standings'] = bool(rec['create_standings'])
        rec['create_stats'] = bool(rec['create_stats'])
        rec['published'] = bool(rec['published'])
        rec['start_date'] = datetime.strptime(rec['start_date'], '%Y-%m-%d') if rec['start_date'] else None
        rec['end_date'] = datetime.strptime(rec['end_date'], '%Y-%m-%d') if rec['end_date'] else None

        db_collection=db["tournaments"]
        filter= {'tiny_name': rec['t_tiny_name']}
        new_value={"$push" : { "seasons.$[y].rounds.$[r].matchdays" : { "name" : rec['name'], "type": rec['type'], "start_date": rec['start_date'], "end_date": rec['end_date'], "create_standings" : rec['create_standings'], "create_stats" : rec['create_stats'], "published" : rec['published'] } } }
        array_filters=[{"y.year" : rec['season_year']}, {"r.name" : rec['r_name']}]
        
        print("Inserting Matchday: ", filter, '/', new_value)
        db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)

      except ValueError as e:
        print("ERROR at ", rec['t_tiny_name'], '/', rec['season_year'], '/', rec['r_name'], '/', rec['name'])
        print(e)
        exit()

    # add MATCHES
    with open("data/data_matches.csv", encoding='utf-8') as f:
      csv_reader = csv.DictReader(f)
      name_records = list(csv_reader)
      
    for rec in name_records:
      try:
        rec['season_year'] = int(rec['season_year'])
        rec['home_score'] = int(rec['home_score'])
        rec['away_score'] = int(rec['away_score'])
        rec['overtime'] = bool(rec['overtime'])
        rec['shootout'] = bool(rec['shootout'])
        rec['published'] = bool(rec['published'])
        rec['start_time'] = datetime.strptime(rec['start_time'], '%Y-%m-%d %H:%M:%S') if rec['start_time'] else None

        db_collection=db["tournaments"]
        filter= {'tiny_name': rec['t_tiny_name']}
        new_value={"$push" : { "seasons.$[y].rounds.$[r].matchdays.$[md].matches" : { "match_id" : rec['match_id'], "home_team": rec['home_team'], "away_team": rec['away_team'], "status": rec['status'], "venue": rec['venue'], "home_score": rec['home_score'], "away_score": rec['home_score'], "away_score": rec['away_score'], "overtime": rec['overtime'], "shootout": rec['shootout'],  "start_time": rec['start_time'], "published" : rec['published'] } } }
        array_filters=[{"y.year" : rec['season_year']}, {"r.name" : rec['r_name']}, {"md.name" : rec['md_name']}]
        
        print("Inserting Matches: ", filter, '/', new_value)
        db_collection.update_one(filter, new_value, array_filters=array_filters, upsert=False)

      except ValueError as e:
        print("ERROR at ", rec['t_tiny_name'], '/', rec['season_year'], '/', rec['r_name'], '/', rec['md_name'], '/', rec['match_id'])
        print(e)
        exit()
        
  case _:
    print("Unknown parameter value!")
    
print("SUCCESS")
