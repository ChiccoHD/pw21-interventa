"""Dashboard di Interventa. Avvio: streamlit run app/dashboard.py"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

st.set_page_config(page_title="Interventa · Dashboard", page_icon="📊", layout="wide")
st.navigation([
    st.Page("pagine/andamento.py", title="Andamento del servizio", icon=":material/insights:", default=True),
    st.Page("pagine/qualita.py", title="Qualità dei dati", icon=":material/fact_check:"),
]).run()
