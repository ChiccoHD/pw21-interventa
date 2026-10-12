"""Test della pipeline. Uso: python -m pytest"""

import shutil
import sqlite3

import pandas as pd
import pytest

from src import config as cfg
from src import etl, genera_dati, kpi, metriche
from src.qualita import esegui_controlli


@pytest.fixture(scope="module")
def ambiente(tmp_path_factory):
    base = tmp_path_factory.mktemp("pw21")
    raw, db = base / "raw", base / "dw.sqlite"
    genera_dati.main(["--out", str(raw)])
    etl.carica_iniziale(raw, db, None)
    etl.carica_incrementi(raw / "incrementi", db, None)
    return {"base": base, "raw": raw, "db": db}


def _copia_db(ambiente, tmp_path):
    copia = tmp_path / "copia.sqlite"
    shutil.copy(ambiente["db"], copia)
    return copia


def _uno(db, sql):
    with sqlite3.connect(db) as con:
        return con.execute(sql).fetchone()[0]


def test_volumi_del_dataset_iniziale(ambiente):
    for nome in ["clienti", "fornitori", "operatori", "richieste"]:
        n = len(pd.read_csv(ambiente["raw"] / f"{nome}.csv"))
        assert 300 <= n <= 620, f"{nome}: {n} righe"


def test_generatore_riproducibile(tmp_path):
    genera_dati.main(["--out", str(tmp_path / "a")])
    genera_dati.main(["--out", str(tmp_path / "b")])
    for f in ["clienti.csv", "richieste.csv", "incrementi/2026-01/clienti.csv", "incrementi/2026-02/richieste.csv"]:
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()


def test_nessun_dato_personale(ambiente):
    clienti = pd.read_csv(ambiente["raw"] / "clienti.csv")
    assert set(clienti.columns) == {"cliente_id", "zona", "data_iscrizione", "canale_iscrizione"}


def test_dati_puliti_nel_warehouse(ambiente):
    db = ambiente["db"]
    assert _uno(db, "SELECT COUNT(*) FROM fact_richieste WHERE importo < 0") == 0
    assert _uno(db, "SELECT COUNT(*) - COUNT(DISTINCT richiesta_id) FROM fact_richieste") == 0
    with sqlite3.connect(db) as con:
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
        zone = {z for (z,) in con.execute("SELECT DISTINCT zona FROM dim_cliente WHERE sk_cliente > 0")}
        categorie = {c for (c,) in con.execute("SELECT DISTINCT categoria FROM dim_fornitore WHERE sk_fornitore > 0")}
    assert zone <= set(cfg.ZONE)
    assert categorie <= set(cfg.CATEGORIE)


def test_tutti_i_controlli_senza_errori(ambiente):
    with sqlite3.connect(ambiente["db"]) as con:
        esiti = esegui_controlli(con)
    assert (esiti["esito"] != "ERRORE").all(), esiti[esiti["esito"] == "ERRORE"]


def test_calendario_completo(ambiente):
    attesi = (pd.Timestamp("2026-02-28") - pd.Timestamp(cfg.DATA_INIZIO)).days + 1
    assert _uno(ambiente["db"], "SELECT COUNT(*) FROM dim_tempo") == attesi


def test_registro_dei_caricamenti(ambiente):
    with sqlite3.connect(ambiente["db"]) as con:
        reg = pd.read_sql_query("SELECT tipo, periodo, esito FROM etl_caricamenti ORDER BY id_caricamento", con)
    assert reg.values.tolist() == [["iniziale", "2025", "COMPLETATO"],
                                   ["incrementale", "2026-01", "COMPLETATO"],
                                   ["incrementale", "2026-02", "COMPLETATO"]]


def test_scarti_registrati(ambiente):
    with sqlite3.connect(ambiente["db"]) as con:
        motivi = {m for (m,) in con.execute("SELECT descrizione FROM etl_eventi WHERE tipo = 'scarto'")}
    assert {"importo mancante o negativo", "fornitore inesistente"} <= motivi


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


