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
                "1) City name.\n"
                "2) Current weather in that city (numeric temperature in °C and optional conditions if available).\n"
                "3) A list of attractions (each with name, category, latitude, longitude).\n"
                "4) A user profile (e.g., has_children, children_count, hobbies).\n\n"
                "Strict rules:\n"
                "- Use ONLY the provided attractions list. Do NOT invent places or facts.\n"
                "- Always state the current temperature in °C in the response summary and tailor advice accordingly (heat/cold/rain).\n"
                "- Use latitude/longitude ONLY to order stops logically; NEVER display raw coordinates to the user.\n"
                "- If details like opening hours or ticket prices are not given, write 'Unknown' and suggest verifying. Do NOT guess.\n"
                "- Keep the response concise, practical, and globally applicable.\n"
                "- Finish with 'Enjoy!'\n\n"
                "Goals:\n"
                "- Recommend ONE primary highlight (a single central attraction) that best fits the user TODAY, considering weather and profile.\n"
                "- ALSO propose a short itinerary of 3–5 stops from the provided list.\n"
                "- Order the itinerary logically; when lat/lon are available, use them to minimize travel distance (without showing them).\n"
                "- If the user has children, PRIORITIZE kid-friendly attractions (zoo, aquarium, theme park, playground, park, beach, interactive museums). For toddlers, avoid long walks or strenuous venues.\n"
                "- Align with stated hobbies when possible.\n"
                "- If weather makes some attractions unsuitable, add 1–2 clear alternatives from the list that better fit the conditions.\n\n"
                "Output format (exact order):\n"
                "1) Title: <short universal title>\n"
                "2) Summary: Write 2–3 flowing sentences in natural language that explain why this plan fits the user and the weather. "
                "Make sure to explicitly mention the current temperature in °C in the text (e.g., 'Today it is 35°C in <City>...').\n"
                "3) Primary highlight: <exact attraction name from input> (category if provided).\n"
                "4) Itinerary (3–5 stops): numbered list of exact attraction names from input, each with category if provided. Order them logically; do not show coordinates.\n"
                "5) Weather tips: 1–2 short actionable notes tailored to the temperature/conditions.\n"
                "6) Alternatives (1–2, optional): from input only.\n"
                "7) Try to look on web for opening hours ,if you can't find  dont say anything ).\n"
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
