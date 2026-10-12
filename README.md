# Interventa · Data warehouse e dashboard per una startup di servizi on-demand

Project Work, traccia **PW 21**: *Progettare l'analisi dei dati per una startup digitale di servizi on-demand*
(Tema 1 — La digitalizzazione dell'impresa · Corso di laurea L-31, Informatica per le aziende digitali).

**Interventa** è una startup **fittizia** che, tramite app, mette in contatto clienti che hanno bisogno di un
intervento in casa (idraulico, elettricista, pulizie, climatizzazione, …) con ditte partner (fornitori) e i loro
operatori, in sette zone della Sicilia. Il prototipo raccoglie i dati sparsi dei quattro sistemi aziendali in un
unico archivio per l'analisi e li presenta in una dashboard.

```
genera_dati.py ──► data/raw/*.csv ──► etl.py ──► data/warehouse/interventa_dw.sqlite ──► dashboard.py
 (dati sintetici)    (4 file CSV)    (pulizia)        (schema a stella)                   (Streamlit)
                                         └──► data/scarti/  (righe scartate + report qualità)
```

## Avvio rapido (circa 3 minuti)

Requisiti: Python 3.10 o successivo.

```bash
git clone https://github.com/ChiccoHD/pw21-interventa.git
cd pw21-interventa
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

python esegui_tutto.py          # genera i dati, esegue l'ETL, calcola i KPI e apre la dashboard
```

La dashboard si apre nel browser all'indirizzo <http://localhost:8501> (per chiuderla: Ctrl+C nel terminale).

Se PowerShell blocca l'attivazione dell'ambiente ("esecuzione di script disabilitata"), eseguire una volta
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

I singoli passi si possono anche eseguire uno alla volta:

```bash
python -m src.genera_dati        # 1. crea i CSV in data/raw/
python -m src.etl                # 2. pulisce i dati e crea il data warehouse SQLite
python -m src.kpi                # 3. stampa gli indicatori calcolati con le query SQL
streamlit run app/dashboard.py   # 4. apre la dashboard
python -m pytest                 # controlli automatici sull'intera pipeline
```

## Parametri di riproducibilità

Con gli stessi parametri si ottengono esattamente gli stessi dati (generatore pseudo-casuale con seme fisso).

| Parametro | Default | Opzione |
|---|---|---|
| Seme casuale | 2 | `--seed` |
| Clienti / fornitori / operatori / richieste | 500 / 300 / 350 / 600 | `--clienti` `--fornitori` `--operatori` `--richieste` |
| Periodo delle richieste | 01/01/2025 – 31/12/2025 | `src/config.py` |
| Quota di righe con difetti voluti | 3% | `--pulito` per disattivarli |

Esempio: `python -m src.genera_dati --seed 7 --richieste 450 --pulito`

## Struttura del progetto

```
├── src/
│   ├── config.py          parametri: zone, categorie, prezzi, stagionalità, fasce orarie
│   ├── genera_dati.py     generatore dei dati sintetici (CSV)
│   ├── etl.py             Estrazione, Trasformazione e Caricamento
│   ├── kpi.py             esegue le query di sql/kpi.sql
│   └── metriche.py        calcolo dei KPI per la dashboard
├── sql/
│   ├── schema.sql         schema a stella (tabelle, chiavi, indici, vista v_richieste)
│   └── kpi.sql            query degli indicatori
├── app/dashboard.py       dashboard Streamlit
├── tests/                 test automatici (pytest)
├── tools/screenshot.py    screenshot della dashboard (Playwright, opzionale)
├── data/
│   ├── raw/               CSV generati (dataset condivisibile)
│   ├── warehouse/         file SQLite del data warehouse
│   └── scarti/            righe scartate dall'ETL e report di qualità
└── docs/                  diagrammi e screenshot
```

## Il modello dei dati

![Schema a stella](docs/schema_stella.png)

- **Tabella dei fatti `fact_richieste`** — una riga per ogni richiesta di servizio. Misure: importo,
  tempo di erogazione (minuti tra la richiesta e la chiusura dell'intervento), indicatori 0/1 di erogazione,
  annullamento e ritardo.
- **Dimensioni** — `dim_cliente`, `dim_fornitore`, `dim_operatore`, `dim_tempo` (calendario giornaliero completo).
  Ogni dimensione ha una **chiave surrogata** (`sk_*`) distinta dal codice di origine e un membro
  *Sconosciuto* (chiave 0) usato quando il dato manca alla fonte.
- **Zona di analisi** = zona del cliente, cioè il luogo in cui il servizio viene erogato.

## Cosa fa l'ETL

| Problema nei dati di origine | Trattamento |
|---|---|
| Maiuscole e spazi incoerenti (`" PALERMO"`, `"catania  "`) | ricondotti al valore canonico |
| Importi con la virgola (`"89,50"`) | convertiti in numero |
| Date in due formati (`2025-03-14 10:30` / `14/03/2025 10:30`) | entrambi riconosciuti |
| Stati scritti in modo diverso (`"Completata"`, `"annullato"`, …) | normalizzati in `completata` / `in_ritardo` / `annullata` |
| Righe duplicate | rimosse |
| Importi negativi, fornitori o clienti inesistenti | scartati e registrati in `data/scarti/righe_scartate.csv` con il motivo |
| Operatore mancante | collegato al membro *Sconosciuto*, la richiesta resta nelle analisi |

Al termine l'ETL verifica l'integrità referenziale e che il totale degli incassi caricati coincida con quello
dei dati validi. Il riepilogo è in `data/scarti/report_qualita.txt`.

## Indicatori (definizioni)

| KPI | Definizione |
|---|---|
| Richieste totali | tutte le richieste valide, comprese le annullate |
| Incassi | somma degli importi delle richieste erogate (completate o in ritardo) |
| Tempo medio di erogazione | media dei minuti tra richiesta e chiusura, sulle richieste erogate |
| Clienti attivi | clienti distinti con almeno una richiesta erogata nel periodo |
| Clienti che tornano | clienti con 2 o più richieste erogate ÷ clienti attivi |
| % annullate / % in ritardo | sul totale delle richieste / sulle richieste erogate |

Le stesse definizioni sono implementate in SQL (`sql/kpi.sql`) e in pandas (`src/metriche.py`);
un test verifica che diano risultati identici.

## Dashboard

![Dashboard](docs/screenshot/01_dashboard_completa.png)

Filtri: periodo, zona, categoria di servizio; andamento per settimana o per mese. Le variazioni dei KPI sono
confrontate con il periodo precedente di pari durata (se presente nei dati).

## Privacy

Tutti i dati sono generati dal programma. I clienti sono identificati solo da un codice, una zona,
una data di iscrizione e il canale di iscrizione: non esistono nomi, indirizzi, telefoni o email.
I nomi dei fornitori sono combinazioni casuali di parole.
