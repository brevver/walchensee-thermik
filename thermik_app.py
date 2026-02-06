import streamlit as st
import streamlit.components.v1 as components
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
import plotly.graph_objects as go

# --- 1. KONFIGURATION & HEADER ---
st.set_page_config(page_title="Walchensee Thermik", page_icon="🏄‍♂️", layout="centered")
st.title("🏄‍♂️ Walchensee Thermik-Orakel")
st.markdown("Live-Vorhersage basierend auf Luftdruckdifferenzen (München-Innsbruck).")

# Status-Meldung für dich zum Debuggen (verschwindet, wenn alles klappt)
status_placeholder = st.empty()
status_placeholder.info("⏳ Initialisiere App...")

# --- 2. DATEN-ABRUF (BACKEND) ---
@st.cache_data(ttl=3600)
def get_weather_data():
    # Setup API
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Koordinaten (vereinfacht)
    lat_wal = 47.58
    lon_wal = 11.35
    lat_muc = 48.13
    lon_muc = 11.58
    lat_inn = 47.26
    lon_inn = 11.40
    lat_boz = 46.50
    lon_boz = 11.35

    url = "https://api.open-meteo.com/v1/forecast"
    
    # Parameter
    params = {
        "latitude": [lat_wal, lat_muc, lat_inn, lat_boz],
        "longitude": [lon_wal, lon_muc, lon_inn, lon_boz],
        "hourly": ["temperature_2m", "pressure_msl", "cloud_cover", "wind_speed_10m", "wind_direction_10m"],
        "timezone": "Europe/Berlin",
        "forecast_days": 3
    }

    responses = openmeteo.weather_api(url, params=params)

    # Helper Funktion zum Verarbeiten der API-Antwort
    def process(response, prefix):
        hourly = response.Hourly()
        
        # Zeitachse bauen
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

    # Daten verarbeiten
    df_wal = process(responses[0], "wal")
    df_muc = process(responses[1], "muc")
    df_inn = process(responses[2], "inn")
    df_boz = process(responses[3], "boz")

    # Zusammenfügen
    df = df_wal.merge(df_muc[["date", "press_muc"]], on="date")
    df = df.merge(df_inn[["date", "press_inn"]], on="date")
    df = df.merge(df_boz[["date", "press_boz"]], on="date")
    return df

# --- 3. BERECHNUNG (LOGIK) ---
def calculate_thermik_score(row):
    score = 0
    
    # Werte auslesen
    p_muc = row["press_muc"]
    p_inn = row["press_inn"]
    p_boz = row["press_boz"]
    cloud = row["cloud_wal"]
    temp = row["temp_wal"]
    wind_dir = row["dir_wal"]

    # 1. Delta Nord
    delta_nord = p_muc - p_inn
    if delta_nord > 2.0:
        score += 40
    elif delta_nord > 0.5:
        score += 20
    
    # 2. Sonne
    if cloud < 30:
        score += 30
    elif cloud < 60:
        score += 15
    
    # 3. Temperatur
    if temp > 20:
        score += 10
    elif temp < 14:
        score -= 20
    
    # 4. Windrichtung
    if wind_dir > 100:
        if wind_dir < 260:
            score
