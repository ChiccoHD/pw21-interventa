# Registro delle modifiche

Le versioni seguono lo schema MAGGIORE.MINORE.CORREZIONE.

## 1.6.0 · 22/10/2026
- Nuova pagina "Clienti": fidelizzazione per mese del primo intervento (analisi di coorte), clienti per numero di
  richieste erogate e confronto tra i canali di iscrizione, con filtro per zona.
- Scheda delle categorie con due viste: richieste oppure tempo medio confrontato con il tempo massimo previsto e
  quota di interventi in ritardo.
- Tabelle di dettaglio formattate: barre di quota nelle celle, importi in euro, date e orari in formato italiano.
- Nuovi test per la pagina Clienti e per la vista dei tempi (25 test in totale).

## 1.5.0 · 17/10/2026
- Scelta rapida del periodo nella barra laterale: tutto, anno, ultimi 6 mesi, ultimi 3 mesi o intervallo personalizzato.
- Nuova pagina "Informazioni" con lo scopo del progetto, la guida alla lettura e le definizioni dei KPI.
- Esportazione delle analisi filtrate in Excel, un foglio per tabella.
- Aggiornamento alle nuove API di Streamlit (`width="stretch"` al posto di `use_container_width`, deprecato).
- Test della dashboard con `streamlit.testing`: ogni pagina si apre senza errori, anche con i filtri applicati.
- Numero di versione nella barra laterale e questo registro delle modifiche.

## 1.4.0 · 14/10/2026
- Test automatici su GitHub Actions a ogni modifica, con badge nel README.
- Pubblicazione della dashboard su Streamlit Community Cloud.
- Ricostruzione automatica del warehouse al primo avvio, se assente.

## 1.3.0 · 14/10/2026
- Nuova veste grafica: intestazione, schede KPI con andamento mensile, grafici in schede con commento calcolato.
- Pagina "Qualità dei dati" con banner di esito, badge di stato e linea del tempo delle versioni storiche.

## 1.2.0 · 12/10/2026
- Caricamento incrementale di pacchetti mensili, in transazione e idempotente, con registro dei caricamenti.
- Storico delle anagrafiche (SCD tipo 1 e 2) per clienti, fornitori e operatori.
- Catalogo di 14 controlli di qualità con soglie di avviso e di errore; i caricamenti in errore vengono respinti.

## 1.1.0 · 12/10/2026
- Pubblicazione del progetto su GitHub.
- Progetto rinominato in Interventa; pulizia del codice e dei commenti.
- Diagramma del flusso dei dati.

## 1.0.0 · 11/10/2026
- Prima versione: generatore di dati sintetici, ETL, data warehouse a stella in SQLite, query dei KPI,
  dashboard Streamlit e test automatici.
