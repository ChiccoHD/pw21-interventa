-- ===========================================================================
-- Data warehouse "Manolesta" — schema a stella (SQLite)
--
--                    dim_tempo
--                        |
--   dim_cliente --- fact_richieste --- dim_fornitore
--                        |
--                   dim_operatore
--
-- Grana della tabella dei fatti: UNA riga per OGNI richiesta di servizio.
-- Le dimensioni usano chiavi surrogate (sk_*) distinte dai codici di origine:
-- così il warehouse non dipende dai codici dei sistemi sorgente e in futuro
-- potrà gestire lo storico delle modifiche (Slowly Changing Dimensions).
-- La riga con chiave 0 in ogni dimensione rappresenta il membro "Sconosciuto",
-- usato quando il dato di origine manca (es. operatore non registrato).
-- ===========================================================================

PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_richieste;
DROP TABLE IF EXISTS fact_richieste;
DROP TABLE IF EXISTS dim_cliente;
DROP TABLE IF EXISTS dim_fornitore;
DROP TABLE IF EXISTS dim_operatore;
DROP TABLE IF EXISTS dim_tempo;

-- --------------------------------------------------------------------------
-- Dimensioni
-- --------------------------------------------------------------------------

CREATE TABLE dim_cliente (
    sk_cliente         INTEGER PRIMARY KEY,
    cliente_id         TEXT    NOT NULL UNIQUE,   -- codice di origine (app clienti)
    zona               TEXT    NOT NULL,
    data_iscrizione    TEXT,                      -- formato ISO AAAA-MM-GG
    anno_iscrizione    INTEGER,
    canale_iscrizione  TEXT
);

CREATE TABLE dim_fornitore (
    sk_fornitore       INTEGER PRIMARY KEY,
    fornitore_id       TEXT    NOT NULL UNIQUE,   -- codice di origine (archivio partner)
    nome               TEXT    NOT NULL,
    categoria          TEXT    NOT NULL,          -- categoria di servizio
    zona               TEXT    NOT NULL
);

CREATE TABLE dim_operatore (
    sk_operatore       INTEGER PRIMARY KEY,
    operatore_id       TEXT    NOT NULL UNIQUE,   -- codice di origine (gestionale operatori)
    zona               TEXT    NOT NULL,
    tipo_attivita      TEXT    NOT NULL,
    anni_esperienza    INTEGER,
    fascia_esperienza  TEXT                        -- Junior / Intermedio / Senior
);

CREATE TABLE dim_tempo (
    sk_tempo           INTEGER PRIMARY KEY,       -- AAAAMMGG, es. 20250314
    data               TEXT    NOT NULL UNIQUE,
    anno               INTEGER NOT NULL,
    trimestre          INTEGER NOT NULL,
    mese               INTEGER NOT NULL,
    nome_mese          TEXT    NOT NULL,
    anno_mese          TEXT    NOT NULL,          -- es. 2025-03
    settimana_iso      INTEGER NOT NULL,
    giorno_mese        INTEGER NOT NULL,
    giorno_settimana   INTEGER NOT NULL,          -- 1 = lunedì ... 7 = domenica
    nome_giorno        TEXT    NOT NULL,
    is_weekend         INTEGER NOT NULL           -- 0/1
);

-- --------------------------------------------------------------------------
-- Tabella dei fatti
-- --------------------------------------------------------------------------

CREATE TABLE fact_richieste (
    sk_richiesta          INTEGER PRIMARY KEY,
    richiesta_id          TEXT    NOT NULL UNIQUE,  -- dimensione degenere
    sk_cliente            INTEGER NOT NULL REFERENCES dim_cliente(sk_cliente),
    sk_fornitore          INTEGER NOT NULL REFERENCES dim_fornitore(sk_fornitore),
    sk_operatore          INTEGER NOT NULL REFERENCES dim_operatore(sk_operatore),
    sk_tempo              INTEGER NOT NULL REFERENCES dim_tempo(sk_tempo),
    ora                   INTEGER NOT NULL CHECK (ora BETWEEN 0 AND 23),
    fascia_oraria         TEXT    NOT NULL,         -- Notte / Mattina / Pomeriggio / Sera
    stato                 TEXT    NOT NULL CHECK (stato IN ('completata','in_ritardo','annullata')),
    -- misure
    importo               REAL    NOT NULL CHECK (importo >= 0),
    tempo_erogazione_min  INTEGER,                  -- NULL se annullata
    flag_erogata          INTEGER NOT NULL,         -- 1 se completata o in ritardo
    flag_annullata        INTEGER NOT NULL,
    flag_ritardo          INTEGER NOT NULL
);

CREATE INDEX ix_fact_tempo     ON fact_richieste(sk_tempo);
CREATE INDEX ix_fact_cliente   ON fact_richieste(sk_cliente);
CREATE INDEX ix_fact_fornitore ON fact_richieste(sk_fornitore);
CREATE INDEX ix_fact_operatore ON fact_richieste(sk_operatore);

-- --------------------------------------------------------------------------
-- Vista "piatta" usata dalla dashboard: i fatti con gli attributi delle
-- dimensioni già uniti. La zona di analisi è quella del cliente, cioè il
-- luogo in cui il servizio viene erogato.
-- --------------------------------------------------------------------------

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
