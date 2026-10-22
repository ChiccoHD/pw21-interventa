"""Dashboard di Interventa. Avvio: streamlit run app/dashboard.py"""

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import VERSIONE  # noqa: E402

RISORSE = Path(__file__).resolve().parent / "risorse"
st.set_page_config(page_title="Interventa · Dashboard", page_icon=":material/home_repair_service:", layout="wide")
st.logo(str(RISORSE / "logo.svg"), icon_image=str(RISORSE / "icona.svg"), size="large")
pagina = st.navigation([
    st.Page("pagine/andamento.py", title="Andamento del servizio", icon=":material/insights:", default=True),
    st.Page("pagine/clienti.py", title="Clienti", icon=":material/group:"),
    st.Page("pagine/qualita.py", title="Qualità dei dati", icon=":material/fact_check:"),
    st.Page("pagine/informazioni.py", title="Informazioni", icon=":material/info:"),
])
pagina.run()
st.sidebar.caption(f"Interventa · versione {VERSIONE}")
