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
    user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], index=default_index, key="user_select")
else:
    user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], index=0, key="user_select")

# ——— LOG WEIGHT ———
st.header(f"{user}'s Log")
col1, col2 = st.columns(2)
with col1:
    date = st.date_input("Date", value=datetime.today())
with col2:
    weight = st.number_input("Weight (lbs)", min_value=50.0, max_value=500.0, step=0.1)

if st.button("Log / Overwrite Weight", use_container_width=True):
    c.execute("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)",
              (user, date.strftime("%Y-%m-%d"), weight))
    conn.commit()
    st.success(f"Logged {weight} lbs on {date.strftime('%b %d')}")
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if not df.empty:
    df['date'] = pd.to_datetime(df['date'])

# ——— IMPORT CSV (100% FIXED) ———
with st.expander("Import Old Data"):
    uploaded = st.file_uploader("Upload backup CSV", type="csv", key="uploader")
    if uploaded:
        try:
            import_df = pd.read_csv(uploaded)

            # Detect columns
            cols_lower = [col.strip().lower() for col in import_df.columns]
            rename_map = {}
            for orig_col, lower_col in zip(import_df.columns, cols_lower):
                if "user" in lower_col:   rename_map[orig_col] = "user"
                if "date" in lower_col:   rename_map[orig_col] = "date"
                if "weight" in lower_col: rename_map[orig_col] = "weight"

            if not all(k in rename_map.values() for k in ["user","date","weight"]):
                st.error("CSV must contain columns with 'User', 'Date', and 'Weight'")
                st.stop()

            import_df = import_df.rename(columns=rename_map)
            import_df = import_df[["user","date","weight"]].dropna()
            import_df = import_df[import_df["user"].isin(["Matthew","Jasmine"])]
            import_df["date"] = pd.to_datetime(import_df["date"], errors="coerce")
            import_df = import_df.dropna(subset=["date","weight"])
            import_df["date"] = import_df["date"].dt.strftime("%Y-%m-%d")

            # ← THIS WAS THE BUG — now fixed
            c.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)", 
                         import_df[["user","date","weight"]].values.tolist())
            conn.commit()

            st.success(f"Imported {len(import_df)} entries!")
            st.rerun()

        except Exception as e:
            st.error(f"Import failed: {e}")

if df.empty:
    st.info("No data yet — start logging or import a backup!")
    st.stop()

# ——— ENHANCED TOOLTIP DATA ———
df = df.sort_values("date").reset_index(drop=True)
df["prev_weight"] = df.groupby("user")["weight"].shift(1)
df["change_prev"] = df["weight"] - df["prev_weight"]
df["days_since_prev"] = df.groupby("user")["date"].diff().dt.days
df["start_weight"] = df.groupby("user")["weight"].transform("first")
df["total_change"] = df["weight"] - df["start_weight"]

df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total" if pd.notna(x) else "Start")
df["tooltip_prev"] = df.apply(
    lambda r: f"{r['change_prev']:+.1f} lbs in {int(r['days_since_prev'])} days" 
    if pd.notna(r['change_prev']) else "", axis=1
)

# ——— TIME RANGE FILTER ———
st.markdown("### Trend Chart")
view = st.radio("View:", ["Week", "30-Day", "90-Day", "Year", "All"], horizontal=True, key="view_range")

today = datetime.today()
cutoffs = {
    "Week": today - timedelta(days=7),
    "30-Day": today - timedelta(days=30),
    "90-Day": today - timedelta(days=90),
    "Year": today - timedelta(days=365),
    "All": df["date"].min()
}
chart_df = df[df["date"] >= pd.to_datetime(cutoffs[view])].copy()

# ——— CHART ———
chart = alt.Chart(chart_df).mark_line(
    point=alt.OverlayMarkDef(size=200, strokeWidth=3)
).encode(
    x=alt.X("date:T", title="Date"),
    y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(zero=False)),
    color=alt.Color("user:N", title="Person"),
    tooltip=[
        alt.Tooltip("user:N", title="Who"),
        alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
        alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
        alt.Tooltip("tooltip_total:N", title="Total Change"),
        alt.Tooltip("tooltip_prev:N", title="Since Last")
    ]
).properties(height=450).interactive()

st.altair_chart(chart, use_container_width=True)

# ——— STATS ———
def get_stats(user_df):
    if user_df.empty: return {"latest":"—","start":"—","change":"—","pct":"—","rate":"—","streak":0}
    user_df = user_df.sort_values("date").reset_index(drop=True)
    start = user_df["weight"].iloc[0]
    latest = user_df["weight"].iloc[-1]
    change = latest - start
    pct = round(change/start*100, 2)
    rate = 0
    if len(user_df) >= 14:
        w14 = user_df["weight"].iloc[-14]
        days = (user_df["date"].iloc[-1] - user_df["date"].iloc[-14]).days
        rate = round((latest - w14) * 7 / days, 2) if days > 0 else 0
    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df["date"].iloc[i+1] - user_df["date"].iloc[i]).days == 1:
            streak += 1
        else: break
    return {"latest":latest, "start":start, "change":f"{change:+.1f}",
            "pct":f"{pct:+.1f}%", "rate":rate, "streak":streak}

m = get_stats(df[df["user"]=="Matthew"])
j = get_stats(df[df["user"]=="Jasmine"])

# ——— STANDINGS ———
st.markdown("### Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest", m["latest"])
    st.caption(f"Started: {m['start']:.1f} lbs")
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest", j["latest"])
    st.caption(f"Started: {j['start']:.1f} lbs")
    st.write(f"**Change:** {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

# ——— LAST ENTRIES + BACKUP ———
st.markdown("### Last 10 Entries")
st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], hide_index=True)

st.download_button(
    "Download Full Backup CSV",
    data=df.to_csv(index=False).encode(),
    file_name=f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
    mime="text/csv"
)
