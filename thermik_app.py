import streamlit as st
import streamlit.components.v1 as components
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
import plotly.graph_objects as go

# --- CONFIG ---
st.set_page_config(page_title="Walchensee Thermik", page_icon="🏄‍♂️", layout="centered")
st.title("🏄‍♂️ Walchensee Thermik-Orakel")
st.markdown("Live-Vorhersage basierend auf Luftdruckdifferenzen (München-Innsbruck).")

# --- CACHING & BACKEND ---
@st.cache_data(ttl=3600)
def get_weather_data():
    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    coords = {
        "Walchensee": {"lat": 47.58, "lon": 11.35},
        "Muenchen":   {"lat": 48.13, "lon": 11.58},
        "Innsbruck":  {"lat": 47.26, "lon": 11.40},
        "Bozen":      {"lat": 46.50, "lon": 11.35}
    }

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": [coords["Walchensee"]["lat"], coords["Muenchen"]["lat"], 
                     coords["Innsbruck"]["lat"], coords["Bozen"]["lat"]],
        "longitude": [coords["Walchensee"]["lon"], coords["Muenchen"]["lon"], 
                      coords["Innsbruck"]["lon"], coords["Bozen"]["lon"]],
        "hourly": ["temperature_2m", "pressure_msl", "cloud_cover", 
                   "wind_speed_10m", "wind_direction_10m"],
        "timezone": "Europe/Berlin",
        "forecast_days": 3
    }

    responses = openmeteo.weather_api(url, params=params)

    def process(response, prefix):
        hourly = response.Hourly()
        data = {"date": pd.date_range(
            start = pd.to_datetime(hourly.Time(), unit = "s", utc = True),
            end = pd.to_datetime(hourly.TimeEnd(), unit = "s", utc = True),
            freq = pd.Timedelta(seconds = hourly.Interval()),
            inclusive = "left"
        )}
        data[f"temp_{prefix}"] = hourly.Variables(0).ValuesAsNumpy()
        data[f"press_{prefix}"] = hourly.Variables(1).ValuesAsNumpy()
        data[f"cloud_{prefix}"] = hourly.Variables(2).ValuesAsNumpy()
        data[f"wind_{prefix}"] = hourly.Variables(3).ValuesAsNumpy()
        data[f"dir_{prefix}"] = hourly.Variables(4).ValuesAsNumpy()
        
        df = pd.DataFrame(data)
        df["date"] = df["date"].dt.tz_convert("Europe/Berlin")
        return df

    df_wal = process(responses[0], "wal")
    df_muc = process(responses[1], "muc")
    df_inn = process(responses[2], "inn")
    df_boz = process(responses[3], "boz")

    df = df_wal.merge(df_muc[["date", "press_muc"]], on="date")
    df = df.merge(df_inn[["date", "press_inn"]], on="date")
    df = df.merge(df_boz[["date", "press_boz"]], on="date")
    return df

def calculate_thermik_score(row):
    score = 0
    # Delta Nord
    delta_nord = row["press_muc"] - row["press_inn"]
    if delta_nord > 2.0: score += 40
    elif delta_nord > 0.5: score += 20
    # Sonne
    if row["cloud_wal"] < 30: score += 30
    elif row["cloud_wal"] < 60: score += 15
    # Temperatur
    if row["temp_wal"] > 20: score += 10
    elif row["temp_wal"] < 14: score -= 20
    # Windrichtung
    wd = row["dir_wal"]
    if (
