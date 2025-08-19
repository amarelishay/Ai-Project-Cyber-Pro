# 🗺️ AI Attractions GUI

**AI Attractions GUI** is a Python project that provides personalized recommendations for attractions and restaurants in a chosen city, with an interactive map and AI-generated trip summaries.  

It integrates **OpenStreetMap** (via OSMnx) for attractions data and a **Weather API** for real-time weather conditions, which are used to tailor recommendations.

## ✨ Features
- **Graphical User Interface** (Tkinter + WebView).
- **User input**: city name, interests (food, culture, nature, etc.), personal details (e.g., traveling with children).
- **Data collection**:
  - Attractions from **OpenStreetMap** using OSMnx (Overpass QL).
  - Real-time weather from an external **Weather API**.
- **Data processing**: build a DataFrame with attraction details (name, category, latitude, longitude).
- **Interactive Folium map**:
  - Numbered markers according to the itinerary order.
  - Colored circles for each stop.
  - PolyLine connecting the points.
  - Automatic fit-bounds to show all stops clearly.
- **AI integration** for recommendations:
  - Select attractions most suitable for the given user profile.
  - Filter by **current weather conditions** (temperature, sunny/rainy, etc.).
  - Prioritize popular/well-known attractions from the input data.
  - Explain *why* each recommendation matches the profile.
- **Progress bar** in the GUI showing each pipeline step (query → fetch data → build DataFrame → create map → AI response).

## 📂 Project Structure
AI-Attractions-GUI/
│
├── app_gui.py # GUI (Tkinter + WebView)
├── core.py # Core logic: data fetching, filtering, mapping, AI calls
├── utils.py # Helper functions (JSON parsing, DataFrame conversion, etc.)
├── requirements.txt # Required dependencies
└── README.md # Project documentation

bash
Copy
Edit

## 🛠️ Installation & Usage

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd AI-Attractions-GUI
Create a virtual environment and install dependencies:

bash
Copy
Edit
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
pip install -r requirements.txt
Set up environment variables:
Create a .env file in the project root with:

env
Copy
Edit
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4o-mini
WEATHER_API_KEY=your_weather_api_key_here
WEATHER_API_URL=https://api.weatherapi.com/v1/current.json
Run the application:

bash
Copy
Edit
python app_gui.py
⚙️ Main Dependencies
Tkinter – GUI framework.

Folium – interactive maps.

OSMnx – queries to OpenStreetMap (Overpass QL).

Pandas – data processing.

OpenAI – AI-based recommendations.

Weather API – fetch live temperature and conditions for tailoring results.

🚀 Future Improvements
Enhanced GUI (tabs, loading screens).

Save and reload user search history.

Itinerary planning by travel time (not only distance).

Integration with additional real-time APIs (ratings, reviews, opening hours).
