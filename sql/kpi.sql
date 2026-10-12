-- KPI del data warehouse Interventa. Ogni query è preceduta da "-- name: <nome>".
-- Erogate = completate o in ritardo. Incassi = importi delle erogate.
-- Clienti attivi = clienti con almeno una richiesta erogata; tasso di ritorno = quota con 2 o più.
-- Clienti e fornitori si contano per codice (cliente_id, fornitore_id), non per versione dello storico.

-- name: kpi_sintesi
SELECT
    COUNT(*)                                             AS richieste_totali,
    SUM(flag_erogata)                                    AS richieste_erogate,
    ROUND(SUM(importo), 2)                               AS incassi_euro,
    ROUND(AVG(CASE WHEN flag_erogata = 1 THEN tempo_erogazione_min END), 1)
                                                         AS tempo_medio_min,
    COUNT(DISTINCT CASE WHEN flag_erogata = 1 THEN c.cliente_id END)
                                                         AS clienti_attivi,
    ROUND(100.0 * SUM(flag_annullata) / COUNT(*), 1)     AS perc_annullate,
    ROUND(100.0 * SUM(flag_ritardo) / SUM(flag_erogata), 1)
                                                         AS perc_in_ritardo,
    ROUND(SUM(importo) / SUM(flag_erogata), 2)           AS scontrino_medio_euro
FROM fact_richieste f
JOIN dim_cliente c ON c.sk_cliente = f.sk_cliente;

-- name: tasso_ritorno_clienti
WITH per_cliente AS (
    SELECT c.cliente_id, COUNT(*) AS n_richieste
    FROM fact_richieste f
    JOIN dim_cliente c ON c.sk_cliente = f.sk_cliente
    WHERE f.flag_erogata = 1
    GROUP BY c.cliente_id
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
    cur.nome,
    cur.categoria,
    cur.zona,
    COUNT(*)                         AS richieste,
    ROUND(SUM(f.importo), 2)         AS incassi_euro
FROM fact_richieste f
JOIN dim_fornitore fo  ON fo.sk_fornitore = f.sk_fornitore
JOIN dim_fornitore cur ON cur.fornitore_id = fo.fornitore_id AND cur.corrente = 1
GROUP BY fo.fornitore_id
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

-- name: storico_anagrafiche
SELECT 'clienti' AS anagrafica, COUNT(DISTINCT cliente_id) AS entita, COUNT(*) AS versioni,
       COUNT(*) - COUNT(DISTINCT cliente_id) AS modifiche_storicizzate
FROM dim_cliente WHERE sk_cliente > 0
UNION ALL
SELECT 'fornitori', COUNT(DISTINCT fornitore_id), COUNT(*), COUNT(*) - COUNT(DISTINCT fornitore_id)
FROM dim_fornitore WHERE sk_fornitore > 0
UNION ALL
SELECT 'operatori', COUNT(DISTINCT operatore_id), COUNT(*), COUNT(*) - COUNT(DISTINCT operatore_id)
FROM dim_operatore WHERE sk_operatore > 0;
