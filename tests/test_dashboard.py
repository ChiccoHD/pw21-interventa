"""Test della dashboard: ogni pagina si apre senza errori, anche con i filtri applicati."""

import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import config as cfg

CARTELLA = Path(__file__).resolve().parent.parent / "app" / "pagine"
PAGINE = [str(CARTELLA / f) for f in ["andamento.py", "qualita.py", "informazioni.py", "clienti.py"]]

pytestmark = pytest.mark.skipif(not cfg.DB_PATH.exists(),
                                reason="warehouse assente: eseguire prima python esegui_tutto.py --no-dashboard")


def _apri(pagina):
    return AppTest.from_file(pagina, default_timeout=120).run()


@pytest.mark.parametrize("pagina", PAGINE, ids=["andamento", "qualita", "informazioni", "clienti"])
def test_pagina_senza_errori(pagina):
    at = _apri(pagina)
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("periodo", ["Ultimi 3 mesi", "Ultimi 6 mesi", "Anno 2025"])
def test_filtro_periodo(periodo):
    at = _apri(PAGINE[0])
    at.sidebar.radio[0].set_value(periodo).run()
    assert not at.exception, [e.value for e in at.exception]


def test_filtro_zona_e_categoria():
    at = _apri(PAGINE[0])
    at.sidebar.multiselect[0].set_value(["Palermo"]).run()
    at.sidebar.multiselect[1].set_value(["Pulizie", "Idraulica"]).run()
    assert not at.exception, [e.value for e in at.exception]


def test_qualita_su_ogni_caricamento():
    with sqlite3.connect(cfg.DB_PATH) as con:
        caricamenti = [i for (i,) in con.execute("SELECT id_caricamento FROM etl_caricamenti")]
    at = _apri(PAGINE[1])
    for id_caricamento in caricamenti:
        at.sidebar.radio[0].set_value(id_caricamento).run()
        assert not at.exception, [e.value for e in at.exception]


def test_vista_tempi_categorie():
    at = _apri(PAGINE[0])
    at.segmented_control(key="vista_categorie").set_value("Tempi").run()
    assert not at.exception, [e.value for e in at.exception]


def test_clienti_per_zona():
    at = _apri(PAGINE[3])
    at.sidebar.multiselect[0].set_value(["Catania"]).run()
    assert not at.exception, [e.value for e in at.exception]
