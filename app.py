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

# ——— USER LOGGING ———
params = st.query_params.to_dict()
default_user = "Matthew"
if "user" in params and params["user"] in ["Matthew", "Jasmine"]:
    default_user = params["user"]
user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], 
                           index=0 if default_user == "Matthew" else 1)

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

# ——— CLEAN SINGLE-LINE LEGEND WITH COLORED CIRCLES ———
st.markdown("### Trend Chart")

col1, col2 = st.columns([1, 1])
with col1:
    show_matthew = st.checkbox(
        "Matthew",
        value=True,
        key="cb_matthew"
    )
    if show_matthew:
        st.write('<span style="color:#1E90FF;font-size:24px">●</span> Matthew', unsafe_allow_html=True)
with col2:
    show_jasmine = st.checkbox(
        "Jasmine",
        value=True,
        key="cb_jasmine"
    )
    if show_jasmine:
        st.write('<span style="color:#FF69B4;font-size:24px">●</span> Jasmine', unsafe_allow_html=True)

if not show_matthew and not show_jasmine:
    st.warning("Select at least one user")
    show_matthew = show_jasmine = True

plot_df = df.copy()
if not show_matthew: plot_df = plot_df[plot_df["user"] != "Matthew"]
if not show_jasmine: plot_df = plot_df[plot_df["user"] != "Jasmine"]

# ——— FINAL CHART — 100% RELIABLE TOOLTIPS ———
base = alt.Chart(plot_df).encode(
    x=alt.X("date:T", title=None, axis=alt.Axis(format="%b %d", labelAngle=-45)),
    y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(domain=[100, 190])),
    color=alt.Color("user:N",
                    legend=None,
                    scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#1E90FF","#FF69B4"])),
    tooltip=[
        alt.Tooltip("user:N", title="Name"),
        alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
        alt.Tooltip("weight:Q", title="Weight", format=".1f lbs")
    ]
)

line = base.mark_line(strokeWidth=5)
points = base.mark_circle(size=380, stroke="white", strokeWidth=1)

# This layering method guarantees 100% reliable tooltips
chart = (line + points).properties(height=520).interactive()

st.altair_chart(chart, use_container_width=True)

# ——— LAST 10 & BACKUP ———
st.header("Last 10 Entries")
st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], hide_index=True)

st.download_button("Download Full Backup CSV",
                   df.to_csv(index=False).encode(),
                   f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
                   "text/csv")
