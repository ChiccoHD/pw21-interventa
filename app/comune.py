"""Funzioni condivise dalle pagine della dashboard."""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src import config as cfg
from src.metriche import carica_vista

COLORE = "#1f6f8b"
COLORE_2 = "#e8a33d"
GRIGIO = "#9aa9b1"
SCALA = ["#e8f1f4", "#a9cbd6", "#5b9db2", "#1f6f8b", "#0d3b4c"]
COLORI_ESITO = {"OK": "#d8eedf", "AVVISO": "#fbeccb", "ERRORE": "#f6d2d0",
                "COMPLETATO": "#d8eedf", "RESPINTO": "#f6d2d0"}
MESI_BREVI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
ORDINE_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def num(x, dec=0):
    if x is None or pd.isna(x):
        return "–"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def euro(x):
    return f"{num(x)} €"


def stile(fig, altezza=340):
    fig.update_layout(template="plotly_white", height=altezza,
                      margin=dict(l=10, r=10, t=40, b=10),
                      font=dict(family="Inter, Segoe UI, sans-serif", size=13),
                      title_font=dict(size=15), separators=",.")
    return fig


def colora_esito(valore):
    colore = COLORI_ESITO.get(valore)
    return f"background-color: {colore}" if colore else ""


def verifica_warehouse():
    if not cfg.DB_PATH.exists():
        st.error("Data warehouse non trovato. Esegui prima:  python esegui_tutto.py --no-dashboard")
        st.stop()


@st.cache_data
def vista_richieste():
    return carica_vista(cfg.DB_PATH)


@st.cache_data
def interroga(sql: str) -> pd.DataFrame:
    with sqlite3.connect(cfg.DB_PATH) as con:
        return pd.read_sql_query(sql, con)
