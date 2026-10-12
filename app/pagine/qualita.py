"""Pagina di controllo: registro dei caricamenti, controlli di qualità e storico delle anagrafiche."""

import pandas as pd
import plotly.express as px
import streamlit as st

from app.comune import COLORE, COLORE_2, GRIGIO, colora_esito, interroga, num, stile, verifica_warehouse

verifica_warehouse()

st.title("Qualità dei dati e caricamenti")
st.caption("Esito di ogni caricamento dell'ETL, controlli automatici eseguiti e modifiche "
           "storicizzate nelle anagrafiche.")

caricamenti = interroga("SELECT * FROM etl_caricamenti ORDER BY id_caricamento")
risultati = interroga("SELECT * FROM dq_risultati")
eventi = interroga("SELECT * FROM etl_eventi")

etichette = {r.id_caricamento: f"#{r.id_caricamento} · {r.tipo} {r.periodo} · {r.esito}"
             for r in caricamenti.itertuples()}
scelto = st.selectbox("Caricamento", list(etichette), index=len(etichette) - 1,
                      format_func=etichette.get)
car = caricamenti.set_index("id_caricamento").loc[scelto]
ris = risultati[risultati["id_caricamento"] == scelto]
eve = eventi[eventi["id_caricamento"] == scelto]

if car["esito"] == "COMPLETATO":
    st.success(f"Caricamento {car['tipo']} {car['periodo']} completato e confermato nel warehouse.")
else:
    st.error(f"Caricamento {car['tipo']} {car['periodo']} respinto: almeno un controllo è in errore, "
             "il warehouse è rimasto allo stato precedente.")

c2, c3, c4, c5 = st.columns(4)
c2.metric("Richieste caricate", num(car["righe_caricate"]), help="Nuove righe nella tabella dei fatti.")
c3.metric("Richieste scartate", num(car["righe_scartate"]),
          help=f"Su {num(car['righe_lette'])} righe lette dal file delle richieste.")
c4.metric("Nuove versioni", num(car["nuove_versioni"]),
          help="Modifiche ad attributi storicizzati (SCD tipo 2) di clienti, fornitori e operatori.")
conteggi = ris["esito"].value_counts()
c5.metric("Controlli superati", f"{conteggi.get('OK', 0)} su {len(ris)}",
          help=f"Avvisi: {conteggi.get('AVVISO', 0)} · Errori: {conteggi.get('ERRORE', 0)}")

st.subheader("Controlli di qualità")
tabella = (ris[["descrizione", "violazioni", "totale", "percentuale", "soglia_avviso", "soglia_errore", "esito"]]
           .rename(columns={"descrizione": "Controllo", "violazioni": "Violazioni", "totale": "Su",
                            "percentuale": "%", "soglia_avviso": "Soglia avviso %",
                            "soglia_errore": "Soglia errore %", "esito": "Esito"}))
st.dataframe(tabella.style.map(colora_esito, subset=["Esito"])
             .format({"Violazioni": num, "Su": num, "%": lambda x: num(x, 2),
                      "Soglia avviso %": num, "Soglia errore %": num}),
             use_container_width=True, hide_index=True, height=35 * (len(tabella) + 1) + 3)

col_a, col_b = st.columns(2)
pulizia = eve[eve["tipo"].isin(["correzione", "scarto"])].copy()
if len(pulizia):
    pulizia["voce"] = pulizia["tabella"] + " · " + pulizia["descrizione"]
    pulizia = pulizia.sort_values("righe")
    fig = px.bar(pulizia, x="righe", y="voce", color="tipo", orientation="h", text="righe",
                 color_discrete_map={"correzione": COLORE, "scarto": COLORE_2},
                 title="Correzioni e scarti dell'ETL", labels={"voce": "", "righe": "Righe", "tipo": ""})
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(legend=dict(orientation="h", y=-0.15, x=1, xanchor="right"))
    col_a.plotly_chart(stile(fig, 420), use_container_width=True)

storia = caricamenti.assign(caricamento=lambda d: "#" + d["id_caricamento"].astype(str) + " " + d["periodo"])
fig = px.bar(storia, x="caricamento", y=["righe_caricate", "righe_scartate", "nuove_versioni"],
             barmode="group", color_discrete_sequence=[COLORE, COLORE_2, GRIGIO],
             title="Storico dei caricamenti", labels={"caricamento": "", "value": "Righe", "variable": ""})
