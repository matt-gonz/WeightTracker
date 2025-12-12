import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ——— PERSONAL GOOGLE SHEETS — NO SERVICE ACCOUNT, NO PERMISSIONS ———
# This uses YOUR Google account — you only authenticate once
@st.experimental_singleton
def get_sheet():
    # This will open a Google login popup the first time
    gc = gspread.oauth(
        credentials_filename=None,  # uses your browser login
        flow="console"  # works on Streamlit Cloud
    )
    sh = gc.open_by_key("1ipi81MTgxlyxWylvypOJwbEepia2BF_pQzIT6QdV6IM")
    return sh.sheet1

def load_data():
    try:
        sheet = get_sheet()
        rows = sheet.get_all_values()
        if len(rows) <= 1:
            return pd.DataFrame(columns=["user", "date", "weight"])
        df = pd.DataFrame(rows[1:], columns=rows[0])
        df["date"] = pd.to_datetime(df["date"])
        df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
        return df.dropna(subset=["date", "weight"])
    except Exception as e:
        st.error("Google Sheets login failed. Click below to re-authenticate.")
        if st.button("Re-authenticate with Google"):
            st.experimental_rerun()
        st.stop()

def save_data(df):
    sheet = get_sheet()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.astype(str).values.tolist())

# ——— LOGIN ———
MATTHEW_CODE = "matthew2025"
JASMINE_CODE = "jasmine2025"

if "user" not in st.session_state:
    st.markdown("### Enter Your Passcode")
    code = st.text_input("Passcode", type="password")
    if st.button("Enter"):
        if code == MATTHEW_CODE:
            st.session_state.user = "Matthew"
            st.rerun()
        elif code == JASMINE_CODE:
            st.session_state.user = "Jasmine"
            st.rerun()
        else:
            st.error("Wrong passcode")
    st.stop()

user = st.session_state.user

# ——— APP ———
st.set_page_config(page_title="Weight Duel", layout="centered")
st.title("Weight Duel – Matthew vs Jasmine")
st.sidebar.success(f"Logged in as **{user}**")

# LOG WEIGHT
st.header(f"{user}'s Log")
col1, col2 = st.columns([2, 1])
with col1:
    date_input = st.date_input("Date", datetime.today())
with col2:
    weight_input = st.number_input("Weight (lbs)", 50.0, 500.0, step=0.1, value=150.0)

if st.button("Log / Overwrite Weight", use_container_width=True):
    df = load_data()
    new_row = pd.DataFrame([{"user": user, "date": date_input.strftime("%Y-%m-%d"), "weight": weight_input}])
    df = pd.concat([df, new_row], ignore_index=True)
    df = df.drop_duplicates(subset=["user", "date"], keep="last")
    save_data(df)
    st.success("Logged!")
    st.rerun()

# IMPORTER
st.markdown("---")
st.subheader("Import Old Data")
uploaded = st.file_uploader("Upload backup CSV", type="csv")
if uploaded:
    tmp = pd.read_csv(uploaded)
    tmp = tmp[["user","date","weight"]].dropna()
    tmp["date"] = pd.to_datetime(tmp["date"])
    save_data(tmp)
    st.success(f"Imported {len(tmp)} entries!")
    st.rerun()

# LOAD DATA
df = load_data()
if df.empty:
    st.info("No data yet — start logging!")
    st.stop()

# LEGEND
st.markdown("### Trend Chart")
col1, col2 = st.columns([1, 1])
with col1:
    show_matthew = st.checkbox("", value=True, key="m")
    st.markdown("**<span style='color:#1E90FF'>●</span> Matthew**", unsafe_allow_html=True)
with col2:
    show_jasmine = st.checkbox("", value=True, key="j")
    st.markdown("**<span style='color:#FF69B4'>●</span> Jasmine**", unsafe_allow_html=True)

plot_df = df.copy()
if not show_matthew: plot_df = plot_df[plot_df["user"] != "Matthew"]
if not show_jasmine: plot_df = plot_df[plot_df["user"] != "Jasmine"]

# CHART
line = alt.Chart(plot_df).mark_line(strokeWidth=5).encode(
    x=alt.X("date:T", title=None, axis=alt.Axis(format="%b %d", labelAngle=-45)),
    y=alt.Y("weight:Q", title="Weight (lbs)", scale=alt.Scale(domain=[100, 190])),
    color=alt.Color("user:N", legend=None,
                    scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#1E90FF","#FF69B4"]))
)

points = alt.Chart(plot_df).mark_circle(size=380, stroke="white", strokeWidth=1).encode(
    x="date:T",
    y="weight:Q",
    color=alt.Color("user:N", legend=None,
                    scale=alt.Scale(domain=["Matthew","Jasmine"], range=["#1E90FF","#FF69B4"])),
    tooltip=["user", alt.Tooltip("date:T", format="%b %d, %Y"), alt.Tooltip("weight:Q", format=".1f")]
)

chart = (line + points).properties(height=520).interactive()
st.altair_chart(chart, use_container_width=True)

# LAST 10
st.header("Last 10 Entries")
st.dataframe(df.sort_values("date", ascending=False).head(10)[["user","date","weight"]], hide_index=True)

st.download_button("Download Full Backup CSV",
                   df.to_csv(index=False).encode(),
                   f"weight_duel_backup_{datetime.now():%Y-%m-%d}.csv",
                   "text/csv")
