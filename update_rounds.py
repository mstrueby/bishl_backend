#!/usr/bin/env python

import os

import certifi
import requests
from pymongo import MongoClient

# Get environment variables
BASE_URL = os.environ["BE_API_URL"]

# MongoDB setup
client = MongoClient(os.environ["DB_URL"], tlsCAFile=certifi.where())
db = client[os.environ["DB_NAME"]]
tournaments_collection = db["tournaments"]

# First login user to get token
login_url = f"{BASE_URL}/users/login"
login_data = {"email": os.environ["ADMIN_USER"], "password": os.environ["ADMIN_PASSWORD"]}


def update_rounds():
    # Login and get token
    login_response = requests.post(login_url, json=login_data)
    if login_response.status_code != 200:
        print("Error logging in")
        exit()

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Get all tournaments
    tournaments = tournaments_collection.find({})

    for tournament in tournaments:
        t_alias = tournament.get("alias")

        # Check each season in the tournament
        for season in tournament.get("seasons", []):
            if season.get("alias") == "2024":  # Only process 2024 season
                s_alias = season.get("alias")

                # Process each round in the season
                for round in season.get("rounds", []):
                    r_alias = round.get("alias")

                    print(f"Updating round: {t_alias}/{s_alias}/{r_alias}")

                    # Call patch endpoint for the round
                    patch_url = (
                        f"{BASE_URL}/tournaments/{t_alias}/seasons/{s_alias}/rounds/{round['_id']}"
                    )
                    response = requests.patch(patch_url, json={}, headers=headers)

                    if response.status_code in [200, 304]:
                        print(f"Successfully updated round {r_alias}")
                    else:
                        print(f"Failed to update round {r_alias}: {response.status_code}")


if __name__ == "__main__":
    update_rounds()
