# Interventa · Data warehouse e dashboard per una startup di servizi on-demand

[![Test](https://github.com/ChiccoHD/pw21-interventa/actions/workflows/test.yml/badge.svg)](https://github.com/ChiccoHD/pw21-interventa/actions/workflows/test.yml)
[![Dashboard online](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://pw21-interventa.streamlit.app)

Project Work, traccia **PW 21**: *Progettare l'analisi dei dati per una startup digitale di servizi on-demand*
(Tema 1 — La digitalizzazione dell'impresa · Corso di laurea L-31, Informatica per le aziende digitali).

**Interventa** è una startup **fittizia** che, tramite app, mette in contatto clienti che hanno bisogno di un
intervento in casa (idraulico, elettricista, pulizie, climatizzazione, …) con ditte partner (fornitori) e i loro
operatori, in sette zone della Sicilia. Il prototipo raccoglie i dati sparsi dei quattro sistemi aziendali in un
unico archivio per l'analisi, lo aggiorna mese per mese conservando lo storico delle anagrafiche, ne controlla
la qualità e presenta i risultati in una dashboard.

![Flusso dei dati](docs/flusso_dati.png)

## Prova online

La dashboard è pubblicata su Streamlit Community Cloud e si apre dal browser, senza installare nulla:
**<https://pw21-interventa.streamlit.app>**. Alla prima apertura dopo un periodo di inattività il servizio
può impiegare qualche secondo a ripartire.

A ogni modifica del codice GitHub Actions esegue l'intera pipeline e i test automatici
(`.github/workflows/test.yml`); l'esito è mostrato dal badge in cima a questa pagina.

## Avvio rapido in locale (circa 3 minuti)

Requisiti: Python 3.10 o successivo.

```bash
git clone https://github.com/ChiccoHD/pw21-interventa.git
cd pw21-interventa
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

python esegui_tutto.py          # genera i dati, carica il warehouse, applica i pacchetti mensili e apre la dashboard
```

La dashboard si apre nel browser all'indirizzo <http://localhost:8501> (per chiuderla: Ctrl+C nel terminale).

Se PowerShell blocca l'attivazione dell'ambiente ("esecuzione di script disabilitata"), eseguire una volta
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

I singoli passi si possono anche eseguire uno alla volta:

```bash
python -m src.genera_dati          # 1. dataset iniziale (2025) e pacchetti mensili in data/raw/
python -m src.etl                  # 2. caricamento iniziale: ricrea il data warehouse
python -m src.etl --incrementale   # 3. carica i pacchetti mensili non ancora caricati
python -m src.kpi                  # 4. indicatori calcolati con le query SQL
python -m src.qualita              # 5. controlli di qualità sul warehouse attuale
streamlit run app/dashboard.py     # 6. dashboard
python -m pytest                   # test automatici sull'intera pipeline
```

## Parametri di riproducibilità

Con gli stessi parametri si ottengono esattamente gli stessi dati (generatore pseudo-casuale con seme fisso).

| Parametro | Default | Opzione |
|---|---|---|
| Seme casuale | 2 | `--seed` |
| Dataset iniziale: clienti / fornitori / operatori / richieste | 500 / 300 / 350 / 600 | `--clienti` `--fornitori` `--operatori` `--richieste` |
| Periodo del dataset iniziale | 01/01/2025 – 31/12/2025 | `src/config.py` |
| Pacchetti mensili successivi | 2 (gennaio e febbraio 2026) | `--incrementi` |
| Quota di righe con difetti voluti | 3% | `--pulito` per disattivarli |

Esempio: `python -m src.genera_dati --seed 7 --incrementi 4 --pulito`

## Struttura del progetto

```
├── src/
│   ├── config.py          parametri: zone, categorie, prezzi, stagionalità, storico, pacchetti mensili
│   ├── genera_dati.py     generatore dei dati sintetici (dataset iniziale e pacchetti mensili)
│   ├── etl.py             caricamento iniziale e incrementale, storico delle anagrafiche
│   ├── qualita.py         catalogo dei controlli di qualità
│   ├── kpi.py             esegue le query di sql/kpi.sql
│   └── metriche.py        calcolo dei KPI per la dashboard
├── sql/
│   ├── schema.sql         schema a stella, registro dei caricamenti, esiti dei controlli
│   └── kpi.sql            query degli indicatori
├── app/
│   ├── dashboard.py       avvio e navigazione della dashboard
│   ├── comune.py          funzioni condivise
│   └── pagine/            "Andamento del servizio", "Clienti", "Qualità dei dati" e "Informazioni"
├── tests/                 test automatici (pytest)
├── .github/workflows/     esecuzione automatica dei test su GitHub
├── tools/screenshot.py    screenshot della dashboard (Playwright, opzionale)
├── data/
│   ├── raw/               dataset iniziale (CSV) e incrementi/AAAA-MM/ con i pacchetti mensili
│   ├── warehouse/         file SQLite del data warehouse
│   └── scarti/            righe scartate e report di ogni caricamento
└── docs/                  diagrammi e screenshot
```

## Il modello dei dati

![Schema a stella](docs/schema_stella.png)

- **Tabella dei fatti `fact_richieste`**: una riga per ogni richiesta di servizio. Misure: importo,
  tempo di erogazione (minuti tra la richiesta e la chiusura dell'intervento), indicatori 0/1 di erogazione,
  annullamento e ritardo. Ogni riga indica anche il caricamento che l'ha inserita.
- **Dimensioni**: `dim_cliente`, `dim_fornitore`, `dim_operatore`, `dim_tempo` (calendario giornaliero completo).
  Ogni dimensione ha una **chiave surrogata** (`sk_*`) distinta dal codice di origine e un membro
  *Sconosciuto* (chiave 0) usato quando il dato manca alla fonte.
- **Zona di analisi**: la zona del cliente, cioè il luogo in cui il servizio viene erogato.

### Storico delle anagrafiche (Slowly Changing Dimensions)

| Dimensione | Tipo 2: si conserva la versione precedente | Tipo 1: si sovrascrive |
|---|---|---|
| Cliente | zona (trasloco) | data e canale di iscrizione |
| Fornitore | nome, categoria, zona (cambio di ragione sociale o di sede) | — |
| Operatore | zona, tipo di attività (trasferimento) | anni e fascia di esperienza |

Ogni versione ha un intervallo di validità (`valido_dal`, `valido_al`) e il flag `corrente`. Quando un attributo di
tipo 2 cambia, la versione in vigore viene chiusa al giorno precedente e se ne apre una nuova: le richieste
passate restano collegate alla versione valida alla loro data. Ad esempio, un cliente che a febbraio si trasferisce
da Trapani a Palermo conserva le richieste di gennaio su Trapani e quelle di febbraio su Palermo.

## Cosa fa l'ETL

**Caricamento iniziale** (`python -m src.etl`): ricrea il warehouse e carica il dataset del 2025.
**Caricamento incrementale** (`python -m src.etl --incrementale`): applica, in ordine, i pacchetti mensili di
`data/raw/incrementi/` non ancora caricati. Ogni pacchetto contiene le anagrafiche aggiornate e le richieste del mese.
L'ETL individua le entità nuove, le modifiche da storicizzare e le richieste non ancora presenti. Ricaricare
lo stesso pacchetto non duplica nulla.

Ogni caricamento è una **transazione**: al termine si eseguono i controlli di qualità e, se almeno uno dà
**ERRORE**, tutte le modifiche vengono annullate e il caricamento risulta **RESPINTO** nel registro
`etl_caricamenti`.

| Problema nei dati di origine | Trattamento |
|---|---|
| Maiuscole e spazi incoerenti (`" PALERMO"`, `"catania  "`) | ricondotti al valore canonico |
| Importi con la virgola (`"89,50"`) | convertiti in numero |
| Date in due formati (`2025-03-14 10:30` / `14/03/2025 10:30`) | entrambi riconosciuti |
| Stati scritti in modo diverso (`"Completata"`, `"annullato"`, …) | normalizzati in `completata` / `in_ritardo` / `annullata` |
| Righe duplicate | rimosse |
| Importi negativi, fornitori o clienti inesistenti | scartati e salvati in `data/scarti/` con il motivo |
| Operatore mancante | collegato al membro *Sconosciuto*, la richiesta resta nelle analisi |

Correzioni, scarti e modifiche storicizzate sono registrati anche nel warehouse (tabella `etl_eventi`).

## Controlli di qualità

Il catalogo in `src/qualita.py` contiene 14 regole. Ognuna restituisce il numero di violazioni sul totale; la
percentuale è confrontata con una soglia di **avviso** e una di **errore**. Gli esiti di ogni caricamento sono
salvati nella tabella `dq_risultati`.

| Area | Controlli |
|---|---|
| Integrità | richiesta unica, riferimenti validi alle dimensioni, calendario senza giorni mancanti |
| Coerenza | annullate senza importo né tempo, erogate con tempo, incassi caricati uguali a quelli dei dati validi |
| Plausibilità | tempo di erogazione tra 15 e 600 minuti, importo tra 20 e 500 euro, operatore registrato |
| Storico | una sola versione corrente, intervalli non sovrapposti, ogni richiesta collegata alla versione valida |
| Processo | quota di righe scartate dall'ETL, scostamento del volume mensile dalla media dei tre mesi precedenti |

## Indicatori (definizioni)

| KPI | Definizione |
|---|---|
| Richieste totali | tutte le richieste valide, comprese le annullate |
| Incassi | somma degli importi delle richieste erogate (completate o in ritardo) |
| Tempo medio di erogazione | media dei minuti tra richiesta e chiusura, sulle richieste erogate |
| Clienti attivi | clienti distinti (per codice) con almeno una richiesta erogata nel periodo |
| Clienti che tornano | clienti con 2 o più richieste erogate ÷ clienti attivi |
| % annullate / % in ritardo | sul totale delle richieste / sulle richieste erogate |

Le stesse definizioni sono implementate in SQL (`sql/kpi.sql`) e in pandas (`src/metriche.py`);
un test verifica che diano risultati identici.

## Dashboard

**Andamento del servizio**: indicatori principali, andamento nel tempo, primi 5 fornitori per incassi, richieste
per zona e per categoria (richieste oppure tempi rispetto al massimo previsto), distribuzione per giorno e ora. Filtri: periodo (con scelte rapide), zona, categoria di servizio. Le
variazioni dei KPI sono confrontate con il periodo precedente di pari durata. Le analisi filtrate si
possono scaricare in CSV o in Excel, un foglio per tabella.

![Dashboard](docs/screenshot/01_dashboard_completa.png)

**Clienti**: fidelizzazione per mese del primo intervento (analisi di coorte), clienti per numero di richieste
erogate e confronto tra i canali di iscrizione.

![Clienti](docs/screenshot/05_clienti.png)

**Qualità dei dati**: esito di ogni caricamento, controlli eseguiti con le relative soglie, correzioni e scarti
dell'ETL, registro dei caricamenti e versioni storiche di clienti, fornitori e operatori.

![Qualità dei dati](docs/screenshot/04_qualita_dati.png)

**Informazioni**: scopo del progetto, guida alla lettura, definizioni dei KPI e modello dei dati.

## Test automatici

`python -m pytest` esegue 25 test che verificano, tra l'altro: riproducibilità del generatore, assenza di dati
personali, integrità del warehouse, coerenza tra KPI in SQL e in Python, storico di tipo 1 e 2, idempotenza del
caricamento incrementale e respingimento, con annullamento completo, di un pacchetto con troppi errori.
Altri test aprono ogni pagina della dashboard, anche con i filtri applicati, e verificano che non ci siano errori.

Le modifiche tra una versione e l'altra sono elencate in [CHANGELOG.md](CHANGELOG.md).

## Privacy

Tutti i dati sono generati dal programma. I clienti sono identificati solo da un codice, una zona,
una data di iscrizione e il canale di iscrizione: non esistono nomi, indirizzi, telefoni o email.
I nomi dei fornitori sono combinazioni casuali di parole.
