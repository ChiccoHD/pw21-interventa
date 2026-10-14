"""Stile grafico, componenti e funzioni condivise dalle pagine della dashboard."""

from __future__ import annotations

import html
import sqlite3

import pandas as pd
import streamlit as st

from src import config as cfg
from src.metriche import carica_vista

# Palette (validata per la visione dei colori): blu primario, arancio, acqua
BLU = "#2a78d6"
ARANCIO = "#eb6834"
ACQUA = "#1baf7a"
SCALA_BLU = ["#eef4fc", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
INCHIOSTRO, INCHIOSTRO_2, MUTO = "#14171c", "#52514e", "#898781"
GRIGLIA, SFONDO_CARD = "#e8e8e3", "#ffffff"
STATO = {"OK": ("#0a7d0a", "#e3f4e3", "✓", "OK"),
         "AVVISO": ("#8a5a00", "#fdf1d6", "!", "Avviso"),
         "ERRORE": ("#b42318", "#fbe4e2", "✕", "Errore"),
         "COMPLETATO": ("#0a7d0a", "#e3f4e3", "✓", "Completato"),
         "RESPINTO": ("#b42318", "#fbe4e2", "✕", "Respinto")}
MESI_BREVI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
ORDINE_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
FONT = "Source Sans Pro, Segoe UI, system-ui, sans-serif"

CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1380px; }}
[data-testid="stSidebar"] {{ background: #ffffff; border-right: 1px solid {GRIGLIA}; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}

.testata {{ background: linear-gradient(120deg, #184f95 0%, {BLU} 60%, #3987e5 100%); color: #fff;
           border-radius: 18px; padding: 1.5rem 1.8rem; margin-bottom: 1.2rem; }}
.testata h1 {{ color: #fff; font-size: 1.85rem; margin: 0 0 .25rem; padding: 0; }}
.testata p {{ color: rgba(255,255,255,.85); margin: 0; font-size: .98rem; }}
.chips {{ display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .9rem; }}
.chip {{ background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.28); color: #fff;
        padding: .18rem .7rem; border-radius: 999px; font-size: .82rem; white-space: nowrap; }}

.kpi-griglia {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .9rem; margin-bottom: 1.1rem; }}
@media (max-width: 900px) {{ .kpi-griglia {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.kpi {{ background: {SFONDO_CARD}; border: 1px solid rgba(11,11,11,.08); border-radius: 14px;
       padding: .95rem 1.1rem .8rem; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
.kpi-etichetta {{ font-size: .84rem; color: {INCHIOSTRO_2}; display: flex; justify-content: space-between; gap: .5rem; }}
.kpi-valore {{ font-size: 1.95rem; font-weight: 650; color: {INCHIOSTRO}; line-height: 1.15; margin: .2rem 0 .15rem; }}
.kpi-piede {{ display: flex; justify-content: space-between; align-items: flex-end; gap: .5rem; min-height: 30px; }}
.kpi-nota {{ font-size: .78rem; color: {MUTO}; }}
.delta {{ font-size: .8rem; font-weight: 600; padding: .05rem .45rem; border-radius: 999px; white-space: nowrap; }}
.delta.buono {{ color: #006300; background: #e3f4e3; }}
.delta.cattivo {{ color: #b42318; background: #fbe4e2; }}
.delta.neutro {{ color: {INCHIOSTRO_2}; background: #f0efec; }}

[class*="st-key-card"] {{ background: {SFONDO_CARD}; border: 1px solid rgba(11,11,11,.08); border-radius: 14px;
                         padding: 1rem 1.1rem .4rem; box-shadow: 0 1px 2px rgba(16,24,40,.04); }}
.card-titolo {{ font-weight: 650; font-size: 1.02rem; color: {INCHIOSTRO}; margin: 0; }}
.card-sotto {{ font-size: .86rem; color: {INCHIOSTRO_2}; margin: .1rem 0 .3rem; }}
.card-sotto b {{ color: {INCHIOSTRO}; }}

.badge {{ display: inline-flex; align-items: center; gap: .3rem; font-size: .8rem; font-weight: 600;
         padding: .12rem .55rem; border-radius: 999px; white-space: nowrap; }}
.badge .ic {{ font-weight: 800; }}

.banner {{ display: flex; align-items: center; gap: 1rem; border-radius: 16px; padding: 1.1rem 1.4rem;
          margin-bottom: 1.1rem; border: 1px solid rgba(11,11,11,.06); }}
.banner .icona {{ width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center;
                 font-size: 1.4rem; font-weight: 800; color: #fff; flex: none; }}
.banner .titolo {{ font-weight: 700; font-size: 1.1rem; color: {INCHIOSTRO}; }}
.banner .testo {{ font-size: .9rem; color: {INCHIOSTRO_2}; }}

.tabella {{ width: 100%; border-collapse: collapse; font-size: .88rem; border: 0 !important; }}
.tabella th, .tabella td {{ border-left: 0 !important; border-right: 0 !important; border-top: 0 !important; }}
.tabella th {{ text-align: left; font-weight: 600; color: {INCHIOSTRO_2}; border-bottom: 1px solid {GRIGLIA};
              padding: .5rem .6rem; font-size: .8rem; text-transform: uppercase; letter-spacing: .03em; }}
.tabella td {{ border-bottom: 1px solid #f0efec; padding: .5rem .6rem; color: {INCHIOSTRO}; vertical-align: middle; }}
.tabella td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.tabella th.num {{ text-align: right; }}
.tabella tr.gruppo td {{ background: #f7f8fa; font-weight: 650; color: {INCHIOSTRO_2}; font-size: .8rem;
                        text-transform: uppercase; letter-spacing: .03em; }}
.meter {{ height: 6px; background: #e8f0fb; border-radius: 999px; overflow: hidden; margin-top: .45rem; }}
.meter > span {{ display: block; height: 100%; border-radius: 999px; }}
.piede-pagina {{ color: {MUTO}; font-size: .8rem; margin-top: 1.5rem; }}
</style>
"""

def applica_stile():
    st.markdown(CSS, unsafe_allow_html=True)


def num(x, dec=0):
    if x is None or pd.isna(x):
        return "–"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def euro(x):
    return f"{num(x)} €"


def esc(x) -> str:
    return html.escape(str(x))


def testata(titolo: str, sottotitolo: str, chips: list[str]):
    chip = "".join(f'<span class="chip">{esc(c)}</span>' for c in chips)
    st.markdown(f'<div class="testata"><h1>{esc(titolo)}</h1><p>{esc(sottotitolo)}</p>'
                f'<div class="chips">{chip}</div></div>', unsafe_allow_html=True)


def sparkline(valori, larghezza=118, altezza=32) -> str:
    v = [float(x) for x in valori if x is not None and not pd.isna(x)]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1
    xs = [2 + i * (larghezza - 6) / (len(v) - 1) for i in range(len(v))]
    ys = [altezza - 4 - (y - lo) / rng * (altezza - 8) for y in v]
    punti = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"2,{altezza} " + punti + f" {xs[-1]:.1f},{altezza}"
    return (f'<svg width="{larghezza}" height="{altezza}" viewBox="0 0 {larghezza} {altezza}" aria-hidden="true">'
            f'<polygon points="{area}" fill="{BLU}" opacity=".08"/>'
            f'<polyline points="{punti}" fill="none" stroke="#a9b4c2" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="3.6" fill="{BLU}" stroke="#fff" stroke-width="2"/></svg>')


def kpi_card(etichetta, valore, delta=None, buono_se_sale=True, nota="", trend=None, aiuto=""):
    pill = ""
    if delta is not None and not pd.isna(delta[0]):
        variazione, testo = delta
        if abs(variazione) < 1e-9:
            classe, freccia = "neutro", "■"
        else:
            sale = variazione > 0
            classe = "buono" if sale == buono_se_sale else "cattivo"
            freccia = "▲" if sale else "▼"
        pill = f'<span class="delta {classe}">{freccia} {esc(testo)}</span>'
    titolo = f' title="{esc(aiuto)}"' if aiuto else ""
    return (f'<div class="kpi"{titolo}><div class="kpi-etichetta"><span>{esc(etichetta)}</span>{pill}</div>'
            f'<div class="kpi-valore">{esc(valore)}</div>'
            f'<div class="kpi-piede"><span class="kpi-nota">{esc(nota)}</span>{sparkline(trend) if trend is not None else ""}</div></div>')


def griglia_kpi(card: list[str]):
    st.markdown(f'<div class="kpi-griglia">{"".join(card)}</div>', unsafe_allow_html=True)


def intestazione_card(titolo: str, sottotitolo: str = ""):
    st.markdown(f'<p class="card-titolo">{esc(titolo)}</p>'
                + (f'<p class="card-sotto">{sottotitolo}</p>' if sottotitolo else ""), unsafe_allow_html=True)


def badge(esito: str) -> str:
    colore, sfondo, icona, testo = STATO[esito]
    return (f'<span class="badge" style="color:{colore};background:{sfondo}">'
            f'<span class="ic">{icona}</span>{testo}</span>')


def stile_grafico(fig, altezza=320, legenda=False):
    fig.update_layout(
        template="plotly_white", height=altezza, separators=",.",
        margin=dict(l=4, r=16, t=8, b=4),
        font=dict(family=FONT, size=13, color=INCHIOSTRO_2),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=GRIGLIA, font=dict(family=FONT, size=13, color=INCHIOSTRO)),
        showlegend=legenda,
        legend=dict(orientation="h", y=1.0, yanchor="bottom", x=0, xanchor="left", title_text="",
                    font=dict(size=12)),
        bargap=0.5,
    )
    if legenda:
        fig.update_layout(margin=dict(t=34))
    fig.update_xaxes(showgrid=False, linecolor="#c3c2b7", ticks="", title_font=dict(size=12, color=MUTO),
                     tickfont=dict(color=MUTO))
    fig.update_yaxes(gridcolor=GRIGLIA, gridwidth=1, zeroline=False, linecolor="rgba(0,0,0,0)",
                     title_font=dict(size=12, color=MUTO), tickfont=dict(color=MUTO))
    return fig


CONFIG_GRAFICO = {"displayModeBar": False}


def mostra(fig, colonna=st):
    colonna.plotly_chart(fig, use_container_width=True, config=CONFIG_GRAFICO)


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
