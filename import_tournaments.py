#!/usr/bin/env python

import csv
import json
import os
import requests
from pymongo import MongoClient
import certifi

filename = "data/data_tournaments.csv"
BASE_URL = os.environ['BE_API_URL']
api_url = f"{BASE_URL}/tournaments/"
print("api_url", api_url)

# first login user
login_url = f"{BASE_URL}/users/login"
login_data = {"email": os.environ['ADMIN_USER'], "password": os.environ['ADMIN_PASSWORD']}
login_response = requests.post(login_url, json=login_data)
print("login_response", login_response.status_code)
# get token
token = login_response.json()["token"]
print("token", token)

# User authentication header
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

# empty collection tournaments
client = MongoClient(os.environ['DB_URL'], tlsCAFile=certifi.where())
db = client[os.environ['DB_NAME']]
db_collection = db['tournaments']
print("Delete all documents in tournaments")
db_collection.delete_many({})

# read csv
# iterate over rows and post to tournaments API
with open(filename, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # parse JSON strings if they are not already dictionaries
        if isinstance(row.get('ageGroup'), str):
            row['ageGroup'] = json.loads(row['ageGroup'])
        if isinstance(row.get('defaultSettings'), str):
            row['defaultSettings'] = json.loads(row['defaultSettings'])
        if isinstance(row.get('published'), str):
            row['published'] = row['published'].lower() == 'true'
        if isinstance(row.get('active'), str):
            row['active'] = row['active'].lower() == 'true'
        row['seasons'] = []
        row['external'] = False
        row['legacyId'] = int(row['legacyId'])
        
        print("row: ", row)
        response = requests.post(api_url, json=row, headers=headers)
        if response.status_code == 201:
            print('--> Successfully posted:', row)
        else:
            print('Failed to post:', row, 'Status code:', response.status_code)
