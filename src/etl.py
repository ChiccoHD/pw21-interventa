"""ETL: dai CSV al data warehouse SQLite con schema a stella.

Caricamento iniziale: ricrea il warehouse dal dataset in data/raw/.
Caricamento incrementale: applica i pacchetti mensili di data/raw/incrementi/ non ancora
caricati. Le anagrafiche sono storicizzate (SCD tipo 2 per gli attributi in cfg.SCD2,
tipo 1 per gli altri). Ogni caricamento è una transazione: se un controllo di qualità
dà ERRORE il database torna allo stato precedente e il caricamento risulta RESPINTO.

Uso: python -m src.etl [--incrementale]
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config as cfg
from src.qualita import esegui_controlli

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]

MAPPA_STATI = {
    "completata": "completata", "completato": "completata",
    "in_ritardo": "in_ritardo", "in ritardo": "in_ritardo", "ritardo": "in_ritardo",
    "annullata": "annullata", "annullato": "annullata",
}

SCONOSCIUTO = "Sconosciuto"

# tabella -> (sorgente, chiave naturale, chiave surrogata, attributi)
DIMENSIONI = {
    "dim_cliente": ("clienti", "cliente_id", "sk_cliente",
                    ["zona", "data_iscrizione", "anno_iscrizione", "canale_iscrizione"]),
    "dim_fornitore": ("fornitori", "fornitore_id", "sk_fornitore", ["nome", "categoria", "zona"]),
    "dim_operatore": ("operatori", "operatore_id", "sk_operatore",
                      ["zona", "tipo_attivita", "anni_esperienza", "fascia_esperienza"]),
}


class CaricamentoRespinto(Exception):
    pass


class Report:
    def __init__(self):
        self.righe: list[str] = []
        self.eventi: list[dict] = []
        self.scarti: list[pd.DataFrame] = []

    def log(self, msg: str):
        self.righe.append(msg)
        print("  " + msg)

    def evento(self, tabella: str, tipo: str, descrizione: str, righe: int):
        if righe:
            self.eventi.append({"tabella": tabella, "tipo": tipo, "descrizione": descrizione, "righe": int(righe)})
            self.log(f"[{tabella}] {tipo}: {descrizione} ({int(righe)})")

    def scarta(self, df: pd.DataFrame, tabella: str, motivo: str):
        if len(df):
            self.scarti.append(df.assign(tabella=tabella, motivo=motivo))
            self.evento(tabella, "scarto", motivo, len(df))

    def righe_scartate(self, tabella: str) -> int:
        return sum(e["righe"] for e in self.eventi if e["tabella"] == tabella and e["tipo"] == "scarto")


def estrai(cartella: Path) -> dict[str, pd.DataFrame]:
    return {n: pd.read_csv(cartella / f"{n}.csv", dtype=str, keep_default_na=False, na_values=[""])
            for n in ["clienti", "fornitori", "operatori", "richieste"]}


def pulisci_testo(s: pd.Series) -> pd.Series:
    return s.str.strip().str.replace(r"\s+", " ", regex=True)


def uniforma(s: pd.Series, valori_ammessi) -> pd.Series:
    """Riconduce le varianti di maiuscole e spazi al valore canonico (NaN se sconosciuto)."""
    mappa = {v.lower(): v for v in valori_ammessi}
    return pulisci_testo(s).str.lower().map(mappa)


def parse_data_ora(s: pd.Series) -> pd.Series:
    s = pulisci_testo(s)
    iso = pd.to_datetime(s, format="%Y-%m-%d %H:%M", errors="coerce")
    ita = pd.to_datetime(s, format="%d/%m/%Y %H:%M", errors="coerce")
    return iso.fillna(ita)


def parse_importo(s: pd.Series) -> pd.Series:
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


def _correggi_testo(df, col, valori, tabella, rep):
    prima = df[col]
    df[col] = uniforma(prima, valori)
    rep.evento(tabella, "correzione", f"{col}: maiuscole/spazi uniformati",
               (prima.notna() & df[col].notna() & (prima != df[col])).sum())


def _rimuovi_duplicati(df, chiave, tabella, rep):
    n0 = len(df)
    df = df.drop_duplicates()
    rep.evento(tabella, "correzione", "righe duplicate rimosse", n0 - len(df))
    dup = df[df.duplicated(chiave, keep="first")]
    rep.scarta(dup, tabella, f"{chiave} ripetuto con valori diversi")
    return df.drop(dup.index)


def _scarta_se(df, maschera, tabella, motivo, rep):
    rep.scarta(df[maschera], tabella, motivo)
    return df[~maschera]


def trasforma(raw: dict[str, pd.DataFrame], rep: Report) -> dict[str, pd.DataFrame]:
    zone, categorie = list(cfg.ZONE), list(cfg.CATEGORIE)
    tipi_attivita = [c["operatore"] for c in cfg.CATEGORIE.values()]

    c = raw["clienti"].copy()
    rep.log(f"[clienti] lette {len(c)} righe")
    c = _rimuovi_duplicati(c, "cliente_id", "clienti", rep)
    c["cliente_id"] = pulisci_testo(c["cliente_id"])
    _correggi_testo(c, "zona", zone, "clienti", rep)
    c = _scarta_se(c, c["zona"].isna(), "clienti", "zona non riconosciuta", rep)
    c["data_iscrizione"] = pd.to_datetime(c["data_iscrizione"], errors="coerce")
    c["anno_iscrizione"] = c["data_iscrizione"].dt.year.astype("Int64")
    c["data_iscrizione"] = c["data_iscrizione"].dt.strftime("%Y-%m-%d")
    c["canale_iscrizione"] = pulisci_testo(c["canale_iscrizione"]).fillna(SCONOSCIUTO)

    f = raw["fornitori"].copy()
    rep.log(f"[fornitori] lette {len(f)} righe")
    f = _rimuovi_duplicati(f, "fornitore_id", "fornitori", rep)
    f["fornitore_id"] = pulisci_testo(f["fornitore_id"])
    f["nome"] = pulisci_testo(f["nome"])
    _correggi_testo(f, "zona", zone, "fornitori", rep)
    _correggi_testo(f, "categoria", categorie, "fornitori", rep)
    f = _scarta_se(f, f["zona"].isna() | f["categoria"].isna(), "fornitori",
                   "zona o categoria non riconosciuta", rep)

    o = raw["operatori"].copy()
    rep.log(f"[operatori] lette {len(o)} righe")
    o = _rimuovi_duplicati(o, "operatore_id", "operatori", rep)
    o["operatore_id"] = pulisci_testo(o["operatore_id"])
    _correggi_testo(o, "zona", zone, "operatori", rep)
    _correggi_testo(o, "tipo_attivita", tipi_attivita, "operatori", rep)
    o = _scarta_se(o, o["zona"].isna() | o["tipo_attivita"].isna(), "operatori",
                   "zona o attività non riconosciuta", rep)
    o["anni_esperienza"] = pd.to_numeric(o["anni_esperienza"], errors="coerce").astype("Int64")
    o["fascia_esperienza"] = o["anni_esperienza"].map(fascia_esperienza)

    r = raw["richieste"].copy()
    rep.log(f"[richieste] lette {len(r)} righe")
    r = _rimuovi_duplicati(r, "richiesta_id", "richieste", rep)
    for col in ["richiesta_id", "cliente_id", "fornitore_id", "operatore_id"]:
        r[col] = pulisci_testo(r[col])

    grezza = pulisci_testo(r["data_ora"])
    r["data_ora"] = parse_data_ora(r["data_ora"])
    rep.evento("richieste", "correzione", "data in formato gg/mm/aaaa convertita",
               (pd.to_datetime(grezza, format="%Y-%m-%d %H:%M", errors="coerce").isna()
                & r["data_ora"].notna()).sum())
    r = _scarta_se(r, r["data_ora"].isna(), "richieste", "data/ora non leggibile", rep)

    rep.evento("richieste", "correzione", "importo con la virgola convertito",
               r["importo"].str.contains(",", regex=False, na=False).sum())
    r["importo"] = parse_importo(r["importo"])
    r = _scarta_se(r, r["importo"].isna() | (r["importo"] < 0), "richieste",
                   "importo mancante o negativo", rep)

    stato_grezzo = r["stato"]
    r["stato"] = pulisci_testo(r["stato"]).str.lower().map(MAPPA_STATI)
    rep.evento("richieste", "correzione", "stato normalizzato",
               (stato_grezzo.notna() & r["stato"].notna() & (stato_grezzo != r["stato"])).sum())
    r = _scarta_se(r, r["stato"].isna(), "richieste", "stato non riconosciuto", rep)

    r["tempo_erogazione_min"] = pd.to_numeric(r["tempo_erogazione_min"], errors="coerce").astype("Int64")
    erogata = r["stato"] != "annullata"
    r = _scarta_se(r, erogata & r["tempo_erogazione_min"].isna(), "richieste",
                   "tempo di erogazione mancante per una richiesta erogata", rep)
    annullate = r["stato"] == "annullata"
    rep.evento("richieste", "correzione", "importo azzerato su richiesta annullata",
               (annullate & (r["importo"] != 0)).sum())
    r.loc[annullate, "importo"] = 0.0
    r.loc[annullate, "tempo_erogazione_min"] = pd.NA

    r = _scarta_se(r, ~r["cliente_id"].isin(c["cliente_id"]), "richieste", "cliente inesistente", rep)
    r = _scarta_se(r, ~r["fornitore_id"].isin(f["fornitore_id"]), "richieste", "fornitore inesistente", rep)
    senza_op = r["operatore_id"].isna() | ~r["operatore_id"].isin(o["operatore_id"])
    rep.evento("richieste", "correzione", f"operatore mancante, collegato a '{SCONOSCIUTO}'", senza_op.sum())
    r.loc[senza_op, "operatore_id"] = None

    r["ora"] = r["data_ora"].dt.hour
    r["fascia_oraria"] = r["ora"].map(fascia_oraria)
    r["flag_erogata"] = (r["stato"] != "annullata").astype(int)
    r["flag_annullata"] = (r["stato"] == "annullata").astype(int)
    r["flag_ritardo"] = (r["stato"] == "in_ritardo").astype(int)
    rep.log(f"[richieste] righe valide: {len(r)}")
    return {"clienti": c, "fornitori": f, "operatori": o, "richieste": r}


def _valore_sql(v):
    if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
        return None
    return v.item() if isinstance(v, np.generic) else v


def inserisci(con, tabella: str, df: pd.DataFrame, ignora_esistenti=False):
    if df.empty:
        return
    colonne = list(df.columns)
    sql = (f"INSERT {'OR IGNORE ' if ignora_esistenti else ''}INTO {tabella} ({', '.join(colonne)}) "
           f"VALUES ({', '.join('?' * len(colonne))})")
    righe = [[_valore_sql(v) for v in riga] for riga in df.astype(object).itertuples(index=False)]
    con.executemany(sql, righe)


def calendario(inizio, fine) -> pd.DataFrame:
    giorni = pd.date_range(inizio, fine, freq="D")
    return pd.DataFrame({
        "sk_tempo": giorni.strftime("%Y%m%d").astype(int),
        "data": giorni.strftime("%Y-%m-%d"),
        "anno": giorni.year,
        "trimestre": giorni.quarter,
        "mese": giorni.month,
        "nome_mese": [MESI[m - 1] for m in giorni.month],
        "anno_mese": giorni.strftime("%Y-%m"),
        "settimana_iso": giorni.isocalendar()["week"].to_numpy(),
        "giorno_mese": giorni.day,
        "giorno_settimana": giorni.dayofweek + 1,
        "nome_giorno": [GIORNI[d] for d in giorni.dayofweek],
        "is_weekend": (giorni.dayofweek >= 5).astype(int),
    })


def _testo(s: pd.Series) -> pd.Series:
    def norma(v):
        if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
            return ""
        if isinstance(v, (float, np.floating)) and float(v).is_integer():
            return str(int(v))
        return str(v)
    return s.astype(object).map(norma)


def _diversi(a: pd.Series, b: pd.Series) -> pd.Series:
    return _testo(a) != _testo(b)


def aggiorna_dimensione(con, tabella: str, nuovi: pd.DataFrame, data_effetto: str) -> tuple[int, int, int]:
    """Confronta l'anagrafica ricevuta con le versioni correnti e applica SCD tipo 1 e 2.

    Restituisce (nuove entità, nuove versioni, entità aggiornate in tipo 1).
    """
    _, chiave, sk, attributi = DIMENSIONI[tabella]
    tipo2 = cfg.SCD2[tabella]
    tipo1 = [a for a in attributi if a not in tipo2]
    nuovi = nuovi[[chiave] + attributi].reset_index(drop=True)
    correnti = pd.read_sql_query(f"SELECT * FROM {tabella} WHERE corrente = 1 AND {sk} > 0", con)
    m = nuovi.merge(correnti, on=chiave, how="left", suffixes=("", "_db"), indicator=True)
    prossimo_sk = con.execute(f"SELECT COALESCE(MAX({sk}), 0) + 1 FROM {tabella}").fetchone()[0]
    inizio_nuove = cfg.INIZIO_VALIDITA if correnti.empty else data_effetto

    entita = m[m["_merge"] == "left_only"][[chiave] + attributi].copy()
    esistenti = m[m["_merge"] == "both"]
    cambio2 = np.zeros(len(esistenti), dtype=bool)
    for a in tipo2:
        cambio2 |= _diversi(esistenti[a], esistenti[a + "_db"]).to_numpy()
    cambio1 = np.zeros(len(esistenti), dtype=bool)
    for a in tipo1:
        cambio1 |= _diversi(esistenti[a], esistenti[a + "_db"]).to_numpy()

    versioni = esistenti[cambio2]
    if len(versioni):
        giorno_prima = (pd.Timestamp(data_effetto) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        con.executemany(f"UPDATE {tabella} SET valido_al = ?, corrente = 0 WHERE {sk} = ?",
                        [(giorno_prima, int(x)) for x in versioni[sk]])

    parti = [df for df in (entita.assign(valido_dal=inizio_nuove),
                           versioni[[chiave] + attributi].assign(valido_dal=data_effetto)) if len(df)]
    da_inserire = pd.concat(parti, ignore_index=True) if parti else entita.assign(valido_dal=inizio_nuove)
    da_inserire.insert(0, sk, range(prossimo_sk, prossimo_sk + len(da_inserire)))
    inserisci(con, tabella, da_inserire.assign(valido_al=cfg.FINE_VALIDITA, corrente=1))

    aggiornati = esistenti[cambio1]
    if tipo1 and len(aggiornati):
        assegna = ", ".join(f"{a} = ?" for a in tipo1)
        con.executemany(f"UPDATE {tabella} SET {assegna} WHERE {chiave} = ?",
                        [[_valore_sql(v) for v in riga[tipo1]] + [riga[chiave]] for _, riga in aggiornati.iterrows()])
    return len(entita), len(versioni), len(aggiornati)


def _sk_valide(con, tabella: str, richieste: pd.DataFrame) -> pd.Series:
    """Chiave surrogata della versione valida alla data di ogni richiesta (0 se manca)."""
    _, chiave, sk, _ = DIMENSIONI[tabella]
    versioni = pd.read_sql_query(f"SELECT {chiave}, {sk}, valido_dal, valido_al FROM {tabella} WHERE {sk} > 0", con)
    m = (richieste[["richiesta_id", chiave]].assign(data=richieste["data_ora"].dt.strftime("%Y-%m-%d"))
         .merge(versioni, on=chiave, how="left"))
    m = m[m[sk].isna() | ((m["data"] >= m["valido_dal"]) & (m["data"] <= m["valido_al"]))]
    m = m.drop_duplicates("richiesta_id")
    return (richieste[["richiesta_id"]].merge(m[["richiesta_id", sk]], on="richiesta_id", how="left")[sk]
            .fillna(0).astype(int).to_numpy())


def carica_fatti(con, r: pd.DataFrame, id_caricamento: int) -> tuple[int, int, float]:
    presenti = {x for (x,) in con.execute("SELECT richiesta_id FROM fact_richieste")}
    nuove = r[~r["richiesta_id"].isin(presenti)].reset_index(drop=True)
    fatti = pd.DataFrame({
        "richiesta_id": nuove["richiesta_id"],
        "sk_cliente": _sk_valide(con, "dim_cliente", nuove),
        "sk_fornitore": _sk_valide(con, "dim_fornitore", nuove),
        "sk_operatore": _sk_valide(con, "dim_operatore", nuove),
        "sk_tempo": nuove["data_ora"].dt.strftime("%Y%m%d").astype(int),
        "id_caricamento": id_caricamento,
        "ora": nuove["ora"],
        "fascia_oraria": nuove["fascia_oraria"],
        "stato": nuove["stato"],
        "importo": nuove["importo"].round(2),
        "tempo_erogazione_min": nuove["tempo_erogazione_min"],
        "flag_erogata": nuove["flag_erogata"],
        "flag_annullata": nuove["flag_annullata"],
        "flag_ritardo": nuove["flag_ritardo"],
    }).sort_values(["sk_tempo", "ora", "richiesta_id"])
    inserisci(con, "fact_richieste", fatti)
    return len(fatti), len(r) - len(fatti), round(float(fatti["importo"].sum()), 2)


def connetti(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, isolation_level=None)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def crea_warehouse(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = connetti(db_path)
    con.executescript(cfg.SQL_SCHEMA.read_text(encoding="utf-8"))
    con.execute("PRAGMA foreign_keys = ON")
    ignoto = {"valido_dal": cfg.INIZIO_VALIDITA, "valido_al": cfg.FINE_VALIDITA, "corrente": 1}
    inserisci(con, "dim_cliente", pd.DataFrame([{"sk_cliente": 0, "cliente_id": "N/D", "zona": SCONOSCIUTO,
                                                 "canale_iscrizione": SCONOSCIUTO, **ignoto}]))
    inserisci(con, "dim_fornitore", pd.DataFrame([{"sk_fornitore": 0, "fornitore_id": "N/D", "nome": SCONOSCIUTO,
                                                   "categoria": SCONOSCIUTO, "zona": SCONOSCIUTO, **ignoto}]))
    inserisci(con, "dim_operatore", pd.DataFrame([{"sk_operatore": 0, "operatore_id": "N/D", "zona": SCONOSCIUTO,
                                                   "tipo_attivita": SCONOSCIUTO,
                                                   "fascia_esperienza": SCONOSCIUTO, **ignoto}]))
    return con


def esegui_caricamento(con, cartella: Path, tipo: str, periodo: str, data_effetto: str,
                       cartella_scarti: Path | None = None) -> dict:
    print(f"Caricamento {tipo} {periodo}")
    rep = Report()
    raw = estrai(cartella)
    dati = trasforma(raw, rep)
    r = dati["richieste"]
    lette, scartate = len(raw["richieste"]), rep.righe_scartate("richieste")
    id_c = con.execute("SELECT COALESCE(MAX(id_caricamento), 0) + 1 FROM etl_caricamenti").fetchone()[0]
    registro = {"id_caricamento": id_c, "tipo": tipo, "periodo": periodo,
                "eseguito_il": datetime.now().isoformat(timespec="seconds"),
                "righe_lette": lette, "righe_caricate": 0, "righe_scartate": scartate,
                "nuove_entita": 0, "nuove_versioni": 0, "esito": "COMPLETATO"}

    con.execute("BEGIN")
    try:
        inserisci(con, "etl_caricamenti", pd.DataFrame([registro]))
        for tabella, (sorgente, *_ ) in DIMENSIONI.items():
            entita, versioni, tipo1 = aggiorna_dimensione(con, tabella, dati[sorgente], data_effetto)
            registro["nuove_entita"] += entita
            registro["nuove_versioni"] += versioni
            rep.evento(tabella, "storico", "nuove entità", entita if tipo == "incrementale" else 0)
            rep.evento(tabella, "storico", "nuove versioni (SCD tipo 2)", versioni)
            rep.evento(tabella, "storico", "attributi sovrascritti (SCD tipo 1)", tipo1)

        if tipo == "iniziale":
            inizio, fine = cfg.DATA_INIZIO, cfg.DATA_FINE
        else:
            inizio, fine = data_effetto, pd.Timestamp(data_effetto) + pd.offsets.MonthEnd(0)
        if len(r):
            inizio, fine = min(pd.Timestamp(inizio), r["data_ora"].min()), max(pd.Timestamp(fine), r["data_ora"].max())
        inserisci(con, "dim_tempo", calendario(pd.Timestamp(inizio).normalize(), pd.Timestamp(fine).normalize()),
                  ignora_esistenti=True)

        caricate, gia_presenti, incassi = carica_fatti(con, r, id_c)
        rep.evento("richieste", "correzione", "già presenti nel warehouse, ignorate", gia_presenti)
        registro["righe_caricate"] = caricate
        con.execute("UPDATE etl_caricamenti SET righe_caricate = ?, nuove_entita = ?, nuove_versioni = ? "
                    "WHERE id_caricamento = ?", (caricate, registro["nuove_entita"], registro["nuove_versioni"], id_c))

        esiti = esegui_controlli(con, {"id": id_c, "incassi": incassi, "lette": lette, "scartate": scartate})
        _salva_esiti(con, id_c, rep, esiti)
        if (esiti["esito"] == "ERRORE").any():
            raise CaricamentoRespinto(", ".join(esiti.loc[esiti["esito"] == "ERRORE", "regola"]))
        con.execute("COMMIT")
    except CaricamentoRespinto as e:
        con.execute("ROLLBACK")
        registro.update(esito="RESPINTO", righe_caricate=0, nuove_entita=0, nuove_versioni=0)
        con.execute("BEGIN")
        inserisci(con, "etl_caricamenti", pd.DataFrame([registro]))
        _salva_esiti(con, id_c, rep, esiti)
        con.execute("COMMIT")
        rep.log(f"[esito] RESPINTO: controlli in errore -> {e}")
    except Exception:
        con.execute("ROLLBACK")
        raise

    for _, x in esiti[esiti["esito"] != "OK"].iterrows():
        rep.log(f"[qualità] {x['esito']}: {x['descrizione']} ({x['percentuale']}%)")
    rep.log(f"[esito] {registro['esito']}: {registro['righe_caricate']} richieste caricate, "
            f"{registro['nuove_versioni']} nuove versioni nelle anagrafiche")
    if cartella_scarti is not None:
        _salva_scarti(rep, cartella_scarti, periodo)
    return registro


def _salva_esiti(con, id_c, rep, esiti):
    inserisci(con, "etl_eventi", pd.DataFrame(rep.eventi).assign(id_caricamento=id_c))
    inserisci(con, "dq_risultati", esiti.assign(id_caricamento=id_c))


def _salva_scarti(rep, cartella: Path, periodo: str):
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / f"report_{periodo}.txt").write_text("\n".join(rep.righe) + "\n", encoding="utf-8")
    scarti = pd.concat(rep.scarti) if rep.scarti else pd.DataFrame(columns=["tabella", "motivo"])
    scarti.to_csv(cartella / f"scarti_{periodo}.csv", index=False)


def carica_iniziale(cartella=cfg.DIR_RAW, db_path=cfg.DB_PATH, cartella_scarti=cfg.DIR_SCARTI) -> dict:
    if cartella_scarti is not None and Path(cartella_scarti).exists():
        shutil.rmtree(cartella_scarti)
    con = crea_warehouse(Path(db_path))
    periodo = cfg.DATA_INIZIO[:4] if cfg.DATA_INIZIO[:4] == cfg.DATA_FINE[:4] else f"{cfg.DATA_INIZIO}_{cfg.DATA_FINE}"
    esito = esegui_caricamento(con, Path(cartella), "iniziale", periodo, cfg.INIZIO_VALIDITA, cartella_scarti)
    con.close()
    return esito


def carica_incrementi(cartella=cfg.DIR_INCREMENTI, db_path=cfg.DB_PATH, cartella_scarti=cfg.DIR_SCARTI) -> list[dict]:
    """Carica, in ordine, i pacchetti mensili non ancora caricati con successo."""
    con = connetti(Path(db_path))
    fatti = {p for (p,) in con.execute("SELECT periodo FROM etl_caricamenti WHERE esito = 'COMPLETATO'")}
    pacchetti = sorted(p for p in Path(cartella).glob("????-??") if p.is_dir()) if Path(cartella).exists() else []
    esiti = []
    for p in pacchetti:
        if p.name in fatti:
            print(f"Pacchetto {p.name} già caricato: ignorato")
            continue
        esiti.append(esegui_caricamento(con, p, "incrementale", p.name, f"{p.name}-01", cartella_scarti))
    if not pacchetti:
        print("Nessun pacchetto incrementale da caricare")
    con.close()
    return esiti


def main(argv=None):
    ap = argparse.ArgumentParser(description="ETL del data warehouse Interventa.")
    ap.add_argument("--incrementale", action="store_true", help="carica solo i nuovi pacchetti mensili")
    a = ap.parse_args(argv)
    if a.incrementale:
        carica_incrementi()
    else:
        carica_iniziale()
    print(f"Warehouse: {cfg.DB_PATH}")


if __name__ == "__main__":
    main()
