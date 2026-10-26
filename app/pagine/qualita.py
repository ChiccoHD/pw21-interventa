"""Pagina di controllo: caricamenti, controlli di qualità e storico delle anagrafiche."""

import pandas as pd
import plotly.express as px
import streamlit as st

from app.comune import (piede_pagina, ACQUA, ARANCIO, BLU, MESI_BREVI, STATO, applica_stile, badge, esc, griglia_kpi, interroga,
                        intestazione_card, kpi_card, mostra, num, stile_grafico, testata, verifica_warehouse)
from src import config as cfg
from src.qualita import REGOLE

AREE = {
    "fatti_chiave_unica": "Integrità", "fatti_riferimenti": "Integrità", "calendario_completo": "Integrità",
    "annullate_coerenti": "Coerenza", "erogate_con_tempo": "Coerenza", "incassi_caricati": "Coerenza",
    "tempo_plausibile": "Plausibilità", "importo_plausibile": "Plausibilità", "operatore_noto": "Plausibilità",
    "versione_corrente_unica": "Storico", "versioni_non_sovrapposte": "Storico", "fatti_versione_valida": "Storico",
    "scarti_caricamento": "Processo", "volume_mensile": "Processo",
}
ORDINE_AREE = ["Integrità", "Coerenza", "Plausibilità", "Storico", "Processo"]

applica_stile()
verifica_warehouse()

caricamenti = interroga("SELECT * FROM etl_caricamenti ORDER BY id_caricamento")
risultati = interroga("SELECT * FROM dq_risultati")
eventi = interroga("SELECT * FROM etl_eventi")
caricamenti["quando"] = pd.to_datetime(caricamenti["eseguito_il"]).dt.strftime("%d/%m/%Y %H:%M")

testata("Qualità dei dati", "Esito dei caricamenti dell'ETL, controlli automatici e storico delle anagrafiche",
        [f"{len(caricamenti)} caricamenti", f"{len(REGOLE)} controlli per caricamento",
         f"{(caricamenti['esito'] == 'RESPINTO').sum()} respinti"])

st.sidebar.markdown("**Caricamento da esaminare**")
etichette = {r.id_caricamento: f"#{r.id_caricamento} · {r.tipo} {r.periodo}" for r in caricamenti.itertuples()}
scelto = st.sidebar.radio("Caricamento", list(etichette)[::-1], format_func=etichette.get,
                          label_visibility="collapsed")
st.sidebar.caption("Ogni caricamento è una transazione: se un controllo dà errore viene annullato.")

car = caricamenti.set_index("id_caricamento").loc[scelto]
ris = risultati[risultati["id_caricamento"] == scelto].copy()
eve = eventi[eventi["id_caricamento"] == scelto]
colore, sfondo, icona, _ = STATO[car["esito"]]
conteggi = ris["esito"].value_counts()
testo = (f"{num(car['righe_caricate'])} richieste caricate e {num(car['nuove_versioni'])} nuove versioni nelle "
         f"anagrafiche. Controlli: {conteggi.get('OK', 0)} superati, {conteggi.get('AVVISO', 0)} avvisi, "
         f"{conteggi.get('ERRORE', 0)} errori."
         if car["esito"] == "COMPLETATO" else
         "Almeno un controllo è in errore: tutte le modifiche sono state annullate e il warehouse è rimasto "
         "allo stato precedente.")
st.markdown(f'<div class="banner" style="background:{sfondo}"><div class="icona" style="background:{colore}">'
            f'{icona}</div><div><div class="titolo">Caricamento #{scelto} · {esc(car["tipo"])} {esc(car["periodo"])}'
            f' · {STATO[car["esito"]][3]}</div><div class="testo">Eseguito il {esc(car["quando"])}. {testo}</div>'
            f'</div></div>', unsafe_allow_html=True)

superati = conteggi.get("OK", 0)
quota_scarti = 100 * car["righe_scartate"] / car["righe_lette"] if car["righe_lette"] else 0
meter = (f'<div class="meter"><span style="width:{100 * superati / max(len(ris), 1):.0f}%;'
         f'background:{STATO["OK"][0] if superati == len(ris) else BLU}"></span></div>')
