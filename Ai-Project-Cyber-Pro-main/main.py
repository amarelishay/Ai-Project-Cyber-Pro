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
    place = get_ai_dictation(city_name)

    TAGS = {
        "tourism": ["attraction","museum","gallery","zoo","theme_park","viewpoint","aquarium","artwork","information"],
        "leisure": ["park","garden","playground","nature_reserve","sports_centre","pitch","stadium","swimming_pool","fitness_centre","golf_course","marina","water_park"],
        "amenity": ["cafe","restaurant","fast_food","bar","pub","biergarten","theatre","cinema","arts_centre","library","ice_cream","marketplace","fountain","spa","sauna"],
        "shop": ["mall","department_store","supermarket","bakery","confectionery","deli","outdoor"],
        "historic": ["castle","monument","memorial","ruins","archaeological_site","heritage"],
        "natural": ["beach","wood","peak"]
    }

    ox.settings.timeout = 180
    frames = []

    for key, values in TAGS.items():
        try:
            g = ox.features_from_place(place, tags={key: values})
        except Exception:
            continue

        # דאגה לשדות בסיס
        if "name" not in g.columns:
            g["name"] = None
        keep = ["name", "geometry"]
        if key in g.columns:
            keep.append(key)
        g = g[keep].copy()

        # ניקוי
        g = g[g["name"].notna() & (g["name"].astype(str).str.strip() != "")]
        if key not in g.columns:
            continue
        g = g[g[key].notna()]
        if g.empty:
            continue

        # ודא שה־CRS מוגדר כ-WGS84 אם חסר
        if g.crs is None:
            g = g.set_crs(epsg=4326)

        # חישוב centroid במטרי (3857) ואז המרה חזרה ל-4326
        g_proj = g.to_crs(epsg=3857)
        centroids_proj = gpd.GeoSeries(g_proj.geometry.centroid, crs=g_proj.crs)
        centroids_wgs84 = centroids_proj.to_crs(epsg=4326)

        g["lat"] = centroids_wgs84.y.values
        g["lon"] = centroids_wgs84.x.values

        g["category"] = key + ":" + g[key].astype(str).str.strip()
        frames.append(g[["name", "category", "lat", "lon"]])

    if not frames:
        return pd.DataFrame(columns=["name", "category", "lat", "lon"])

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

    has_children_flag = (has_children == "y")
    user_profile = {
        "has_children": has_children_flag,
        "children_count": children_count,
        "hobbies": hobbies,
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
