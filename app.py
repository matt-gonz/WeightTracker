import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import sqlite3
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ——— GOOGLE SHEETS BACKUP (100% working) ———
@st.cache_resource(ttl=3600)  # Cache client for 1 hour
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["google_credentials"], scope)
    return gspread.authorize(creds)

def backup_to_google_sheet(user, date, weight):
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1
        sheet.append_row([user, date.strftime("%Y-%m-%d"), float(weight)])
        st.success("Backed up to Google Sheets")
    except Exception as e:
        st.error(f"Backup failed: {str(e)}")

# ——— DATABASE (with proper date handling) ———
conn = sqlite3.connect("weight_tracker.db", check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS weights 
             (user TEXT, date TEXT, weight REAL, PRIMARY KEY (user, date))''')
conn.commit()

st.set_page_config(page_title="Weight Duel", layout="centered")
st.title("Weight Duel – Matthew vs Jasmine")

user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"])
starting_weights = {"Matthew": 160.0, "Jasmine": 130.0}

# ——— LOG WEIGHT ———
st.header(f"{user}'s Log")
date = st.date_input("Date", value=datetime.now().date())
weight = st.number_input("Weight (lbs)", min_value=50.0, max_value=500.0, step=0.1)

if st.button("Log / Overwrite Weight"):
    date_str = date.strftime("%Y-%m-%d")
    c.execute("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)", (user, date_str, weight))
    conn.commit()
    
    # Auto backup
    backup_to_google_sheet(user, date, weight)
    
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if df.empty:
    st.info("No data yet — start logging!")
    st.stop()

df['date'] = pd.to_datetime(df['date'])

# ——— STATS ———
def get_stats(df_user, start):
    if df_user.empty: return {"latest":"—", "change":"—", "pct":"—", "rate":"—", "streak":0}
    df_user = df_user.sort_values('date')
    latest = df_user['weight'].iloc[-1]
    change = latest - start
    pct = round(change/start*100, 2)
    recent = df_user[df_user['date'] > pd.Timestamp.now() - pd.Timedelta(days=14)]
    rate = 0
    if len(recent) >= 2:
        days = (recent['date'].iloc[-1] - recent['date'].iloc[0]).days
        rate = round((latest - recent['weight'].iloc[0]) * 7 / days, 2) if days > 0 else 0
    streak = 1
    for i in range(len(df_user)-2, -1, -1):
        if (df_user['date'].iloc[i+1] - df_user['date'].iloc[i]).days == 1:
            streak += 1
        else:
            break
    return {"latest":latest, "change":f"{change:+.1f}", "pct":f"{pct:+.1f}%", "rate":rate, "streak":streak}

matt = df[df['user'] == "Matthew"]
jas = df[df['user'] == "Jasmine"]
m = get_stats(matt, starting_weights["Matthew"])
j = get_stats(jas, starting_weights["Jasmine"])

# ——— DISPLAY ———
st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest", m["latest"])
    st.write(f"Change: {m['change']} lbs ({m['pct']})")
    st.write(f"14-day rate: {m['rate']} lbs/week")
    st.write(f"Streak: **{m['streak']} days**")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest", j["latest"])
    st.write(f"Change: {j['change']} lbs ({j['pct']})")
    st.write(f"14-day rate: {j['rate']} lbs/week")
    st.write(f"Streak: **{j['streak']} days**")

st.header("Trend Chart")
chart = alt.Chart(df).mark_line(point=True).encode(
    x='date:T', y='weight:Q', color='user:N', tooltip=['user','date','weight']
).properties(height=400).interactive()
st.altair_chart(chart, width="stretch")

st.header("Last 10 Entries")
st.dataframe(df.sort_values('date', ascending=False).head(10)[['user','date','weight']])