griglia_kpi([
    kpi_card("Richieste lette", num(car["righe_lette"]), nota="dal file del pacchetto"),
    kpi_card("Richieste caricate", num(car["righe_caricate"]), nota="nuove righe nella tabella dei fatti"),
    kpi_card("Richieste scartate", num(car["righe_scartate"]), nota=f"{num(quota_scarti, 1)}% delle righe lette"),
    kpi_card("Controlli superati", f"{superati} su {len(ris)}", nota="").replace(
        '<span class="kpi-nota"></span>', f'<span class="kpi-nota" style="flex:1">{meter}</span>'),
])

# --- controlli -------------------------------------------------------------------
with st.container(key="card_controlli"):
    intestazione_card("Controlli di qualità",
                      "Ogni controllo conta le violazioni sul totale; la percentuale è confrontata con la soglia "
                      "di <b>avviso</b> e quella di <b>errore</b>.")
    ris["area"] = ris["regola"].map(AREE)
    righe = []
    for area in ORDINE_AREE:
        gruppo = ris[ris["area"] == area]
        if gruppo.empty:
            continue
        righe.append(f'<tr class="gruppo"><td colspan="5">{area}</td></tr>')
        for r in gruppo.itertuples():
            soglie = "nessuna violazione ammessa" if r.soglia_errore == 0 else (
                f"avviso oltre {num(r.soglia_avviso)}% · errore oltre {num(r.soglia_errore)}%")
            righe.append(f"<tr><td>{esc(r.descrizione)}</td>"
                         f'<td class="num">{num(r.violazioni)} su {num(r.totale)}</td>'
                         f'<td class="num">{num(r.percentuale, 2)}%</td>'
                         f'<td style="color:#898781">{soglie}</td><td>{badge(r.esito)}</td></tr>')
    st.markdown('<table class="tabella"><thead><tr><th>Controllo</th><th class="num">Violazioni</th>'
                '<th class="num">%</th><th>Soglie</th><th>Esito</th></tr></thead><tbody>'
                + "".join(righe) + "</tbody></table><br>", unsafe_allow_html=True)

col_a, col_b = st.columns([1.35, 1], gap="medium")

with col_a, st.container(key="card_pulizia"):
    pulizia = eve[eve["tipo"].isin(["correzione", "scarto"])].copy()
    corrette = pulizia.loc[pulizia["tipo"] == "correzione", "righe"].sum()
    scartate = pulizia.loc[pulizia["tipo"] == "scarto", "righe"].sum()
    intestazione_card("Correzioni e scarti dell'ETL",
                      f"<b>{num(corrette)}</b> valori corretti automaticamente, <b>{num(scartate)}</b> righe "
                      "scartate perché non recuperabili.")
    if len(pulizia):
        pulizia["voce"] = pulizia["tabella"].str.capitalize() + " · " + pulizia["descrizione"]
        pulizia["tipo"] = pulizia["tipo"].map({"correzione": "Correzione", "scarto": "Scarto"})
        pulizia = pulizia.sort_values(["tipo", "righe"], ascending=[False, True])
        fig = px.bar(pulizia, x="righe", y="voce", color="tipo", orientation="h", text="righe",
                     color_discrete_map={"Correzione": BLU, "Scarto": ARANCIO})
        fig.update_traces(textposition="outside", cliponaxis=False, textfont=dict(color="#14171c"),
                          marker_cornerradius=4, hovertemplate="<b>%{y}</b><br>Righe: %{x}<extra></extra>")
        stile_grafico(fig, 40 + 30 * len(pulizia), legenda=True)
        fig.update_xaxes(visible=False, range=[0, pulizia["righe"].max() * 1.2])
        fig.update_yaxes(title=None, gridcolor="rgba(0,0,0,0)", categoryorder="array",
                         categoryarray=pulizia["voce"].tolist())
        mostra(fig)
    file_scarti = cfg.DIR_SCARTI / f"scarti_{car['periodo']}.csv"
    if file_scarti.exists() and scartate:
        st.download_button("Scarica le righe scartate (CSV)", file_scarti.read_bytes(),
                           file_name=file_scarti.name, mime="text/csv", icon=":material/download:",
                           key="scarica_scarti")

