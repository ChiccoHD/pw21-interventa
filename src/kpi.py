"""Esegue le query di sql/kpi.sql. Uso: python -m src.kpi [nome_query ...]"""

from __future__ import annotations

import re
import sqlite3
import sys

import pandas as pd

from src import config as cfg


def carica_query(percorso=cfg.SQL_KPI) -> dict[str, str]:
    testo = percorso.read_text(encoding="utf-8")
    blocchi = re.split(r"^-- name:\s*(\w+)\s*$", testo, flags=re.M)
    return {blocchi[i]: blocchi[i + 1].strip() for i in range(1, len(blocchi), 2)}


def esegui(nome: str, con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(carica_query()[nome], con)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    query = carica_query()
    nomi = argv or list(query)
    pd.set_option("display.width", 140, "display.max_columns", 20)
    with sqlite3.connect(cfg.DB_PATH) as con:
        for nome in nomi:
            print(f"\n=== {nome} ===")
            print(pd.read_sql_query(query[nome], con).to_string(index=False))


if __name__ == "__main__":
    main()
