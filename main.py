from __future__ import annotations

import os
from typing import Dict, List, Optional

import requests
import osmnx as ox
import pandas as pd
import geopandas as gpd
import numpy as np
from dotenv import load_dotenv

from ai import get_ai_response, get_ai_dictation


def get_weather(city: str) -> float:
    url = "https://api.weatherapi.com/v1/current.json"
    api_key = os.getenv("WEATHER_KEY")
    if not api_key:
        raise RuntimeError("Missing WEATHER_KEY environment variable")

    params = {"q": get_ai_dictation(city), "key": api_key}
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


def getActivities(city_name: str) -> pd.DataFrame:
    # נורמליזציה (כמו אצלך)
    place = get_ai_dictation(city_name)

    # סט תגיות ממוקד ויעיל
    TAGS = {
        # אטרקציות ותרבות
        "tourism": [
            "attraction", "museum", "gallery", "zoo", "theme_park",
            "viewpoint", "aquarium", "artwork", "information"
        ],
        # פנאי/טבע/פארקים
        "leisure": [
            "park", "garden", "playground", "nature_reserve",
            "sports_centre", "pitch", "stadium", "swimming_pool",
            "fitness_centre", "golf_course", "marina", "water_park"
        ],
        # אוכל/בילוי
        "amenity": [
            "cafe", "restaurant", "fast_food", "bar", "pub", "biergarten",
            "theatre", "cinema", "arts_centre", "library", "ice_cream",
            "marketplace", "fountain", "spa", "sauna"
        ],
        # קניות
        "shop": [
            "mall", "department_store", "supermarket", "bakery",
            "confectionery", "deli", "outdoor"
        ],
        # אתרי מורשת/דת
        "historic": [
            "castle", "monument", "memorial", "ruins",
            "archaeological_site", "heritage"
        ],
        # טבע/חוף
        "natural": [
            "beach", "wood", "peak"
        ]
    }

    # אופציונלי: זמן המתנה גבוה יותר ל-Overpass
    ox.settings.timeout = 180  # שניות

    frames = []

    # נבצע שאילתה נפרדת לכל מפתח כדי לצמצם עומס ולמנוע תשובה כבדה מדי
    for key, values in TAGS.items():
        try:
            g = ox.features_from_place(place, tags={key: values})
        except Exception:
            # לא מפיל את הפונקציה אם שאילתה אחת נכשלה
            continue

        # מבטיחים שיש name גם אם לא קיים
        if "name" not in g.columns:
            g["name"] = None

        # נשאיר רק name והעמודה של המפתח הנוכחי
        keep = ["name"]
        if key in g.columns:
            keep.append(key)
        g = g[keep].copy()

        # סינון שמות ריקים
        g = g[g["name"].notna() & (g["name"].astype(str).str.strip() != "")]

        # אם אין את עמודת המפתח, אין לנו קטגוריה—נדלג
        if key not in g.columns:
            continue

        # בונים קטגוריה אחידה key:value (למשל amenity:cinema)
        g = g[g[key].notna()]
        if g.empty:
            continue
        g["category"] = (key + ":" + g[key].astype(str).str.strip())

        frames.append(g[["name", "category"]])

    if not frames:
        return pd.DataFrame(columns=["name", "category"])

    # איחוד ודה-דופליקציה
    df = pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)
    return df

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

    hobbies = input(
        "What are your hobbies or preferred activities ? and if there is somthing you want me to know it's the place :) ").strip()

    user_profile = {
        "has_children": has_children == f"yes have {children_count} children's",
        "children_count": children_count,
        "hobbies": hobbies
    }

    return city_name, weather_info, attractions_list, user_profile




if __name__ == "__main__":
    # city = "tel aviv"
    # Activities = pd.DataFrame(getActivities(city).values)
    # print(Activities)
    # weather = get_weather(city)
    # print(weather)
    # נסיון “שם עיר בלבד” (near=)
    # דורש OPENTRIPMAP_API_KEY ב-.env (חינם)
    city_name, weather_info, attractions_list, user_profile = run_questionnaire()
    print(get_ai_response(city_name, weather_info, attractions_list, user_profile))
