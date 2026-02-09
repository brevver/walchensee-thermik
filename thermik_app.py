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

status = st.empty()
status.info("🚀 App startet...")

# --- LOGIK ---
COORDS = {
    "Walchensee": {"lat": 47.58, "lon": 11.35},
    "Muenchen":   {"lat": 48.13, "lon": 11.58},
    "Innsbruck":  {"lat": 47.26, "lon": 11.40},
    "Bozen":      {"lat": 46.50, "lon": 11.35}
}

def get_json_data(url, params, timeout_val=10):
    r = requests.get(url, params=params, timeout=timeout_val)
    r.raise_for_status()
    return r.json()

def process_single_loc(data_json, prefix):
    hourly = data_json.get("hourly", {})
    times = pd.to_datetime(hourly.get("time", []), utc=True)
    df = pd.DataFrame({"date": times})
    
    mapping = {
        "temperature_2m": f"temp_{prefix}",
        "pressure_msl": f"press_{prefix}",
        "cloud_cover": f"cloud_{prefix}",
        "wind_speed_10m": f"wind_{prefix}",
        "wind_direction_10m": f"dir_{prefix}"
    }
    
    for api_name, col_name in mapping.items():
        if api_name in hourly:
            df[col_name] = hourly[api_name]
            
    if not df.empty:
        df["date"] = df["date"].dt.tz_convert("Europe/Berlin")
        
    return df

def fetch_and_merge(base_url, start_date=None, end_date=None, forecast_days=None, timeout=10):
    params = {
        "latitude": [COORDS["Walchensee"]["lat"], COORDS["Muenchen"]["lat"], 
                     COORDS["Innsbruck"]["lat"], COORDS["Bozen"]["lat"]],
        "longitude": [COORDS["Walchensee"]["lon"], COORDS["Muenchen"]["lon"], 
                      COORDS["Innsbruck"]["lon"], COORDS["Bozen"]["lon"]],
        "hourly": "temperature_2m,pressure_msl,cloud_cover,wind_speed_10m,wind_direction_10m",
        "timezone": "Europe/Berlin"
    }
    
    if forecast_days:
        params["forecast_days"] = forecast_days
    if start_date and end_date:
        params["start_date"] = start_date
        params["end_date"] = end_date
        
    resp = get_json_data(base_url, params, timeout)
    
    df_wal = process_single_loc(resp[0], "wal")
    df_muc = process_single_loc(resp[1], "muc")
    df_inn = process_single_loc(resp[2], "inn")
    df_boz = process_single_loc(resp[3], "boz")
    
    df = df_wal.merge(df_muc[["date", "press_muc"]], on="date")
    df = df.merge(df_inn[["date", "press_inn"]], on="date")
    df = df.merge(df_boz[["date", "press_boz"]], on="date")
