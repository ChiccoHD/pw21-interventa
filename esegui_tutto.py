"""Genera i dati, esegue l'ETL, calcola i KPI e apre la dashboard.

Uso: python esegui_tutto.py [--no-dashboard]
"""

import subprocess
import sys

PASSI = [
    ("1/3 Generazione dei dati sintetici", [sys.executable, "-m", "src.genera_dati"]),
    ("2/3 ETL e caricamento nel data warehouse", [sys.executable, "-m", "src.etl"]),
    ("3/3 Calcolo dei KPI in SQL", [sys.executable, "-m", "src.kpi", "kpi_sintesi", "tasso_ritorno_clienti"]),
]

for titolo, comando in PASSI:
    print(f"\n>>> {titolo}")
    subprocess.run(comando, check=True)

if "--no-dashboard" not in sys.argv:
    print("\n>>> Avvio della dashboard (Ctrl+C per chiudere)")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app/dashboard.py"])
