#!/usr/bin/env python

import csv
import json
import os
import requests
from pymongo import MongoClient
import certifi

filename = "data/data_players.csv"
BASE_URL = os.environ['BE_API_URL']
api_url = f"{BASE_URL}/"
print("api_url", api_url)

# first login user
login_url = f"{BASE_URL}/users/login"
login_data = {
    "email": os.environ['ADMIN_USER'],
    "password": os.environ['ADMIN_PASSWORD']
}
login_response = requests.post(login_url, json=login_data)
print("login_response", login_response.status_code)
if login_response.status_code != 200:
    print("Error logging in - Repl online?")
    exit(1)

# get token
token = login_response.json()["token"]
print("token", token)

# User authentication header
headers = {'Authorization': f'Bearer {token}'}

# Connect to the MongoDB collection
client = MongoClient(os.environ['DB_URL'], tlsCAFile=certifi.where())
db = client[os.environ['DB_NAME']]
db_collection = db['players']

import argparse

# Set up argument parser
parser = argparse.ArgumentParser(description='Manage players.')
parser.add_argument('--deleteAll',
                    action='store_true',
                    help='Delete all players.')
parser.add_argument('--importAll',
                    action='store_true',
                    help='Import all players.')
args = parser.parse_args()

if args.deleteAll:
    delete_result = db_collection.delete_many({})
    print(f"Deleted {delete_result.deleted_count} players from the database.")
    # delete csv file update_legacy_players.csv
    log_file_path = 'update_legacy_players.csv'
    if os.path.exists(log_file_path):
        os.remove(log_file_path)
        print(f"Deleted log file: {log_file_path}")

# read csv
# iterate over rows and post to tournaments API
with open("data/data_players.csv", encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['py_id'] != '':
            continue
        # parse JSON strings if they are not already dictionaries
        if isinstance(row.get('full_face_req'), str):
            row['full_face_req'] = row['full_face_req'].lower() == 'true'
        row['legacy_id'] = int(row['legacy_id'])

        # transform row object to a PlayerBase instance object
        #player = PlayerBase(**row)
        #print("row", row)

        response = requests.post(f"{BASE_URL}/players/",
                                 files={
                                     'firstname': (None, row['firstname']),
                                     'lastname': (None, row['lastname']),
                                     'birthdate': (None, row['birthdate']),
                                     'nationality': (None, row['nationality']),
                                     'position': (None, row['player_position']),
                                     'full_face_req':
                                     (None, row['full_face_req']),
                                     'source': (None, row['source']),
                                     'legacy_id': (None, row['legacy_id'])
                                 },
                                 headers=headers)
        if response.status_code == 422:
            print('422 Error: Unprocessable Entity')
            try:
                error_details = response.json()
                print('Error details:', error_details)
            except json.JSONDecodeError:
                print('Failed to parse error response JSON')
        if response.status_code == 201:
            new_player_id = response.json().get('_id')
                            
            with open('update_legacy_players.csv',
                      mode='a',
                      newline='',
                      encoding='utf-8') as log_file:
                log_writer = csv.writer(log_file)
                log_writer.writerow([
                    f"update tblplayer set py_id='{new_player_id}' where id_tblPlayer={row['legacy_id']};"
                ])
            print(f"--> Successfully posted Player ({new_player_id}): {row}")
            if not args.importAll:
                print("--importAll flag not set, exiting.")
                exit()
        else:
            print('Failed to post Player: ', row, ' - Status code:',
                  response.status_code)
            exit()
