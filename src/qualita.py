"""Controlli di qualità dei dati, eseguiti dall'ETL a ogni caricamento.

Ogni regola è una query che restituisce (violazioni, totale). La percentuale di
violazioni è confrontata con due soglie: oltre la soglia di avviso l'esito è AVVISO,
oltre la soglia di errore è ERRORE e il caricamento viene respinto.

Uso: python -m src.qualita   (controlla il warehouse attuale senza salvare gli esiti)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pandas as pd

from src import config as cfg


@dataclass(frozen=True)
class Regola:
    nome: str
    descrizione: str
    sql: str
    soglia_avviso: float = 0.0
    soglia_errore: float = 0.0


def _versioni(tabella, chiave, sk):
    return f"SELECT {chiave} AS chiave, {sk} AS sk, valido_dal, valido_al, corrente FROM {tabella} WHERE {sk} > 0"


_TUTTE_LE_VERSIONI = " UNION ALL ".join(
    f"SELECT '{t}' AS tab, * FROM ({_versioni(t, k, s)})"
    for t, k, s in [("dim_cliente", "cliente_id", "sk_cliente"),
                    ("dim_fornitore", "fornitore_id", "sk_fornitore"),
                    ("dim_operatore", "operatore_id", "sk_operatore")])

REGOLE = [
    Regola("fatti_chiave_unica", "Ogni richiesta compare una sola volta",
           "SELECT COUNT(*) - COUNT(DISTINCT richiesta_id), COUNT(*) FROM fact_richieste"),
    Regola("fatti_riferimenti", "Ogni richiesta punta a dimensioni esistenti",
           """SELECT SUM(c.sk_cliente IS NULL OR fo.sk_fornitore IS NULL OR o.sk_operatore IS NULL
                         OR t.sk_tempo IS NULL), COUNT(*)
              FROM fact_richieste f
              LEFT JOIN dim_cliente c ON c.sk_cliente = f.sk_cliente
              LEFT JOIN dim_fornitore fo ON fo.sk_fornitore = f.sk_fornitore
              LEFT JOIN dim_operatore o ON o.sk_operatore = f.sk_operatore
              LEFT JOIN dim_tempo t ON t.sk_tempo = f.sk_tempo"""),
    Regola("annullate_coerenti", "Le richieste annullate non hanno importo né tempo di erogazione",
           """SELECT SUM(flag_annullata = 1 AND (importo <> 0 OR tempo_erogazione_min IS NOT NULL)),
                     SUM(flag_annullata) FROM fact_richieste"""),
    Regola("erogate_con_tempo", "Le richieste erogate hanno il tempo di erogazione",
           "SELECT SUM(tempo_erogazione_min IS NULL), COUNT(*) FROM fact_richieste WHERE flag_erogata = 1"),
    Regola("tempo_plausibile", "Tempo di erogazione tra 15 e 600 minuti",
           """SELECT SUM(tempo_erogazione_min NOT BETWEEN 15 AND 600), COUNT(*)
              FROM fact_richieste WHERE flag_erogata = 1""", 1, 5),
    Regola("importo_plausibile", "Importo delle richieste erogate tra 20 e 500 euro",
           "SELECT SUM(importo NOT BETWEEN 20 AND 500), COUNT(*) FROM fact_richieste WHERE flag_erogata = 1",
           1, 5),
    Regola("operatore_noto", "Richieste con operatore registrato",
           "SELECT SUM(sk_operatore = 0), COUNT(*) FROM fact_richieste", 2, 10),
    Regola("versione_corrente_unica", "Ogni entità delle anagrafiche ha una sola versione corrente",
           f"""SELECT SUM(n <> 1), COUNT(*) FROM (
                   SELECT tab, chiave, SUM(corrente) AS n FROM ({_TUTTE_LE_VERSIONI}) GROUP BY tab, chiave)"""),
    Regola("versioni_non_sovrapposte", "Gli intervalli di validità delle versioni non si sovrappongono",
           f"""WITH v AS ({_TUTTE_LE_VERSIONI})
               SELECT (SELECT COUNT(*) FROM v a JOIN v b
                         ON a.tab = b.tab AND a.chiave = b.chiave AND a.sk < b.sk
                        AND a.valido_dal <= b.valido_al AND b.valido_dal <= a.valido_al),
                      (SELECT COUNT(*) FROM v)"""),
    Regola("fatti_versione_valida", "Ogni richiesta è collegata alla versione valida alla sua data",
           """SELECT SUM(t.data NOT BETWEEN c.valido_dal AND c.valido_al
                      OR t.data NOT BETWEEN fo.valido_dal AND fo.valido_al
                      OR (f.sk_operatore > 0 AND t.data NOT BETWEEN o.valido_dal AND o.valido_al)), COUNT(*)
              FROM fact_richieste f
              JOIN dim_tempo t ON t.sk_tempo = f.sk_tempo
              JOIN dim_cliente c ON c.sk_cliente = f.sk_cliente
              JOIN dim_fornitore fo ON fo.sk_fornitore = f.sk_fornitore
              JOIN dim_operatore o ON o.sk_operatore = f.sk_operatore"""),
    Regola("calendario_completo", "Il calendario non ha giorni mancanti",
           """SELECT CAST(julianday(MAX(data)) - julianday(MIN(data)) + 1 AS INTEGER) - COUNT(*),
                     CAST(julianday(MAX(data)) - julianday(MIN(data)) + 1 AS INTEGER) FROM dim_tempo"""),
    Regola("incassi_caricati", "Gli incassi caricati coincidono con quelli dei dati validi",
           """SELECT ABS(ROUND(COALESCE((SELECT SUM(importo) FROM fact_richieste WHERE id_caricamento = :id), 0)
                              - :incassi, 2)), :incassi"""),
    Regola("scarti_caricamento", "Richieste scartate dall'ETL nell'ultimo caricamento",
           "SELECT :scartate, :lette", 1, 5),
    Regola("volume_mensile", "Scostamento delle richieste dell'ultimo mese dalla media dei tre precedenti",
           """WITH m AS (SELECT t.anno_mese, COUNT(*) AS n FROM fact_richieste f
                         JOIN dim_tempo t ON t.sk_tempo = f.sk_tempo
                         GROUP BY t.anno_mese ORDER BY t.anno_mese DESC LIMIT 4),
                   ultimo AS (SELECT n FROM m ORDER BY anno_mese DESC LIMIT 1),
                   prec AS (SELECT AVG(n) AS media, COUNT(*) AS k FROM
                            (SELECT n FROM m ORDER BY anno_mese DESC LIMIT 3 OFFSET 1))
              SELECT CASE WHEN k = 3 THEN ABS((SELECT n FROM ultimo) - media) ELSE 0 END,
                     CASE WHEN k = 3 THEN media ELSE 0 END FROM prec""", 50, 150),
]


def valuta(percentuale, regola: Regola) -> str:
    if percentuale > regola.soglia_errore:
        return "ERRORE"
    if percentuale > regola.soglia_avviso:
        return "AVVISO"
    return "OK"


def esegui_controlli(con: sqlite3.Connection, parametri: dict | None = None) -> pd.DataFrame:
    parametri = {"id": None, "incassi": 0, "lette": 0, "scartate": 0, **(parametri or {})}
    righe = []
    for r in REGOLE:
        violazioni, totale = con.execute(r.sql, parametri).fetchone()
        violazioni, totale = float(violazioni or 0), float(totale or 0)
        percentuale = round(100 * violazioni / totale, 2) if totale else 0.0
        righe.append({"regola": r.nome, "descrizione": r.descrizione, "violazioni": violazioni,
                      "totale": totale, "percentuale": percentuale, "soglia_avviso": r.soglia_avviso,
                      "soglia_errore": r.soglia_errore, "esito": valuta(percentuale, r)})
    return pd.DataFrame(righe)


def main():
    with sqlite3.connect(cfg.DB_PATH) as con:
        esiti = esegui_controlli(con)
    pd.set_option("display.width", 140)
    print(esiti[["regola", "violazioni", "totale", "percentuale", "esito"]].to_string(index=False))


if __name__ == "__main__":
    main()