fig.for_each_trace(lambda t: t.update(name={"righe_caricate": "Richieste caricate",
                                            "righe_scartate": "Richieste scartate",
                                            "nuove_versioni": "Nuove versioni"}[t.name]))
fig.update_layout(legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
col_b.plotly_chart(stile(fig, 420), use_container_width=True)

st.subheader("Registro dei caricamenti")
caricamenti["eseguito_il"] = pd.to_datetime(caricamenti["eseguito_il"]).dt.strftime("%d/%m/%Y %H:%M")
registro = caricamenti[["id_caricamento", "tipo", "periodo", "eseguito_il", "righe_lette", "righe_caricate",
                        "righe_scartate", "nuove_entita", "nuove_versioni", "esito"]].rename(columns={
    "id_caricamento": "#", "tipo": "Tipo", "periodo": "Periodo", "eseguito_il": "Eseguito il",
    "righe_lette": "Richieste lette", "righe_caricate": "Caricate", "righe_scartate": "Scartate",
    "nuove_entita": "Nuove entità", "nuove_versioni": "Nuove versioni", "esito": "Esito"})
st.dataframe(registro.style.map(colora_esito, subset=["Esito"])
             .format({c: num for c in ["Richieste lette", "Caricate", "Scartate", "Nuove entità", "Nuove versioni"]}),
             use_container_width=True, hide_index=True)

st.subheader("Storico delle anagrafiche (SCD tipo 2)")
st.caption("Quando cambia un attributo storicizzato (zona del cliente; nome, categoria o zona del fornitore; "
           "zona o attività dell'operatore) si chiude la versione precedente e se ne apre una nuova: "
           "le richieste passate restano attribuite ai dati validi alla loro data.")
riepilogo = interroga("""
    SELECT 'Clienti' AS Anagrafica, COUNT(DISTINCT cliente_id) AS "Entità", COUNT(*) AS Versioni
    FROM dim_cliente WHERE sk_cliente > 0
    UNION ALL SELECT 'Fornitori', COUNT(DISTINCT fornitore_id), COUNT(*) FROM dim_fornitore WHERE sk_fornitore > 0
    UNION ALL SELECT 'Operatori', COUNT(DISTINCT operatore_id), COUNT(*) FROM dim_operatore WHERE sk_operatore > 0""")
riepilogo["Modifiche storicizzate"] = riepilogo["Versioni"] - riepilogo["Entità"]
st.dataframe(riepilogo, use_container_width=True, hide_index=True)

scelta = st.radio("Mostra le versioni di", ["Clienti", "Fornitori", "Operatori"], horizontal=True)
query = {
    "Clienti": """SELECT cliente_id AS Codice, zona AS Zona, valido_dal AS "Valido dal", valido_al AS "Valido al",
                         corrente AS Corrente FROM dim_cliente
                  WHERE cliente_id IN (SELECT cliente_id FROM dim_cliente GROUP BY cliente_id HAVING COUNT(*) > 1)""",
    "Fornitori": """SELECT fornitore_id AS Codice, nome AS Nome, categoria AS Categoria, zona AS Zona,
                           valido_dal AS "Valido dal", valido_al AS "Valido al", corrente AS Corrente FROM dim_fornitore
                    WHERE fornitore_id IN (SELECT fornitore_id FROM dim_fornitore GROUP BY fornitore_id HAVING COUNT(*) > 1)""",
    "Operatori": """SELECT operatore_id AS Codice, zona AS Zona, tipo_attivita AS "Attività",
                           valido_dal AS "Valido dal", valido_al AS "Valido al", corrente AS Corrente FROM dim_operatore
                    WHERE operatore_id IN (SELECT operatore_id FROM dim_operatore GROUP BY operatore_id HAVING COUNT(*) > 1)""",
}[scelta]
versioni = interroga(query + ' ORDER BY Codice, "Valido dal"')
versioni["Valido al"] = versioni["Valido al"].replace("9999-12-31", "—")
versioni["Corrente"] = versioni["Corrente"].map({1: "sì", 0: "no"})
st.dataframe(versioni, use_container_width=True, hide_index=True)