with col_b, st.container(key="card_storico_caricamenti"):
    incrementali = caricamenti[caricamenti["tipo"] == "incrementale"]
    intestazione_card("Storico dei caricamenti",
                      f"Caricamento iniziale di <b>{num(caricamenti['righe_caricate'].iloc[0])}</b> richieste, "
                      f"poi {len(incrementali)} pacchetti mensili, confrontati qui sotto.")
    lungo = incrementali.melt(id_vars=["id_caricamento", "periodo"],
                             value_vars=["righe_caricate", "righe_scartate", "nuove_versioni"],
                             var_name="misura", value_name="righe")
    lungo["misura"] = lungo["misura"].map({"righe_caricate": "Richieste caricate",
                                           "righe_scartate": "Richieste scartate",
                                           "nuove_versioni": "Nuove versioni"})
    lungo["caricamento"] = "#" + lungo["id_caricamento"].astype(str) + " " + lungo["periodo"]
    fig = px.bar(lungo, x="caricamento", y="righe", color="misura", barmode="group", text="righe",
                 color_discrete_map={"Richieste caricate": BLU, "Richieste scartate": ARANCIO,
                                     "Nuove versioni": ACQUA})
    fig.update_traces(textposition="outside", cliponaxis=False, textfont=dict(color="#14171c", size=11),
                      marker_cornerradius=4, hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>")
    stile_grafico(fig, 300, legenda=True)
    fig.update_yaxes(title=None, range=[0, lungo["righe"].max() * 1.18] if len(lungo) else None)
    fig.update_xaxes(title=None)
    if len(lungo):
        mostra(fig)
    else:
        st.info("Nessun pacchetto incrementale caricato.")

# --- registro --------------------------------------------------------------------
with st.container(key="card_registro"):
    intestazione_card("Registro dei caricamenti")
    righe = "".join(
        f"<tr><td>#{r.id_caricamento}</td><td>{esc(r.tipo)}</td><td>{esc(r.periodo)}</td><td>{esc(r.quando)}</td>"
        f'<td class="num">{num(r.righe_lette)}</td><td class="num">{num(r.righe_caricate)}</td>'
        f'<td class="num">{num(r.righe_scartate)}</td><td class="num">{num(r.nuove_entita)}</td>'
        f'<td class="num">{num(r.nuove_versioni)}</td><td>{badge(r.esito)}</td></tr>'
        for r in caricamenti.itertuples())
    st.markdown('<table class="tabella"><thead><tr><th>#</th><th>Tipo</th><th>Periodo</th><th>Eseguito il</th>'
                '<th class="num">Lette</th><th class="num">Caricate</th><th class="num">Scartate</th>'
                '<th class="num">Nuove entità</th><th class="num">Nuove versioni</th><th>Esito</th></tr></thead>'
                f"<tbody>{righe}</tbody></table><br>", unsafe_allow_html=True)

# --- storico delle anagrafiche ---------------------------------------------------
st.markdown("### Storico delle anagrafiche")
st.caption("Quando cambia un attributo storicizzato (SCD tipo 2) la versione in vigore viene chiusa e se ne apre "
           "una nuova: le richieste passate restano attribuite ai dati validi alla loro data.")

tabelle = {"Clienti": ("dim_cliente", "cliente_id", "sk_cliente", "zona"),
           "Fornitori": ("dim_fornitore", "fornitore_id", "sk_fornitore", "nome || ' · ' || zona"),
           "Operatori": ("dim_operatore", "operatore_id", "sk_operatore", "zona || ' · ' || tipo_attivita")}
schede = []
for nome, (tab, chiave, sk, _) in tabelle.items():
    r = interroga(f"SELECT COUNT(DISTINCT {chiave}) AS entita, COUNT(*) AS versioni FROM {tab} WHERE {sk} > 0").iloc[0]
    schede.append(kpi_card(nome, num(r["entita"]),
                           nota=f"{num(r['versioni'])} versioni · {num(r['versioni'] - r['entita'])} modifiche storicizzate"))
griglia_kpi(schede[:3] + [kpi_card("Attributi storicizzati", "6",
                                   nota="zona cliente; nome, categoria, zona fornitore; zona, attività operatore")])

with st.container(key="card_versioni"):
    sx, dx = st.columns([1, 1.2], vertical_alignment="bottom")
    anagrafica = sx.segmented_control("Anagrafica", list(tabelle), default="Clienti") or "Clienti"
    tab, chiave, sk, descr = tabelle[anagrafica]
    versioni = interroga(f"""SELECT {chiave} AS codice, {descr} AS descrizione, valido_dal, valido_al, corrente,
                                    (SELECT COUNT(*) FROM fact_richieste f WHERE f.{sk} = d.{sk}) AS richieste
                             FROM {tab} d WHERE {chiave} IN
                               (SELECT {chiave} FROM {tab} GROUP BY {chiave} HAVING COUNT(*) > 1)
                             ORDER BY codice, valido_dal""")
    codici = versioni["codice"].unique().tolist()
    codice = dx.selectbox(f"Entità con più versioni ({len(codici)})", codici)
    v = versioni[versioni["codice"] == codice].copy()
    inizio_dati = pd.Timestamp(cfg.DATA_INIZIO)
    fine_dati = pd.to_datetime(interroga("SELECT MAX(data) AS d FROM dim_tempo")["d"].iloc[0])
    v["dal"] = pd.to_datetime(v["valido_dal"]).clip(lower=inizio_dati)
    v["al"] = pd.to_datetime(v["valido_al"].replace(cfg.FINE_VALIDITA, fine_dati.strftime("%Y-%m-%d")))
    v["al"] = v["al"].clip(upper=fine_dati) + pd.Timedelta(days=1)
    v["versione"] = [f"Versione {i + 1}" for i in range(len(v))]
    v["stato"] = v["corrente"].map({1: "Corrente", 0: "Chiusa"})
    intestazione_card(f"Versioni di {codice}",
                      " → ".join(f"<b>{esc(d)}</b>" for d in v["descrizione"]) +
                      f" · richieste collegate: {' / '.join(num(x) for x in v['richieste'])}")
    fig = px.timeline(v, x_start="dal", x_end="al", y="versione", color="stato", text="descrizione",
                      custom_data=["valido_dal", "valido_al", "richieste"],
                      color_discrete_map={"Corrente": BLU, "Chiusa": "#b7c3d3"})
    fig.update_traces(textposition="inside", insidetextanchor="start", textfont=dict(color="#ffffff"),
                      marker_cornerradius=4,
                      hovertemplate="<b>%{text}</b><br>Valida dal %{customdata[0]} al %{customdata[1]}"
                                    "<br>Richieste collegate: %{customdata[2]}<extra></extra>")
    fig.update_traces(selector=dict(name="Chiusa"), textfont_color="#14171c")
    stile_grafico(fig, 90 + 46 * len(v), legenda=True)
    fig.update_yaxes(autorange="reversed", title=None, gridcolor="rgba(0,0,0,0)")
    tacche = pd.date_range(inizio_dati, fine_dati, freq="2MS")
    fig.update_xaxes(title=None, showgrid=True, gridcolor="#f0efec", tickvals=tacche,
                     ticktext=[f"{MESI_BREVI[t.month - 1]} {t.year}" for t in tacche])
    mostra(fig)
    tabella = v[["versione", "descrizione", "valido_dal", "valido_al", "stato", "richieste"]].copy()
    tabella["valido_al"] = tabella["valido_al"].replace(cfg.FINE_VALIDITA, "in vigore")
    tabella["valido_dal"] = tabella["valido_dal"].replace(cfg.INIZIO_VALIDITA, "dall'inizio")
    st.dataframe(tabella.rename(columns={"versione": "Versione", "descrizione": "Attributi", "valido_dal": "Valida dal",
                                         "valido_al": "Valida al", "stato": "Stato", "richieste": "Richieste"}),
                 width="stretch", hide_index=True)

piede_pagina()
