"""Pagina informativa: scopo del progetto, definizioni dei KPI e modello dei dati."""

from pathlib import Path

import streamlit as st

from app.comune import applica_stile, esc, interroga, intestazione_card, num, testata, verifica_warehouse

DOCS = Path(__file__).resolve().parents[2] / "docs"
REPOSITORY = "https://github.com/ChiccoHD/pw21-interventa"

applica_stile()
verifica_warehouse()

caricamenti = interroga("SELECT periodo, righe_caricate FROM etl_caricamenti WHERE esito = 'COMPLETATO' "
                        "ORDER BY id_caricamento")
testata("Informazioni sul progetto",
        "Project Work PW 21 · Corso di laurea L-31 Informatica per le aziende digitali",
        ["Dati sintetici", "Nessuna informazione personale", f"{len(caricamenti)} caricamenti completati"])

with st.container(key="card_scopo"):
    intestazione_card("Che cos'è Interventa")
    st.markdown(
        "Interventa è una startup **fittizia** che, tramite app, organizza interventi a domicilio (idraulica, "
        "elettricità, pulizie, climatizzazione e altri) in sette zone della Sicilia, appoggiandosi a ditte partner "
        "e ai loro operatori. Il prototipo riunisce i dati dei quattro sistemi aziendali (app clienti, archivio dei "
        "fornitori, gestione degli operatori, piattaforma delle richieste) in un data warehouse con schema a stella, "
        "lo aggiorna mese per mese conservando lo storico delle anagrafiche e ne controlla la qualità a ogni "
        "caricamento.")

col_a, col_b = st.columns(2, gap="medium")
with col_a, st.container(key="card_lettura"):
    intestazione_card("Come leggere la dashboard")
    st.markdown(
        "- **Andamento del servizio**: indicatori principali, andamento mensile e analisi per fornitore, zona, "
        "categoria e fascia oraria. I filtri nella barra laterale valgono per tutta la pagina.\n"
        "- **Clienti**: fidelizzazione per mese del primo intervento, frequenza di utilizzo e confronto tra i "
        "canali di iscrizione.\n"
        "- **Variazioni**: con un periodo diverso da *Tutto*, ogni indicatore è confrontato con il periodo "
        "precedente di pari durata; verde indica un miglioramento, rosso un peggioramento.\n"
        "- **Zona**: è quella del cliente, cioè il luogo dell'intervento, valida alla data della richiesta.\n"
        "- **Qualità dei dati**: esito di ogni caricamento, controlli eseguiti e versioni storiche delle "
        "anagrafiche.")

with col_b, st.container(key="card_aggiornamento"):
    intestazione_card("Dati e aggiornamenti")
    righe = "".join(f'<tr><td>{esc(r.periodo)}</td><td class="num">{num(r.righe_caricate)}</td></tr>'
                    for r in caricamenti.itertuples())
    st.markdown('<table class="tabella"><thead><tr><th>Caricamento</th><th class="num">Richieste caricate</th>'
                f"</tr></thead><tbody>{righe}</tbody></table>", unsafe_allow_html=True)
    st.caption("I dati sono prodotti da un generatore con seme casuale fisso: ogni esecuzione della pipeline "
               "restituisce gli stessi risultati.")

with st.container(key="card_definizioni"):
    intestazione_card("Definizioni degli indicatori")
    definizioni = [
        ("Richieste totali", "Tutte le richieste valide ricevute nel periodo, comprese le annullate."),
        ("Incassi", "Somma degli importi delle richieste erogate (completate o in ritardo)."),
        ("Tempo medio di erogazione", "Media dei minuti tra la richiesta e la chiusura dell'intervento, "
                                      "calcolata sulle sole richieste erogate."),
        ("Clienti attivi", "Clienti distinti, contati per codice, con almeno una richiesta erogata nel periodo."),
        ("Clienti che tornano", "Quota dei clienti attivi con almeno due richieste erogate nel periodo."),
        ("Richieste annullate", "Quota delle richieste annullate sul totale delle richieste."),
        ("Erogate in ritardo", "Quota delle richieste erogate oltre il tempo massimo previsto per la categoria."),
        ("Scontrino medio", "Incassi divisi per il numero di richieste erogate."),
    ]
    righe = "".join(f"<tr><td><b>{esc(k)}</b></td><td>{esc(v)}</td></tr>" for k, v in definizioni)
    st.markdown('<table class="tabella"><thead><tr><th>Indicatore</th><th>Definizione</th></tr></thead>'
                f"<tbody>{righe}</tbody></table><br>", unsafe_allow_html=True)

with st.container(key="card_modello"):
    intestazione_card("Modello dei dati",
                      "Una riga della tabella dei fatti per ogni richiesta, collegata a quattro dimensioni; "
                      "clienti, fornitori e operatori conservano lo storico delle modifiche.")
    if (DOCS / "schema_stella.png").exists():
        st.image(str(DOCS / "schema_stella.png"), width="stretch")

st.markdown(f'<p class="piede-pagina">Codice sorgente, dati e documentazione: '
            f'<a href="{REPOSITORY}" target="_blank">{REPOSITORY}</a></p>', unsafe_allow_html=True)
