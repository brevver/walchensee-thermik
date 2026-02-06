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

# Debug-Status
debug_box = st.empty()
debug_box.info("⚙️ System startet...")

# --- 2. API CLIENT (OHNE DATEI-CACHE) ---
# Wir nutzen eine normale Session ohne Schreibzugriff auf die Festplatte
http_session = requests.Session() 
openmeteo = openmeteo_requests.Client(session=http_session)

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
    
    # 4. Windrichtung
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
    df2 = process_response_to_df(responses[1], "muc")
    df3 = process_response_to_df(responses[2], "inn")
    df4 = process_response_to_df(responses[3], "boz")

    df = df1.merge(df2[["date", "press_muc"]], on="date")
    df = df.merge(df3[["date", "press_inn"]], on="date")
    df = df.merge(df4[["date", "press_boz"]], on="date")
    return df

@st.cache_data(ttl=3600)
def get_history_check():
    # Wir nehmen Daten bis vor 5 Tagen
    end_date = date.today() - timedelta(days=5)
    start_date = end_date - timedelta(days=90)
    
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": [COORDS["Walchensee"]["lat"], COORDS["Muenchen"]["lat"], COORDS["Innsbruck"]["lat"], COORDS["Bozen"]["lat"]],
        "longitude": [COORDS["Walchensee"]["lon"], COORDS["Muenchen"]["lon"], COORDS["Innsbruck"]["lon"], COORDS["Bozen"]["lon"]],
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "hourly": ["temperature_2m", "pressure_msl", "cloud_cover", "wind_speed_10m", "wind_direction_10m"],
        "timezone": "Europe/Berlin"
    }
    
    try:
        responses = openmeteo.weather_api(url, params=params)
        df1 = process_response_to_df(responses[0], "wal")
        df2 = process_response_to_df(responses[1], "muc")
        df3 = process_response_to_df(responses[2], "inn")
        df4 = process_response_to_df(responses[3], "boz")

        df = df1.merge(df2[["date", "press_muc"]], on="date")
        df = df.merge(df3[["date", "press_inn"]], on="date")
        df = df.merge(df4[["date", "press_boz"]], on="date")
        
        df["score"] = df.apply(calculate_thermik_score, axis=1)
        
        # Nur 11-17 Uhr prüfen
        hour = df["date"].dt.hour
        df_day = df[(hour >= 11) & (hour <= 17)]
        
        # Suche Tage > 70 Score
        good_days = df_day[df_day["score"] >= 70]
        
        if not good_days.empty:
            return good_days["date"].max() # Neuestes Datum
        return None
        
    except Exception as e:
        return None

# --- 5. EXECUTION ---

# Schritt A: Historie
debug_box.info("📚 Lade Historie (letzte 90 Tage)...")
last_good = get_history_check()

if last_good:
    st.info(f"🏆 Letzter perfekter Tag (Score > 70): **{last_good.strftime('%d.%m
