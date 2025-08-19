# # main.py
# import pythoncom
# pythoncom.CoInitialize()  # חייב להיות הכי מוקדם שאפשר: לפני כל import שמערב COM

from app_gui import App

if __name__ == "__main__":
    App().mainloop()