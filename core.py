# core.py
# ------------------------------
# לוגיקה מרכזית לפרויקט:
# - מזג אוויר (חינמי, ללא מפתח: Open-Meteo; ואם יש WEATHER_KEY – WeatherAPI)
# - שליפה חכמה מ-OSM עם הגבלה ≤300 ישירות בשרת (Overpass QL) + Fallback ל-OSMnx
# - בניית מסלול קצר (Nearest Neighbor)
# - יצירת מפה (Folium) כ-HTML להטמעה ב-GUI
# - חילוץ שמות אטרקציות מטקסט תשובת ה-AI והתאמתם ל-DF המקורי
# ------------------------------

from __future__ import annotations
import os
import re
from staticmap import StaticMap, CircleMarker, Line
from PIL import Image

from typing import Optional, Tuple, List, Dict

import requests
import pandas as pd
import geopandas as gpd
import osmnx as ox
from difflib import get_close_matches
import folium
from shapely.geometry import Point

# נרמול שם מקום (עיר) – מגיע מ-ai.py אצלך
try:
    from ai import get_ai_dictation
except Exception:
    # גיבוי: החזר את הטקסט כמו שהוא אם אין פונקציה
    def get_ai_dictation(city: str) -> str:
        return str(city).strip()

# ------------------------------
#          Weather
# ------------------------------

def _geocode_for_weather(city: str) -> Optional[Tuple[float, float]]:
    """
    גיאוקוד קליל עבור מזג אוויר (אם אין WeatherAPI): משתמש ב-Nominatim (OSM).
    """
    try:
        q = get_ai_dictation(city)
        loc = ox.geocode(q)  # (lat, lon)
        return float(loc[0]), float(loc[1])
    except Exception:
        return None


def _weather_open_meteo(city: str) -> Optional[str]:
    """
    פנייה חינמית ל-Open-Meteo (ללא מפתח).
    מחזיר מחרוזת בפורמט: '<temp>°C, <conditions>' או None.
    """
    coords = _geocode_for_weather(city)
    if not coords:
        return None
    lat, lon = coords
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon, "current_weather": True}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        cur = data.get("current_weather") or {}
        temp = cur.get("temperature")  # Celsius
        # מצב כללי – אין מלל קבוע, נשאיר רק טמפ'
        if temp is None:
            return None
        return f"{temp}°C"
    except Exception:
        return None


def _weather_weatherapi(city: str, api_key: str) -> Optional[str]:
    """
    אם יש WEATHER_KEY – נשתמש ב-WeatherAPI (כבר עבד אצלך).
    פורמט החזרה: '<temp>°C, <condition-text>'
    """
    url = "http://api.weatherapi.com/v1/current.json"
    params = {"key": api_key, "q": get_ai_dictation(city), "aqi": "no", "lang": "en"}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        cur = data.get("current", {})
        t = cur.get("temp_c")
        cond = ((cur.get("condition") or {}).get("text") or "").strip()
        if t is None:
            return None
        return f"{t}°C" + (f", {cond}" if cond else "")
    except Exception:
        return None


def get_weather(city: str) -> str:
    """
    מחזיר מחרוזת מזג אוויר לתזמון מול ה-LLM:
    תמיד יכיל טמפרטורה ב-°C (ואם יש – גם מלל מצב).
    """
    key = os.getenv("WEATHER_KEY") or os.getenv("WEATHERAPI_KEY")
    if key:
        s = _weather_weatherapi(city, key)
        if s:
            return s
    s = _weather_open_meteo(city)
    if s:
        return s
    # גיבוי: לפחות נחזיר Unknown כדי שהמודל יתייחס בהתאם
    return "Unknown"


# ------------------------------
#        OSM Attractions
# ------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# קבוצות תגים – כמו אצלך
OSM_TAGS: Dict[str, List[str]] = {
    "tourism": ["attraction", "museum", "gallery", "zoo", "theme_park", "viewpoint", "aquarium", "artwork", "information"],
    "leisure": ["park", "garden", "playground", "nature_reserve", "sports_centre", "pitch", "stadium", "swimming_pool", "fitness_centre", "golf_course", "marina", "water_park"],
    "amenity": ["cafe", "restaurant", "fast_food", "bar", "pub", "biergarten", "theatre", "cinema", "arts_centre", "library", "ice_cream", "marketplace", "fountain", "spa", "sauna"],
    "shop": ["mall", "department_store", "supermarket", "bakery", "confectionery", "deli", "outdoor"],
    "historic": ["castle", "monument", "memorial", "ruins", "archaeological_site", "heritage"],
    "natural": ["beach", "wood", "peak"]
}

