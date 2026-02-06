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
    
    return df

def calc_score(row):
    score = 0
    p_muc = row.get("press_muc", 0)
    p_inn = row.get("press_inn", 0)
    p_boz = row.get("press_boz", 0)
    cloud = row.get("cloud_wal", 100)
    temp = row.get("temp_wal", 0)
    wd = row.get("dir_wal", 0)

    delta = p_muc - p_inn
    
    if delta > 2.0: score += 40
    elif delta > 0.5: score += 20
    
    if cloud < 30: score += 30
    elif cloud < 60: score += 15
    
    if temp > 20: score += 10
    elif temp < 14: score -= 20
    
    if wd > 100 and wd < 260: score -= 20
            
    if (p_boz - p_inn) > 3.0: return 0
        
    return max(0, min(100, score))

# --- MAIN APP ---

# 1. VORHERSAGE
try:
    status.info("📡 Lade Wettervorhersage...")
    
    df = fetch_and_merge("https://api.open-meteo.com/v1/forecast", forecast_days=3, timeout=10)
    
    df["score"] = df.apply(calc_score, axis=1)
    df["delta"] = df["press_muc"] - df["press_inn"]
    
    status.empty()
    
    # HIER WAR DER FEHLER - JETZT SICHER:
    # Wir holen erst alle Datums-Objekte
    all_dates = df["date"].dt.date
    # Dann machen wir sie einzigartig
    unique_dates = all_dates.unique()
    # Und nehmen die ersten 3
    days = unique_dates[:3]

    tabs = st.tabs(["Heute", "Morgen", "Übermorgen"])

    for i, day in enumerate(days):
        with tabs[i]:
            daily = df[df["date"].dt.date == day]
            h = daily["date"].dt.hour
            daytime = daily[(h >= 11) & (h <= 17)]
            
            if daytime.empty:
                st.info("Keine Tagesdaten.")
                continue

            max_s = daytime["score"].max()
            avg_d = daytime["delta"].mean()
            max_t = daytime["temp_wal"].max()
            
            # Ampel
            st.markdown("### Prognose")
            c1, c2, c3 = st.columns(3)
            with c1:
                s_val = int(max_s)
                if max_s >= 70: st.success(f"## ✅ GO!\nScore: {s_val}")
                elif max_s >= 50: st.warning(f"## ⚠️ JEIN\nScore: {s_val}")
                else: st.error(f"## 🛑 NOPE\nScore: {s_val}")
                
            with c2: st.metric("Delta (MUC-INN)", f"{avg_d:.1f} hPa")
            with c3: st.metric("Max Temp", f"{max_t:.1f} °C")
            
            st.divider()
            
            # Chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily["date"], y=daily["score"], mode='lines+markers', name='Score', line=dict(color='#00CC96', width=3)))
            fig.add_trace(go.Scatter(x=daily["date"], y=daily["delta"], mode='lines', name='Druck', line=dict(color='#636EFA', width=2, dash='dot'), yaxis="y2"))
            fig.update_layout(height=300, margin=dict(t=30, b=10, l=10, r=10), yaxis=dict(title="Score", range=[0, 105]), yaxis2=dict(title="hPa", overlaying="y", side="right"), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Fehler bei Vorhersage: {e}")


# 2. HISTORIE (180 TAGE)
st.markdown("---")
hist_placeholder = st.empty()
hist_placeholder.text("⏳ Lade Statistik der letzten 180 Tage (kann dauern)...")

try:
    today = date.today()
    end_d = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    start_d = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    
    # Timeout 45s
    df_hist = fetch_and_merge("https://archive-api.open-meteo.com/v1/archive", start_date=start_d, end_date=end_d, timeout=45)
    
    df_hist["score"] = df_hist.apply(calc_score, axis=1)
    
    # Filter
    h_hist = df_hist["date"].dt.hour
    daytime_hist = df_hist[(h_hist >= 11) & (h_hist <= 17)]
    
    # Gute Stunden
    good_hours = daytime_hist[daytime_hist["score"] >= 70]
    
    if not good_hours.empty:
        # Einzigartige Tage
        unique_days = good_hours["date"].dt.date.unique()
        
        # Sortieren & Top 3
        # Um sicherzugehen: erst in Liste wandeln, dann sortieren
        days_list = list(unique_days)
        days_list.sort(reverse=True)
        top_3 = days_list[:3]
        
        # Text bauen
        dates_str = [d.strftime('%d.%m.%Y') for d in top_3]
        result_text = ", ".join(dates_str)
        
        hist_placeholder.info(f"🏆 Die letzten Top-Tage (Score > 70): **{result_text}**")
    else:
        hist_placeholder.info("❄️ Keine perfekten Bedingungen in den letzten 180 Tagen.")
        
except Exception as e:
    hist_placeholder.caption(f"Historie konnte nicht geladen werden.")


# 3. FOOTER
with st.expander("📸 Live-Webcam", expanded=False):
    components.iframe("https://www.addicted-sports.com/webcam/walchensee/urfeld/", height=500, scrolling=True)

with st.expander("ℹ️ Algorithmus", expanded=False):
    st.markdown("Score: Druck (MUC-INN), Sonne, Temp, Windrichtung.")

with st.expander("⚖️ Rechtliches", expanded=False):
    st.markdown("Hobby-Projekt. Nutzung auf eigene Gefahr.")
