from __future__ import annotations
import folium
import os, sys, subprocess, webbrowser
import requests
import osmnx as ox
import pandas as pd
import geopandas as gpd
import re
from ai import get_ai_response, get_ai_dictation
from difflib import get_close_matches
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

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
def open_file_in_browser(path: str) -> str:
    """פותח את הקובץ בדפדפן ברירת המחדל ומחזיר URL מקומי לקובץ."""
    abs_path = os.path.abspath(path)
    url = "file://" + abs_path.replace("\\", "/")
    try:
        if sys.platform.startswith("win"):
            os.startfile(abs_path)  # Windows
        elif sys.platform == "darwin":
            subprocess.run(["open", abs_path], check=False)  # macOS
        else:
            subprocess.run(["xdg-open", abs_path], check=False)  # Linux
    except Exception:
        # fallback
        webbrowser.open(url)
    return url
def nearest_neighbor_itinerary(df: pd.DataFrame, start_lat: float, start_lon: float, stops: int = 4) -> pd.DataFrame:
    """בניית מסלול קצר לפי קרבה (approx)."""
    if df.empty:
        return df.copy()
    work = df.dropna(subset=["lat", "lon"]).copy()
    route = []
    cur_lat, cur_lon = start_lat, start_lon
    for _ in range(min(stops, len(work))):
        idx = ((work["lat"] - cur_lat)**2 + (work["lon"] - cur_lon)**2).idxmin()
        step = work.loc[idx]
        route.append(step)
        cur_lat, cur_lon = float(step["lat"]), float(step["lon"])
        work = work.drop(index=idx)
    return pd.DataFrame(route).reset_index(drop=True)
def create_map(city_center: tuple[float, float], points_df: pd.DataFrame, out_path: str = "itinerary_map.html") -> str:
    m = folium.Map(location=city_center, zoom_start=13)
    coords = []
    for i, row in points_df.iterrows():
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue
        title = f"{i+1}. {row.get('name','')}"
        cat = row.get("category", "")
        folium.Marker(
            location=[float(row["lat"]), float(row["lon"])],
            popup=folium.Popup(f"<b>{title}</b><br/>{cat}", max_width=250),
            tooltip=title
        ).add_to(m)
        coords.append((float(row["lat"]), float(row["lon"])))
    if len(coords) >= 2:
        folium.PolyLine(coords).add_to(m)
    m.save(out_path)
    # פותח ומחזיר URL
    return open_file_in_browser(out_path)
def getActivities(city_name: str, limit: int = 300) -> pd.DataFrame:
    place = get_ai_dictation(city_name)

    # קבוצות התגים כפי שהגדרת (נשתמש בהן ל-RegEx בשאילתה)
    TAGS = {
        "tourism": ["attraction","museum","gallery","zoo","theme_park","viewpoint","aquarium","artwork","information"],
        "leisure": ["park","garden","playground","nature_reserve","sports_centre","pitch","stadium","swimming_pool","fitness_centre","golf_course","marina","water_park"],
        "amenity": ["cafe","restaurant","fast_food","bar","pub","biergarten","theatre","cinema","arts_centre","library","ice_cream","marketplace","fountain","spa","sauna"],
        "shop": ["mall","department_store","supermarket","bakery","confectionery","deli","outdoor"],
        "historic": ["castle","monument","memorial","ruins","archaeological_site","heritage"],
        "natural": ["beach","wood","peak"]
    }

    # 1) חשב BBOX של המקום כדי להגביל את השאילתא
    try:
        gdf_place = ox.geocode_to_gdf(place)
        west, south, east, north = gdf_place.union_all().bounds  # (minx, miny, maxx, maxy)
    except Exception:
        # אם גיאוקוד נכשל – נפיל חזרה ליישום הישן שלך
        return _fallback_getActivities(place, TAGS, limit)

    # 2) בנה Overpass QL עם limit כולל (out … 300)
    # נשתמש ב-nwr (nodes/ways/relations), ונבקש center כדי לקבל lat/lon גם ל-ways/relations
    parts = []
    for key, vals in TAGS.items():
        # בנה regex כמו (attraction|museum|gallery|...)
        pattern = "(" + "|".join(vals) + ")"
        parts.append(f'nwr["{key}"~"{pattern}"]({south},{west},{north},{east});')

    union = "\n  ".join(parts)
    ql = f"""
    [out:json][timeout:180];
    (
      {union}
    );
    out center {int(limit)};
    """

    try:
        resp = requests.post(OVERPASS_URL, data={"data": ql}, timeout=180)
        resp.raise_for_status()
        data = resp.json()
        elements = data.get("elements", [])
        rows = []
        for el in elements:
            tags = el.get("tags", {}) or {}
            name = tags.get("name")
            if not name or not str(name).strip():
                continue

            # קח lat/lon: ל-nodes יש lat/lon, ל-ways/relations יש center
            if "lat" in el and "lon" in el:
                lat = el["lat"]; lon = el["lon"]
            else:
                center = el.get("center")
                if not center:
                    continue
                lat = center.get("lat"); lon = center.get("lon")
                if lat is None or lon is None:
                    continue

            # היררכיית קטגוריה: נרשום key:value הראשון שמופיע מ-TAGS
            cat = None
            for key, vals in TAGS.items():
                val = tags.get(key)
                if val:
                    cat = f"{key}:{val}"
                    break

            rows.append({
                "name": name,
                "category": cat or "",
                "lat": float(lat),
                "lon": float(lon),
            })

        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=["name", "category", "lat", "lon"])
        # ניקוי כפילויות ושמירה על גודל מקסימלי (ליתר ביטחון)
        df = df.drop_duplicates(subset=["name","lat","lon"]).reset_index(drop=True)
        if len(df) > limit:
            df = df.head(limit).reset_index(drop=True)
        return df

    except Exception:
        # על כשל ברשת/פורמט – fallback ליישום הקודם שלך
        return _fallback_getActivities(place, TAGS, limit)


