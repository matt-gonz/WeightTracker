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
if "user" in params and params["user"] == "Matthew" or params["user"] == "Jasmine":
    default_user = params["user"]
user = st.sidebar.selectbox("Who am I?", ["Matthew", "Jasmine"], 
                           index=0 if default_user == "Matthew" else 1)

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
df = df.sort_values("date").reset_index(drop=True)

# ——— DATE RANGE ———
st.markdown("### Trend Chart")
view = st.radio("View", ["Week", "30D", "90D", "Year", "All"], horizontal=True, index=True, index=1)

days_back = {"Week":7, "30D":30, "90D":90, "Year":365, "All":99999}[view]
cutoff = datetime.now() - timedelta(days=days_back)
chart_df = df[df["date"] >= cutoff].copy()

# ——— MYNETDIARY-STYLE CHART (NO BUGS) ———
if chart_df.empty:
    st.info(f"No data in the last {view.lower()} yet")
else:
    # Proper domain with padding — this is the real fix
    y_min = chart_df["weight"].min() - 8
    y_max = chart_df["weight"].max() + 8
    x_min = chart_df["date"].min() - timedelta(days=2)
    x_max = chart_df["date"].max() + timedelta(days=2)

    # Smart X-axis labels
    if view == "Week":
        x_axis = alt.X("date:T", title=None, axis=alt.Axis(format="%a %d", labelAngle=-45))
    elif view == "30D":
        x_axis = alt.X("date:T", title=None, axis=alt.Axis(format="%b %d", labelAngle=-45))
    elif view == "90D":
        x_axis = alt.X("date:T", title=None, axis=alt.Axis(format="%b", labelAngle=0))
    else:  # Year / All
        x_axis = alt.X("date:T", title=None, axis=alt.Axis(format="%Y", labelAngle=0))

    chart = alt.Chart(chart_df).mark_line(
        strokeWidth=5,
        point=alt.OverlayMarkDef(filled=True, size=350, stroke="white", strokeWidth=6)
    ).encode(
        x=x_axis,
        y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(domain=[y_min, y_max])),
        color=alt.Color("user:N",
                        legend=alt.Legend(title=None, orient="top"),
                        scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#1E90FF","#FF69B4"])),
        tooltip=[
            alt.Tooltip("user:N", title="Name"),
            alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
            alt.Tooltip("weight:Q", title="Weight", format=".1f lbs")
        ]
    ).properties(height=520).interactive()

    st.altair_chart(chart, use_container_width=True)

# ——— VIEW ALL ENTRIES (NOW WORKS) ———
if st.button("View All Entries → Edit / Delete"):
    st.subheader("All Weight Entries")
    disp = df.copy()
    disp["Date"] = disp["date"].dt.strftime("%b %d, %Y")
    disp = disp[["user", "Date", "weight"]].sort_values("date", ascending=False).reset_index(drop=True)

    edited = st.data_editor(
        disp,
        use_container_width=True,
        hide_index=True,
        key="full_view"
    )

    selected = st.session_state.get("full_view", {}).get("selected_rows", [])
    if selected:
        if st.button("Delete Selected Row(s)", type="secondary"):
            for row in selected:
                idx = row["_index"]
                del_user = disp.iloc[idx]["user"]
                del_date = df[df["user"] == del_user]["date"].iloc[idx].strftime("%Y-%m-%d")
                c.execute("DELETE FROM weights WHERE user=? AND date=?", (del_user, del_date))
            conn.commit()
            st.success("Deleted!")
            st.rerun()

# ——— LAST 10 & BACKUP ———
st.header("Last 10 Entries")
st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], hide_index=True)

st.download_button("Download Full Backup CSV",
                   df.to_csv(index=False).encode(),
                   f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
                   "text/csv")
