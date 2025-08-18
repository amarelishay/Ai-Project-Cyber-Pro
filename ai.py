import json
import os

import numpy as np
import pandas as pd
from openai import OpenAI

import os
from dotenv import load_dotenv


def _to_serializable(x):
    if isinstance(x, set):
        return list(x)
    if isinstance(x, (np.generic,)):  # np.int64, np.float32 וכו'
        return np.asarray(x).item()
    return x


def df_to_safe_json(df: pd.DataFrame) -> str:
    # ממיר DF לרשימת רשומות JSON, ומסדר כל ערך בעייתי
    records = df.to_dict(orient="records")
    safe_records = [{k: _to_serializable(v) for k, v in row.items()} for row in records]
    return json.dumps(safe_records, ensure_ascii=False)


def dict_to_safe_json(d: dict) -> str:
    return json.dumps({k: _to_serializable(v) for k, v in d.items()}, ensure_ascii=False)


def load_env(dotenv_path: str = ".env") -> None:
    """
    טוען משתני סביבה מקובץ .env אם הוא קיים.

    :param dotenv_path: נתיב לקובץ .env (ברירת מחדל - בתיקייה הראשית של הפרויקט)
    """
    if os.path.exists(dotenv_path):
        try:
            load_dotenv(dotenv_path)
        except Exception as e:
            print(f"⚠️ Error loading environment variables from {dotenv_path}: {e}")
    else:
        print(f"⚠️ No .env file found at {dotenv_path}")


def get_ai_dictation(city_name, max_tokens=800, temperature=0.4):
    # טעינת משתני סביבה
    load_env()

    # בדיקת מפתח API
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "[Error: OPENAI_API_KEY not set. Please create a .env file with your API key.]"

    # יצירת לקוח OpenAI
    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL")

    messages = [
        {
            "role": "system",
            "content": (
                "Normalize a city name for use with OSMnx.\n"
                "Input may be in any language or misspelled English and may include extra words.\n"
                "Extract only the city name (ignore any unrelated words).\n"
                "If Hebrew → translate to the official English city name.\n"
                "If English → correct spelling and capitalization to the official form.\n"
                "Output exactly in the format: <City>, <Country> (single comma, one space).\n"
                "Return only the normalized string, nothing else.\n"
                "Examples:\n"
                "אשדוד → Ashdod, Israel\n"
                "ashhdod → Ashdod, Israel"
            )
        },
        {
            "role": "user",
            "content": f"City: {city_name}"
        }
    ]

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[AI error: {e}]"


def get_ai_response(city_name, weather_info, attractions_list, user_profile,
                    prompt="", context="", max_tokens=800, temperature=0.2):
    """Get AI trip recommendation from OpenAI API"""

    # טעינת משתני סביבה
    load_env()

    # בדיקת מפתח API
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "[Error: OPENAI_API_KEY not set. Please create a .env file with your API key.]"

    # יצירת לקוח OpenAI
    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL")

    # הפוך את האטרקציות והפרופיל למחרוזות בטוחות
    if isinstance(attractions_list, pd.DataFrame):
        attractions_str = df_to_safe_json(attractions_list)
    else:
        # אם זה כבר רשימת דיקט/דאטה—ננסה לסדר
        attractions_str = json.dumps(attractions_list, default=_to_serializable, ensure_ascii=False)

    user_profile_str = dict_to_safe_json(user_profile)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a trip recommendation assistant.\n"
                "You will receive:\n"
                "1) City name (if it's not in the same language as your response, translate it in your response).\n"
                "2) Current weather in that city (numeric temperature in °C and optional conditions if available).\n"
                "3) A list of attractions (each with name, category, latitude, longitude).\n"
                "4) A user profile (e.g., has_children, children_count, hobbies).\n\n"
                "Strict rules:\n"
                "- Only choose attractions from the provided list. Do NOT invent new places.\n"
                "- Evaluate the attractions by combining:\n"
                "   • Your general knowledge about these places (e.g., popularity, highlights).\n"
                "   • Information you can search on the web if available.\n"
                "- Rank and recommend the most suitable and highly regarded attractions for this user profile.\n"
                "- If unsure about a place’s quality or relevance, mark it as 'Unknown' or exclude it.\n"
                "- Always mention the current temperature in °C in the summary and tailor advice accordingly.\n"
                "- Use latitude/longitude ONLY for logical ordering; never display them.\n"
                "- If opening hours, tickets, or details are not known, write 'Unknown' and suggest verifying. Do not guess numbers.\n"
                "- Keep the response concise, practical, and easy to follow.\n"
                "- Finish with 'Enjoy!'\n\n"
                "Goals:\n"
                "- Recommend ONE primary highlight: the most recommended attraction TODAY for this profile and weather.\n"
                "- ALSO propose a short itinerary (3–5 stops) of the best-ranked attractions from the list.\n"
                "- Order the itinerary logically (considering lat/lon proximity).\n"
                "- If the user has children, prioritize child-friendly attractions (zoo, aquarium, theme park, playground, park, beach, interactive museums). For toddlers, avoid strenuous venues.\n"
                "- Align with hobbies when possible.\n"
                "- If the weather makes some options unsuitable, replace them with better-ranked alternatives from the list.\n\n"
                "Output format (exact order):\n"
                "1) Title: <short universal title>\n"
                "2) Summary: 2–3 natural sentences explaining why this plan fits the user and weather. Explicitly mention the temperature in °C.\n"
                "3) Primary highlight: <exact attraction name from input> (category if provided). Add a brief factual/contextual note if confidently known.\n"
                "4) Itinerary (3–5 stops): numbered list of the best-ranked attractions from the input, with categories. Add short factual notes if confidently known.\n"
                "5) Weather tips: 1–2 actionable notes tailored to temperature/conditions.\n"
                "6) Alternatives (1–2, optional): next-best attractions from the list.\n"
                "7) Notes: explicitly list any key 'Unknowns' (e.g., 'Opening hours: Unknown').\n"
                "8) Close: 'Enjoy!'\n")
        },
        {
            "role": "user",
            "content": (
                f"City: {city_name}\n"
                f"Weather: {weather_info}\n"
                f"Attractions (JSON): {attractions_str}\n"
                f"User profile (JSON): {user_profile_str}\n\n"
                "Please recommend an outing for this user."
            )
        }
    ]

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return f"[AI error: {e}]"