def _fallback_getActivities(place: str, TAGS: dict, limit: int) -> pd.DataFrame:
    """
    נפילה לשיטה הקודמת (OSMnx features_from_place) ואם צריך – חתך ל-300 מקס'.
    """
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

        # עצור מוקדם אם כבר חרגת מהתקציב
        if sum(len(f) for f in frames) >= limit:
            break

    if not frames:
        return pd.DataFrame(columns=["name", "category", "lat", "lon"])

    df = pd.concat(frames, ignore_index=True).drop_duplicates().reset_index(drop=True)
    # קיצוץ אחרון
    if len(df) > limit:
        df = df.head(limit).reset_index(drop=True)
    return df
def geocode_city_center(place: str) -> tuple[float, float]:
    """מחזיר (lat, lon) למרכז העיר בעזרת OSMnx (חינמי)."""
    lat, lon = ox.geocode(place)  # (lat, lon)
    return float(lat), float(lon)
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
def _normalize_name(s: str) -> str:
    """נרמול שם להשוואה: אותיות/ספרות מכל שפה, רווחים יחידים, לואורקייס."""
    s = s.strip()
    # הסר מירכאות וסימני פיסוק נפוצים
    s = re.sub(r"[\"'’“”„`]", "", s)
    # הסר טקסט בסוגריים (כולל תרגום/כינוי)
    s_no_paren = re.sub(r"\s*\([^)]*\)\s*", " ", s).strip()
    # שמור רק אותיות/ספרות ורווחים
    s_no_punct = re.sub(r"[^\w\s\u0590-\u05FF]", " ", s_no_paren, flags=re.UNICODE)
    s_spaced = re.sub(r"\s+", " ", s_no_punct)
    return s_spaced.lower().strip()

def _extract_candidate_lines(answer_text: str) -> list[str]:
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
    for line in answer_text.splitlines():
        m = re.match(r"^\s*-\s*(.+)$", line.strip())
        if m:
            names.append(m.group(1).strip())

    # חתוך תיאורים אחרי מפרידי טקסט נפוצים (en/em dash וכו')
    cleaned = []
    for n in names:
        n = re.split(r"\s+[–—-]\s+", n, maxsplit=1)[0].strip()
        cleaned.append(n)
    return cleaned

def _variants(name: str) -> list[str]:
    """וריאנטים מועילים לניסיון התאמה: מלא, בלי סוגריים, התוכן שבסוגריים."""
    base = name.strip()
    no_paren = re.sub(r"\s*\([^)]*\)\s*", " ", base).strip()
    in_paren = re.findall(r"\(([^)]{2,})\)", base)
    vars_ = [base, no_paren]
    vars_.extend(in_paren)
    # הסר כפילויות תוך שמירת סדר
    seen = set(); out=[]
    for v in vars_:
        if v and v not in seen:
            seen.add(v); out.append(v)
    return out

