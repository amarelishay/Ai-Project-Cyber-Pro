# core.py
from __future__ import annotations
import os
import re
from typing import Optional, Tuple, List, Dict

import requests
import pandas as pd
import geopandas as gpd
import osmnx as ox
from difflib import get_close_matches
import folium

# נרמול שם מקום (עיר) – מגיע מ-ai.py אצלך
try:
    from ai import get_ai_dictation
except Exception:
    def get_ai_dictation(city: str) -> str:
        return str(city).strip()

# ------------------------------
#          Weather
# ------------------------------

def _geocode_for_weather(city: str) -> Optional[Tuple[float, float]]:
    try:
        q = get_ai_dictation(city)
        lat, lon = ox.geocode(q)  # (lat, lon)
        return float(lat), float(lon)
    except Exception:
        return None

def _weather_open_meteo(city: str) -> Optional[str]:
    coords = _geocode_for_weather(city)
    if not coords:
        return None
    lat, lon = coords
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon, "current_weather": True}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        cur = (r.json() or {}).get("current_weather") or {}
        temp = cur.get("temperature")
        if temp is None:
            return None
        return f"{temp}°C"
    except Exception:
        return None

def _weather_weatherapi(city: str, api_key: str) -> Optional[str]:
    url = "http://api.weatherapi.com/v1/current.json"
    params = {"key": api_key, "q": get_ai_dictation(city), "aqi": "no", "lang": "en"}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        cur = (r.json() or {}).get("current", {}) or {}
        t = cur.get("temp_c")
        cond = ((cur.get("condition") or {}).get("text") or "").strip()
        if t is None:
            return None
        return f"{t}°C" + (f", {cond}" if cond else "")
    except Exception:
        return None

def get_weather(city: str) -> str:
    key = os.getenv("WEATHER_KEY") or os.getenv("WEATHERAPI_KEY")
    if key:
        s = _weather_weatherapi(city, key)
        if s:
            return s
    s = _weather_open_meteo(city)
    return s or "Unknown"

# ------------------------------
#        OSM Attractions
# ------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_TAGS: Dict[str, List[str]] = {
    "tourism": ["attraction","museum","gallery","zoo","theme_park","viewpoint","aquarium","artwork","information"],
    "leisure": ["park","garden","playground","nature_reserve","sports_centre","pitch","stadium","swimming_pool","fitness_centre","golf_course","marina","water_park"],
    "amenity": ["cafe","restaurant","fast_food","bar","pub","biergarten","theatre","cinema","arts_centre","library","ice_cream","marketplace","fountain","spa","sauna"],
    "shop": ["mall","department_store","supermarket","bakery","confectionery","deli","outdoor"],
    "historic": ["castle","monument","memorial","ruins","archaeological_site","heritage"],
    "natural": ["beach","wood","peak"]
}

def _bbox_for_place(place: str) -> Optional[Tuple[float, float, float, float]]:
    try:
        gdf = ox.geocode_to_gdf(place)
        minx, miny, maxx, maxy = gdf.unary_union.bounds
        return (minx, miny, maxx, maxy)
    except Exception:
        return None

def _overpass_query_bounded(tags: Dict[str, List[str]], bbox: Tuple[float,float,float,float], limit: int) -> str:
    west, south, east, north = bbox
    parts = []
    for k, vals in tags.items():
        pat = "(" + "|".join(vals) + ")"
        parts.append(f'nwr["{k}"~"{pat}"]({south},{west},{north},{east});')
    union = "\n  ".join(parts)
    return f"""
    [out:json][timeout:180];
    (
      {union}
    );
    out center {int(limit)};
    """

def _fetch_overpass(ql: str) -> List[dict]:
    r = requests.post(
        OVERPASS_URL,
        data={"data": ql},
        timeout=180,
        headers={"User-Agent": "AIProject/1.0 (+overpass)"}
    )
    r.raise_for_status()
    return (r.json() or {}).get("elements", [])

