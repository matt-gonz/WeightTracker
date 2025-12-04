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

st.set_page_config(page_title="Weight Duel", layout="centered")
st.title("Weight Duel – Matthew vs Jasmine")

# ——— USER SELECTION ———
params = st.query_params.to_dict()
default_index = 0
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_index = 0 if params["user"] == "Matthew" else 1
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

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if not df.empty:
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
else:
    df = pd.DataFrame(columns=["user", "date", "weight"])

# ——— IMPORT (100% reliable) ———
st.markdown("---")
st.subheader("Import Old Data")
uploaded = st.file_uploader("Upload backup CSV", type="csv", key="import")
if uploaded:
    try:
        tmp = pd.read_csv(uploaded)
        rename_map = {}
        for col in tmp.columns:
            l = col.strip().lower()
            if "user" in l: rename_map[col] = "user"
            if "date" in l: rename_map[col] = "date"
            if "weight" in l or "lbs" in l: rename_map[col] = "weight"
        tmp = tmp.rename(columns=rename_map)
        tmp = tmp[["user","date","weight"]].dropna()
        tmp = tmp[tmp["user"].isin(["Matthew","Jasmine"])]
        tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce")
        tmp = tmp.dropna(subset=["date","weight"])
        tmp["date"] = tmp["date"].dt.strftime("%Y-%m-%d")
        c.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)", tmp.values.tolist())
        conn.commit()
        st.success(f"Imported {len(tmp)} entries!")
        st.rerun()
    except Exception as e:
        st.error(f"Import failed: {e}")

# ——— TOOLTIP ———
if not df.empty:
    df["total_change"] = df["weight"] - df.groupby("user")["weight"].transform("first")
    df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total")
else:
    df["tooltip_total"] = ""

# ——— DATE RANGE ———
st.markdown("### Trend Chart")
view = st.radio("View", ["Week","30D","90D","Year","All"], horizontal=True, index=1, key="range")
days = {"Week":7, "30D":30, "90D":90, "Year":365, "All":99999}[view]
cutoff = datetime.now() - timedelta(days=days)
chart_df = df[df["date"] >= cutoff].copy() if not df.empty else df.copy()

# ——— FINAL PERFECT CHART ———
if chart_df.empty:
    st.info("No data in this time range yet")
else:
    # Padding so even 1 point looks beautiful
    w_min, w_max = chart_df["weight"].min(), chart_df["weight"].max()
    w_pad = max((w_max - w_min) * 0.15, 6)
    y_domain = [w_min - w_pad, w_max + w_pad]

    d_min, d_max = chart_df["date"].min(), chart_df["date"].max()
    d_pad = timedelta(days=max((d_max - d_min).days * 0.15, 2))
    x_domain = [d_min - d_pad, d_max + d_pad]

    chart = alt.Chart(chart_df).mark_line(
        strokeWidth=4,
        point=alt.OverlayMarkDef(size=280, filled=True, stroke="white", strokeWidth=4)
    ).encode(
        x=alt.X("date:T", title=None, scale=alt.Scale(domain=x_domain)),
        y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(domain=y_domain)),
        color=alt.Color("user:N",
                        legend=alt.Legend(title=None, orient="top", direction="horizontal"),
                        scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#00CC96","#FF6B6B"])),
        tooltip=[
            alt.Tooltip("user:N", title="Who"),
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
            alt.Tooltip("tooltip_total:N", title="Total Change")
        ]
    ).properties(
        height=520
    ).interactive()

    st.altair_chart(chart, use_container_width=True)

# ——— STATS ———
def get_stats(user_df):
    if user_df.empty:
        return {"latest":"—", "change":"—", "pct":"—", "rate":"—", "streak":0}
    u = user_df.sort_values("date").reset_index(drop=True)
    start = u.iloc[0]["weight"]
    latest = u.iloc[-1]["weight"]
    change = latest - start
    pct = change / start * 100
    rate = "—"
    if len(u) >= 14:
        days = (u.iloc[-1]["date"] - u.iloc[-14]["date"]).days
        if days > 0:
            rate = f"{(latest - u.iloc[-14]['weight']) * 7 / days:+.1f}"
    streak = 1
    for i in range(len(u)-2, -1, -1):
        if (u.iloc[i+1]["date"] - u.iloc[i]["date"]).days == 1:
            streak += 1
        else: break
    return {"latest":f"{latest:.1f}", "change":f"{change:+.1f}", "pct":f"{pct:+.1f}%", "rate":rate, "streak":streak}

m = get_stats(df[df["user"]=="Matthew"])
j = get_stats(df[df["user"]=="Jasmine"])

st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest", f"{m['latest']} lbs" if m["latest"] != "—" else "—")
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest", f"{j['latest']} lbs" if j["latest"] != "—" else "—")
    st.write(f"**Change:** {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

st.header("Last 10 Entries")
st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], 
             hide_index=True, use_container_width=True)

st.download_button("Download Full Backup CSV",
                   df.to_csv(index=False).encode(),
                   f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
                   "text/csv")