def test_incrementale_idempotente(ambiente, tmp_path):
    db = _copia_db(ambiente, tmp_path)
    prima = _uno(db, "SELECT COUNT(*) FROM fact_richieste")
    assert etl.carica_incrementi(ambiente["raw"] / "incrementi", db, None) == []
    con = etl.connetti(db)
    esito = etl.esegui_caricamento(con, ambiente["raw"] / "incrementi" / "2026-02", "incrementale",
                                   "2026-02-bis", "2026-02-01")
    con.close()
    assert esito["righe_caricate"] == 0 and esito["nuove_versioni"] == 0
    assert _uno(db, "SELECT COUNT(*) FROM fact_richieste") == prima


def test_storico_tipo_2(ambiente):
    with sqlite3.connect(ambiente["db"]) as con:
        v = pd.read_sql_query("""SELECT cliente_id, sk_cliente, zona, valido_dal, valido_al, corrente
                                 FROM dim_cliente WHERE cliente_id IN
                                   (SELECT cliente_id FROM dim_cliente GROUP BY cliente_id HAVING COUNT(*) > 1)
                                 ORDER BY cliente_id, valido_dal""", con)
        fatti = pd.read_sql_query("""SELECT f.sk_cliente, t.data FROM fact_richieste f
                                     JOIN dim_tempo t ON t.sk_tempo = f.sk_tempo""", con)
    assert len(v) > 0
    for _, g in v.groupby("cliente_id"):
        assert g["corrente"].tolist()[-1] == 1 and g["corrente"].sum() == 1
        assert g["zona"].iloc[0] != g["zona"].iloc[1]
        fine_vecchia = pd.Timestamp(g["valido_al"].iloc[0])
        assert fine_vecchia + pd.Timedelta(days=1) == pd.Timestamp(g["valido_dal"].iloc[1])
    m = fatti.merge(v, on="sk_cliente")
    assert ((m["data"] >= m["valido_dal"]) & (m["data"] <= m["valido_al"])).all()


def test_storico_tipo_1(ambiente):
    base = pd.read_csv(ambiente["raw"] / "operatori.csv").set_index("operatore_id")["anni_esperienza"]
    with sqlite3.connect(ambiente["db"]) as con:
        dw = pd.read_sql_query("SELECT operatore_id, anni_esperienza FROM dim_operatore WHERE sk_operatore > 0", con)
    dw = dw[dw["operatore_id"].isin(base.index)]
    assert (dw["anni_esperienza"].to_numpy() == base.loc[dw["operatore_id"]].to_numpy() + 1).all()


def test_caricamento_respinto_e_annullato(ambiente, tmp_path):
    db = _copia_db(ambiente, tmp_path)
    pacchetto = tmp_path / "2026-03"
    shutil.copytree(ambiente["raw"] / "incrementi" / "2026-02", pacchetto)
    r = pd.read_csv(pacchetto / "richieste.csv", dtype=str)
    r["richiesta_id"] = "R9" + r["richiesta_id"].str[2:]
    r["data_ora"] = r["data_ora"].str.replace("2026-02", "2026-03").str.replace("/02/2026", "/03/2026")
    r.loc[r.index[: len(r) // 5], "importo"] = "-10"
    r.to_csv(pacchetto / "richieste.csv", index=False)

    prima = {t: _uno(db, f"SELECT COUNT(*) FROM {t}") for t in ["fact_richieste", "dim_tempo", "dim_cliente"]}
    con = etl.connetti(db)
    esito = etl.esegui_caricamento(con, pacchetto, "incrementale", "2026-03", "2026-03-01")
    con.close()
    assert esito["esito"] == "RESPINTO"
    assert {t: _uno(db, f"SELECT COUNT(*) FROM {t}") for t in prima} == prima
    assert _uno(db, "SELECT esito FROM dq_risultati WHERE regola = 'scarti_caricamento' "
                    "ORDER BY id_caricamento DESC LIMIT 1") == "ERRORE"


def test_dati_senza_difetti_nessuno_scarto(tmp_path):
    genera_dati.main(["--out", str(tmp_path), "--pulito"])
    for cartella in [tmp_path, tmp_path / "incrementi" / "2026-01"]:
        rep = etl.Report()
        etl.trasforma(etl.estrai(cartella), rep)
        assert rep.scarti == []
