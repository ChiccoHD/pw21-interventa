"""Generatore dei dati sintetici di Interventa.

Produce il dataset iniziale (data/raw/*.csv, anno 2025) e i pacchetti mensili
successivi (data/raw/incrementi/AAAA-MM/), con nuove richieste e anagrafiche aggiornate.

Uso: python -m src.genera_dati [--seed N] [--richieste N] [--incrementi N] [--pulito]
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from src import config as cfg

PREFISSI = ["Pronto", "Tecno", "Sud", "Casa", "Isola", "Sole", "Trinacria", "Mare",
            "Delta", "Alfa", "Futura", "Rapida", "Nuova", "Punto", "Global"]
RADICI = {"Idraulica": "Idraulica", "Elettricità": "Impianti", "Pulizie": "Clean",
          "Climatizzazione": "Clima", "Elettrodomestici": "Ripara",
          "Giardinaggio": "Verde", "Piccoli traslochi": "Trasporti"}
SUFFISSI = ["Service", "Group", "Srl", "Pro", "Team", "Lab", "Point", "Sicilia"]
CANALI = (["app Android", "app iOS", "sito web"], [0.5, 0.35, 0.15])


@dataclass
class Stato:
    """Anagrafiche correnti e pesi di scelta, aggiornati mese per mese."""
    clienti: pd.DataFrame
    fornitori: pd.DataFrame
    operatori: pd.DataFrame
    fedelta: np.ndarray
    popolarita: np.ndarray
    ultima_richiesta: int


def _pesi(valori):
    p = np.array(valori, dtype=float)
    return p / p.sum()


def _mesi_tra(inizio, fine):
    a, b = pd.Timestamp(inizio), pd.Timestamp(fine)
    return (b.year - a.year) * 12 + (b.month - a.month)


def date_crescenti(rng, n, inizio, fine, crescita=0.05):
    """n date ordinate tra inizio e fine, più dense verso la fine del periodo."""
    giorni = pd.date_range(inizio, fine, freq="D")
    mesi = (giorni.year - giorni[0].year) * 12 + (giorni.month - giorni[0].month)
    idx = rng.choice(len(giorni), size=n, p=_pesi((1 + crescita) ** mesi.to_numpy()))
    return giorni[np.sort(idx)]


def coppie_zona_categoria(rng, n):
    """n coppie (zona, categoria) che coprono almeno una volta ogni combinazione."""
    zone, categorie = list(cfg.ZONE), list(cfg.CATEGORIE)
    coppie = [(z, c) for z in zone for c in categorie]
    for _ in range(n - len(coppie)):
        coppie.append(_coppia_casuale(rng))
    rng.shuffle(coppie)
    return coppie


def _coppia_casuale(rng):
    categorie = list(cfg.CATEGORIE)
    return (rng.choice(list(cfg.ZONE), p=_pesi(list(cfg.ZONE.values()))),
            rng.choice(categorie, p=_pesi([cfg.CATEGORIE[c]["peso"] for c in categorie])))


def _nome_fornitore(rng, categoria):
    return f"{rng.choice(PREFISSI)} {RADICI[categoria]} {rng.choice(SUFFISSI)}"


def genera_clienti(rng, n):
    return pd.DataFrame({
        "cliente_id": [f"C{i:04d}" for i in range(1, n + 1)],
        "zona": rng.choice(list(cfg.ZONE), size=n, p=_pesi(list(cfg.ZONE.values()))),
        "data_iscrizione": date_crescenti(rng, n, cfg.DATA_LANCIO, cfg.DATA_FINE).strftime("%Y-%m-%d"),
        "canale_iscrizione": rng.choice(CANALI[0], size=n, p=CANALI[1]),
    })


def genera_fornitori(rng, n):
    coppie = coppie_zona_categoria(rng, n)
    nomi, usati = [], set()
    for _, cat in coppie:
        nome = _nome_fornitore(rng, cat)
        if nome in usati:
            nome = f"{nome} {rng.integers(2, 99)}"
        usati.add(nome)
        nomi.append(nome)
    return pd.DataFrame({
        "fornitore_id": [f"F{i:03d}" for i in range(1, n + 1)],
        "nome": nomi,
        "categoria": [c for _, c in coppie],
        "zona": [z for z, _ in coppie],
    })


def genera_operatori(rng, n):
    coppie = coppie_zona_categoria(rng, n)
    return pd.DataFrame({
        "operatore_id": [f"O{i:03d}" for i in range(1, n + 1)],
        "zona": [z for z, _ in coppie],
        "tipo_attivita": [cfg.CATEGORIE[c]["operatore"] for _, c in coppie],
        "anni_esperienza": rng.integers(0, 16, size=n),
    })


def _compila_richiesta(rng, cat, data_ora, s: Stato):
    """Sceglie cliente, fornitore e operatore e simula l'esito dell'intervento."""
    par = cfg.CATEGORIE[cat]
    iscrizione = pd.to_datetime(s.clienti["data_iscrizione"]).to_numpy()
    idonei = np.where(iscrizione <= np.datetime64(data_ora.date()))[0]
    c_idx = rng.choice(idonei, p=_pesi(s.fedelta[idonei]))
    zona = s.clienti.at[c_idx, "zona"]
    f, o = s.fornitori, s.operatori
    cand_f = f.index[(f["zona"] == zona) & (f["categoria"] == cat)].to_numpy()
    f_idx = rng.choice(cand_f, p=_pesi(s.popolarita[cand_f]))
    cand_o = o.index[(o["zona"] == zona) & (o["tipo_attivita"] == par["operatore"])].to_numpy()
    o_idx = rng.choice(cand_o)

    ora = data_ora.hour
    picco = ora in cfg.ORE_PICCO
    if rng.random() < (0.11 if picco else 0.07):
        stato, importo, tempo = "annullata", 0.0, None
    else:
        tempo = par["tempo"] * rng.lognormal(0, 0.25)
        if picco:
            tempo *= 1.15
        tempo *= 1 - min(o.at[o_idx, "anni_esperienza"], 10) * 0.012
        if rng.random() < 0.08:
            tempo *= rng.uniform(1.4, 2.2)
        tempo = int(round(tempo))
        stato = "in_ritardo" if tempo > par["sla"] else "completata"
        importo = max(25.0, rng.normal(par["prezzo"], par["sd"]))
        if data_ora.weekday() >= 5 or ora >= 19 or ora < 7:
            importo *= 1.20
        importo = round(importo * 2) / 2

    return {
        "cliente_id": s.clienti.at[c_idx, "cliente_id"],
        "fornitore_id": f.at[f_idx, "fornitore_id"],
        "operatore_id": o.at[o_idx, "operatore_id"],
        "data_ora": data_ora.strftime("%Y-%m-%d %H:%M"),
        "importo": importo,
        "tempo_erogazione_min": tempo,
        "stato": stato,
    }


def _tabella_richieste(righe, primo_id):
    df = pd.DataFrame(righe).sort_values("data_ora").reset_index(drop=True)
    df.insert(0, "richiesta_id", [f"R{i:05d}" for i in range(primo_id, primo_id + len(df))])
    df["tempo_erogazione_min"] = df["tempo_erogazione_min"].astype("Int64")
    return df


def genera_richieste(rng, n, s: Stato):
    """Richieste dell'anno iniziale: crescita mensile, giorno della settimana e stagionalità."""
    categorie = list(cfg.CATEGORIE)
    pc = _pesi([cfg.CATEGORIE[c]["peso"] for c in categorie])
    giorni = pd.date_range(cfg.DATA_INIZIO, cfg.DATA_FINE, freq="D")
    mese_idx = (giorni.month - 1).to_numpy()
    crescita = (1 + cfg.CRESCITA_MENSILE) ** mese_idx
    peso_giorno = np.array(cfg.PESO_GIORNO)[giorni.dayofweek.to_numpy()]
    peso_ora = _pesi(cfg.PESO_ORA)

    righe = []
    for _ in range(n):
        cat = rng.choice(categorie, p=pc)
        stagione = np.array(cfg.STAGIONALITA.get(cat, [1.0] * 12))[mese_idx]
        giorno = giorni[rng.choice(len(giorni), p=_pesi(crescita * peso_giorno * stagione))]
        ora = int(rng.choice(24, p=peso_ora))
        data_ora = datetime(giorno.year, giorno.month, giorno.day, ora, int(rng.integers(0, 60)))
        righe.append(_compila_richiesta(rng, cat, data_ora, s))
    return _tabella_richieste(righe, 1)