def _bbox_for_place(place: str) -> Optional[Tuple[float, float, float, float]]:
    """החזרת Bounding Box של המקום (west, south, east, north)."""
    try:
        gdf = ox.geocode_to_gdf(place)
        minx, miny, maxx, maxy = gdf.unary_union.bounds
        return (minx, miny, maxx, maxy)
    except Exception:
        return None


def _overpass_query_bounded(tags: Dict[str, List[str]], bbox: Tuple[float,float,float,float], limit: int) -> str:
    """בונה שאילתת Overpass QL עם הגבלה כוללת (out center <limit>)."""
    west, south, east, north = bbox
    parts = []
    for k, vals in tags.items():
        pat = "(" + "|".join(vals) + ")"
        parts.append(f'nwr["{k}"~"{pat}"]({south},{west},{north},{east});')
    union = "\n  ".join(parts)
    ql = f"""
    [out:json][timeout:180];
    (
      {union}
    );
    out center {int(limit)};
    """
    return ql


def _fetch_overpass(ql: str) -> List[dict]:
    r = requests.post(OVERPASS_URL, data={"data": ql}, timeout=180)
    r.raise_for_status()
    return (r.json() or {}).get("elements", [])


def getActivities(city_name: str, limit: int = 300) -> pd.DataFrame:
    """
    שליפה מ-OSM עם הגבלה לכל היותר 'limit' רשומות כבר מהשרת.
    פורמט החזרה: name, category, lat, lon (ללא קואורדינטות בדפוס גיאומטרי).
    """
    place = get_ai_dictation(city_name)
    bbox = _bbox_for_place(place)

    # נסה קודם Overpass עם limit
    if bbox:
        try:
            ql = _overpass_query_bounded(OSM_TAGS, bbox, limit)
            elements = _fetch_overpass(ql)
            rows = []
            for el in elements:
                tags = el.get("tags", {}) or {}
                name = tags.get("name")
                if not name or not str(name).strip():
                    continue

                # קואורדינטות: ל-nodes יש lat/lon; ל-ways/relations יש center
                if "lat" in el and "lon" in el:
                    lat, lon = el["lat"], el["lon"]
                else:
                    center = el.get("center") or {}
                    lat, lon = center.get("lat"), center.get("lon")
                if lat is None or lon is None:
                    continue

                # קטגוריה – key:value הראשון שקיים מתוך הסט
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
                df = df.drop_duplicates(subset=["name", "lat", "lon"]).reset_index(drop=True)
                if len(df) > limit:
                    df = df.head(limit).reset_index(drop=True)
                return df
        except Exception:
            pass  # ניפול ל-Fallback

    # Fallback – OSMnx features_from_place, עם עצירה מוקדמת + תיקון CRS לחישוב centroids
    ox.settings.timeout = 180
    frames: List[pd.DataFrame] = []

    for key, values in OSM_TAGS.items():
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

        # ודא CRS
        if g.crs is None:
            g = g.set_crs(epsg=4326)

        # חישוב centroid "נכון": הקרנה למטרי ואז חזרה ל-WGS84
        g_proj = g.to_crs(epsg=3857)
        centroids_proj = gpd.GeoSeries(g_proj.geometry.centroid, crs=g_proj.crs)
        centroids_wgs84 = centroids_proj.to_crs(epsg=4326)

        g["lat"] = centroids_wgs84.y.values
        g["lon"] = centroids_wgs84.x.values

        g["category"] = key + ":" + g[key].astype(str).str.strip()
        frames.append(g[["name", "category", "lat", "lon"]])

        # עצירה מוקדמת – אם כבר עברנו limit נחלקל מיד
        if sum(len(f) for f in frames) >= limit:
            break

    if not frames:
        return pd.DataFrame(columns=["name", "category", "lat", "lon"])

    df = pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)
    if len(df) > limit:
        df = df.head(limit).reset_index(drop=True)
    return df


# ------------------------------
#  Route building (Nearest Neighbor)
# ------------------------------

def geocode_city_center(place: str) -> Tuple[float, float]:
    """מחזיר (lat, lon) למרכז העיר בעזרת OSMnx."""
    lat, lon = ox.geocode(place)  # (lat, lon)
    return float(lat), float(lon)


