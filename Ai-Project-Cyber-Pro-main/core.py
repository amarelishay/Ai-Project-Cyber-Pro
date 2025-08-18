# core.py
import os
import requests
import osmnx as ox
import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from ai import get_ai_dictation

load_dotenv()

def get_weather(city: str) -> float:
    url = "https://api.weatherapi.com/v1/current.json"
    api_key = os.getenv("WEATHER_KEY")
    if not api_key:
        raise RuntimeError("Missing WEATHER_KEY environment variable")
    params = {"q": get_ai_dictation(city), "key": api_key}
    headers = {"accept": "application/json"}

    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return float(data.get("current", {}).get("temp_c"))

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
        if "name" not in g.columns:
            g["name"] = None
        keep = ["name", "geometry"]
        if key in g.columns:
            keep.append(key)
        g = g[keep].copy()
        g = g[g["name"].notna() & (g["name"].astype(str).str.strip() != "")]
        if key not in g.columns:
            continue
        g = g[g[key].notna()]
        if g.empty:
            continue
        if g.crs is None:
            g = g.set_crs(epsg=4326)
        g_proj = g.to_crs(epsg=3857)
        centroids_proj = gpd.GeoSeries(g_proj.geometry.centroid, crs=g_proj.crs)
        centroids_wgs84 = centroids_proj.to_crs(epsg=4326)
        g["lat"] = centroids_wgs84.y.values
        g["lon"] = centroids_wgs84.x.values
        g["category"] = key + ":" + g[key].astype(str).str.strip()
        frames.append(g[["name", "category", "lat", "lon"]])
    if not frames:
        return pd.DataFrame(columns=["name", "category", "lat", "lon"])
    return pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)