def genera_richieste_mese(rng, inizio_mese: pd.Timestamp, s: Stato):
    """Richieste di un singolo mese successivo, con la stessa crescita del primo anno."""
    categorie = list(cfg.CATEGORIE)
    mese = inizio_mese.month - 1
    k = _mesi_tra(cfg.DATA_INIZIO, inizio_mese)
    attese = cfg.N_RICHIESTE * (1 + cfg.CRESCITA_MENSILE) ** k / sum(
        (1 + cfg.CRESCITA_MENSILE) ** m for m in range(12))
    pc = _pesi([cfg.CATEGORIE[c]["peso"] * cfg.STAGIONALITA.get(c, [1.0] * 12)[mese] for c in categorie])
    giorni = pd.date_range(inizio_mese, inizio_mese + pd.offsets.MonthEnd(0), freq="D")
    peso_giorno = _pesi(np.array(cfg.PESO_GIORNO)[giorni.dayofweek.to_numpy()])
    peso_ora = _pesi(cfg.PESO_ORA)

    righe = []
    for _ in range(rng.poisson(attese)):
        cat = rng.choice(categorie, p=pc)
        giorno = giorni[rng.choice(len(giorni), p=peso_giorno)]
        ora = int(rng.choice(24, p=peso_ora))
        data_ora = datetime(giorno.year, giorno.month, giorno.day, ora, int(rng.integers(0, 60)))
        righe.append(_compila_richiesta(rng, cat, data_ora, s))
    df = _tabella_richieste(righe, s.ultima_richiesta + 1)
    s.ultima_richiesta += len(df)
    return df