def nearest_neighbor_itinerary(df: pd.DataFrame, start_lat: float, start_lon: float, stops: int = 4) -> pd.DataFrame:
    """
    בונה מסלול קצר לפי קרבה (approx). אם df קטן – יחזיר את הקיים.
    """
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
    """
    שולף שמות מהרשובה:
    - Primary highlight: <name>
    - Itinerary: שורות ממוספרות '1. <name> – ...'
    - Alternatives: שורות שמתחילות ב'- <name>'
    """
    names = []

    # Primary highlight
    m = re.search(r"(?im)^Primary highlight:\s*(.+)$", answer_text)
    if m:
        names.append(m.group(1).strip())

    # Itinerary numbered lines
    for line in answer_text.splitlines():
        m = re.match(r"^\s*\d+\.\s*(.+)$", line.strip())
        if m:
            names.append(m.group(1).strip())

    # Alternatives bullet lines
    parsing_alts = False
    for line in answer_text.splitlines():
        if re.match(r"(?i)^\s*Alternatives?:", line.strip()):
            parsing_alts = True
            continue
        if parsing_alts:
            m = re.match(r"^\s*-\s*(.+)$", line.strip())
            if m:
                names.append(m.group(1).strip())
            # עצור אם הגענו לחלק הבא
            if re.match(r"^\s*(Weather tips|Notes|Close|Enjoy!)", line.strip(), re.I):
                break

    # חתוך תיאורים אחרי מפרידי טקסט נפוצים (en dash / em dash וכו')
    cleaned = []
    for n in names:
        n = re.split(r"\s+[–—-]\s+", n, maxsplit=1)[0].strip()
        cleaned.append(n)
    return cleaned


def _variants(name: str) -> List[str]:
    """וריאנטים מועילים: מלא, בלי סוגריים, והתוכן שבסוגריים (תרגום/כינוי)."""
    base = name.strip()
    no_paren = re.sub(r"\s*\([^)]*\)\s*", " ", base).strip()
    in_paren = re.findall(r"\(([^)]{2,})\)", base)
    vars_ = [base, no_paren] + in_paren
    seen: set[str] = set(); out: List[str] = []
    for v in vars_:
        if v and v not in seen:
            seen.add(v); out.append(v)
    return out


def select_places_from_answer(df: pd.DataFrame, answer_text: str) -> pd.DataFrame:
    """
    מקבל DF מלא של אטרקציות + טקסט תשובת המודל,
    ומחזיר DF עם המקומות שהוזכרו (Primary/Itinerary/Alternatives) באותו פורמט: name, category, lat, lon.
    """
    if df.empty:
        return df.copy()

    for c in ["name", "category", "lat", "lon"]:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in attractions DataFrame")

    # אינדקס שמות מנורמלים -> אינדקסים מקוריים
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
        # נסה וריאנטים: מלא / בלי סוגריים / התוכן שבסוגריים
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

        # פאזי-מאץ' עדין אם אין התאמה ישירה
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
    יוצר קובץ HTML עם מפה, סימונים ומסלול מחובר. לא פותח דפדפן.
    החזרה: נתיב לקובץ HTML (עבור GUI להטענה פנימית).
    """
    m = folium.Map(location=city_center, zoom_start=13)
    coords = []
    for i, row in points_df.iterrows():
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue
        title = f"{i+1}. {row.get('name','')}"
        cat = row.get("category", "")
        folium.Marker(
            location=[float(row["lat"]), float(row["lon"])],
            popup=folium.Popup(f"<b>{title}</b><br/>{cat}", max_width=260),
            tooltip=title
        ).add_to(m)
        coords.append((float(row["lat"]), float(row["lon"])))
    if len(coords) >= 2:
        folium.PolyLine(coords).add_to(m)
    m.save(out_path)
    return out_path

def create_static_map_image(city_center: tuple[float, float], points_df: pd.DataFrame,
                            out_path: str = "itinerary_map.png") -> str:
    """
    PNG סטטי של המפה: מסלול + סמנים.
    - אם יש >=2 נקודות: מתאים פריימינג אוטומטי לכל הנקודות (fit to bounds).
    - אם יש 1 נקודה: מתמקד עליה בזום נוח.
    - אם אין נקודות: מתמקד במרכז העיר בזום כללי.
    """
    m = StaticMap(900, 640, url_template="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")

    coords = []
    for i, row in points_df.iterrows():
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue
        lat = float(row["lat"]); lon = float(row["lon"])
        m.add_marker(CircleMarker((lon, lat), '#2c7be5', 10 if i == 0 else 8))
        coords.append((lon, lat))

    if len(coords) >= 2:
        m.add_line(Line(coords, '#2c7be5', 3))
        # ⚡ בלי center/zoom — StaticMap יבצע fit-to-bounds אוטומטי לכל הסמנים/הקו
        image = m.render()
    elif len(coords) == 1:
        # נקודה אחת — התקרבות נעימה
        (lon, lat) = coords[0]
        image = m.render(zoom=15, center=(lon, lat))
    else:
        # אין נקודות — מרכז עיר
        clat, clon = float(city_center[0]), float(city_center[1])
        image = m.render(zoom=13, center=(clon, clat))
