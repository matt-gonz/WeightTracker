import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import sqlite3

# ——— DATABASE ———
conn = sqlite3.connect("weight_tracker.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS weights 
             (user TEXT, date TEXT, weight REAL, PRIMARY KEY (user, date))''')
conn.commit()

st.set_page_config(page_title="Weight Duel", layout="centered")
st.title("Weight Duel – Matthew vs Jasmine")

# ——— USER SELECTION ———
params = st.query_params.to_dict()
default_user = "Matthew" if params.get("user") == "Matthew" else "Jasmine"
user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], 
                           index=0 if default_user == "Matthew" else 1)

# ——— LOG WEIGHT ———
st.header(f"{user}'s Log")
col1, col2 = st.columns([2, 1])
with col1:
    date_input = st.date_input("Date", datetime.today())
with col2:
    weight_input = st.number_input("Weight (lbs)", 50.0, 500.0, step=0.1, value=150.0)

if st.button("Log / Overwrite Weight", use_container_width=True):
    c.execute("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)",
              (user, date_input.strftime("%Y-%m-%d"), weight_input))
    conn.commit()
    st.success("Logged!")
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if df.empty:
    st.info("No data yet — start logging!")
    st.stop()

df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date")

# ——— IMPORT CSV ———
with st.expander("Import Old Data"):
    uploaded = st.file_uploader("Upload backup CSV", type="csv")
    if uploaded:
        try:
            temp = pd.read_csv(uploaded)
            cols = [c.lower().strip() for c in temp.columns]
            rename = {}
            for col in temp.columns:
                l = col.lower().strip()
                if "user" in l: rename[col] = "user"
                if "date" in l: rename[col] = "date"
                if "weight" in l: rename[col] = "weight"
            temp = temp.rename(columns=rename)[["user","date","weight"]].dropna()
            temp = temp[temp["user"].isin(["Matthew","Jasmine"])]
            temp["date"] = pd.to_datetime(temp["date"], errors="coerce")
            temp = temp.dropna()
            temp["date"] = temp["date"].dt.strftime("%Y-%m-%d")
            c.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)", temp.values.tolist())
            conn.commit()
            st.success(f"Imported {len(temp)} entries!")
            st.rerun()
        except:
            st.error("Invalid file")

# ——— TOOLTIP DATA ———
df["change"] = df.groupby("user")["weight"].diff()
df["days_gap"] = df.groupby("user")["date"].diff().dt.days
df["total_change"] = df["weight"] - df.groupby("user")["weight"].transform("first")

df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total" if pd.notna(x) else "")
df["tooltip_prev"] = df.apply(
    lambda r: f"{r['change']:+.1f} lbs in {int(r['days_gap'])} day{'' if r['days_gap']==1 else 's'}"
    if pd.notna(r['change']) else "", axis=1
)

# ——— DATE RANGE FILTER (THIS IS THE FIX) ———
st.markdown("### Trend Chart")
view = st.radio("View", ["Week", "30D", "90D", "Year", "All"], horizontal=True, index=1)

days_back = {"Week": 7, "30D": 30, "90D": 90, "Year": 365, "All": 9999}[view]
cutoff = datetime.now() - timedelta(days=days_back)
chart_df = df[df["date"] >= cutoff].copy()

if chart_df.empty:
    st.info("No data in this time range yet.")
    st.stop()

# ——— CLEAN, BEAUTIFUL CHART ———
line = alt.Chart(chart_df).mark_line(point=alt.OverlayMarkDef(size=180, filled=True)).encode(
    x=alt.X("date:T", title="Date"),
    y=alt.Y("weight:Q", title="Weight (lbs)"),
    color=alt.Color("user:N", title="Person",
                    scale=alt.Scale(domain=["Matthew", "Jasmine"],
                                    range=["#00CC96", "#FF6B6B"])),
    tooltip=[
        alt.Tooltip("user:N", title="Who"),
        alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
        alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
        alt.Tooltip("tooltip_total:N", title="Total Change"),
        alt.Tooltip("tooltip_prev:N", title="Since Last")
    ]
).properties(
    height=480
).interactive()

st.altair_chart(line, use_container_width=True)

# ——— STATS ———
def stats(user_df):
    if user_df.empty: return {"latest":"—", "change":"—", "pct":"—", "rate":0, "streak":0}
    user_df = user_df.sort_values("date")
    start = user_df.iloc[0]["weight"]
    latest = user_df.iloc[-1]["weight"]
    change = latest - start
    pct = change / start * 100
    rate = 0
    if len(user_df) >= 14:
        w14 = user_df.iloc[-14]["weight"]
        days = (user_df.iloc[-1]["date"] - user_df.iloc[-14]["date"]).days
        rate = round((latest - w14) * 7 / days, 2) if days > 0 else 0
    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df.iloc[i+1]["date"] - user_df.iloc[i]["date"]).days == 1:
            streak += 1
        else: break
    return {"latest":latest, "change":f"{change:+.1f}", "pct":f"{pct:+.1f}%", "rate":rate, "streak":streak}

m = stats(df[df["user"] == "Matthew"])
j = stats(df[df["user"] == "Jasmine"])

st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest", m["latest"])
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest", j["latest"])
    st.write(f"**Change:** {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

# ——— LAST ENTRIES & BACKUP ———
st.header("Last 10 Entries")
st.dataframe(df.tail(10)[["user","date","weight"]], hide_index=True)

st.download_button(
    "Download Full Backup CSV",
    data=df.to_csv(index=False).encode(),
    file_name=f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
    mime="text/csv"
)
