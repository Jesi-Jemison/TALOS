import streamlit as st


# Configure the TALOS browser page
st.set_page_config(
    page_title="TALOS",
    page_icon="⚙️",
    layout="wide",
)


# TALOS header
st.title("⚙️ TALOS")

st.write(
    "A guardian at the gate between messy data "
    "and trustworthy analysis."
)

st.divider()


# File upload
uploaded_file = st.file_uploader(
    "Upload a CSV file for inspection",
    type=["csv"],
)


# Development notice
st.info(
    "🚧 TALOS is currently under development. "
    "Data quality checks are coming next."
)
