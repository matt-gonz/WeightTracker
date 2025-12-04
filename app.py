import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import sqlite3

# ——— DATABASE (bulletproof) ———
@st.cache_resource
def get_db():
    conn = sqlite3.connect("weight_tracker.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS weights 
                 (user TEXT, date TEXT, weight REAL, PRIMARY KEY (user, date))''')
    conn.commit()
    return conn, c

conn, c = get_db()

st.set_page_config(page_title="Weight Duel", layout="centered", initial_sidebar_state="expanded")
st.title("Weight Duel – Matthew vs Jasmine")

# ——— USER SELECTION ———
params = st.query_params.to_dict()
default_index = 0
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_index = 0 if params["user"] == "Matthew" else 1
user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], index=default_index, key="user_select")

# ——— LOG WEIGHT ———
st.header(f"{user}'s Log")
col1, col2 = st.columns([3, 2])
with col1:
    date_input = st.date_input("Date", datetime.today(), key="date_log")
with col2:
    weight_input = st.number_input("Weight (lbs)", 50.0, 500.0, step=0.1, value=150.0, key="weight_log")

if st.button("Log / Overwrite Weight", use_container_width=True):
    c.execute("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)",
              (user, date_input.strftime("%Y-%m-%d"), weight_input))
    conn.commit()
    st.success(f"Logged {weight_input} lbs on {date_input:%b %d}")
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
has_data = not df.empty

if has_data:
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["total_change"] = df["weight"] - df.groupby("user")["weight"].transform("first")
    df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total")
else:
    st.info("No data yet — log a weight or import a backup!")
    st.stop()

# ——— IMPORT ———
with st.expander("Import Old Data"):
    uploaded = st.file_uploader("Upload CSV backup", type="csv", key="uploader")
    if uploaded:
        try:
            tmp = pd.read_csv(uploaded)
            rename = {}
            for col in tmp.columns:
                l = col.strip().lower()
                if "user" in l: rename[col] = "user"
                if "date" in l: rename[col] = "date"
                if "weight" in l or "lbs" in l: rename[col] = "weight"
            tmp = tmp.rename(columns=rename)[["user","date","weight"]].dropna()
            tmp = tmp[tmp["user"].isin(["Matthew","Jasmine"])]
            tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce")
            tmp = tmp.dropna()
            tmp["date"] = tmp["date"].dt.strftime("%Y-%m-%d")
            c.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)", tmp.values.tolist())
            conn.commit()
            st.success(f"Imported {len(tmp)} entries!")
            st.rerun()
        except Exception as e:
            st.error(f"Import failed: {e}")

# ——— PERFECT MYNETDIARY-STYLE CHART ———
st.markdown("### Weight Trend")

# Radio buttons with proper key
view = st.radio(
    "View range:",
    ["Week", "30D", "90D", "Year", "All"],
    horizontal=True,
    index=1,
    key="view_range"
)

days_back = {"Week": 7, "30D": 30, "90D": 90, "Year": 365, "All": 99999}[view]
cutoff_date = datetime.now() - timedelta(days=days_back)
chart_df = df[df["date"] >= cutoff_date].copy()

# If no data in range, show message but keep chart ready
if chart_df.empty:
    st.info(f"No weights in the last {view.lower()} yet")
    chart_df = pd.DataFrame({"date": [datetime.now()], "weight": [150], "user": ["Matthew"]})  # dummy for axis

# Exact MyNetDiary behavior: snap X-axis to selected range, but allow panning/zooming
selection = alt.selection_interval(bind="scales", encodings=["x"])

chart = alt.Chart(chart_df).mark_line(
    strokeWidth=4.5,
    point=alt.OverlayMarkDef(size=300, filled=True, stroke="white", strokeWidth=5)
).encode(
    x=alt.X("date:T", title=None,
            scale=alt.Scale(domain=(cutoff_date, datetime.now() + timedelta(days=1)))),
    y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(zero=False)),
    color=alt.Color("user:N",
                    legend=alt.Legend(title=None, orient="top", symbolSize=200),
                    scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#00E676", "#FF5252"])),
    tooltip=[
        alt.Tooltip("user:N", title="Name"),
        alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
        alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
        alt.Tooltip("tooltip_total:N", title="Total Change")
    ]
).add_params(selection).properties(
    height=520,
    width="container"
).interactive()

st.altair_chart(chart, use_container_width=True)

# ——— STATS ———
def stats(person):
    data = df[df["user"] == person]
    if data.empty:
        return {"latest":"—", "change":"—", "pct":"—", "rate":"—", "streak":0}
    data = data.sort_values("date").reset_index(drop=True)
    start = data.iloc[0]["weight"]
    latest = data.iloc[-1]["weight"]
    change = latest - start
    rate = "—"
    if len(data) >= 14:
        days = (data.iloc[-1]["date"] - data.iloc[-14]["date"]).days
        if days > 0:
            rate = f"{(latest - data.iloc[-14]['weight']) * 7 / days:+.1f}"
    streak =  = 1
    for i in range(len(data)-2, -1, -1):
        if (data.iloc[i+1]["date"] - data.iloc[i]["date"]).days == 1:
            streak += 1
        else:
            break
    return {
        "latest": f"{latest:.1f}",
        "change": f"{change:+.1f}",
        "pct": f"{change/start*100:+.1f}%",
        "rate": rate,
        "streak": streak
    }

m = stats("Matthew")
j = stats("Jasmine")

# ——— STANDINGS ———
st.markdown("### Current Standings")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Matthew")
    st.metric("Latest Weight", f"{m['latest']} lbs")
    st.caption(f"Change: {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with col2:
    st.subheader("Jasmine")
    st.metric("Latest Weight", f"{j['latest']} lbs")
    st.caption(f"Change: {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

# ——— LAST ENTRIES & BACKUP ———
st.markdown("### Last 10 Entries")
st.dataframe(
    df.sort_values("date", ascending=False).head(10)[["user","date","weight"]],
    hide_index=True,
    use_container_width=True
)

st.download_button(
    "Download Full Backup CSV",
    data=df.to_csv(index=False).encode(),
    file_name=f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
    mime="text/csv"
)
