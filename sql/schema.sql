-- Data warehouse Interventa: schema a stella (SQLite).
-- Grana dei fatti: una riga per richiesta. Chiave 0 = membro "Sconosciuto".
-- Dimensioni con storico (SCD tipo 2): ogni versione ha un intervallo di validità
-- [valido_dal, valido_al] e il flag corrente.

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_richieste;
DROP TABLE IF EXISTS dq_risultati;
DROP TABLE IF EXISTS etl_eventi;
DROP TABLE IF EXISTS etl_caricamenti;
DROP TABLE IF EXISTS fact_richieste;
DROP TABLE IF EXISTS dim_cliente;
DROP TABLE IF EXISTS dim_fornitore;
DROP TABLE IF EXISTS dim_operatore;
DROP TABLE IF EXISTS dim_tempo;

CREATE TABLE dim_cliente (
    sk_cliente         INTEGER PRIMARY KEY,
    cliente_id         TEXT    NOT NULL,
    zona               TEXT    NOT NULL,
    data_iscrizione    TEXT,
    anno_iscrizione    INTEGER,
    canale_iscrizione  TEXT,
    valido_dal         TEXT    NOT NULL,
    valido_al          TEXT    NOT NULL,
    corrente           INTEGER NOT NULL,
    UNIQUE (cliente_id, valido_dal)
);

CREATE TABLE dim_fornitore (
    sk_fornitore       INTEGER PRIMARY KEY,
    fornitore_id       TEXT    NOT NULL,
    nome               TEXT    NOT NULL,
    categoria          TEXT    NOT NULL,
    zona               TEXT    NOT NULL,
    valido_dal         TEXT    NOT NULL,
    valido_al          TEXT    NOT NULL,
    corrente           INTEGER NOT NULL,
    UNIQUE (fornitore_id, valido_dal)
);

CREATE TABLE dim_operatore (
    sk_operatore       INTEGER PRIMARY KEY,
    operatore_id       TEXT    NOT NULL,
    zona               TEXT    NOT NULL,
    tipo_attivita      TEXT    NOT NULL,
    anni_esperienza    INTEGER,
    fascia_esperienza  TEXT,
    valido_dal         TEXT    NOT NULL,
    valido_al          TEXT    NOT NULL,
    corrente           INTEGER NOT NULL,
    UNIQUE (operatore_id, valido_dal)
);

CREATE TABLE dim_tempo (
    sk_tempo           INTEGER PRIMARY KEY,       -- AAAAMMGG
    data               TEXT    NOT NULL UNIQUE,
    anno               INTEGER NOT NULL,
    trimestre          INTEGER NOT NULL,
    mese               INTEGER NOT NULL,
    nome_mese          TEXT    NOT NULL,
    anno_mese          TEXT    NOT NULL,
    settimana_iso      INTEGER NOT NULL,
    giorno_mese        INTEGER NOT NULL,
    giorno_settimana   INTEGER NOT NULL,
    nome_giorno        TEXT    NOT NULL,
    is_weekend         INTEGER NOT NULL
);

CREATE TABLE etl_caricamenti (
    id_caricamento     INTEGER PRIMARY KEY,
    tipo               TEXT    NOT NULL CHECK (tipo IN ('iniziale','incrementale')),
    periodo            TEXT    NOT NULL,
    eseguito_il        TEXT    NOT NULL,
    righe_lette        INTEGER,
    righe_caricate     INTEGER,
    righe_scartate     INTEGER,
    nuove_entita       INTEGER,
    nuove_versioni     INTEGER,
    esito              TEXT    NOT NULL CHECK (esito IN ('COMPLETATO','RESPINTO'))
);

CREATE TABLE fact_richieste (
    sk_richiesta          INTEGER PRIMARY KEY,
    richiesta_id          TEXT    NOT NULL UNIQUE,
    sk_cliente            INTEGER NOT NULL REFERENCES dim_cliente(sk_cliente),
    sk_fornitore          INTEGER NOT NULL REFERENCES dim_fornitore(sk_fornitore),
    sk_operatore          INTEGER NOT NULL REFERENCES dim_operatore(sk_operatore),
    sk_tempo              INTEGER NOT NULL REFERENCES dim_tempo(sk_tempo),
    id_caricamento        INTEGER NOT NULL REFERENCES etl_caricamenti(id_caricamento),
    ora                   INTEGER NOT NULL CHECK (ora BETWEEN 0 AND 23),
    fascia_oraria         TEXT    NOT NULL,
    stato                 TEXT    NOT NULL CHECK (stato IN ('completata','in_ritardo','annullata')),
    importo               REAL    NOT NULL CHECK (importo >= 0),
    tempo_erogazione_min  INTEGER,
    flag_erogata          INTEGER NOT NULL,
    flag_annullata        INTEGER NOT NULL,
    flag_ritardo          INTEGER NOT NULL
);

CREATE INDEX ix_fact_tempo     ON fact_richieste(sk_tempo);
CREATE INDEX ix_fact_cliente   ON fact_richieste(sk_cliente);
CREATE INDEX ix_fact_fornitore ON fact_richieste(sk_fornitore);
CREATE INDEX ix_fact_operatore ON fact_richieste(sk_operatore);

-- Correzioni e scarti registrati dall'ETL a ogni caricamento
CREATE TABLE etl_eventi (
    id_caricamento     INTEGER NOT NULL,
    tabella            TEXT    NOT NULL,
    tipo               TEXT    NOT NULL CHECK (tipo IN ('correzione','scarto','storico')),
    descrizione        TEXT    NOT NULL,
    righe              INTEGER NOT NULL
);

-- Esiti dei controlli di qualità (src/qualita.py)
CREATE TABLE dq_risultati (
    id_caricamento     INTEGER NOT NULL,
    regola             TEXT    NOT NULL,
    descrizione        TEXT    NOT NULL,
    violazioni         REAL    NOT NULL,
    totale             REAL    NOT NULL,
    percentuale        REAL    NOT NULL,
    soglia_avviso      REAL    NOT NULL,
    soglia_errore      REAL    NOT NULL,
    esito              TEXT    NOT NULL CHECK (esito IN ('OK','AVVISO','ERRORE'))
);

-- Vista usata dalla dashboard: ogni richiesta con gli attributi validi alla sua data
CREATE VIEW v_richieste AS
SELECT
    f.richiesta_id,
    t.data, t.anno, t.trimestre, t.mese, t.nome_mese, t.anno_mese,
    t.settimana_iso, t.giorno_settimana, t.nome_giorno, t.is_weekend,
    f.ora, f.fascia_oraria,
    c.cliente_id, c.zona, c.canale_iscrizione,
    fo.fornitore_id, fo.nome AS fornitore, fo.categoria,
    o.operatore_id, o.tipo_attivita, o.fascia_esperienza,
    f.stato, f.importo, f.tempo_erogazione_min,
    f.flag_erogata, f.flag_annullata, f.flag_ritardo
FROM fact_richieste f
JOIN dim_tempo     t  ON t.sk_tempo     = f.sk_tempo
JOIN dim_cliente   c  ON c.sk_cliente   = f.sk_cliente
JOIN dim_fornitore fo ON fo.sk_fornitore = f.sk_fornitore
JOIN dim_operatore o  ON o.sk_operatore = f.sk_operatore;
