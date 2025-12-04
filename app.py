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

# ——— USER SELECTION (Matthew default) ———
params = st.query_params.to_dict()
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_index = 0 if params["user"] == "Matthew" else 1
    user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], index=default_index)
else:
    user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], index=0)

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
    df = df.sort_values("date")

# ——— IMPORT TOOL ———
st.markdown("---")
st.subheader("Import Old Data")
uploaded_file = st.file_uploader("Upload a backup CSV", type="csv")

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
df["change_prev"] = df.groupby("user")["weight"].diff()
df["days_gap"] = df.groupby("user")["date"].diff().dt.days

df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total")
df["tooltip_prev"] = df.apply(
    lambda r: f"{r['change_prev']:+.1f} lbs in {int(r['days_gap'])}d" if pd.notna(r['change_prev']) else "", axis=1
)

# ——— DATE RANGE FILTER ———
st.markdown("### Trend Chart")
view = st.radio("View", ["Week", "30D", "90D", "Year", "All"], horizontal=True, index=1)
days_back = {"Week":7, "30D":30, "90D":90, "Year":365, "All":99999}[view]
cutoff = datetime.now() - timedelta(days=days_back)
chart_df = df[df["date"] >= cutoff].copy()

# ——— FIXED CHART (no more tiny dot!) ———
chart = alt.Chart(chart_df).mark_line(
    point=alt.OverlayMarkDef(size=180, filled=True, fillOpacity=1)
).encode(
    x=alt.X("date:T", title="Date", axis=alt.Axis(format="%b %d")),
    y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(zero=False)),
    color=alt.Color("user:N", title="Person",
                    scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#00CC96","#FF6B6B"])),
    tooltip=[
        alt.Tooltip("user:N", title="Who"),
        alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
        alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
        alt.Tooltip("tooltip_total:N", title="Total Change"),
        alt.Tooltip("tooltip_prev:N", title="Since Last")
    ]
).properties(
    height=500,
    width="container"
).interactive(bind_y=False)   # prevents weird vertical squishing

st.altair_chart(chart, use_container_width=True)

# ——— STATS (with +/− on 14-day rate) ———
def get_stats(user_df):
    user_df = user_df.sort_values("date").reset_index(drop=True)
    start = user_df["weight"].iloc[0]
    latest = user_df["weight"].iloc[-1]
    change = latest - start
    pct = round(change/start*100, 2)

    rate = 0.0
    if len(user_df) >= 14:
        w14 = user_df["weight"].iloc[-14]
        days = (user_df["date"].iloc[-1] - user_df["date"].iloc[-14]).days
        if days > 0:
            rate = round((latest - w14) * 7 / days, 2)

    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df["date"].iloc[i+1] - user_df["date"].iloc[i]).days == 1:
            streak += 1
        else:
            break

    return {
        "latest": latest,
        "change": f"{change:+.1f}",
        "pct": f"{pct:+.1f}%",
        "rate": f"{rate:+.1f}",        # ← now shows + or − correctly
        "streak": streak
    }

m = get_stats(df[df["user"] == "Matthew"])
j = get_stats(df[df["user"] == "Jasmine"])

# ——— STANDINGS ———
st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest Weight", f"{m['latest']:.1f} lbs")
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest Weight", f"{j['latest']:.1f} lbs")
    st.write(f"**Change:** {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

# ——— LAST 10 & BACKUP ———
st.header("Last 10 Entries")
st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], hide_index=True)

st.download_button(
    "Download Full Backup CSV",
    data=df.to_csv(index=False).encode(),
    file_name=f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
    mime="text/csv"
)
