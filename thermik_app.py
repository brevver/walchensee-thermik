import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

# --- CONFIG ---
st.set_page_config(page_title="Walchensee Thermik", page_icon="🏄‍♂️", layout="centered")
st.title("🏄‍♂️ Walchensee Thermik-Orakel")
st.markdown("Live-Vorhersage basierend auf Luftdruckdifferenzen (München-Innsbruck).")

# Status-Box
status = st.empty()
status.info("🚀 App startet...")

# --- LOGIK ---
COORDS = {
    "Walchensee": {"lat": 47.58, "lon": 11.35},
    "Muenchen":   {"lat": 48.13, "lon": 11.58},
    "Innsbruck":  {"lat": 47.26, "lon": 11.40},
    "Bozen":      {"lat": 46.50, "lon": 11.35}
}

def get_json_data(url, params):
    """Einfache JSON Abfrage"""
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def process_single_loc(data_json, prefix):
    """Wandelt JSON Antwort in DataFrame"""
    hourly = data_json.get("hourly", {})
    
    # Zeitachse
    times = pd.to_datetime(hourly.get("time", []), utc=True)
    
    df = pd.DataFrame({"date": times})
    
    # Variablen zuordnen
    if "temperature_2m" in hourly:
        df[f"temp_{prefix}"] = hourly["temperature_2m"]
    if "pressure_msl" in hourly:
        df[f"press_{prefix}"] = hourly["pressure_msl"]
    if "cloud_cover" in hourly:
        df[f"cloud_{prefix}"] = hourly["cloud_cover"]
    if "wind_speed_10m" in hourly:
        df[f"wind_{prefix}"] = hourly["wind_speed_10m"]
    if "wind_direction_10m" in hourly:
        df[f"dir_{prefix}"] = hourly["wind_direction_10m"]
        
    # Zeitzone anpassen
    if not df.empty:
        df["date"] = df["date"].dt.tz_convert("Europe/Berlin")
        
    return df

def fetch_and_merge(base_url, start_date=None, end_date=None, forecast_days=None):
    # Parameter bauen
    params = {
        "latitude": [COORDS["Walchensee"]["lat"], COORDS["Muenchen"]["lat"], COORDS["Innsbruck"]["lat"], COORDS["Bozen"]["lat"]],
        "longitude": [COORDS["Walchensee"]["lon"], COORDS["Muenchen"]["lon"], COORDS["Innsbruck"]["lon"], COORDS["Bozen"]["lon"]],
        "hourly": "temperature_2m,pressure_msl,cloud_cover,wind_speed_10m,wind_direction_10m",
        "timezone": "Europe/Berlin"
    }
    
    if forecast_days:
        params["forecast_days"] = forecast_days
    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date
        
    # Abfrage
    resp = get_json_data(base_url, params)
    
    # Einzeln verarbeiten
    df_wal = process_single_loc(resp[0], "wal")
    df_muc = process_single_loc(resp[1], "muc")
    df_inn = process_single_loc(resp[2], "inn")
    df_boz = process_single_loc(resp[3], "boz")
    
    # Mergen
    df = df_wal.merge(df_muc[["date", "press_muc"]], on="date")
    df = df.merge(df_inn[["date", "press_inn"]], on="date")
    df = df.merge(df_boz[["date", "press_boz"]], on="date")
    
    return df

def calc_score(row):
    score = 0
    # Werte holen (Fallback 0)
    p_muc = row.get("press_muc", 0)
    p_inn = row.get("press_inn", 0)
    p_boz = row.get("press_boz", 0)
    cloud = row.get("cloud_wal", 100)
    temp = row.get("temp_wal", 0)
    wd = row.get("dir_wal", 0)

    delta = p_muc - p_inn
    
    # 1. Delta
    if delta > 2.0: score += 40
    elif delta > 0.5: score += 20
    
    # 2. Sonne
    if cloud < 30: score += 30
    elif cloud < 60: score += 15
    
    # 3. Temp
    if temp > 20: score
