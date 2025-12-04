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
default_user = "Matthew"
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_user = params["user"]
user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], index=0 if default_user == "Matthew" else 1)

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
    st.success(f"Logged {weight_input} lbs on {date_input:%b %d, %Y}")
    st.rerun()

# ——— ALWAYS-VISIBLE IMPORTER ———
st.markdown("---")
st.subheader("Import Old Data")
uploaded = st.file_uploader("Upload backup CSV (user, date, weight)", type="csv")

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

# ——— LOAD DATA ———
df = pd.read_sql_query("SELECT * FROM weights", conn)
if df.empty:
    st.info("No data yet — start logging!")
    st.stop()

df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)
df["total_change"] = df["weight"] - df.groupby("user")["weight"].transform("first")
df["tooltip_total"] = df["total_change"].apply(lambda x: f"{x:+.1f} lbs total")

# ——— DATE RANGE ———
st.markdown("### Trend Chart")
view = st.radio("View", ["Week", "30D", "90D", "Year", "All"], horizontal=True, index=1)

days_back = {"Week": 7, "30D": 30, "90D": 90, "Year": 365, "All": 99999}[view]
cutoff = datetime.now() - timedelta(days=days_back)
chart_df = df[df["date"] >= cutoff].copy()

if chart_df.empty:
    st.info(f"No data in the last {view.lower()} yet")
else:
    # Smart X-axis
    x_format = "%b %d" if view in ["Week", "30D"] else "%b %Y"
    x_title = "Date" if view in ["Week", "30D"] else "Month"

    chart = alt.Chart(chart_df).mark_line(
        strokeWidth=4,
        point=alt.OverlayMarkDef(filled=True, size=300, stroke="white", strokeWidth=6)
    ).encode(
        x=alt.X("date:T", title=x_title, axis=alt.Axis(format=x_format, tickCount=6)),
        y=alt.Y("weight:Q", title="Weight (lbs)"),
        color=alt.Color("user:N",
                        legend=alt.Legend(title=None, orient="top", direction="horizontal"),
                        scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#00E676","#FF5252"])),
        tooltip=[
            alt.Tooltip("user:N", title="Name"),
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("weight:Q", title="Weight", format=".1f lbs"),
            alt.Tooltip("tooltip_total:N", title="Total Change")
        ]
    ).properties(height=520).interactive()

    st.altair_chart(chart, use_container_width=True)

# ——— DELETE ENTRY ———
st.markdown("### Delete Entry")
last_10 = df.sort_values("date", ascending=False).head(10).copy()
last_10["date_str"] = last_10["date"].dt.strftime("%Y-%m-%d")

if not last_10.empty:
    delete_key = st.selectbox(
        "Select entry to delete",
        options=last_10.index,
        format_func=lambda i: f"{last_10.loc[i, 'user']} — {last_10.loc[i, 'date']:%b %d, %Y} — {last_10.loc[i, 'weight']:.1f} lbs"
    )
    if st.button("Delete This Entry", type="secondary"):
        delete_user = last_10.loc[delete_key, "user"]
        delete_date = last_10.loc[delete_key, "date_str"]
        c.execute("DELETE FROM weights WHERE user = ? AND date = ?", (delete_user, delete_date))
        conn.commit()
        st.success("Entry deleted!")
        st.rerun()

# ——— STATS ———
def get_stats(person_df):
    if person_df.empty:
        return {"latest":"—", "change":"—", "pct":"—", "rate":"—", "streak":0}
    p = person_df.sort_values("date").reset_index(drop=True)
    start = p.iloc[0]["weight"]
    latest = p.iloc[-1]["weight"]
    change = latest - start
    rate = "—"
    if len(p) >= 14:
        days = (p.iloc[-1]["date"] - p.iloc[-14]["date"]).days
        if days > 0:
            rate = f"{(latest - p.iloc[-14]['weight']) * 7 / days:+.1f}"
    streak = 1
    for i in range(len(p)-2, -1, -1):
        if (p.iloc[i+1]["date"] - p.iloc[i]["date"]).days == 1:
            streak += 1
        else:
            break
    return {"latest":f"{latest:.1f}", "change":f"{change:+.1f}", "pct":f"{change/start*100:+.1f}%", "rate":rate, "streak":streak}

m = get_stats(df[df["user"] == "Matthew"])
j = get_stats(df[df["user"] == "Jasmine"])

# ——— STANDINGS ———
st.header("Current Standings")
col1, col2 = st.columns(2)
with col1:
    st.subheader("Matthew")
    st.metric("Latest Weight", f"{m['latest']} lbs")
    st.write(f"**Change:** {m['change']} lbs ({m['pct']})")
    st.write(f"**14-day rate:** {m['rate']} lbs/week")
    st.write(f"**Streak:** {m['streak']} days")
with col2:
    st.subheader("Jasmine")
    st.metric("Latest Weight", f"{j['latest']} lbs")
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
