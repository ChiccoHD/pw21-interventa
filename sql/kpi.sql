-- ===========================================================================
-- Indicatori principali (KPI) calcolati sul data warehouse.
-- Ogni query è preceduta da "-- name: <nome>" così src/kpi.py può eseguirle
-- una alla volta e stamparne il risultato.
--
-- Definizioni adottate:
--   richieste erogate  = stato 'completata' oppure 'in_ritardo' (non annullate)
--   incassi            = somma degli importi delle richieste erogate
--   tempo di erogazione= minuti tra la richiesta e la chiusura dell'intervento
--   clienti attivi     = clienti distinti con almeno una richiesta erogata
--   tasso di ritorno   = clienti con 2+ richieste erogate / clienti attivi
-- ===========================================================================

-- name: kpi_sintesi
SELECT
    COUNT(*)                                             AS richieste_totali,
    SUM(flag_erogata)                                    AS richieste_erogate,
    ROUND(SUM(importo), 2)                               AS incassi_euro,
    ROUND(AVG(CASE WHEN flag_erogata = 1 THEN tempo_erogazione_min END), 1)
                                                         AS tempo_medio_min,
    COUNT(DISTINCT CASE WHEN flag_erogata = 1 THEN sk_cliente END)
                                                         AS clienti_attivi,
    ROUND(100.0 * SUM(flag_annullata) / COUNT(*), 1)     AS perc_annullate,
    ROUND(100.0 * SUM(flag_ritardo) / SUM(flag_erogata), 1)
                                                         AS perc_in_ritardo,
    ROUND(SUM(importo) / SUM(flag_erogata), 2)           AS scontrino_medio_euro
FROM fact_richieste;

-- name: tasso_ritorno_clienti
WITH per_cliente AS (
    SELECT sk_cliente, COUNT(*) AS n_richieste
    FROM fact_richieste
    WHERE flag_erogata = 1
    GROUP BY sk_cliente
)
SELECT
    COUNT(*)                                             AS clienti_attivi,
    SUM(n_richieste >= 2)                                AS clienti_di_ritorno,
    ROUND(100.0 * SUM(n_richieste >= 2) / COUNT(*), 1)   AS tasso_ritorno_perc
FROM per_cliente;

-- name: andamento_mensile
SELECT
    t.anno_mese,
    COUNT(*)                                  AS richieste,
    SUM(f.flag_annullata)                     AS annullate,
    ROUND(SUM(f.importo), 2)                  AS incassi_euro,
    ROUND(AVG(f.tempo_erogazione_min), 1)     AS tempo_medio_min
FROM fact_richieste f
JOIN dim_tempo t ON t.sk_tempo = f.sk_tempo
GROUP BY t.anno_mese
ORDER BY t.anno_mese;

-- name: incassi_per_zona
SELECT
    c.zona,
    COUNT(*)                                  AS richieste,
    ROUND(SUM(f.importo), 2)                  AS incassi_euro,
    ROUND(100.0 * SUM(f.importo) / (SELECT SUM(importo) FROM fact_richieste), 1)
                                              AS quota_incassi_perc,
    ROUND(AVG(f.tempo_erogazione_min), 1)     AS tempo_medio_min
FROM fact_richieste f
JOIN dim_cliente c ON c.sk_cliente = f.sk_cliente
GROUP BY c.zona
ORDER BY incassi_euro DESC;

-- name: richieste_per_categoria
SELECT
    fo.categoria,
    COUNT(*)                                              AS richieste,
    ROUND(SUM(f.importo), 2)                              AS incassi_euro,
    ROUND(AVG(f.tempo_erogazione_min), 1)                 AS tempo_medio_min,
    ROUND(100.0 * SUM(f.flag_ritardo) / SUM(f.flag_erogata), 1) AS perc_in_ritardo
FROM fact_richieste f
JOIN dim_fornitore fo ON fo.sk_fornitore = f.sk_fornitore
GROUP BY fo.categoria
ORDER BY richieste DESC;

-- name: top5_fornitori_per_incassi
SELECT
    fo.fornitore_id,
    fo.nome,
    fo.categoria,
    fo.zona,
    COUNT(*)                         AS richieste,
    ROUND(SUM(f.importo), 2)         AS incassi_euro
FROM fact_richieste f
JOIN dim_fornitore fo ON fo.sk_fornitore = f.sk_fornitore
GROUP BY fo.sk_fornitore
ORDER BY incassi_euro DESC
LIMIT 5;

-- name: annullamenti_per_fascia_oraria
SELECT
    f.fascia_oraria,
    COUNT(*)                                          AS richieste,
    ROUND(100.0 * SUM(f.flag_annullata) / COUNT(*), 1) AS perc_annullate,
    ROUND(AVG(f.tempo_erogazione_min), 1)             AS tempo_medio_min
FROM fact_richieste f
GROUP BY f.fascia_oraria
ORDER BY MIN(f.ora);
