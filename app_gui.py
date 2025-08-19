# app_gui.py
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import webbrowser

from ai import get_ai_dictation, get_ai_response
from core import (
    get_weather, getActivities,
    geocode_city_center, select_places_from_answer,
    nearest_neighbor_itinerary, create_map,  # Folium → HTML
)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Attractions – GUI")
        self.geometry("1100x720")

        # מצב לפתיחת מפה בדפדפן
        self._last_selected_df = pd.DataFrame()
        self._last_center = (32.08, 34.78)
        self._current_map_html = None  # נתיב HTML של המפה

        # ===== Top controls =====
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="עיר:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.city_var = tk.StringVar(value="Tel Aviv")
        ttk.Entry(top, textvariable=self.city_var, width=24).grid(row=0, column=1, sticky="w")

        ttk.Label(top, text="תחביבים/העדפות:").grid(row=0, column=2, sticky="w", padx=(16, 6))
        self.hobbies_var = tk.StringVar(value="food, culture")
        ttk.Entry(top, textvariable=self.hobbies_var, width=28).grid(row=0, column=3, sticky="w")

        self.has_children = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="יש ילדים", variable=self.has_children).grid(row=0, column=4, padx=8)

        ttk.Label(top, text="מס' ילדים:").grid(row=0, column=5, sticky="w")
        self.children_var = tk.StringVar(value="0")
        ttk.Entry(top, textvariable=self.children_var, width=5).grid(row=0, column=6, sticky="w")

        # ===== Buttons + Progress =====
        actions = ttk.Frame(self, padding=(10, 6))
        actions.pack(fill="x")
        self.search_btn = ttk.Button(actions, text="חפש המלצות", command=self.on_search)
        self.search_btn.pack(side="left")

        # determinate progress (0..100)
        self.progress = ttk.Progressbar(actions, mode="determinate", length=180, maximum=100, value=0)
        self.progress.pack(side="left", padx=12)

        self.status_var = tk.StringVar(value="מוכן")
        ttk.Label(actions, textvariable=self.status_var).pack(side="left", padx=12)

        # ===== Split panes =====
        split = ttk.Panedwindow(self, orient="horizontal")
        split.pack(fill="both", expand=True, padx=10, pady=10)

        # Left: AI + table (ALL API results)
        left = ttk.Frame(split)
        split.add(left, weight=1)

        lf_ai = ttk.LabelFrame(left, text="תשובת ה-AI", padding=8)
        lf_ai.pack(fill="x", padx=0, pady=(0, 8))
        self.ai_text = tk.Text(lf_ai, height=8, wrap="word")
        self.ai_text.pack(fill="both", expand=True)

        cols = ("name", "category", "lat", "lon")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=14)
        headers = ["שם", "קטגוריה", "Lat", "Lon"]
        for c, h in zip(cols, headers):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=180 if c == "name" else 120, anchor="center")
        self.tree.pack(fill="both", expand=True)

        # Right: כפתור לפתיחת המפה בדפדפן
        right = ttk.LabelFrame(split, text="מפה (תיפתח בדפדפן)", padding=8)
        split.add(right, weight=1)

        self.open_ext_btn = ttk.Button(right, text="פתח מפה בדפדפן", command=self._open_in_browser)
        self.open_ext_btn.pack(anchor="ne")
        self.open_ext_btn.configure(state="disabled")  # יופעל לאחר יצירת המפה

        # ENTER מפעיל חיפוש
        self.bind("<Return>", lambda e: self.on_search())

    # ---------- Progress helpers ----------
    def set_progress(self, pct: int, msg: str = ""):
        """עדכון אחוז + טקסט סטטוס בצורה בטוחה ל־GUI (גם מתוך thread)."""
        def _apply():
            self.progress.configure(value=max(0, min(100, int(pct))))
            if msg:
                self.status_var.set(msg)
        self.after(0, _apply)

    # ---------- UI helpers ----------
    def set_busy(self, busy: bool, msg: str = ""):
        if busy:
            self.search_btn.configure(state="disabled")
            self.open_ext_btn.configure(state="disabled")
            self.status_var.set(msg or "מתחיל...")
            self.progress.configure(value=0)
        else:
            self.search_btn.configure(state="normal")
            # כפתור המפה יופעל רק אם יש קובץ HTML תקין (_update_ui דואג לזה)
            self.status_var.set(msg or "מוכן")

    def clear_results(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.ai_text.delete("1.0", "end")
        self._current_map_html = None
        self.open_ext_btn.configure(state="disabled")
        self.progress.configure(value=0)

    # ---------- Button action ----------
    def on_search(self):
        city = self.city_var.get().strip()
        if not city:
            messagebox.showwarning("חסר עיר", "נא להזין עיר.")
            return
        hobbies = self.hobbies_var.get().strip()
        has_children = self.has_children.get()
        try:
            children_count = int(self.children_var.get().strip() or 0)
        except ValueError:
            children_count = 0

        self.clear_results()
        self.set_busy(True, "מביא נתונים...")

        threading.Thread(
            target=self._do_search,
            args=(city, hobbies, has_children, children_count),
            daemon=True
        ).start()

    # ---------- Work function (background) ----------
    def _do_search(self, city, hobbies, has_children, children_count):
        try:
            self.set_progress(5, "מאתר מזג אוויר…")
            weather_info = get_weather(city)

            self.set_progress(15, "טוען אטרקציות מה־OSM…")
            df_attr = getActivities(
                city,
                limit=300,
                progress_callback=lambda p, m: self.set_progress(p, m)
            )   # name, category, lat, lon

            self.set_progress(60, "חושב המלצה חכמה…")
            user_profile = {
                "has_children": bool(has_children),
                "children_count": int(children_count),
                "hobbies": hobbies,
            }
            ai_msg = get_ai_response(city, weather_info, df_attr, user_profile)

            self.set_progress(75, "מחשב מרכז עיר…")
            place = get_ai_dictation(city)
            center = geocode_city_center(place)
            self._last_center = center

            self.set_progress(82, "מתאים שמות מהתשובה…")
            selected_df = select_places_from_answer(df_attr, ai_msg)
            self._last_selected_df = selected_df.copy()

            self.set_progress(88, "מסדר מסלול קצר…")
            itin_df = nearest_neighbor_itinerary(
                selected_df, center[0], center[1],
                stops=min(5, len(selected_df))
            ) if not selected_df.empty else selected_df

            self.set_progress(94, "בונה מפה אינטראקטיבית…")
            html_path = create_map(
                center,
                itin_df if not itin_df.empty else selected_df,
                out_path="itinerary_map.html"
            )
            self._current_map_html = os.path.abspath(html_path)

            self.set_progress(100, "מסיים…")
            self.after(0, lambda: self._update_ui(ai_msg, df_attr))
        except Exception as e:
            self.after(0, lambda: self._handle_error(e))

    # ---------- UI update ----------
    def _update_ui(self, ai_msg: str, api_df: pd.DataFrame):
        try:
            # טקסט ה-AI
            self.ai_text.insert("1.0", ai_msg if isinstance(ai_msg, str) else str(ai_msg))

            # טבלה: כל מה שה-API החזיר
            for _, row in api_df.iterrows():
                self.tree.insert("", "end", values=(
                    str(row.get("name", "")),
                    str(row.get("category", "")),
                    str(row.get("lat", "")),
                    str(row.get("lon", "")),
                ))

            # הפעל את כפתור "פתח בדפדפן" אם יש קובץ HTML מוכן
            if self._current_map_html and os.path.exists(self._current_map_html):
                self.open_ext_btn.configure(state="normal")
        finally:
            self.set_busy(False, "הושלם")

    def _open_in_browser(self):
        """פותח את המפה האינטראקטיבית בדפדפן חיצוני."""
        if not self._current_map_html or not os.path.exists(self._current_map_html):
            messagebox.showinfo("מפה", "אין קובץ מפה לפתוח.")
            return
        url = "file:///" + self._current_map_html.replace("\\", "/")
        webbrowser.open(url)

if __name__ == "__main__":
    App().mainloop()
