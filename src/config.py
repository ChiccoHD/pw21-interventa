"""Parametri condivisi del prototipo.

Tutti i valori sono inventati: descrivono "Manolesta", una startup fittizia
di servizi per la casa su richiesta attiva in sette zone della Sicilia.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR_RAW = ROOT / "data" / "raw"
DIR_SCARTI = ROOT / "data" / "scarti"
DB_PATH = ROOT / "data" / "warehouse" / "manolesta_dw.sqlite"
SQL_SCHEMA = ROOT / "sql" / "schema.sql"
SQL_KPI = ROOT / "sql" / "kpi.sql"

# Parametri di default del generatore (sovrascrivibili da riga di comando)
SEED = 2
N_CLIENTI = 500
N_FORNITORI = 300
N_OPERATORI = 350
N_RICHIESTE = 600
DATA_INIZIO = "2025-01-01"
DATA_FINE = "2025-12-31"
DATA_LANCIO = "2024-09-01"      # da qui partono le iscrizioni dei clienti
QUOTA_SPORCO = 0.03             # quota di righe "sporcate" apposta per l'ETL

# Zona -> peso (quota attesa di clienti)
ZONE = {
    "Palermo": 0.28,
    "Catania": 0.25,
    "Messina": 0.14,
    "Siracusa": 0.10,
    "Ragusa": 0.08,
    "Trapani": 0.08,
    "Agrigento": 0.07,
}

# Categoria -> peso, prezzo medio (euro), dev. std prezzo,
#              tempo medio di erogazione (minuti), SLA (minuti), tipo operatore
CATEGORIE = {
    "Idraulica":            dict(peso=0.20, prezzo=90,  sd=30, tempo=95,  sla=150, operatore="Tecnico idraulico"),
    "Elettricità":          dict(peso=0.17, prezzo=85,  sd=28, tempo=90,  sla=150, operatore="Tecnico elettricista"),
    "Pulizie":              dict(peso=0.22, prezzo=60,  sd=15, tempo=170, sla=240, operatore="Addetto pulizie"),
    "Climatizzazione":      dict(peso=0.13, prezzo=120, sd=40, tempo=110, sla=180, operatore="Tecnico climatizzazione"),
    "Elettrodomestici":     dict(peso=0.12, prezzo=95,  sd=30, tempo=100, sla=160, operatore="Tecnico elettrodomestici"),
    "Giardinaggio":         dict(peso=0.09, prezzo=70,  sd=20, tempo=150, sla=220, operatore="Giardiniere"),
    "Piccoli traslochi":    dict(peso=0.07, prezzo=180, sd=60, tempo=210, sla=300, operatore="Addetto traslochi"),
}

# Stagionalità mensile per categoria (moltiplicatore, indice 0 = gennaio)
STAGIONALITA = {
    "Climatizzazione":   [0.5, 0.5, 0.6, 0.8, 1.2, 1.9, 2.4, 2.3, 1.3, 0.7, 0.5, 0.7],
    "Giardinaggio":      [0.5, 0.7, 1.3, 1.6, 1.6, 1.2, 0.9, 0.7, 1.0, 1.1, 0.8, 0.6],
    "Pulizie":           [0.9, 0.8, 0.9, 1.1, 1.0, 1.1, 1.2, 1.1, 1.0, 0.9, 0.9, 1.3],
    "Piccoli traslochi": [0.8, 0.8, 0.9, 1.0, 1.0, 1.2, 1.3, 1.1, 1.3, 1.0, 0.8, 0.8],
}

# Peso per giorno della settimana (0 = lunedì)
PESO_GIORNO = [1.15, 1.00, 1.00, 1.00, 1.05, 0.90, 0.45]

# Peso per ora del giorno: picchi a metà mattina e a fine pomeriggio
PESO_ORA = [0.05, 0.03, 0.02, 0.02, 0.02, 0.05, 0.20, 0.60,
            1.20, 1.60, 1.50, 1.20, 0.80, 0.70, 0.90, 1.10,
            1.30, 1.60, 1.50, 1.10, 0.70, 0.40, 0.20, 0.10]
ORE_PICCO = {9, 10, 17, 18}

# Crescita mensile della startup (+% richieste al mese)
CRESCITA_MENSILE = 0.06

STATI = ["completata", "in_ritardo", "annullata"]
