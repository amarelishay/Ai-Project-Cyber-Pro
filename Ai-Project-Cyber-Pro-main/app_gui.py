# app_gui_threaded.py
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# ייבוא הלוגיקה שלך (התאם למסלולי הקבצים שלך)
from core import get_weather, getActivities
from ai import get_ai_response


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AI Attractions – Threaded GUI")
        self.geometry("860x560")

        # ===== Top controls =====
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="עיר:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.city_var = tk.StringVar(value="Tel Aviv")
        self.city_entry = ttk.Entry(top, textvariable=self.city_var, width=24)
        self.city_entry.grid(row=0, column=1, sticky="w")

        ttk.Label(top, text="תחביבים/העדפות:").grid(row=0, column=2, sticky="w", padx=(16, 6))
        self.hobbies_var = tk.StringVar(value="food, culture")
        self.hobbies_entry = ttk.Entry(top, textvariable=self.hobbies_var, width=28)
        self.hobbies_entry.grid(row=0, column=3, sticky="w")

        self.has_children = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="יש ילדים", variable=self.has_children).grid(row=0, column=4, padx=8)

        ttk.Label(top, text="מס' ילדים:").grid(row=0, column=5, sticky="w")
        self.children_var = tk.StringVar(value="0")
        ttk.Entry(top, textvariable=self.children_var, width=5).grid(row=0, column=6, sticky="w")

        # ===== Filters =====
        filters = ttk.LabelFrame(self, text="סינונים (רשות)", padding=8)
        filters.pack(fill="x", padx=10)

        ttk.Label(filters, text="דירוג מינימלי:").grid(row=0, column=0, sticky="w")
        self.min_rating_var = tk.StringVar(value="4.0")
        ttk.Entry(filters, textvariable=self.min_rating_var, width=6).grid(row=0, column=1, padx=(6, 12))

        ttk.Label(filters, text="תקציב:").grid(row=0, column=2, sticky="w")
        self.budget_var = tk.StringVar(value="Any")
        ttk.Combobox(filters, textvariable=self.budget_var,
                     values=["Any", "Free", "Low", "Medium", "High"],
                     width=10, state="readonly").grid(row=0, column=3)

        # ===== Buttons + Progress =====
        actions = ttk.Frame(self, padding=(10, 6))
        actions.pack(fill="x")

        self.search_btn = ttk.Button(actions, text="חפש המלצות", command=self.on_search)
        self.search_btn.pack(side="left")

        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=180)
        self.progress.pack(side="left", padx=12)

        self.status_var = tk.StringVar(value="מוכן")
        ttk.Label(actions, textvariable=self.status_var).pack(side="left", padx=12)
        # ===== AI response (free text) =====
        top_ai = ttk.LabelFrame(self, text="תשובת ה-AI", padding=8)
        top_ai.pack(fill="both", expand=False, padx=10, pady=(10, 5))
        self.ai_text = tk.Text(top_ai, height=6, wrap="word")
        self.ai_text.pack(fill="both", expand=True)
        # Enter triggers search
        self.city_entry.bind("<Return>", lambda e: self.on_search())


        # ===== Results table =====
        cols = ("name", "city", "category", "price", "rating", "lat", "lon")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14)
        headers = ["שם", "עיר", "קטגוריה", "מחיר", "דירוג", "Lat", "Lon"]
        for c, h in zip(cols, headers):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=120 if c not in ("name",) else 220, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))


    # ---------- UI helpers ----------
    def set_busy(self, busy: bool, msg: str = ""):
        if busy:
            self.search_btn.configure(state="disabled")
            self.status_var.set(msg or "מבצע חיפוש...")
            self.progress.start(12)  # מהירות סיבוב
        else:
            self.search_btn.configure(state="normal")
            self.status_var.set(msg or "מוכן")
            self.progress.stop()

    def clear_results(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.ai_text.delete("1.0", "end")

    # ---------- Button action ----------
    def on_search(self):
        city = self.city_var.get().strip()
        if not city:
            messagebox.showwarning("חסר עיר", "נא להזין עיר.")
            return

        try:
            min_rating = float(self.min_rating_var.get().strip() or 0.0)
        except ValueError:
            min_rating = 0.0

        budget = self.budget_var.get()
        hobbies = self.hobbies_var.get().strip()
        has_children = self.has_children.get()
        try:
            children_count = int(self.children_var.get().strip() or 0)
        except ValueError:
            children_count = 0

        self.clear_results()
        self.set_busy(True, "מביא נתונים...")

        # מריצים את העבודה הכבדה ב-Thread כדי שה-GUI לא ייתקע
        threading.Thread(
            target=self._do_search,
            args=(city, hobbies, has_children, children_count, budget, min_rating),
            daemon=True
        ).start()

    # ---------- Work function (runs in background thread) ----------
    def _do_search(self, city, hobbies, has_children, children_count, budget, min_rating):
        try:
            # שלב 1: מזג אוויר
            weather_info = get_weather(city)  # temp_c (float)
            # שלב 2: אטרקציות (DataFrame: name, category, lat, lon)
            df_attr = getActivities(city)

            # אפשר לצמצם/לדרג כאן לפי budget/min_rating אם יש לך מודל/לוגיקה משלך
            # לדוגמה: נשאיר הכל, ונוסיף price/rating דמו להצגה נוחה
            df = df_attr.copy()
            if "name" not in df.columns:
                df["name"] = ""
            if "category" not in df.columns:
                df["category"] = ""
            if "lat" not in df.columns:
                df["lat"] = None
            if "lon" not in df.columns:
                df["lon"] = None

            # שדות דמו כדי להמחיש (במידה ואין לך ציונים אמיתיים)
            df["price"] = "Medium"
            df["rating"] = 4.5

            # סינונים (אופציונלי)
            if budget != "Any":
                df = df[df["price"] == budget]
            try:
                df = df[df["rating"] >= float(min_rating)]
            except Exception:
                pass

            # שלב 3: פרופיל משתמש ותשובת AI
            user_profile = {
                "has_children": bool(has_children),
                "children_count": int(children_count),
                "hobbies": hobbies,
            }
            ai_msg = get_ai_response(city, weather_info, df_attr, user_profile)

            # החזרה ל-UI thread: עדכון טבלה וטקסט
            self.after(0, lambda: self._update_ui(df, ai_msg))

        except Exception as e:
            self.after(0, lambda: self._handle_error(e))

    # ---------- UI update after background completes ----------
    def _update_ui(self, df, ai_msg: str):
        try:
            # טבלה
            for _, row in df.head(200).iterrows():  # מגביל עד 200 להצגה
                self.tree.insert("", "end", values=(
                    str(row.get("name", "")),
                    self.city_var.get(),
                    str(row.get("category", "")),
                    str(row.get("price", "")),
                    str(row.get("rating", "")),
                    str(row.get("lat", "")),
                    str(row.get("lon", "")),
                ))
            # טקסט AI
            self.ai_text.insert("1.0", ai_msg if isinstance(ai_msg, str) else str(ai_msg))
        finally:
            self.set_busy(False, "הושלם")

    def _handle_error(self, err: Exception):
        self.set_busy(False, "שגיאה")
        messagebox.showerror("שגיאה", str(err))


if __name__ == "__main__":
    App().mainloop()
