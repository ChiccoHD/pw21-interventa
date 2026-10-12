"""Controlli automatici sull'intera pipeline (eseguire con: python -m pytest)."""

import sqlite3

import pandas as pd
import pytest

from src import config as cfg
from src import etl, genera_dati, kpi, metriche


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    """Genera dati e warehouse in una cartella temporanea (non tocca data/)."""
    base = tmp_path_factory.mktemp("pw21")
    raw, db = base / "raw", base / "dw.sqlite"
    genera_dati.main(["--out", str(raw)])
    rep = etl.Report()
    dati = etl.trasforma(etl.estrai(raw), rep)
    etl.carica(dati, db, rep)
    return {"raw": raw, "db": db, "rep": rep}


def test_volumi_richiesti_dalla_traccia(ambiente):
    for nome in ["clienti", "fornitori", "operatori", "richieste"]:
        n = len(pd.read_csv(ambiente["raw"] / f"{nome}.csv"))
        assert 300 <= n <= 620, f"{nome}: {n} righe"


def test_generatore_riproducibile(tmp_path):
    genera_dati.main(["--out", str(tmp_path / "a")])
    genera_dati.main(["--out", str(tmp_path / "b")])
    for nome in ["clienti", "richieste"]:
        assert (tmp_path / "a" / f"{nome}.csv").read_bytes() == (tmp_path / "b" / f"{nome}.csv").read_bytes()


def test_nessun_dato_personale(ambiente):
    clienti = pd.read_csv(ambiente["raw"] / "clienti.csv")
    assert set(clienti.columns) == {"cliente_id", "zona", "data_iscrizione", "canale_iscrizione"}


def test_dati_puliti_nel_warehouse(ambiente):
    with sqlite3.connect(ambiente["db"]) as con:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        assert con.execute("SELECT COUNT(*) FROM fact_richieste WHERE importo < 0").fetchone()[0] == 0
        dup = con.execute("SELECT COUNT(*) - COUNT(DISTINCT richiesta_id) FROM fact_richieste").fetchone()[0]
        assert dup == 0
        zone = {z for (z,) in con.execute("SELECT DISTINCT zona FROM dim_cliente WHERE sk_cliente > 0")}
        assert zone <= set(cfg.ZONE)
        categorie = {c for (c,) in con.execute("SELECT DISTINCT categoria FROM dim_fornitore WHERE sk_fornitore > 0")}
        assert categorie <= set(cfg.CATEGORIE)
        # le annullate non generano incasso né tempo di erogazione
        r = con.execute("""SELECT COUNT(*) FROM fact_richieste WHERE flag_annullata = 1
                           AND (importo <> 0 OR tempo_erogazione_min IS NOT NULL)""").fetchone()[0]
        assert r == 0


def test_dim_tempo_calendario_completo(ambiente):
    with sqlite3.connect(ambiente["db"]) as con:
        n = con.execute("SELECT COUNT(*) FROM dim_tempo").fetchone()[0]
    attesi = (pd.Timestamp(cfg.DATA_FINE) - pd.Timestamp(cfg.DATA_INIZIO)).days + 1
    assert n == attesi


def test_scarti_registrati(ambiente):
    motivi = {m for df in ambiente["rep"].scarti for m in df["motivo"]}
    assert "importo mancante o negativo" in motivi
    assert "fornitore inesistente" in motivi


def test_kpi_sql_e_dashboard_coincidono(ambiente):
    df = metriche.carica_vista(ambiente["db"])
    k_py = metriche.kpi(df)
    with sqlite3.connect(ambiente["db"]) as con:
        s = kpi.esegui("kpi_sintesi", con).iloc[0]
        t = kpi.esegui("tasso_ritorno_clienti", con).iloc[0]
    assert k_py["richieste_totali"] == s["richieste_totali"]
    assert k_py["incassi_euro"] == pytest.approx(s["incassi_euro"])
    assert k_py["tempo_medio_min"] == pytest.approx(s["tempo_medio_min"])
    assert k_py["clienti_attivi"] == s["clienti_attivi"]
    assert k_py["tasso_ritorno_perc"] == pytest.approx(t["tasso_ritorno_perc"])


def test_dati_senza_difetti_nessuno_scarto(tmp_path):
    genera_dati.main(["--out", str(tmp_path), "--pulito"])
    rep = etl.Report()
    etl.trasforma(etl.estrai(tmp_path), rep)
    assert rep.scarti == []
