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
    if (wd > 100) and (wd < 260): score -= 20
    # Föhn
    if (row["press_boz"] - row["press_inn"]) > 3.0: return 0
    return max(0, min(100, score))

# --- MAIN EXECUTION ---
# Wir entfernen hier das 'try', um Einrückungsfehler zu vermeiden
with st.spinner('Lade Wetterdaten...'):
    df = get_weather_data()
    
df["score"] = df.apply(calculate_thermik_score, axis=1)
df["delta_nord"] = df["press_muc"] - df["press_inn"]

days = df["date"].dt.date.unique()[:3]
tabs = st.tabs(["Heute", "Morgen", "Übermorgen"])

for i, day in enumerate(days):
    with tabs[i]:
        daily_data = df[df["date"].dt.date == day]
        
        # Filter Tag
        mask = (daily_data["date"].dt.hour >= 11) & (daily_data["date"].dt.hour <= 17)
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
            if max_score >= 70: st.success(f"## ✅ GO!\nScore: {int(max_score)}")
            elif max_score >= 50: st.warning(f"## ⚠️ JEIN\nScore: {int(max_score)}")
            else: st.error(f"## 🛑 NOPE\nScore: {int(max_score)}")
        
        with c2: st.metric("Delta (MUC-INN)", f"{avg_delta:.1f} hPa")
        with c3: st.metric("Max Temp", f"{max_temp:.1f} °C")
        
        st.divider()

        # Chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily_data["date"], y=daily_data["score"], 
            mode='lines+markers', name='Score', line=dict(color='#00CC96', width=3)))
        fig.add_trace(go.Scatter(x=daily_data["date"], y=daily_data["delta_nord"], 
            mode='lines', name='Druck', line=dict(color='#636EFA', width=2, dash='dot'), yaxis="y2"))
        
        fig.update_layout(height=300, margin=dict(t=30, b=10, l=10, r=10),
            yaxis=dict(title="Score", range=[0, 105]),
            yaxis2=dict(title="hPa", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

# --- WEBCAM & FOOTER ---
st.markdown("---")
with st.expander("📸 Live-Webcam (Addicted Sports)", expanded=False):
    st.write("Check den Wind:")
    components.iframe("https://www.addicted-sports.com/webcam/walchensee/urfeld/", height=500, scrolling=True)

st.markdown("---")
with st.expander("⚖️ Rechtliches (Impressum & Datenschutz)", expanded=False):
    st.markdown("""
    **Haftungsausschluss:** Dies ist ein privates Hobby-Projekt. Nutzung auf eigene Gefahr. Keine Gewähr für die Richtigkeit der Wetterdaten.
    
    **Datenschutz:** Durch das Laden der Webcam werden Daten an addicted-sports.com übertragen. Hosting via Streamlit Cloud.
    """)
