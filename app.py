import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import sqlite3

# ——— DATABASE ———
conn = sqlite3.connect("weight_tracker.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS weights 
             (user TEXT, date TEXT, weight REAL, PRIMARY KEY (user, date))''')
conn.commit()

st.set_page_config(page_title="Weight Duel", layout="centered")
st.title("Weight Duel – Matthew vs Jasmine")

# ——— AUTO-SELECT USER FROM URL (WORKS PERFECTLY) ———
params = st.query_params.to_dict()
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_index = 0 if params["user"] == "Matthew" else 1
    user = st.sidebar.selectbox(
        "Who am I?",
        options=["Matthew", "Jasmine"],
        index=default_index,
        key="user_select"
    )
else:
    user = st.sidebar.selectbox(
        "Who am I?",
        options=["Matthew", "Jasmine"],
        index=0,
        key="user_select"
    )

starting_weights = {"Matthew": 160.0, "Jasmine": 130.0}

# ——— LOG WEIGHT ———
st.header(f"{user}'s Log")
date = st.date_input("Date", value=datetime.now().date())
weight = st.number_input("Weight (lbs)", min_value=50.0, max_value=500.0, step=0.1)

if st.button("Log / Overwrite Weight"):
    c.execute("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)",
              (user, date.strftime("%Y-%m-%d"), weight))
    conn.commit()
    st.success(f"{user}: {weight} lbs logged for {date.strftime('%Y-%m-%d')}!")
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if not df.empty:
    df['date'] = pd.to_datetime(df['date'])

if df.empty:
    st.info("No data yet — start logging!")
    st.stop()

# ——— STATS ———
def get_stats(user_df, start):
    if user_df.empty: return {"latest":"—","change":"—","pct":"—","rate":"—","streak":0}
    user_df = user_df.sort_values('date')
    latest = user_df['weight'].iloc[-1]
    change = latest - start
    pct = round(change/start*100, 2)
    recent = user_df[user_df['date'] > pd.Timestamp.now() - pd.Timedelta(days=14)]
    rate = 0
    if len(recent) >= 2:
        days = (recent['date'].iloc[-1] - recent['date'].iloc[0]).days
        rate = round((latest - recent['weight'].iloc[0]) * 7 / days, 2) if days > 0 else 0
    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df['date'].iloc[i+1] - user_df['date'].iloc[i]).days == 1:
            streak += 1
        else: break
    return {"latest":latest, "change":f"{change:+.1f}", "pct":f"{pct:+.1f}%", "rate":rate, "streak":streak}

matt = df[df['user'] == "Matthew"]
jas  = df[df['user'] == "Jasmine"]
m = get_stats(matt, starting_weights["Matthew"])
j = get_stats(jas , starting_weights["Jasmine"])

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

# ——— BACKUP BUTTON ———
st.markdown("---")
st.subheader("Never lose your data")
csv = df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="Download full backup CSV",
    data=csv,
    file_name=f"weight_duel_backup_{datetime.now().strftime('%Y-%m-%d')}.csv",
    mime="text/csv"
)
