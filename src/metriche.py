"""KPI della dashboard: stesse definizioni di sql/kpi.sql (verificate dai test)."""

from __future__ import annotations

import sqlite3

import pandas as pd

from src import config as cfg


def carica_vista(db_path=cfg.DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        df = pd.read_sql_query("SELECT * FROM v_richieste", con)
    df["data"] = pd.to_datetime(df["data"])
    return df


def filtra(df, inizio=None, fine=None, zone=None, categorie=None) -> pd.DataFrame:
    m = pd.Series(True, index=df.index)
    if inizio is not None:
        m &= df["data"] >= pd.Timestamp(inizio)
    if fine is not None:
        m &= df["data"] <= pd.Timestamp(fine)
    if zone:
        m &= df["zona"].isin(zone)
    if categorie:
        m &= df["categoria"].isin(categorie)
    return df[m]


def kpi(df: pd.DataFrame) -> dict:
    erogate = df[df["flag_erogata"] == 1]
    per_cliente = erogate.groupby("cliente_id").size()
    n = len(df)
    return {
        "richieste_totali": n,
        "richieste_erogate": len(erogate),
        "incassi_euro": round(float(df["importo"].sum()), 2),
        "tempo_medio_min": round(float(erogate["tempo_erogazione_min"].mean()), 1) if len(erogate) else None,
        "clienti_attivi": int(per_cliente.size),
        "clienti_di_ritorno": int((per_cliente >= 2).sum()),
        "tasso_ritorno_perc": round(100 * (per_cliente >= 2).mean(), 1) if per_cliente.size else None,
        "perc_annullate": round(100 * df["flag_annullata"].mean(), 1) if n else None,
        "perc_in_ritardo": round(100 * erogate["flag_ritardo"].mean(), 1) if len(erogate) else None,
    }