def getActivities(city_name: str, limit: int = 300, progress_callback=None) -> pd.DataFrame:
    """שליפה מ-OSM עם הגבלה ≤limit מהשרת; Fallback ל-OSMnx. מחזיר name,category,lat,lon."""
    def ping(p, m=""):
        if callable(progress_callback):
            try:
                progress_callback(int(p), m)
            except Exception:
                pass

    place = get_ai_dictation(city_name)
    ping(18, "מחשב גבולות עיר…")
    bbox = _bbox_for_place(place)

    # נסיון 1: Overpass
    if bbox:
        try:
            ping(22, "שולח שאילתת Overpass…")
            ql = _overpass_query_bounded(OSM_TAGS, bbox, limit)
            elements = _fetch_overpass(ql)

            ping(40, "ממיר תוצאות ל-DataFrame…")
            rows = []
            for el in elements:
                tags = el.get("tags", {}) or {}
                name = tags.get("name")
                if not name or not str(name).strip():
                    continue

                if "lat" in el and "lon" in el:
                    lat, lon = el["lat"], el["lon"]
                else:
                    center = el.get("center") or {}
                    lat, lon = center.get("lat"), center.get("lon")
                if lat is None or lon is None:
                    continue

                cat = ""
                for k in OSM_TAGS.keys():
                    v = tags.get(k)
                    if v:
                        cat = f"{k}:{v}"
                        break

                rows.append({
                    "name": str(name).strip(),
                    "category": cat,
                    "lat": float(lat),
                    "lon": float(lon),
                })

            df = pd.DataFrame(rows)
            if not df.empty:
                ping(52, "מנקה כפילויות…")
                df = df.drop_duplicates(subset=["name","lat","lon"]).reset_index(drop=True)
                if len(df) > limit:
                    df = df.head(limit).reset_index(drop=True)
                ping(55, "סיים Overpass.")
                return df
        except Exception:
            ping(30, "Overpass נכשל, עובר ל-OSMnx…")

    # נסיון 2: OSMnx (fallback)
    ping(35, "OSMnx: טוען שכבות לפי תגיות…")
    ox.settings.timeout = 180
    frames: List[pd.DataFrame] = []
    total_keys = len(OSM_TAGS)

    for i, (key, values) in enumerate(OSM_TAGS.items(), start=1):
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
        centroids_proj = g_proj.geometry.centroid
        centroids_wgs84 = gpd.GeoSeries(centroids_proj, crs=g_proj.crs).to_crs(epsg=4326)

        g["lat"] = centroids_wgs84.y.values
        g["lon"] = centroids_wgs84.x.values
        g["category"] = key + ":" + g[key].astype(str).str.strip()

        frames.append(g[["name", "category", "lat", "lon"]])

        # עדכון התקדמות יחסי
        ping(35 + int(50 * (i / max(1, total_keys))), f"OSMnx: מעבד {key} ({i}/{total_keys})…")

        # עצירה מוקדמת
        if sum(len(f) for f in frames) >= limit:
            break

    if not frames:
        ping(96, "לא נמצאו תוצאות.")
        return pd.DataFrame(columns=["name", "category", "lat", "lon"])

    ping(92, "מאחד תוצאות…")
    df = pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)
    if len(df) > limit:
        df = df.head(limit).reset_index(drop=True)
    ping(96, "סיים OSMnx.")
    return df

# ------------------------------
#  Route building (Nearest Neighbor)
# ------------------------------

def geocode_city_center(place: str) -> Tuple[float, float]:
    lat, lon = ox.geocode(place)  # (lat, lon)
    return float(lat), float(lon)

def nearest_neighbor_itinerary(df: pd.DataFrame, start_lat: float, start_lon: float, stops: int = 4) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    work = df.dropna(subset=["lat", "lon"]).copy()
    route = []
    cur_lat, cur_lon = start_lat, start_lon
    for _ in range(min(stops, len(work))):
        idx = ((work["lat"] - cur_lat) ** 2 + (work["lon"] - cur_lon) ** 2).idxmin()
        step = work.loc[idx]
        route.append(step)
        cur_lat, cur_lon = float(step["lat"]), float(step["lon"])
        work = work.drop(index=idx)
    return pd.DataFrame(route).reset_index(drop=True)

# ------------------------------
#   Parse AI answer → selected places
# ------------------------------

