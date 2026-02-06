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
            score -= 20
            
    # 5. Foehn Check
    delta_foehn = p_boz - p_inn
    if delta_foehn > 3.0:
        return 0
        
    # Ergebnis begrenzen
    final_score = max(0, score)
    final_score = min(100, final_score)
    
    return final_score

# --- 4. HAUPTPROGRAMM (MIT FEHLERSUCHE) ---

# Wir definieren eine Funktion für den Hauptteil, damit wir Fehler abfangen können
def run_app():
    status_placeholder.info("📡 Lade Wetterdaten von Open-Meteo...")
    df = get_weather_data()
    
    status_placeholder.info("🧮 Berechne Thermik-Wahrscheinlichkeiten...")
    df["score"] = df.apply(calculate_thermik_score, axis=1)
    df["delta_nord"] = df["press_muc"] - df["press_inn"]

    # Alles hat geklappt -> Status löschen
    status_placeholder.empty()

    days = df["date"].dt.date.unique()[:3]
    tabs = st.tabs(["Heute", "Morgen", "Übermorgen"])

    for i, day in enumerate(days):
        with tabs[i]:
            daily_data = df[df["date"].dt.date == day]
            
            # Filter Tag (11 bis 17 Uhr)
            hour = daily_data["date"].dt.hour
            mask = (hour >= 11) & (hour <= 17)
            daytime_data = daily_data[mask]
            
            if daytime_data.empty:
                st.info("Keine Tagesdaten.")
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
            
            with c2:
                st.metric("Delta (MUC-INN)", f"{avg_delta:.1f} hPa")
                
            with c3:
                st.metric("Max Temp", f"{max_temp:.1f} °C")
            
            st.divider()

            # Chart
            fig = go.Figure()
            
            # Linie 1: Score
            fig.add_trace(go.Scatter(
                x=daily_data["date"], 
                y=daily_data["score"], 
                mode='lines+markers', 
                name='Score', 
                line=dict(color='#00CC96', width=3)
            ))
            
            # Linie 2: Druck
            fig.add_trace(go.Scatter(
                x=daily_data["date"], 
                y=daily_data["delta_nord"], 
                mode='lines', 
                name='Druck', 
                line=dict(color='#636EFA', width=2, dash='dot'), 
                yaxis="y2"
            ))
            
            # Layout
            fig.update_layout(
                height=300, 
                margin=dict(t=30, b=10, l=10, r=10),
                yaxis=dict(title="Score", range=[0, 105]),
                yaxis2=dict(title="hPa", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.1)
            )
            
            st.plotly_chart(fig, use_container_width=True)

# --- START DER APP ---
try:
    run_app()
except Exception as e:
    st.error("❌ Es ist ein Fehler aufgetreten!")
    st.error(f"Details: {e}")
    st.warning("Tipp: Überprüfe die requirements.txt auf GitHub.")

# --- 5. WEBCAM & INFO (AUSSERHALB DER LOGIK) ---
st.markdown("---")
with st.expander("📸 Live-Webcam (Addicted Sports)", expanded=False):
    st.write("Check den Wind:")
    components.iframe("https://www.addicted-sports.com/webcam/walchensee/urfeld/", height=500, scrolling=True)

with st.expander("ℹ️ So funktioniert die Vorhersage (Algorithmus)", expanded=False):
    st.markdown("""
    ### Die Formel für den Walchensee
    Dieser Algorithmus sucht speziell nach **lokaler Thermik**, die normale Wetterapps oft übersehen.
    
    **Der Score (0-100) setzt sich so zusammen:**
    
    1. **🌪 Druckdifferenz ("Der Motor"):** Ist der Luftdruck in München höher als in Innsbruck, drückt Luft in die Alpen.
       * *Ideal:* > 2 hPa Differenz (+40 Punkte).
       
    2. **☀️ Sonne & Wolken ("Die Heizung"):**
       Die Berghänge müssen aufheizen.
       * *Ideal:* Weniger als 30% Bewölkung (+30 Punkte).
       
    3. **🌡 Temperatur ("Die Basis"):**
       Kalte Luft (< 14°C) entwickelt kaum Thermik.
       * *Ideal:* > 20°C (+10 Punkte).
       
    4. **🚫 Windrichtung ("Der Störfaktor"):**
       Grundwind aus Süd oder West stört die Thermik-Düse.
       * *Strafe:* -20 Punkte.
       
    5. **⚠️ Föhn-Check ("Der Killer"):**
       Wenn der Druck in Bozen viel höher ist als in Innsbruck, herrscht Südföhn.
       * *Folge:* Score ist sofort 0 (Föhn ist böig und keine saubere Thermik).
    """)

st.markdown("---")
with st.expander("⚖️ Rechtliches (Haftungsausschluss & Datenschutz)", expanded=False):
    st.markdown("""
    **Haftungsausschluss:** Dies ist ein privates Hobby-Projekt. Nutzung auf eigene Gefahr. Keine Gewähr für die Richtigkeit der Wetterdaten.
    
    **Datenschutz:** Durch das Laden der Webcam werden Daten an addicted-sports.com übertragen. Hosting via Streamlit Cloud.
    """)
