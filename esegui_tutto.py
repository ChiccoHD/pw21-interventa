"""Genera i dati, esegue l'ETL, calcola i KPI e apre la dashboard.

Uso: python esegui_tutto.py [--no-dashboard]
"""

import subprocess
import sys

PASSI = [
    ("1/4 Generazione dei dati sintetici", [sys.executable, "-m", "src.genera_dati"]),
    ("2/4 Caricamento iniziale del data warehouse", [sys.executable, "-m", "src.etl"]),
    ("3/4 Caricamento incrementale dei pacchetti mensili", [sys.executable, "-m", "src.etl", "--incrementale"]),
    ("4/4 Calcolo dei KPI in SQL", [sys.executable, "-m", "src.kpi", "kpi_sintesi", "tasso_ritorno_clienti",
                                    "storico_anagrafiche"]),
]

for titolo, comando in PASSI:
    print(f"\n>>> {titolo}")
    subprocess.run(comando, check=True)

if "--no-dashboard" not in sys.argv:
    print("\n>>> Avvio della dashboard (Ctrl+C per chiudere)")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app/dashboard.py"])