def _normalize_name(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[\"'’“”„`]", "", s)
    s_no_paren = re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    s_no_punct = re.sub(r"[^\w\s\u0590-\u05FF]", " ", s_no_paren, flags=re.UNICODE)
    s_spaced = re.sub(r"\s+", " ", s_no_punct)
    return s_spaced.lower().strip()

def _extract_candidate_lines(answer_text: str) -> List[str]:
    names = []
    m = re.search(r"(?im)^Primary highlight:\s*(.+)$", answer_text)
    if m:
        names.append(m.group(1).strip())
    for line in answer_text.splitlines():
        m = re.match(r"^\s*\d+\.\s*(.+)$", line.strip())
        if m:
            names.append(m.group(1).strip())
    parsing_alts = False
    for line in answer_text.splitlines():
        if re.match(r"(?i)^\s*Alternatives?:", line.strip()):
            parsing_alts = True
            continue
        if parsing_alts:
            m = re.match(r"^\s*-\s*(.+)$", line.strip())
            if m:
                names.append(m.group(1).strip())
            if re.match(r"^\s*(Weather tips|Notes|Close|Enjoy!)", line.strip(), re.I):
                break
    cleaned = []
    for n in names:
        n = re.split(r"\s+[–—-]\s+", n, maxsplit=1)[0].strip()
        cleaned.append(n)
    return cleaned

def _variants(name: str) -> List[str]:
    base = name.strip()
    no_paren = re.sub(r"\s*\([^)]*\)\s*", " ", base).strip()
    in_paren = re.findall(r"\(([^)]]{2,})\)", base)
    vars_ = [base, no_paren] + in_paren
    out, seen = [], set()
    for v in vars_:
        if v and v not in seen:
            seen.add(v); out.append(v)
    return out

def select_places_from_answer(df: pd.DataFrame, answer_text: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    for c in ["name", "category", "lat", "lon"]:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in attractions DataFrame")

    name_index: Dict[str, List[int]] = {}
    for idx, row in df.iterrows():
        norm = _normalize_name(str(row["name"]))
        name_index.setdefault(norm, []).append(idx)

    raw_candidates = _extract_candidate_lines(answer_text)
    picked_indices: List[int] = []
    seen = set()
    all_norm_names = list(name_index.keys())

    for raw in raw_candidates:
        matched = False
        for v in _variants(raw):
            norm = _normalize_name(v)
            if norm in name_index:
                for idx in name_index[norm]:
                    if idx not in seen:
                        picked_indices.append(idx); seen.add(idx)
                matched = True
                break
        if matched:
            continue
        norm_full = _normalize_name(raw)
        close = get_close_matches(norm_full, all_norm_names, n=1, cutoff=0.85)
        if close:
            for idx in name_index[close[0]]:
                if idx not in seen:
                    picked_indices.append(idx); seen.add(idx)

    return df.loc[picked_indices, ["name", "category", "lat", "lon"]].reset_index(drop=True)

# ------------------------------
#            Map (Folium)
# ------------------------------

def create_map(city_center: Tuple[float, float], points_df: pd.DataFrame, out_path: str = "itinerary_map.html") -> str:
    """
    יוצר HTML אינטראקטיבי עם:
    - סיכות ממוספרות לפי סדר המסלול
    - עיגולי צבע מתחת לכל סיכה (קלירות)
    - קו PolyLine בין התחנות
    - fit_bounds אוטומטי לכל הנקודות
    """
    m = folium.Map(location=city_center, zoom_start=13)

    coords = []
    clean = points_df.dropna(subset=["lat", "lon"]).copy()
    for i, row in clean.reset_index(drop=True).iterrows():
        lat = float(row["lat"]); lon = float(row["lon"])
        name = str(row.get("name", ""))
        cat  = str(row.get("category", ""))

        # עיגול צבעוני – שיהיה קל לראות גם בלי האייקון
        folium.CircleMarker(
            location=[lat, lon],
            radius=7 if i == 0 else 6,
            weight=2,
            fill=True,
            fill_opacity=0.9
        ).add_to(m)

        # סיכה ממוספרת (DivIcon)
        folium.Marker(
            location=[lat, lon],
            tooltip=f"{i+1}. {name}",
            popup=folium.Popup(f"<b>{i+1}. {name}</b><br/>{cat}", max_width=260),
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    background:#2c7be5;
                    color:#fff;
                    border-radius:14px;
                    width:28px;height:28px;
                    line-height:28px;
                    text-align:center;
                    font-weight:700;
                    font-size:12px;
                    box-shadow:0 0 0 2px #fff;
                ">{i+1}</div>"""
            )
        ).add_to(m)

        coords.append([lat, lon])

    # קו המסלול + התאמת תיחום
    if len(coords) >= 2:
        folium.PolyLine(coords, weight=3).add_to(m)
        m.fit_bounds(coords)
    elif len(coords) == 1:
        m.location = coords[0]; m.zoom_start = 15

    m.save(out_path)
    return out_path
