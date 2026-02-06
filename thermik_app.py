import streamlit as st
import streamlit.components.v1 as components
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
import plotly.graph_objects as go
from datetime import date, timedelta

# --- 1. SETUP ---
st.set_page_config(page_title="Walchensee Thermik", page_icon="🏄‍♂️", layout="centered")
st.title("🏄‍♂️ Walchensee Thermik-Orakel")
st.markdown("Live-Vorhersage basierend auf Luftdruckdifferenzen (München-Innsbruck).")

# Debug-Status (damit wir sehen, was passiert)
debug_box = st.empty()
debug_box.info("⚙️ System startet...")

# --- 2. API CLIENT ---
cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)

# Koordinaten
COORDS = {
    "Walchensee": {"lat": 47.58, "lon": 11.35},
    "Muenchen":   {"lat": 48.13, "lon": 11.58},
    "Innsbruck":  {"lat": 47.26, "lon": 11.40},
    "Bozen":      {"lat": 46.50, "lon": 11.35}
}

# --- 3. LOGIK ---
def process_response_to_df(response, prefix):
    hourly = response.Hourly()
    start = pd.to_datetime(hourly.Time(), unit = "s", utc = True)
    end = pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True)
    interval = hourly.Interval()
    
    time_range = pd.date_range(start=start, end=end, freq=pd.Timedelta(seconds=interval), inclusive="left")
    
    data = {"date": time_range}
    data[f"temp_{prefix}"] = hourly.Variables(0).ValuesAsNumpy()
    data[f"press_{prefix}"] = hourly.Variables(1).ValuesAsNumpy()
    data[f"cloud_{prefix}"] = hourly.Variables(2).ValuesAsNumpy()
    data[f"wind_{prefix}"] = hourly.Variables(3).ValuesAsNumpy()
    data[f"dir_{prefix}"] = hourly.Variables(4).ValuesAsNumpy()
    
    df = pd.DataFrame(data)
    df["date"] = df["date"].dt.tz_convert("Europe/Berlin")
    return df

def calculate_thermik_score(row):
    score = 0
    p_muc = row["press_muc"]
    p_inn = row["press_inn"]
    p_boz = row["press_boz"]
    cloud = row["cloud_wal"]
    temp = row["temp_wal"]
    wd = row["dir_wal"]

    # 1. Delta Nord
    delta = p_muc - p_inn
    if delta > 2.0: score += 40
    elif delta > 0.5: score += 20
    
    # 2. Sonne
    if cloud < 30: score += 30
    elif cloud < 60: score += 15
    
    # 3. Temperatur
    if temp > 20: score += 10
    elif temp < 14: score -= 20
    
    # 4. Windrichtung (Süd/West penalty)
    if wd > 100 and wd < 260: score -= 20
            
    # 5. Foehn Killer
    if (p_boz - p_inn) > 3.0: return 0
        
    return max(0, min(100, score))

# --- 4. DATEN ABRUFEN ---

@st.cache_data(ttl=3600)
def get_forecast():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": [COORDS["Walchensee"]["lat"], COORDS["Muenchen"]["lat"], COORDS["Innsbruck"]["lat"], COORDS["Bozen"]["lat"]],
        "longitude": [COORDS["Walchensee"]["lon"], COORDS["Muenchen"]["lon"], COORDS["Innsbruck"]["lon"], COORDS["Bozen"]["lon"]],
        "hourly": ["temperature_2m", "pressure_msl", "cloud_cover", "wind_speed_10m", "wind_direction_10m"],
        "timezone": "Europe/Berlin",
        "forecast_days": 3
    }
    responses = openmeteo.weather_api(url, params=params)
    
    df1 = process_response_to_df(responses[0], "wal")
    df2
