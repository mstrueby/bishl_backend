#!/usr/bin/env python
import argparse
import csv
import os

import certifi
import requests
from pymongo import MongoClient

from models.clubs import TeamBase

# Get environment variables
filename = "data/data_new_teams.csv"
BASE_URL = os.environ['BE_API_URL']
BASE_URL = os.environ['BE_API_URL_PROD']

# MongoDB setup
client = MongoClient(os.environ['DB_URL'], tlsCAFile=certifi.where())
db = client[os.environ['DB_NAME']]

# Set up argument parser
parser = argparse.ArgumentParser(description='Manage teams.')
parser.add_argument('--importAll',
                    action='store_true',
                    help='Import all teams.')
args = parser.parse_args()

# First login user to get token
login_url = f"{BASE_URL}/users/login"
login_data = {
    "email": os.environ['SYS_ADMIN_EMAIL'],
    "password": os.environ['SYS_ADMIN_PASSWORD']
}

try:
    # Login and get token
    login_response = requests.post(login_url, json=login_data)
    if login_response.status_code != 200:
        print("Error logging in")
        exit()

    token = login_response.json()["token"]
    headers = {
        'Authorization': f'Bearer {token}'
    }

    with open(filename, encoding='utf-8') as f:
        reader = csv.DictReader(f,
                             delimiter=';',
                             quotechar='"',
                             doublequote=True,
                             skipinitialspace=True)
        for row in reader:
            #print(row)
            clubAlias=row['clubAlias']
            # Create a new team instance
            team = TeamBase(
                name=row['name'],
                alias=row['alias'],
                fullName=row['fullName'],
                shortName=row['shortName'],
                tinyName=row['tinyName'],
                ageGroup=row['ageGroup'],
                teamNumber=row['teamNumber'],
                active=True,
                external=False,
                ishdId=row['ishdId'],
            )

            # Post the new team to the endpoint
            post_url = f"{BASE_URL}/clubs/{clubAlias}/teams/"
            response = requests.post(post_url, data=team.__dict__, headers=headers)

            # Check the response status
            if response.status_code == 201:
                print(f"Successfully added team: {clubAlias} / {team.name}")
                if not args.importAll:
                    print("--importAll flag not set, exiting.")
                    exit()
            elif response.status_code == 409:
                print(f"Team already exists: {clubAlias} / {team.name}")
            else:
                print(f"Failed to add team: {clubAlias} {team.name}. Status Code: {response.status_code}")
                exit()

except Exception as e:
    print(f"An error occurred: {str(e)}")
    print(f"Type of error: {type(e).__name__}")
    print(f"Arguments: {e.args}")
