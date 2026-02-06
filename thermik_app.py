import streamlit as st
import streamlit.components.v1 as components
import openmeteo_requests
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Walchensee Thermik", page_icon="🏄‍♂️", layout="centered")
st.title("🏄‍♂️ Walchensee Thermik-Orakel")
st.markdown("Live-Vorhersage basierend auf Luftdruckdifferenzen (München-Innsbruck).")

# --- 2. API CLIENT (Speicher-Cache statt Datei-Cache) ---
http_session = requests.Session() 
openmeteo = openmeteo_requests.Client(session=http_session)

COORDS = {
    "Walchensee": {"lat": 47.58, "lon": 11.35},
    "Muenchen":   {"lat": 48.13, "lon": 11.58},
    "Innsbruck":  {"lat": 47.26, "lon": 11.40},
    "Bozen":      {"lat": 46.50, "lon": 11.35}
}

# --- 3. HELFER & LOGIK ---
def process_data(response, prefix):
    hourly = response.Hourly()
    start = pd.to_datetime(hourly.Time(), unit = "s", utc = True)
    end = pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True)
    
    # Zeitreihe erstellen
    freq = pd.Timedelta(seconds=hourly.Interval())
    time_range = pd.date_range(start=start, end=end, freq=freq, inclusive="left")
    
    data = {"date": time_range}
    data[f"temp_{prefix}"] = hourly.Variables(0).ValuesAsNumpy()
    data[f"press_{prefix}"] = hourly.Variables(1).ValuesAsNumpy()
    data[f"cloud_{prefix}"] = hourly.Variables(2).ValuesAsNumpy()
    data[f"wind_{prefix}"] = hourly.Variables(3).ValuesAsNumpy()
    data[f"dir_{prefix}"] = hourly.Variables(4).ValuesAsNumpy()
    
    df = pd.DataFrame(data)
    df["date"] = df["date"].dt.tz_convert("Europe/Berlin")
    return df
