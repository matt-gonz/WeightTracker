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
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_index = 0 if params["user"] == "Matthew" else 1
else:
    default_index = 0
user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], index=default_index)

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

# ——— LOAD & PREPARE DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if df.empty:
    st.info("No data yet — start logging or import a backup!")
    st.stop()

df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)

# ——— IMPORT TOOL ———
st.markdown("---")
st.subheader("Import Old Data")
uploaded = st.file_uploader("Upload backup CSV", type="csv")
if uploaded:
    try:
        tmp = pd.read_csv(uploaded)
        cols = [c.strip().lower() for c in tmp.columns]
        rename_map = {}
        for c in tmp.columns:
            l = c.strip().lower()
            if "user" in l:  rename_map[c] = "user"
            if "date" in l:  rename_map[c] = "date"
            if "weight" in l: rename_map[c] = "weight"
        tmp = tmp.rename(columns=rename_map)[["user","date","weight"]].dropna()
        tmp = tmp[tmp["user"].isin(["Matthew","Jasmine"])]
        tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce")
        tmp = tmp.dropna()
        tmp["date"] = tmp["date"].dt.strftime("%Y-%m-%d")
        c.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)", tmp.values.tolist())
        conn.commit()
        st.success(f"Imported {len(tmp)} rows")
        st.rerun()
    except:
        st.error("Import failed — check your CSV")

# ——— TOOLTIP DATA ———
df["total_change"] = df["weight"] - df.groupby("user")["weight"].transform("first")
df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total")

# ——— DATE RANGE ———
st.markdown("### Trend Chart")
view = st.radio("View", ["Week","30D","90D","Year","All"], horizontal=True, index=1)
days = {"Week":7, "30D":30, "90D":90, "Year":365, "All":99999}[view]
cutoff = datetime.now() - timedelta(days=days)
chart_df = df[df["date"] >= cutoff].copy()

# ——— THE BULLETPROOF CHART FIX ———
if len(chart_df) == 0:
    st.info("No data in this time range yet")
    st.stop()

# Force nice axis limits even with 1 or 2 points
weight_min = chart_df["weight"].min() - 5
weight_max = chart_df["weight"].max() + 5
date_min = chart_df["date"].min() - timedelta(days=1)
date_max = chart_df["date"].max() + timedelta(days=1)

base = alt.Chart(chart_df).mark_line(
    point=alt.OverlayMarkDef(color="white", size=200, strokeWidth=4)
).encode(
    x=alt.X("date:T", title="Date",
            scale=alt.Scale(domain=[date_min, date_max])),
    y=alt.Y("weight:Q", title="Weight (lbs)",
            scale=alt.Scale(domain=[weight_min, weight_max])),
    color=alt.Color("user:N", legend=alt.Legend(title=""),
                    scale=alt.Scale(domain=["Matthew","Jasmine"],
                                    range=["#00CC96","#FF6B6B"])),
    tooltip=[
        alt.Tooltip("user:N", title="Who"),
        alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
        alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
        alt.Tooltip("tooltip_total:N", title="Total Change")
    ]
).properties(
    height=500
).interactive(bind_y=False)

st.altair_chart(base, use_container_width=True)

# ——— STATS (with proper +/− on rate) ———
def get_stats(u):
    u = u.sort_values("date").reset_index(drop=True)
    start = u.iloc[0]["weight"]
    latest = u.iloc[-1]["weight"]
    change = latest - start
    rate = 0.0
    if len(u) >= 14:
        days = (u.iloc[-1]["date"] - u.iloc[-14]["date"]).days
        if days > 0:
            rate = round((latest - u.iloc[-14]["weight"]) * 7 / days, 1)
    return {
        "latest": f"{latest:.1f}",
        "change": f"{change:+.1f}",
        "pct": f"{change/start*100:+.1f}%",
        "rate": f"{rate:+.1f}",
        "streak": sum(1 for i in range(1,len(u)) if (u.iloc[i]["date"]-u.iloc[i-1]["date"]).days==1) + 1
    }

m = get_stats(df[df["user"]=="Matthew"])
j = get_stats(df[df["user"]=="Jasmine"])

st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest", m["latest"] + " lbs")
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest", j["latest"] + " lbs")
    st.write(f"**Change:** {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

# ——— LAST 10 + BACKUP ———
st.header("Last 10 Entries")
st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], hide_index=True)

st.download_button("Download Full Backup CSV",
                   df.to_csv(index=False).encode(),
                   f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
                   "text/csv")
