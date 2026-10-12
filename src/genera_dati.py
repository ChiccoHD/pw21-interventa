"""Generatore dei dati sintetici di Interventa (CSV in data/raw/).

Uso: python -m src.genera_dati [--seed N] [--richieste N] [--pulito]
"""

from __future__ import annotations

import argparse
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


def _pesi(valori):
    p = np.array(valori, dtype=float)
    return p / p.sum()


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
    pz = _pesi(list(cfg.ZONE.values()))
    pc = _pesi([cfg.CATEGORIE[c]["peso"] for c in categorie])
    for _ in range(n - len(coppie)):
        coppie.append((rng.choice(zone, p=pz), rng.choice(categorie, p=pc)))
    rng.shuffle(coppie)
    return coppie


def genera_clienti(rng, n):
    return pd.DataFrame({
        "cliente_id": [f"C{i:04d}" for i in range(1, n + 1)],
        "zona": rng.choice(list(cfg.ZONE), size=n, p=_pesi(list(cfg.ZONE.values()))),
        "data_iscrizione": date_crescenti(rng, n, cfg.DATA_LANCIO, cfg.DATA_FINE).strftime("%Y-%m-%d"),
        "canale_iscrizione": rng.choice(["app Android", "app iOS", "sito web"], size=n, p=[0.5, 0.35, 0.15]),
    })


def genera_fornitori(rng, n):
    coppie = coppie_zona_categoria(rng, n)
    nomi, usati = [], set()
    for _, cat in coppie:
        nome = f"{rng.choice(PREFISSI)} {RADICI[cat]} {rng.choice(SUFFISSI)}"
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


def genera_richieste(rng, n, clienti, fornitori, operatori):
    categorie = list(cfg.CATEGORIE)
    pc = _pesi([cfg.CATEGORIE[c]["peso"] for c in categorie])

    giorni = pd.date_range(cfg.DATA_INIZIO, cfg.DATA_FINE, freq="D")
    mese_idx = (giorni.month - 1).to_numpy()
    crescita = (1 + cfg.CRESCITA_MENSILE) ** mese_idx
    peso_giorno = np.array(cfg.PESO_GIORNO)[giorni.dayofweek.to_numpy()]
    peso_ora = _pesi(cfg.PESO_ORA)

    iscrizione = pd.to_datetime(clienti["data_iscrizione"]).to_numpy()
    fedelta = rng.lognormal(0, 1.0, size=len(clienti))
    popolarita = rng.pareto(1.1, size=len(fornitori)) + 0.02
    esperienza = operatori["anni_esperienza"].to_numpy()

    righe = []
    for _ in range(n):
        cat = rng.choice(categorie, p=pc)
        par = cfg.CATEGORIE[cat]
        stagione = np.array(cfg.STAGIONALITA.get(cat, [1.0] * 12))[mese_idx]
        giorno = giorni[rng.choice(len(giorni), p=_pesi(crescita * peso_giorno * stagione))]
        ora = int(rng.choice(24, p=peso_ora))
        data_ora = datetime(giorno.year, giorno.month, giorno.day, ora, int(rng.integers(0, 60)))

        # cliente già iscritto; fornitore e operatore della sua zona e della categoria richiesta
        idonei = np.where(iscrizione <= np.datetime64(giorno.date()))[0]
        c_idx = rng.choice(idonei, p=_pesi(fedelta[idonei]))
        zona = clienti.at[c_idx, "zona"]
        cand_f = fornitori.index[(fornitori["zona"] == zona) & (fornitori["categoria"] == cat)].to_numpy()
        f_idx = rng.choice(cand_f, p=_pesi(popolarita[cand_f]))
        cand_o = operatori.index[(operatori["zona"] == zona)
                                 & (operatori["tipo_attivita"] == par["operatore"])].to_numpy()
        o_idx = rng.choice(cand_o)

        picco = ora in cfg.ORE_PICCO
        if rng.random() < (0.11 if picco else 0.07):
            stato, importo, tempo = "annullata", 0.0, None
        else:
            tempo = par["tempo"] * rng.lognormal(0, 0.25)
            if picco:
                tempo *= 1.15
            tempo *= 1 - min(esperienza[o_idx], 10) * 0.012
            if rng.random() < 0.08:
                tempo *= rng.uniform(1.4, 2.2)
            tempo = int(round(tempo))
            stato = "in_ritardo" if tempo > par["sla"] else "completata"
            importo = max(25.0, rng.normal(par["prezzo"], par["sd"]))
            if data_ora.weekday() >= 5 or ora >= 19 or ora < 7:
                importo *= 1.20
            importo = round(importo * 2) / 2

        righe.append({
            "cliente_id": clienti.at[c_idx, "cliente_id"],
            "fornitore_id": fornitori.at[f_idx, "fornitore_id"],
            "operatore_id": operatori.at[o_idx, "operatore_id"],
            "data_ora": data_ora.strftime("%Y-%m-%d %H:%M"),
            "importo": importo,
            "tempo_erogazione_min": tempo,
            "stato": stato,
        })

    df = pd.DataFrame(righe).sort_values("data_ora").reset_index(drop=True)
    df.insert(0, "richiesta_id", [f"R{i:05d}" for i in range(1, len(df) + 1)])
    df["tempo_erogazione_min"] = df["tempo_erogazione_min"].astype("Int64")
    return df


def _varia_testo(rng, s):
    return rng.choice([s.lower(), s.upper(), f" {s}", f"{s}  "])


def sporca(rng, clienti, fornitori, operatori, richieste, quota):
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
    r.loc[rng.choice(completate, 3, replace=False), "importo"] = -50.0
    r.loc[rng.choice(r.index, 2, replace=False), "fornitore_id"] = "F999"
    duplicati = r.loc[campione(r, quota / 3)]
    r = pd.concat([r, duplicati]).sort_index(kind="stable").reset_index(drop=True)
    return clienti, fornitori, operatori, r


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera i CSV sintetici di Interventa.")
    ap.add_argument("--seed", type=int, default=cfg.SEED, help="seme casuale")
    ap.add_argument("--clienti", type=int, default=cfg.N_CLIENTI)
    ap.add_argument("--fornitori", type=int, default=cfg.N_FORNITORI)
    ap.add_argument("--operatori", type=int, default=cfg.N_OPERATORI)
    ap.add_argument("--richieste", type=int, default=cfg.N_RICHIESTE)
    ap.add_argument("--pulito", action="store_true", help="esporta i dati senza difetti")
    ap.add_argument("--out", default=str(cfg.DIR_RAW), help="cartella di destinazione")
    a = ap.parse_args(argv)

    rng = np.random.default_rng(a.seed)
    clienti = genera_clienti(rng, a.clienti)
    fornitori = genera_fornitori(rng, a.fornitori)
    operatori = genera_operatori(rng, a.operatori)
    richieste = genera_richieste(rng, a.richieste, clienti, fornitori, operatori)
    if not a.pulito:
        clienti, fornitori, operatori, richieste = sporca(
            rng, clienti, fornitori, operatori, richieste, cfg.QUOTA_SPORCO)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for nome, df in [("clienti", clienti), ("fornitori", fornitori),
                     ("operatori", operatori), ("richieste", richieste)]:
        df.to_csv(out / f"{nome}.csv", index=False)
        print(f"  {nome + '.csv':<15} {len(df):>5} righe")
    print(f"Dati generati in {out} (seed={a.seed}, difetti={'no' if a.pulito else 'sì'})")


if __name__ == "__main__":
    main()
