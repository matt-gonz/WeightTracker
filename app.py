import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import sqlite3
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# ——— GOOGLE SHEETS BACKUP ———
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["google_credentials"], scope)
    return gspread.authorize(creds)

def append_to_google_sheet(user, date, weight):
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1
        sheet.append_row([user, date.strftime("%Y-%m-%d"), weight])
        st.success("Backed up to Google Sheets")
    except Exception as e:
        st.error(f"Backup failed: {str(e)}")

# ——— DATABASE ———
conn = sqlite3.connect("weight_tracker.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS weights 
             (user TEXT, date DATE, weight REAL, PRIMARY KEY (user, date))''')
conn.commit()

st.set_page_config(page_title="Weight Duel", layout="centered")
st.title("Weight Duel – Matthew vs Jasmine")

user = st.sidebar.selectbox("Who are you?", ["Matthew", "Jasmine"])
starting_weights = {"Matthew": 160.0, "Jasmine": 130.0}

# ——— LOG WEIGHT ———
st.header(f"{user}'s Log")
date = st.date_input("Date", value=datetime.now().date())
weight_input = st.number_input("Weight (lbs)", min_value=50.0, max_value=500.0, step=0.1)

if st.button("Log / Overwrite Weight"):
    c.execute("INSERT OR REPLACE INTO weights (user, date, weight) VALUES (?, ?, ?)",
              (user, date, weight_input))
    conn.commit()
    
    # Auto backup
    try:
        append_to_google_sheet(user, date, weight_input)
    except:
        pass  # Already handled inside function
    
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights ORDER BY date", conn)
df['date'] = pd.to_datetime(df['date'])

if df.empty:
    st.info("No data yet — start logging!")
    st.stop()

# ——— STATS ———
def get_stats(user_df, start_weight):
    if user_df.empty:
        return {"latest": "-", "change": "-", "pct": "-", "rate": "-", "streak": 0}
    user_df = user_df.sort_values('date').reset_index(drop=True)
    latest = user_df['weight'].iloc[-1]
    change = latest - start_weight
    pct = round(change / start_weight * 100, 2)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=14)
    recent = user_df[user_df['date'] > cutoff]
    rate = 0
    if len(recent) >= 2:
        days = (recent['date'].iloc[-1] - recent['date'].iloc[0]).days
        rate = round((latest - recent['weight'].iloc[0]) * 7 / days, 2) if days > 0 else 0
    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df['date'].iloc[i+1] - user_df['date'].iloc[i]).days == 1:
            streak += 1
        else:
            break
    return {"latest": latest, "change": f"{change:+.1f}", "pct": f"{pct:+.1f}%", "rate": rate, "streak": streak}

matt = df[df['user'] == "Matthew"]
jas = df[df['user'] == "Jasmine"]
matt_stats = get_stats(matt, starting_weights["Matthew"])
jas_stats = get_stats(jas, starting_weights["Jasmine"])

# ——— DISPLAY ———
st.header("Current Standings")
cols = st.columns(2)
with cols[0]:
    st.subheader("Matthew")
    st.metric("Latest", matt_stats["latest"])
    st.write(f"Change: {matt_stats['change']} lbs ({matt_stats['pct']})")
    st.write(f"14-day rate: {matt_stats['rate']} lbs/week")
    st.write(f"Streak: **{matt_stats['streak']} days**")
with cols[1]:
    st.subheader("Jasmine")
    st.metric("Latest", jas_stats["latest"])
    st.write(f"Change: {jas_stats['change']} lbs ({jas_stats['pct']})")
    st.write(f"14-day rate: {jas_stats['rate']} lbs/week")
    st.write(f"Streak: **{jas_stats['streak']} days**")

st.header("Trend Chart")
chart = alt.Chart(df).mark_line(point=True).encode(
    x='date:T', y='weight:Q', color='user:N', tooltip=['user', 'date', 'weight']
).properties(width=700, height=400).interactive()
st.altair_chart(chart, width="stretch")  # Fixed: no more warnings

st.header("Last 10 Entries")
st.dataframe(df.sort_values('date', ascending=False).head(10))
