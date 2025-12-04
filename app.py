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

# ——— AUTO-SELECT USER FROM URL ———
params = st.query_params.to_dict()
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_index = 0 if params["user"] == "Matthew" else 1
    user = st.sidebar.selectbox("Who am I?", options=["Matthew", "Jasmine"], index=default_index, key="user_select")
else:
    user = st.sidebar.selectbox("Who am I?", options=["Matthew", "Jasmine"], index=0, key="user_select")

# ——— LOG WEIGHT ———
st.header(f"{user}'s Log")
date = st.date_input("Date", value=datetime.now().date())
weight = st.number_input("Weight (lbs)", min_value=50.0, max_value=500.0, step=0.1)

if st.button("Log / Overwrite Weight"):
    c.execute("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)",
              (user, date.strftime("%Y-%m-%d"), weight))
    conn.commit()
    st.success("Logged!")
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if not df.empty:
    df['date'] = pd.to_datetime(df['date'])

# ——— IMPORT CSV (STRICT: skips any row missing User/Date/Weight) ———
st.markdown("---")
st.subheader("Import Your Old Data")
uploaded_file = st.file_uploader("Upload a backup CSV to restore", type="csv")

if uploaded_file is not None:
    try:
        import_df = pd.read_csv(uploaded_file)

        # Normalize column names
        import_df = import_df.rename(columns=lambda x: x.strip().lower())
        col_map = {
            col: new_name for col in import_df.columns
            for new_name in ["user", "date", "weight"]
            if new_name in col or "weight" in col or col in ["user", "date", "weight"]
        }
        import_df = import_df.rename(columns=col_map)

        # Must have all three columns
        if not all(col in import_df.columns for col in ["user", "date", "weight"]):
            st.error("CSV must contain columns: User, Date, Weight")
            st.stop()

        # Clean data — drop any row missing even one value
        before = len(import_df)
        import_df = import_df[["user", "date", "weight"]].dropna()
        import_df = import_df[import_df["user"].isin(["Matthew", "Jasmine"])]
        import_df["date"] = pd.to_datetime(import_df["date"], errors="coerce")
        import_df = import_df.dropna(subset=["date"])
        import_df["weight"] = pd.to_numeric(import_df["weight"], errors="coerce")
        import_df = import_df.dropna(subset=["weight"])
        import_df["date"] = import_df["date"].dt.strftime("%Y-%m-%d")

        if len(import_df) == 0:
            st.error("No valid entries found in the CSV.")
        else:
            skipped = before - len(import_df)
            c.executemany("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)", import_df.values.tolist())
            conn.commit()
            st.success(f"Imported {len(import_df)} entries! (skipped {skipped} invalid/missing rows)")
            st.rerun()

    except Exception as e:
        st.error(f"Import failed: {e}")

# ——— CONTINUE ONLY IF DATA EXISTS ———
if df.empty and uploaded_file is None:
    st.info("No data yet — start logging or import a backup!")
    st.stop()

# ——— STATS ———
def get_stats(user_df):
    if user_df.empty:
        return {"latest":"—","start":"—","change":"—","pct":"—","rate":"—","streak":0}
    user_df = user_df.sort_values('date').reset_index(drop=True)
    start_weight = user_df['weight'].iloc[0]
    latest = user_df['weight'].iloc[-1]
    total_change = latest - start_weight
    pct = round(total_change / start_weight * 100, 2)
    fourteen_days_ago = pd.Timestamp.today() - pd.Timedelta(days=14)
    recent = user_df[user_df['date'] >= fourteen_days_ago]
    rate = 0
    if len(recent) >= 2:
        days_span = (recent['date'].iloc[-1] - recent['date'].iloc[0]).days
        weight_change = latest - recent['weight'].iloc[0]
        rate = round(weight_change * 7 / days_span, 2) if days_span > 0 else 0
    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df['date'].iloc[i+1] - user_df['date'].iloc[i]).days == 1:
            streak += 1
        else:
            break
    return {"latest":latest, "start":start_weight, "change":f"{total_change:+.1f}", "pct":f"{pct:+.1f}%", "rate":rate, "streak":streak}

matt = df[df['user'] == "Matthew"]
jas  = df[df['user'] == "Jasmine"]
m = get_stats(matt)
j = get_stats(jas)

# ——— DISPLAY ———
st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest", m["latest"])
    st.caption(f"Started at {m['start']:.1f} lbs")
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest", j["latest"])
    st.caption(f"Started at {j['start']:.1f} lbs")
    st.write(f"**Change:** {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

st.header("Trend Chart")
chart = alt.Chart(df).mark_line(point=True).encode(
    x='date:T', y='weight:Q', color='user:N', tooltip=['user','date','weight']
).properties(height=400).interactive()
st.altair_chart(chart, width="stretch")

st.header("Last 10 Entries")
st.dataframe(df.sort_values('date', ascending=False).head(10)[['user','date','weight']], hide_index=True)

# ——— BACKUP + IMPORT ———
st.markdown("---")
st.subheader("Data Safety")
col1, col2 = st.columns(2)
with col1:
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Backup CSV",
        data=csv,
        file_name=f"weight_duel_backup_{datetime.now().strftime('%Y-%m-%d')}.csv",
        mime="text/csv"
    )
with col2:
    st.caption("Download monthly  Restore anytime")
