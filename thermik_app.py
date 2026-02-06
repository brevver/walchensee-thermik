import streamlit as st
import streamlit.components.v1 as components
import openmeteo_requests
import requests_cache
import pandas as pd
from retry_requests import retry
import plotly.graph_objects as go
from datetime import date, timedelta

# --- 1. KONFIGURATION & HEADER ---
st.set_page_config(page_title="Walchensee Thermik", page_icon="🏄‍♂️", layout="centered")
st.title("🏄‍♂️ Walchensee Thermik-Orakel")
st.markdown("Live-Vorhersage basierend auf Luftdruckdifferenzen (München-Innsbruck).")

# Platzhalter für Statusmeldungen
status_placeholder = st.empty()

# --- 2. API SETUP (CACHE) ---
# Wir nutzen Session-Caching für Performance
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

# --- 3. HELPER FUNKTIONEN ---
def process_api_response(response, prefix):
    """Verarbeitet die API-Antwort in ein Pandas DataFrame"""
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
    """Der Kern-Algorithmus: Berechnet Wahrscheinlichkeit 0-100"""
    score = 0
    p_muc = row["press_muc"]
    p_inn = row["press_inn"]
    p_boz = row["press_boz"]
    cloud = row["cloud_wal"]
    temp = row["temp_wal"]
    wind_dir = row["dir_wal"]

    # 1. Delta Nord
    delta_nord = p_muc - p_inn
    if delta_nord > 2.0: score += 40
    elif delta_nord > 0.5: score += 20
    
    # 2. Sonne
    if cloud < 30: score += 30
    elif cloud < 60: score += 15
    
    # 3. Temperatur
    if temp > 20: score += 10
    elif temp < 14: score -= 20
    
    # 4. Windrichtung
    if wind_dir > 100 and wind_dir < 260: score -= 20
            
    # 5. Foehn Check
    if (p_boz - p_inn) > 3.0: return 0
        
    return max(0, min(100, score))

# --- 4. DATEN ABRUFEN (LIVE & HISTORIE) ---

@st.cache_data(ttl=3600)
def get_forecast_data():
    """Holt die Vorhersage für 3 Tage"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": [COORDS["Walchensee"]["lat"], COORDS["Muenchen"]["lat"], COORDS["Innsbruck"]["lat"], COORDS["Bozen"]["lat"]],
        "longitude": [COORDS["Walchensee"]["lon"], COORDS["Muenchen"]["lon"], COORDS["Innsbruck"]["lon"], COORDS["Bozen"]["lon"]],
        "hourly": ["temperature_2m", "pressure_msl", "cloud_cover", "wind_speed_10m", "wind_direction_10m"],
        "timezone": "Europe/Berlin",
        "forecast_days": 3
    }
    responses = openmeteo.weather_api(url, params=params)
    
    df_wal = process_api_response(responses[0], "wal")
    df_muc = process_api_response(responses[1], "muc")
    df_inn = process_api_response(responses[2], "inn")
    df_boz = process_api_response(responses[3], "boz")

    df = df_wal.merge(df_muc[["date", "press_muc"]], on="date")
    df = df.merge(df_inn[["date", "press_inn"]], on="date")
    df = df.merge(df_boz[["date", "press_boz"]], on="date")
    return df

@st.cache_data(ttl=3600)
def get_last_perfect_day():
    """Sucht in den letzten 90 Tagen nach dem letzten grünen Tag"""
    # Zeitraum definieren: Gestern bis vor 90 Tagen
    end_date = date.today() - timedelta(days=1)
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
        
        # Daten verarbeiten
        df_wal = process_api_response(responses[0], "wal")
        df_muc = process_api_response(responses[1], "muc")
        df_inn = process_api_response(responses[2], "inn")
        df_boz = process_api_response(responses[3], "boz")

        df = df_wal.merge(df_muc[["date", "press_muc"]], on="date")
        df = df.merge(df_inn[["date", "press_inn"]], on="date")
        df = df.merge(df_boz[["date", "press_boz"]], on="date")
        
        # Score berechnen
        df["score"] = df.apply(calculate_thermik_score, axis=1)
        
        # Nur relevante Stunden (11-17 Uhr)
        hour = df["date"].dt.hour
        df_daytime = df[(hour >= 11) & (hour <= 17)].copy()
        
        # Filtern nach Score > 70 (Grün)
        good_days = df_daytime[df_daytime["score"] >= 70]
        
        if not good_days.empty:
            # Den allerletzten Eintrag finden
            last_date = good_days["date"].max()
            return last_date
        return None
        
    except Exception:
        return None

# --- 5. HAUPTPROGRAMM ---
def run_app():
    # A) Historie checken (läuft im Hintergrund durch Cache schnell)
    last_good_date = get_last_perfect_day()
    if last_good_date:
        formatted_date = last_good_date.strftime("%d.%m.%Y")
        st.info(f"🏆 Letzter perfekter Thermik-Tag (Score > 70): **{formatted_date}**")
    else:
        st.info("❄️ In den letzten 90 Tagen gab es keine perfekten Bedingungen.")

    # B) Vorhersage laden
    status_placeholder.text("Lade Vorhersage...")
    df = get_forecast_data()
    status_placeholder.empty() # Text löschen
    
    df["score"] = df.apply(calculate_thermik_score, axis=1)
    df["delta_nord"] = df["press_muc"] - df["press_inn"]

    # Tabs erstellen
    days = df["date"].dt.date.unique()[:3]
    tabs = st.tabs(["Heute", "Morgen", "Übermorgen"])

    for i, day in enumerate(days):
        with tabs[i]:
            daily_data = df[df["date"].dt.date == day]
            
            # Filter Tag
            hour = daily_data["date"].dt.hour
            daytime_data = daily_data[(hour >= 11) & (hour <= 17)]
            
            if daytime_data.empty:
                st.write("Keine Daten.")
                continue

            max_score = daytime_data["score"].max()
            avg_delta = daytime_data["delta_nord"].mean()
            max_temp = daytime_data["temp_wal"].max()
            
            # Ampel
            st.markdown("### Prognose")
            c1, c2, c3 = st.columns(3)
            
            with c1:
                score_int = int(max_score)
                if max_score >= 70:
                    st.success(f"## ✅ GO!\nScore: {score_int}")
                elif max_score >= 50:
                    st.warning(f"## ⚠️ JEIN\nScore: {score_int}")
                else:
                    st.error(f"## 🛑 NOPE\nScore: {score_int}")
            
            with c2: st