def _sposta_in_altra_zona(rng, df, quota, gruppo):
    """Cambia zona a una quota di righe, senza lasciare scoperta nessuna combinazione."""
    zone = list(cfg.ZONE)
    for i in rng.permutation(df.index)[:int(round(len(df) * quota))]:
        if gruppo and ((df["zona"] == df.at[i, "zona"]) & (df[gruppo] == df.at[i, gruppo])).sum() < 2:
            continue
        altre = [z for z in zone if z != df.at[i, "zona"]]
        df.at[i, "zona"] = rng.choice(altre, p=_pesi([cfg.ZONE[z] for z in altre]))


def applica_modifiche(rng, inizio_mese: pd.Timestamp, s: Stato):
    """Evoluzione delle anagrafiche all'inizio di un nuovo mese."""
    fine_mese = inizio_mese + pd.offsets.MonthEnd(0)

    iscritti = s.clienti.index[pd.to_datetime(s.clienti["data_iscrizione"]) < inizio_mese]
    clienti_esistenti = s.clienti.loc[iscritti].copy()
    _sposta_in_altra_zona(rng, clienti_esistenti, cfg.QUOTA_TRASLOCHI_CLIENTI, None)
    s.clienti.loc[iscritti, "zona"] = clienti_esistenti["zona"]

    j = _mesi_tra(cfg.DATA_LANCIO, inizio_mese)
    mesi_base = _mesi_tra(cfg.DATA_LANCIO, cfg.DATA_FINE) + 1
    attesi = cfg.N_CLIENTI * 1.05 ** j / sum(1.05 ** m for m in range(mesi_base))
    n_nuovi = rng.poisson(attesi)
    primo = len(s.clienti) + 1
    nuovi = pd.DataFrame({
        "cliente_id": [f"C{i:04d}" for i in range(primo, primo + n_nuovi)],
        "zona": rng.choice(list(cfg.ZONE), size=n_nuovi, p=_pesi(list(cfg.ZONE.values()))),
        "data_iscrizione": pd.to_datetime(np.sort(rng.choice(
            pd.date_range(inizio_mese, fine_mese, freq="D"), size=n_nuovi))).strftime("%Y-%m-%d"),
        "canale_iscrizione": rng.choice(CANALI[0], size=n_nuovi, p=CANALI[1]),
    })
    s.clienti = pd.concat([s.clienti, nuovi], ignore_index=True)
    s.fedelta = np.concatenate([s.fedelta, rng.lognormal(0, 1.0, size=n_nuovi)])

    _sposta_in_altra_zona(rng, s.fornitori, cfg.QUOTA_TRASFERIMENTI_FORNITORI, "categoria")
    for i in rng.permutation(s.fornitori.index)[:int(round(len(s.fornitori) * cfg.QUOTA_CAMBI_NOME_FORNITORI))]:
        parole = s.fornitori.at[i, "nome"].split()
        parole[2] = rng.choice([x for x in SUFFISSI if x != parole[2]])
        s.fornitori.at[i, "nome"] = " ".join(parole[:3])
    primo = len(s.fornitori) + 1
    nuovi_f = []
    for i in range(primo, primo + cfg.NUOVI_FORNITORI_MESE):
        zona, cat = _coppia_casuale(rng)
        nuovi_f.append({"fornitore_id": f"F{i:03d}", "nome": _nome_fornitore(rng, cat),
                        "categoria": cat, "zona": zona})
    s.fornitori = pd.concat([s.fornitori, pd.DataFrame(nuovi_f)], ignore_index=True)
    s.popolarita = np.concatenate([s.popolarita, rng.pareto(1.1, size=len(nuovi_f)) + 0.02])

    _sposta_in_altra_zona(rng, s.operatori, cfg.QUOTA_TRASFERIMENTI_OPERATORI, "tipo_attivita")
    if inizio_mese.month == 1:
        s.operatori["anni_esperienza"] += 1
    primo = len(s.operatori) + 1
    nuovi_o = []
    for i in range(primo, primo + cfg.NUOVI_OPERATORI_MESE):
        zona, cat = _coppia_casuale(rng)
        nuovi_o.append({"operatore_id": f"O{i:03d}", "zona": zona,
                        "tipo_attivita": cfg.CATEGORIE[cat]["operatore"],
                        "anni_esperienza": int(rng.integers(0, 6))})
    s.operatori = pd.concat([s.operatori, pd.DataFrame(nuovi_o)], ignore_index=True)


