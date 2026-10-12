"""Procedura ETL: dai CSV di data/raw/ al data warehouse SQLite.

    Estrazione      legge i quattro file CSV come testo (nessuna conversione implicita)
    Trasformazione  pulisce e uniforma: spazi, maiuscole, formati di data e
                    di importo, stati; elimina i duplicati; scarta le righe non
                    valide salvandole con il motivo in data/scarti/
    Caricamento     ricrea lo schema a stella (sql/schema.sql), popola le
                    dimensioni con chiavi surrogate e poi la tabella dei fatti

Uso:
    python -m src.etl
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src import config as cfg

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

MAPPA_STATI = {
    "completata": "completata", "completato": "completata",
    "in_ritardo": "in_ritardo", "in ritardo": "in_ritardo", "ritardo": "in_ritardo",
    "annullata": "annullata", "annullato": "annullata",
}

SCONOSCIUTO = "Sconosciuto"


# ---------------------------------------------------------------------------
# Estrazione
# ---------------------------------------------------------------------------

def estrai(cartella: Path = cfg.DIR_RAW) -> dict[str, pd.DataFrame]:
    nomi = ["clienti", "fornitori", "operatori", "richieste"]
    return {n: pd.read_csv(cartella / f"{n}.csv", dtype=str, keep_default_na=False,
                           na_values=[""]) for n in nomi}


# ---------------------------------------------------------------------------
# Trasformazione
# ---------------------------------------------------------------------------

def pulisci_testo(s: pd.Series) -> pd.Series:
    """Rimuove spazi superflui (inizio, fine e doppi)."""
    return s.str.strip().str.replace(r"\s+", " ", regex=True)


def uniforma(s: pd.Series, valori_ammessi) -> pd.Series:
    """Riconduce varianti di maiuscole/spazi al valore canonico; NaN se sconosciuto."""
    mappa = {v.lower(): v for v in valori_ammessi}
    return pulisci_testo(s).str.lower().map(mappa)


def parse_data_ora(s: pd.Series) -> pd.Series:
    """Accetta sia AAAA-MM-GG HH:MM sia GG/MM/AAAA HH:MM."""
    s = pulisci_testo(s)
    iso = pd.to_datetime(s, format="%Y-%m-%d %H:%M", errors="coerce")
    ita = pd.to_datetime(s, format="%d/%m/%Y %H:%M", errors="coerce")
    return iso.fillna(ita)


def parse_importo(s: pd.Series) -> pd.Series:
    """Accetta il punto o la virgola come separatore decimale."""
    return pd.to_numeric(pulisci_testo(s).str.replace(",", ".", regex=False), errors="coerce")


def fascia_oraria(ora: int) -> str:
    if ora < 7:
        return "Notte"
    if ora < 13:
        return "Mattina"
    if ora < 19:
        return "Pomeriggio"
    return "Sera"


def fascia_esperienza(anni) -> str:
    if pd.isna(anni):
        return SCONOSCIUTO
    return "Junior" if anni < 3 else ("Intermedio" if anni < 8 else "Senior")


class Report:
    """Raccoglie i controlli di qualità e le righe scartate."""

    def __init__(self):
        self.righe: list[str] = []
        self.scarti: list[pd.DataFrame] = []

    def log(self, msg: str):
        self.righe.append(msg)
        print("  " + msg)

    def scarta(self, df: pd.DataFrame, tabella: str, motivo: str):
        if len(df):
            self.scarti.append(df.assign(tabella=tabella, motivo=motivo))
            self.log(f"[{tabella}] scartate {len(df)} righe: {motivo}")


def _rimuovi_duplicati(df, chiave, tabella, rep):
    n0 = len(df)
    df = df.drop_duplicates()
    if n0 - len(df):
        rep.log(f"[{tabella}] rimossi {n0 - len(df)} duplicati esatti")
    dup = df[df.duplicated(chiave, keep="first")]
    rep.scarta(dup, tabella, f"{chiave} ripetuto con valori diversi")
    return df.drop(dup.index)


def _scarta_se(df, maschera, tabella, motivo, rep):
    rep.scarta(df[maschera], tabella, motivo)
    return df[~maschera]


def trasforma(raw: dict[str, pd.DataFrame], rep: Report) -> dict[str, pd.DataFrame]:
    zone, categorie = list(cfg.ZONE), list(cfg.CATEGORIE)
    tipi_attivita = [c["operatore"] for c in cfg.CATEGORIE.values()]

    # --- clienti ----------------------------------------------------------
    c = raw["clienti"].copy()
    rep.log(f"[clienti] lette {len(c)} righe")
    c = _rimuovi_duplicati(c, "cliente_id", "clienti", rep)
    c["cliente_id"] = pulisci_testo(c["cliente_id"])
    c["zona"] = uniforma(c["zona"], zone)
    c = _scarta_se(c, c["zona"].isna(), "clienti", "zona non riconosciuta", rep)
    c["data_iscrizione"] = pd.to_datetime(c["data_iscrizione"], errors="coerce")
    c["anno_iscrizione"] = c["data_iscrizione"].dt.year.astype("Int64")
    c["data_iscrizione"] = c["data_iscrizione"].dt.strftime("%Y-%m-%d")
    c["canale_iscrizione"] = pulisci_testo(c["canale_iscrizione"]).fillna(SCONOSCIUTO)

    # --- fornitori --------------------------------------------------------
    f = raw["fornitori"].copy()
    rep.log(f"[fornitori] lette {len(f)} righe")
    f = _rimuovi_duplicati(f, "fornitore_id", "fornitori", rep)
    f["fornitore_id"] = pulisci_testo(f["fornitore_id"])
    f["nome"] = pulisci_testo(f["nome"])
    f["zona"] = uniforma(f["zona"], zone)
    f["categoria"] = uniforma(f["categoria"], categorie)
    f = _scarta_se(f, f["zona"].isna() | f["categoria"].isna(), "fornitori",
                   "zona o categoria non riconosciuta", rep)

    # --- operatori --------------------------------------------------------
    o = raw["operatori"].copy()
    rep.log(f"[operatori] lette {len(o)} righe")
    o = _rimuovi_duplicati(o, "operatore_id", "operatori", rep)
    o["operatore_id"] = pulisci_testo(o["operatore_id"])
    o["zona"] = uniforma(o["zona"], zone)
    o["tipo_attivita"] = uniforma(o["tipo_attivita"], tipi_attivita)
    o = _scarta_se(o, o["zona"].isna() | o["tipo_attivita"].isna(), "operatori",
                   "zona o attività non riconosciuta", rep)
    o["anni_esperienza"] = pd.to_numeric(o["anni_esperienza"], errors="coerce").astype("Int64")
    o["fascia_esperienza"] = o["anni_esperienza"].map(fascia_esperienza)

    # --- richieste --------------------------------------------------------
    r = raw["richieste"].copy()
    rep.log(f"[richieste] lette {len(r)} righe")
    r = _rimuovi_duplicati(r, "richiesta_id", "richieste", rep)
    for col in ["richiesta_id", "cliente_id", "fornitore_id", "operatore_id"]:
        r[col] = pulisci_testo(r[col])

    r["data_ora"] = parse_data_ora(r["data_ora"])
    r = _scarta_se(r, r["data_ora"].isna(), "richieste", "data/ora non leggibile", rep)

    r["importo"] = parse_importo(r["importo"])
    r = _scarta_se(r, r["importo"].isna() | (r["importo"] < 0), "richieste",
                   "importo mancante o negativo", rep)

    r["stato"] = pulisci_testo(r["stato"]).str.lower().map(MAPPA_STATI)
    r = _scarta_se(r, r["stato"].isna(), "richieste", "stato non riconosciuto", rep)

    r["tempo_erogazione_min"] = pd.to_numeric(r["tempo_erogazione_min"], errors="coerce").astype("Int64")
    erogata = r["stato"] != "annullata"
    r = _scarta_se(r, erogata & r["tempo_erogazione_min"].isna(), "richieste",
                   "tempo di erogazione mancante per una richiesta erogata", rep)
    # Coerenza: una richiesta annullata non genera incasso né tempo di erogazione
    annullate = r["stato"] == "annullata"
    r.loc[annullate, "importo"] = 0.0
    r.loc[annullate, "tempo_erogazione_min"] = pd.NA

    # Integrità referenziale verso le anagrafiche
    r = _scarta_se(r, ~r["cliente_id"].isin(c["cliente_id"]), "richieste", "cliente inesistente", rep)
    r = _scarta_se(r, ~r["fornitore_id"].isin(f["fornitore_id"]), "richieste", "fornitore inesistente", rep)
    senza_op = r["operatore_id"].isna() | ~r["operatore_id"].isin(o["operatore_id"])
    if senza_op.any():
        rep.log(f"[richieste] {int(senza_op.sum())} richieste senza operatore valido "
                f"-> collegate al membro '{SCONOSCIUTO}'")
    r.loc[senza_op, "operatore_id"] = None

    r["ora"] = r["data_ora"].dt.hour
    r["fascia_oraria"] = r["ora"].map(fascia_oraria)
    r["flag_erogata"] = (r["stato"] != "annullata").astype(int)
    r["flag_annullata"] = (r["stato"] == "annullata").astype(int)
    r["flag_ritardo"] = (r["stato"] == "in_ritardo").astype(int)
    rep.log(f"[richieste] righe valide da caricare: {len(r)}")

    return {"clienti": c, "fornitori": f, "operatori": o, "richieste": r}


def costruisci_dim_tempo(inizio, fine) -> pd.DataFrame:
    """Calendario completo (anche i giorni senza richieste)."""
    giorni = pd.date_range(inizio, fine, freq="D")
    iso = giorni.isocalendar()
    return pd.DataFrame({
        "sk_tempo": giorni.strftime("%Y%m%d").astype(int),
        "data": giorni.strftime("%Y-%m-%d"),
        "anno": giorni.year,
        "trimestre": giorni.quarter,
        "mese": giorni.month,
        "nome_mese": [MESI[m - 1] for m in giorni.month],
        "anno_mese": giorni.strftime("%Y-%m"),
        "settimana_iso": iso["week"].to_numpy(),
        "giorno_mese": giorni.day,
        "giorno_settimana": giorni.dayofweek + 1,
        "nome_giorno": [GIORNI[d] for d in giorni.dayofweek],
        "is_weekend": (giorni.dayofweek >= 5).astype(int),
    })


# ---------------------------------------------------------------------------
# Caricamento
# ---------------------------------------------------------------------------

def _con_chiave_surrogata(df, nome_sk, membro_sconosciuto: dict):
    df = df.reset_index(drop=True)
    df.insert(0, nome_sk, range(1, len(df) + 1))
    ignoto = pd.DataFrame([{nome_sk: 0, **membro_sconosciuto}])
    return pd.concat([ignoto, df], ignore_index=True)


def carica(dati: dict[str, pd.DataFrame], db_path: Path, rep: Report):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(cfg.SQL_SCHEMA.read_text(encoding="utf-8"))

    dim_cliente = _con_chiave_surrogata(
        dati["clienti"][["cliente_id", "zona", "data_iscrizione", "anno_iscrizione", "canale_iscrizione"]],
        "sk_cliente", {"cliente_id": "N/D", "zona": SCONOSCIUTO, "canale_iscrizione": SCONOSCIUTO})
    dim_fornitore = _con_chiave_surrogata(
        dati["fornitori"][["fornitore_id", "nome", "categoria", "zona"]],
        "sk_fornitore", {"fornitore_id": "N/D", "nome": SCONOSCIUTO, "categoria": SCONOSCIUTO, "zona": SCONOSCIUTO})
    dim_operatore = _con_chiave_surrogata(
        dati["operatori"][["operatore_id", "zona", "tipo_attivita", "anni_esperienza", "fascia_esperienza"]],
        "sk_operatore", {"operatore_id": "N/D", "zona": SCONOSCIUTO, "tipo_attivita": SCONOSCIUTO,
                         "fascia_esperienza": SCONOSCIUTO})

    r = dati["richieste"]
    inizio = min(pd.Timestamp(cfg.DATA_INIZIO), r["data_ora"].min()).normalize()
    fine = max(pd.Timestamp(cfg.DATA_FINE), r["data_ora"].max()).normalize()
    dim_tempo = costruisci_dim_tempo(inizio, fine)

    # Sostituzione dei codici di origine con le chiavi surrogate
    sk_c = dict(zip(dim_cliente["cliente_id"], dim_cliente["sk_cliente"]))
    sk_f = dict(zip(dim_fornitore["fornitore_id"], dim_fornitore["sk_fornitore"]))
    sk_o = dict(zip(dim_operatore["operatore_id"], dim_operatore["sk_operatore"]))
    fact = pd.DataFrame({
        "richiesta_id": r["richiesta_id"],
        "sk_cliente": r["cliente_id"].map(sk_c),
        "sk_fornitore": r["fornitore_id"].map(sk_f),
        "sk_operatore": r["operatore_id"].map(sk_o).fillna(0).astype(int),
        "sk_tempo": r["data_ora"].dt.strftime("%Y%m%d").astype(int),
        "ora": r["ora"],
        "fascia_oraria": r["fascia_oraria"],
        "stato": r["stato"],
        "importo": r["importo"].round(2),
        "tempo_erogazione_min": r["tempo_erogazione_min"],
        "flag_erogata": r["flag_erogata"],
        "flag_annullata": r["flag_annullata"],
        "flag_ritardo": r["flag_ritardo"],
    }).sort_values(["sk_tempo", "ora", "richiesta_id"])

    with con:
        for nome, df in [("dim_cliente", dim_cliente), ("dim_fornitore", dim_fornitore),
                         ("dim_operatore", dim_operatore), ("dim_tempo", dim_tempo),
                         ("fact_richieste", fact)]:
            df.to_sql(nome, con, if_exists="append", index=False)
            rep.log(f"[load] {nome:<15} {len(df):>5} righe")

    # Controlli finali sul warehouse
    orfani = con.execute("PRAGMA foreign_key_check").fetchall()
    tot_db = con.execute("SELECT ROUND(SUM(importo), 2) FROM fact_richieste").fetchone()[0]
    rep.log(f"[check] violazioni di chiave esterna: {len(orfani)}")
    rep.log(f"[check] incassi totali caricati: {tot_db:.2f} € "
            f"(attesi {r['importo'].sum():.2f} €)")
    assert not orfani, "Il warehouse contiene chiavi esterne non valide"
    assert abs(tot_db - r["importo"].sum()) < 0.01, "Totale importi non coerente"
    con.close()


def salva_report(rep: Report, cartella: Path = cfg.DIR_SCARTI):
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "report_qualita.txt").write_text("\n".join(rep.righe) + "\n", encoding="utf-8")
    scarti = pd.concat(rep.scarti) if rep.scarti else pd.DataFrame(columns=["tabella", "motivo"])
    scarti.to_csv(cartella / "righe_scartate.csv", index=False)


def main():
    print("ETL Manolesta")
    rep = Report()
    raw = estrai()
    dati = trasforma(raw, rep)
    carica(dati, cfg.DB_PATH, rep)
    salva_report(rep)
    print(f"Warehouse pronto: {cfg.DB_PATH}")


if __name__ == "__main__":
    main()
