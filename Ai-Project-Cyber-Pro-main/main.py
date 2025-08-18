from __future__ import annotations


# main.py
from ai import get_ai_response
from core import get_weather, getActivities  # ← מייבא מהלוגיקה

def run_questionnaire():
    print("=== Trip Recommendation Questionnaire ===")
    city_name = input("📍 Which city are you in or planning to visit? ").strip()
    weather_info = get_weather(city_name)
    attractions_list = getActivities(city_name)

    print("\n👤 A few details about you:")
    has_children = input("Do you have children? (y/n): ").strip().lower()
    children_count = 0
    if has_children == "y":
        try:
            children_count = int(input("How many children? ").strip())
        except ValueError:
            print("⚠ Invalid number, saved as 0.")
    hobbies = input("What are your hobbies or preferred activities ? ... ").strip()

    user_profile = {
        "has_children": (has_children == "y"),
        "children_count": children_count,
        "hobbies": hobbies,
    }
    return city_name, weather_info, attractions_list, user_profile

if __name__ == "__main__":
    city_name, weather_info, attractions_list, user_profile = run_questionnaire()
    print(get_ai_response(city_name, weather_info, attractions_list, user_profile))
