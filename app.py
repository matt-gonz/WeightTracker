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

# ——— AUTO-SELECT USER FROM URL ———
params = st.query_params.to_dict()
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_index = 0 if params["user"] == "Matthew" else 1
    user = st.sidebar.selectbox("Who am I?", options=["Matthew", "Jasmine"], index=default_index, key="user_select")
else:
    user = st.sidebar.selectbox("Who am I?", options=["Matthew", "Jasmine"], index=0, key="user_select")

# ——— LOG WEIGHT ———
st.header(f"{user}'s Log")
col1, col2 = st.columns([2, 1])
with col1:
    date = st.date_input("Date", datetime.today())
with col2:
    weight = st.number_input("Weight (lbs)", min_value=50.0, max_value=500.0, step=0.1, value=150.0)

if st.button("Log / Overwrite Weight", use_container_width=True):
    c.execute("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)",
              (user, date.strftime("%Y-%m-%d"), weight))
    conn.commit()
    st.success("Logged!")
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if not df.empty:
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

# ——— IMPORT CSV ———
st.markdown("---")
st.subheader("Import Old Data")
uploaded_file = st.file_uploader("Upload a backup CSV to restore everything", type="csv")

if uploaded_file is not None:
    try:
        import_df = pd.read_csv(uploaded_file)
        cols = [col.strip().lower() for col in import_df.columns]
        user_col = date_col = weight_col = None
        for i, col in enumerate(cols):
            if "user" in col:   user_col = import_df.columns[i]
            if "date" in col:   date_col = import_df.columns[i]
            if "weight" in col: weight_col = import_df.columns[i]

        if not all([user_col, date_col, weight_col]):
            st.error("CSV must have columns containing 'User', 'Date', and 'Weight'")
            st.stop()

        import_df = import_df.rename(columns={user_col:"user", date_col:"date", weight_col:"weight"})
        import_df = import_df[["user","date","weight"]].dropna()
        import_df = import_df[import_df["user"].isin(["Matthew","Jasmine"])]
        import_df["date"] = pd.to_datetime(import_df["date"], errors="coerce")
        import_df = import_df.dropna(subset=["date","weight"])
        import_df["date"] = import_df["date"].dt.strftime("%Y-%m-%d")

        c.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)", import_df.values.tolist())
        conn.commit()
        st.success(f"Imported {len(import_df)} entries!")
        st.rerun()

    except Exception as e:
        st.error(f"Import failed: {e}")

if df.empty:
    st.info("No data yet — start logging or import a backup!")
    st.stop()

# ——— TOOLTIP DATA ———
df["total_change"] = df["weight"] - df.groupby("user")["weight"].transform("first")
df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total" if pd.notna(x) else "")

# ——— DATE RANGE FILTER ———
st.markdown("### Trend Chart")
view = st.radio("View", ["Week", "30D", "90D", "Year", "All"], horizontal=True, index=1)

days_back = {"Week": 7, "30D": 30, "90D": 90, "Year": 365, "All": 99999}[view]
cutoff = datetime.now() - timedelta(days=days_back)
chart_df = df[df["date"] >= cutoff].copy()

# ——— PERFECT GRAPH (FIXED 100%) ———
if chart_df.empty:
    st.info("No data in this time range yet")
else:
    # Padding for nice view even with 1 point
    w_min = chart_df["weight"].min()
    w_max = chart_df["weight"].max()
    padding = max((w_max - w_min) * 0.1, 5)  # At least 5 lbs padding
    y_domain = [w_min - padding, w_max + padding]

    d_min = chart_df["date"].min()
    d_max = chart_df["date"].max()
    date_padding = timedelta(days=max((d_max - d_min).days * 0.1, 1))
    x_domain = [d_min - date_padding, d_max + date_padding]

    chart = alt.Chart(chart_df).mark_line(
        point=alt.OverlayMarkDef(size=200, filled=True)
    ).encode(
        x=alt.X("date:T", scale=alt.Scale(domain=x_domain)),
        y=alt.Y("weight:Q", scale=alt.Scale(domain=y_domain)),
        color=alt.Color("user:N", legend=alt.Legend(title="Person", orient="top", direction="horizontal")),
        tooltip=[
            alt.Tooltip("user:N", title="Who"),
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
            alt.Tooltip("tooltip_total:N", title="Total Change")
        ]
    ).properties(
        height=500
    ).interactive()

    st.altair_chart(chart, use_container_width=True)

# ——— STATS ———
def get_stats(user_df):
    if user_df.empty:
        return {"latest":"—", "change":"—", "pct":"—", "rate":"—", "streak":0}
    
    user_df = user_df.sort_values("date").reset_index(drop=True)
    start = user_df.iloc[0]["weight"]
    latest = user_df.iloc[-1]["weight"]
    change = latest - start
    pct = round(change / start * 100, 2)
    rate = "—"
    if len(user_df) >= 14:
        days = (user_df.iloc[-1]["date"] - user_df.iloc[-14]["date"]).days
        if days > 0:
            rate = f"{(latest - user_df.iloc[-14]['weight']) * 7 / days:+.1f}"
    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df.iloc[i+1]["date"] - user_df.iloc[i]["date"]).days == 1:
            streak += 1
        else:
            break
    return {"latest":f"{latest:.1f}", "change":f"{change:+.1f}", "pct":f"{pct:+.1f}%", "rate":rate, "streak":streak}

m = get_stats(df[df["user"] == "Matthew"])
j = get_stats(df[df["user"] == "Jasmine"])

# ——— STANDINGS ———
st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest", m["latest"] + " lbs" if m["latest"] != "—" else "—")
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest", j["latest"] + " lbs" if j["latest"] != "—" else "—")
    st.write(f"**Change:** {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

st.header("Last 10 Entries")
st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], hide_index=True)

st.download_button("Download Full Backup CSV",
                   df.to_csv(index=False).encode(),
                   f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
                   "text/csv")
