import os
from openai import OpenAI

import os
from dotenv import load_dotenv


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

    messages = [
        {
            "role": "system",
            "content": (
                "You are a trip recommendation assistant. "
                "You will receive:\n"
                "1. The current weather in a specific city.\n"
                "2. A list of attractions in that city.\n"
                "3. The name of the city.\n"
                "4. Personal user details from a questionnaire (e.g., if they have children and how many).\n\n"
                "Your goal:\n"
                "- Suggest the most suitable outing for the user.\n"
                "check what is the best recommendation for the user from the list in web \n"
                "- Take into account the current weather and the user's profile.\n"
                "- Be clear, concise, and provide a short explanation of why you chose this recommendation.\n"
                "- If the weather is not favorable for certain attractions, suggest suitable alternatives. \n"
                "- try to look for some data of each recommendation that you recommend and tell it to the user inside your answer(such as opening hours for example).\n"
                "-if you founded some data tell the user where you founded it \n"
                "answer clearly and shortly and  finish with enjoy  \n "
                "- take into account what the user tell's you about him and his kids"
            )
        },
        {
            "role": "user",
            "content": (
                f"City: {city_name}\n"
                f"Weather: {weather_info}\n"
                f"Attractions: {attractions_list}\n"
                f"User profile: {user_profile}\n\n"
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