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
weight = st.number_input("Weight (lbs)", min_value=50.0, max_value=500.0, step=0.1, value=150.0)

if st.button("Log / Overwrite Weight"):
    c.execute("INSERT OR REPLACE INTO weights VALUES (?, ?, ?)",
              (user, date.strftime("%Y-%m-%d"), weight))
    conn.commit()
    st.success(f"{user}: {weight} lbs on {date.strftime('%b %d')} → Logged!")
    st.rerun()

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if not df.empty:
    df['date'] = pd.to_datetime(df['date'])

# ——— IMPORT CSV (fixed syntax + super forgiving) ———
st.markdown("---")
st.subheader("Import Old Data")
uploaded_file = st.file_uploader("Upload backup CSV", type="csv")

if uploaded_file is not None:
    try:
        import_df = pd.read_csv(uploaded_file)

        # Detect columns by content
        cols = [col.strip().lower() for col in import_df.columns]
        user_col = date_col = weight_col = None
        for i, col in enumerate(cols):
            if "user" in col:   user_col = import_df.columns[i]
            if "date" in col:   date_col = import_df.columns[i]
            if "weight" in col: weight_col = import_df.columns[i]

        if not all([user_col, date_col, weight_col]):
            st.error("CSV must have columns containing the words 'User', 'Date', and 'Weight'")
            st.stop()

        # ←←← FIXED LINE ←←←
        import_df = import_df.rename(columns={user_col: "user", date_col: "date", weight_col: "weight"})

        before = len(import_df)
        import_df = import_df[["user","date","weight"]].dropna()
        import_df = import_df[import_df["user"].isin(["Matthew","Jasmine"])]
        import_df["date"] = pd.to_datetime(import_df["date"], errors="coerce")
        import_df = import_df.dropna(subset=["date","weight"])
        import_df["date"] = import_df["date"].dt.strftime("%Y-%m-%d")

        if len(import_df) > 0:
            skipped = before - len(import_df)
            c.executemany("INSERT OR REPLACE INTO weights VALUES (?,?,?)", import_df.values.tolist())
            conn.commit()
            st.success(f"Imported {len(import_df)} entries! (skipped {skipped} blank/invalid rows)")
            st.rerun()
        else:
            st.error("No valid rows found")
    except Exception as e:
        st.error(f"Import error: {e}")

# ——— STOP IF NO DATA ———
if df.empty and uploaded_file is None:
    st.info("No data yet — start logging or import a CSV!")
    st.stop()

# ——— ENHANCED TOOLTIP DATA ———
df = df.sort_values('date')
df['prev_weight'] = df.groupby('user')['weight'].shift(1)
df['change_since_prev'] = df['weight'] - df['prev_weight']
df['days_since_prev'] = df.groupby('user')['date'].diff().dt.days
df['start_weight'] = df.groupby('user')['weight'].transform('first')
df['total_change'] = df['weight'] - df['start_weight']

df['tooltip_change'] = df.apply(
    lambda row: f"{row['total_change']:+.1f} lbs" if pd.notna(row['total_change']) else "Starting",
    axis=1
)
df['tooltip_prev'] = df.apply(
    lambda row: f" ({row['change_since_prev']:+.1f} lbs in {int(row['days_since_prev'])} days)" 
    if pd.notna(row['change_since_prev']) else "",
    axis=1
)

# ——— STATS ———
def get_stats(user_df):
    if user_df.empty:
        return {"latest":"—","start":"—","change":"—","pct":"—","rate":"—","streak":0}
    user_df = user_df.sort_values('date').reset_index(drop=True)
    start_weight = user_df['weight'].iloc[0]
    latest = user_df['weight'].iloc[-1]
    total_change = latest - start_weight
    pct = round(total_change / start_weight * 100, 2)
    rate = 0
    if len(user_df) >= 14:
        weight_14_ago = user_df['weight'].iloc[-14]
        days_span = (user_df['date'].iloc[-1] - user_df['date'].iloc[-14]).days
        rate = round((latest - weight_14_ago) * 7 / days_span, 2) if days_span > 0 else 0
    streak = 1
    for i in range(len(user_df)-2, -1, -1):
        if (user_df['date'].iloc[i+1] - user_df['date'].iloc[i]).days == 1:
            streak += 1
        else:
            break
    return {"latest":latest, "start":start_weight, "change":f"{total_change:+.1f}",
            "pct":f"{pct:+.1f}%", "rate":rate, "streak":streak}

matt = df[df['user'] == "Matthew"]
jas  = df[df['user'] == "Jasmine"]
m = get_stats(matt)
j = get_stats(jas)

# ——— DISPLAY ———
st.header("Current Standings")
c1, c2 = st.columns(2)
with c1:
    st.subheader("Matthew")
    st.metric("Latest Weight", m["latest"])
    st.caption(f"Started at {m['start']:.1f} lbs")
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with c2:
    st.subheader("Jasmine")
    st.metric("Latest Weight", j["latest"])
    st.caption(f"Started at {j['start']:.1f} lbs")
    st.write(f"**Change:** {j['change']} lbs ({j['pct']})")
    st.write(f"**14-day rate:** {j['rate']} lbs/week")
    st.write(f"**Streak:** {j['streak']} days")

# ——— CHART WITH RICH TOOLTIPS ———
st.header("Trend Chart — Tap any dot!")
chart = alt.Chart(df).mark_line(point=alt.OverlayMarkDef(size=200, filled=True)).encode(
    x=alt.X('date:T', title="Date"),
    y=alt.Y('weight:Q', title="Weight (lbs)"),
    color=alt.Color('user:N', legend=alt.Legend(title="Person")),
    tooltip=[
        alt.Tooltip('user:N', title="Who"),
        alt.Tooltip('date:T', title="Date", format="%b %d, %Y"),
        alt.Tooltip('weight:Q', title="Weight", format=".1f lbs"),
        alt.Tooltip('tooltip_change:N', title="Total Change"),
        alt.Tooltip('tooltip_prev:N', title="Since Last")
    ]
).properties(height=450).interactive()

st.altair_chart(chart, use_container_width=True)

st.header("Last 10 Entries")
st.dataframe(df.sort_values('date', ascending=False).head(10)[['user','date','weight']], hide_index=True)

# ——— BACKUP ———
st.markdown("---")
st.subheader("Data Safety")
csv = df.to_csv(index=False).encode('utf-8')
st.download_button(
    label="Download Full Backup CSV",
    data=csv,
    file_name=f"weight_duel_backup_{datetime.now().strftime('%Y-%m-%d')}.csv",
    mime="text/csv"
)