def _varia_testo(rng, s):
    return rng.choice([s.lower(), s.upper(), f" {s}", f"{s}  "])


def sporca(rng, clienti, fornitori, operatori, richieste, quota, n_negativi=3, n_orfani=2):
    """Introduce nei dati i difetti tipici delle fonti reali, da correggere nell'ETL."""
    def campione(df, q=quota):
        return rng.choice(df.index, size=max(1, int(round(len(df) * q))), replace=False)

    for df, col in [(clienti, "zona"), (fornitori, "zona"), (fornitori, "categoria"), (operatori, "zona")]:
        idx = campione(df)
        df.loc[idx, col] = [_varia_testo(rng, v) for v in df.loc[idx, col]]

    r = richieste.astype({"importo": object, "data_ora": object, "tempo_erogazione_min": object})
    idx = campione(r)
    r.loc[idx, "importo"] = [f"{float(v):.2f}".replace(".", ",") for v in r.loc[idx, "importo"]]
    idx = campione(r)
    r.loc[idx, "data_ora"] = [datetime.strptime(v, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")
                              for v in r.loc[idx, "data_ora"]]
    idx = campione(r)
    varianti = {"completata": ["Completata", "COMPLETATA ", "completato"],
                "in_ritardo": ["In ritardo", "IN_RITARDO", "ritardo"],
                "annullata": ["Annullata", "annullato", "ANNULLATA "]}
    r.loc[idx, "stato"] = [rng.choice(varianti[v]) for v in r.loc[idx, "stato"]]
    r.loc[campione(r, quota / 2), "operatore_id"] = None
    completate = r.index[r["stato"].str.strip().str.lower().str.startswith("compl")]
    r.loc[rng.choice(completate, n_negativi, replace=False), "importo"] = -50.0
    r.loc[rng.choice(r.index, n_orfani, replace=False), "fornitore_id"] = "F999"
    duplicati = r.loc[campione(r, quota / 3)]
    r = pd.concat([r, duplicati]).sort_index(kind="stable").reset_index(drop=True)
    return clienti, fornitori, operatori, r


def scrivi(cartella: Path, tabelle: dict[str, pd.DataFrame]):
    cartella.mkdir(parents=True, exist_ok=True)
    for nome, df in tabelle.items():
        df.to_csv(cartella / f"{nome}.csv", index=False)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera i CSV sintetici di Interventa.")
    ap.add_argument("--seed", type=int, default=cfg.SEED, help="seme casuale")
    ap.add_argument("--clienti", type=int, default=cfg.N_CLIENTI)
    ap.add_argument("--fornitori", type=int, default=cfg.N_FORNITORI)
    ap.add_argument("--operatori", type=int, default=cfg.N_OPERATORI)
    ap.add_argument("--richieste", type=int, default=cfg.N_RICHIESTE)
    ap.add_argument("--incrementi", type=int, default=cfg.N_INCREMENTI, help="pacchetti mensili da generare")
    ap.add_argument("--pulito", action="store_true", help="esporta i dati senza difetti")
    ap.add_argument("--out", default=str(cfg.DIR_RAW), help="cartella di destinazione")
    a = ap.parse_args(argv)
    out = Path(a.out)

    rng = np.random.default_rng(a.seed)
    clienti = genera_clienti(rng, a.clienti)
    fornitori = genera_fornitori(rng, a.fornitori)
    operatori = genera_operatori(rng, a.operatori)
    s = Stato(clienti, fornitori, operatori,
              fedelta=rng.lognormal(0, 1.0, size=len(clienti)),
              popolarita=rng.pareto(1.1, size=len(fornitori)) + 0.02,
              ultima_richiesta=a.richieste)
    richieste = genera_richieste(rng, a.richieste, s)
    s.clienti, s.fornitori, s.operatori = clienti.copy(), fornitori.copy(), operatori.copy()
    tabelle = [clienti, fornitori, operatori, richieste]
    if not a.pulito:
        tabelle = sporca(rng, *tabelle, cfg.QUOTA_SPORCO)
    scrivi(out, dict(zip(["clienti", "fornitori", "operatori", "richieste"], tabelle)))
    print(f"Dataset iniziale in {out} (seed={a.seed}, difetti={'no' if a.pulito else 'sì'}):")
    for nome, df in zip(["clienti", "fornitori", "operatori", "richieste"], tabelle):
        print(f"  {nome + '.csv':<15} {len(df):>5} righe")

    cartella_inc = out / "incrementi"
    if cartella_inc.exists():
        shutil.rmtree(cartella_inc)
    mese = pd.Timestamp(cfg.PRIMO_INCREMENTO + "-01")
    for _ in range(a.incrementi):
        rng_m = np.random.default_rng([a.seed, mese.year, mese.month])
        applica_modifiche(rng_m, mese, s)
        richieste_m = genera_richieste_mese(rng_m, mese, s)
        tabelle = [s.clienti.copy(), s.fornitori.copy(), s.operatori.copy(), richieste_m]
        if not a.pulito:
            tabelle = sporca(rng_m, *tabelle, cfg.QUOTA_SPORCO, n_negativi=1, n_orfani=1)
        scrivi(cartella_inc / f"{mese:%Y-%m}",
               dict(zip(["clienti", "fornitori", "operatori", "richieste"], tabelle)))
        print(f"Pacchetto {mese:%Y-%m}: {len(richieste_m)} richieste, "
              f"{len(s.clienti)} clienti, {len(s.fornitori)} fornitori, {len(s.operatori)} operatori")
        mese += pd.offsets.MonthBegin(1)


if __name__ == "__main__":
    main()
