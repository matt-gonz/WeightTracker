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
            if "user" in l: rename_map[c] = "user"
            if "date" in l:  rename_map[c] = "date"
            if "weight" in l: rename_map[c] = "weight"
        tmp = tmp.rename(columns=rename_map)
        tmp = tmp[["user","date","weight"]].dropna()
        tmp = tmp[tmp["user"].isin(["Matthew","Jasmine"])]
        tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce")
        tmp = tmp.dropna(subset=["date","weight"])
        tmp["date"] = tmp["date"].dt.strftime("%Y-%m-%d")
        c.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)", tmp.values.tolist())
        conn.commit()
        st.success(f"Imported {len(tmp)} rows")
        st.rerun()
    except Exception as e:
        st.error(f"Import failed: {e}")

# ——— TOOLTIP DATA ———
if not df.empty:
    df["total_change"] = df["weight"] - df.groupby("user")["weight"].transform("first")
    df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total")
else:
    df["tooltip_total"] = ""

# ——— DATE RANGE ———
st.markdown("### Trend Chart")
view = st.radio("View", ["Week","30D","90D","Year","All"], horizontal=True, index=1)
days = {"Week":7, "30D":30, "90D":90, "Year":365, "All":99999}[view]
cutoff = datetime.now() - timedelta(days=days)
chart_df = df[df["date"] >= cutoff].copy() if not df.empty else df.copy()

# ——— BULLETPROOF CHART (works with 0, 1 or 1000 points) ———
if chart_df.empty:
    st.info("No data in this time range yet")
else:
    # Add padding so even one point looks good
    w_min = chart_df["weight"].min()
    w_max = chart_df["weight"].max()
    padding = max((w_max - w_min) * 0.1, 5)  # at least 5 lbs padding
    y_domain = [w_min - padding, w_max + padding]

    d_min = chart_df["date"].min()
    d_max = chart_df["date"].max()
    date_padding = timedelta(days=max((d_max - d_min).days * 0.1, 1))
    x_domain = [d_min - date_padding, d_max + date_padding]

    chart = alt.Chart(chart_df).mark_line(
        point=alt.OverlayMarkDef(size=200, filled=True)
    ).encode(
        x=alt.X("date:T", title="Date", scale=alt.Scale(domain=x_domain)),
        y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(domain=y_domain)),
        color=alt.Color("user:N", legend=alt.Legend(title=""),
                        scale=alt.Scale(domain=["Matthew","Jasmine"],
                                        range=["#00CC96","#FF6B6B"])),
        tooltip=[
            alt.Tooltip("user:N", title="Who"),
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
            alt.Tooltip("tooltip_total:N", title="Total Change")
        ]
    ).properties(height=500).interactive(bind_y=False)

    st.altair_chart(chart, use_container_width=True)

# ——— SAFE STATS FUNCTION (never crashes) ———
def get_stats(user_df):
    if user_df.empty:
        return {"latest":"—", "change":"—", "pct":"—", "rate":"—", "streak":0}
    
    user_df = user_df.sort_values("date").reset_index(drop=True)
    start = user_df.iloc[0]["weight"]
    latest = user_df.iloc[-1]["weight"]
    change = latest - start
    pct = change / start * 100

    rate = "—"
    if len(user_df) >= 14:
        days = (user_df.iloc[-1]["date"] - user_df.iloc[-14]["date"]).days
        if days > 0:
            rate_val = (latest - user_df.iloc[-14]["weight"]) * 7 / days
            rate = f"{rate_val:+.1f}"

    # streak
    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df.iloc[i+1]["date"] - user_df.iloc[i]["date"]).days == 1:
            streak += 1
        else:
            break

    return {
        "latest": f"{latest:.1f}",
        "change": f"{change:+.1f}",
        "pct": f"{pct:+.1f}%",
        "rate": rate,
        "streak": streak
    }

m_stats = get_stats(df[df["user"] == "Matthew"])
j_stats = get_stats(df[df["user"] == "Jasmine"])

# ——— STANDINGS ———
st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest Weight", m_stats["latest"] + " lbs" if m_stats["latest"] != "—" else "—")
    st.write(f"**Change:** {m_stats['change']} lbs ({m_stats['pct']})")
    st.write(f"**14-day rate:** {m_stats['rate']} lbs/week")
    st.write(f"**Streak:** {m_stats['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest Weight", j_stats["latest"] + " lbs" if j_stats["latest"] != "—" else "—")
    st.write(f"**Change:** {j_stats['change']} lbs ({j_stats['pct']})")
    st.write(f"**14-day rate:** {j_stats['rate']} lbs/week")
    st.write(f"**Streak:** {j_stats['streak']} days")

# ——— LAST 10 + BACKUP ———
st.header("Last 10 Entries")
if not df.empty:
    st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], hide_index=True)
else:
    st.write("No entries yet")

st.download_button(
    "Download Full Backup CSV",
    data=df.to_csv(index=False).encode(),
    file_name=f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
    mime="text/csv"
)