def select_places_from_answer(df: pd.DataFrame, answer_text: str) -> pd.DataFrame:
    """
    מחזיר DF חדש עם המקומות שהמודל הזכיר בתשובה (Primary / Itinerary / Alternatives),
    באותו פורמט בדיוק: name, category, lat, lon, ובאותו סדר הופעה.
    """
    if df.empty:
        return df.copy()

    required = ["name", "category", "lat", "lon"]
    for c in required:
        if c not in df.columns:
            raise ValueError(f"Missing required column '{c}' in attractions DataFrame")

    # אינדקס שמות מנורמלים -> אינדקסים מקוריים (תומך בכפילויות שם)
    name_index: dict[str, list[int]] = {}
    for idx, row in df.iterrows():
        nm = str(row["name"])
        norm = _normalize_name(nm)
        name_index.setdefault(norm, []).append(idx)

    # שלוף מועמדים מהטקסט
    raw_candidates = _extract_candidate_lines(answer_text)

    picked_indices: list[int] = []
    seen = set()

    # לכלי פאזי-מאץ' – כל השמות המנורמלים הקיימים
    all_norm_names = list(name_index.keys())

    for raw in raw_candidates:
        matched = False
        # נסה וריאנטים: מלא / בלי סוגריים / התוכן שבסוגריים
        for v in _variants(raw):
            norm = _normalize_name(v)
            if norm in name_index:
                for idx in name_index[norm]:
                    if idx not in seen:
                        picked_indices.append(idx)
                        seen.add(idx)
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
                    picked_indices.append(idx)
                    seen.add(idx)

    # החזר DF נקי בסדר שנמצאו
    return df.loc[picked_indices, ["name", "category", "lat", "lon"]].reset_index(drop=True)



if __name__ == "__main__":
    # city = "tel aviv"
    # Activities = pd.DataFrame(getActivities(city).values)
    # print(Activities)
    # weather = get_weather(city)
    # print(weather)
    # נסיון “שם עיר בלבד” (near=)
    # דורש OPENTRIPMAP_API_KEY ב-.env (חינם)
    # city_name, weather_info, attractions_list, user_profile = run_questionnaire()
    # # attractions_list = attach_images(attractions_list, city_name)
    # print(get_ai_response(city_name, weather_info, attractions_list, user_profile))
    # city_name, weather_info, attractions_list, user_profile = run_questionnaire()
    #
    # place = get_ai_dictation(city_name)
    # center = geocode_city_center(place)
    # response=get_ai_response(city_name, weather_info, attractions_list, user_profile)
    # itin_df = nearest_neighbor_itinerary(select_places_from_answer(attractions_list, response), center[0], center[1], stops=4)
    #
    # # צור מפה ל-itinerary (אם אין מסלול/נתונים, אפשר גם להעביר את attractions_list)
    # map_path = create_map(itin_df)
    # print(f"✅ Map saved to: {map_path}")
    # map_url = create_map(itin_df)
    # print(f"✅ Map opened: {map_url}")
    # # תשובת ה-LLM שלך (נשאר כמו שהוא)
    #
    # print(response)
    if __name__ == "__main__":
        city_name, weather_info, attractions_list, user_profile = run_questionnaire()

        # מרכז העיר + תשובת המודל
        place = get_ai_dictation(city_name)
        center = geocode_city_center(place)

        response = get_ai_response(city_name, weather_info, attractions_list, user_profile)
        # אם get_ai_response מחזיר טקסט בלבד:
        text = response
        # אם אצלך הוא מחזיר (text, selected_json) – שנה לשורה מעל בהתאם

        # שלוף רק את המקומות שהמודל הזכיר
        selected_df = select_places_from_answer(attractions_list, text)

        # בנה מסלול קצר על סמך הבחירות; אם לא נבחר כלום – נשתמש בכל הרשימה
        base_df = selected_df if not selected_df.empty else attractions_list
        itin_df = nearest_neighbor_itinerary(base_df, center[0], center[1],stops=10)

        # צור מפה ופתח אותה
        map_url = create_map(center, itin_df if not itin_df.empty else base_df)
        print(f"✅ Map opened: {map_url}")

        # הדפס את הטקסט למשתמש
        print(text)
