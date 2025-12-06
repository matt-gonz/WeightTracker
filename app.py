import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import sqlite3

# ——— PASSCODE PROTECTION (SEPARATE FOR EACH PERSON) ———
MATTHEW_CODE = "matt2025"   # ← Change to whatever you want
JASMINE_CODE = "jaz2025"    # ← Change to whatever you want

if "user" not in st.session_state:
    st.markdown("### Weight Duel — Enter Your Passcode")
    code = st.text_input("Passcode", type="password", key="passcode_input")
    if st.button("Enter"):
        if code == MATTHEW_CODE:
            st.session_state.user = "Matthew"
            st.success("Welcome, Matthew!")
            st.rerun()
        elif code == JASMINE_CODE:
            st.session_state.user = "Jasmine"
            st.success("Welcome, Jasmine!")
            st.rerun()
        else:
            st.error("Wrong passcode")
    st.stop()

user = st.session_state.user

# ——— DATABASE ———
conn = sqlite3.connect("weight_tracker.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS weights 
             (user TEXT, date TEXT, weight REAL, PRIMARY KEY (user, date))''')
conn.commit()

st.set_page_config(page_title="Weight Duel", layout="centered")
st.title("Weight Duel – Matthew vs Jasmine")

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

# ——— IMPORTER ———
st.markdown("---")
st.subheader("Import Old Data")
uploaded = st.file_uploader("Upload backup CSV", type="csv")
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
df = df.sort_values("date")

# ——— LEGEND ———
st.markdown("### Trend Chart")

col1, col2 = st.columns([1, 1])
with col1:
    show_matthew = st.checkbox("", value=True, key="m")
    st.markdown("**<span style='color:#1E90FF'>●</span> Matthew**", unsafe_allow_html=True)
with col2:
    show_jasmine = st.checkbox("", value=True, key="j")
    st.markdown("**<span style='color:#FF69B4'>●</span> Jasmine**", unsafe_allow_html=True)

if not show_matthew and not show_jasmine:
    st.warning("Select at least one user")
    show_matthew = show_jasmine = True

plot_df = df.copy()
if not show_matthew: plot_df = plot_df[plot_df["user"] != "Matthew"]
if not show_jasmine: plot_df = plot_df[plot_df["user"] != "Jasmine"]

# ——— FINAL PERFECT CHART ———
chart = alt.Chart(plot_df).mark_line(
    point=True,
    strokeWidth=5
).encode(
    x=alt.X("date:T", title=None, axis=alt.Axis(format="%b %d", labelAngle=-45)),
    y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(domain=[100, 190])),
    color=alt.Color("user:N", legend=None,
                    scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#1E90FF","#FF69B4"]))
).properties(height=520).interactive()

st.altair_chart(chart, use_container_width=True)

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

st.download_button("Download Full Backup CSV",
                   df.to_csv(index=False).encode(),
                   f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
                   "text/csv")
