import os
import requests
import osmnx as ox
import pandas as pd
import geopandas as gpd
import numpy as np

from ai import get_ai_response


def get_weather(city: str) -> float:
    url = "https://api.weatherapi.com/v1/current.json"
    api_key = os.getenv("WEATHER_KEY")
    if not api_key:
        raise RuntimeError("Missing WEATHER_KEY environment variable")

    params = {"q": city, "key": api_key}
    headers = {"accept": "application/json"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # הגנה על מבנה הנתונים:
        return float(data.get("current", {}).get("temp_c"))
    except (ValueError, TypeError):
        # ValueError/TypeError: אם temp_c חסר/לא מספר, או JSON לא תקין
        raise RuntimeError(f"Unexpected response format: {resp.text}")
    except requests.RequestException as e:
        raise RuntimeError(f"HTTP error: {e}")


# -----------------------------------------------------


def getActivities(city_name):
    city_name += ", Israel"
    TAGS = {
        "tourism": ["attraction"],  # אטרקציות
        "amenity": ["cafe", "cinema"],  # בתי קפה וקולנוע
        "shop": ["mall"]  # קניונים
    }
    gdf = ox.features_from_place(city_name, tags=TAGS)[
        ["name", "tourism", "amenity", "shop", "geometry"]
    ].copy()

    # מסנן רק מה שיש לו שם
    gdf = gdf[gdf["name"].notna()]

    # יוצרים עמודת category מאוחד
    gdf["category"] = (
        gdf["tourism"].combine_first(gdf["amenity"]).combine_first(gdf["shop"])
    )

    # נשאיר רק name + category + geometry
    gdf = gdf[["name", "category"]]

    return gdf
#--------------------------------------------
def run_questionnaire():
    print("=== Trip Recommendation Questionnaire ===")

    # City name
    city_name = input("📍 Which city are you in or planning to visit? ").strip()

    # Weather info
    weather_info = get_weather(city_name)

    # List of attractions
    attractions_list = getActivities(city_name)

    # User profile
    print("\n👤 A few details about you:")
    has_children = input("Do you have children? (y/n): ").strip().lower()
    children_count = 0
    if has_children == "y":
        try:
            children_count = int(input("How many children? ").strip())
        except ValueError:
            print("⚠ Invalid number, saved as 0.")

    hobbies = input("What are your hobbies or preferred activities? ").strip()

    user_profile = {
        "has_children": has_children == "yes",
        "children_count": children_count,
        "hobbies": hobbies
    }

    return city_name, weather_info, attractions_list, user_profile

if __name__ == "__main__":
    #
    # city = "Ashdod"
    # Activities = pd.DataFrame(getActivities(city).values).to_json
    # print(Activities)
    # weather = get_weather(city)
    # print(weather)
    city_name, weather_info, attractions_list, user_profile = run_questionnaire()
    print(get_ai_response(city_name, weather_info, attractions_list, user_profile))