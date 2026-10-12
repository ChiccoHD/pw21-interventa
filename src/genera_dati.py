"""Generatore di dati sintetici per la startup fittizia "Manolesta".

Produce quattro file CSV in data/raw/:
    clienti.csv, fornitori.csv, operatori.csv, richieste.csv

I dati sono interamente inventati e non contengono informazioni personali:
i clienti sono identificati solo da un codice, una zona e una data.

Per rendere significativa la fase di pulizia dell'ETL, una piccola quota di
righe viene "sporcata" di proposito (maiuscole/spazi incoerenti, importi con
la virgola, date in formato diverso, duplicati, valori mancanti o non validi).
Con --pulito i dati vengono esportati senza difetti.

Uso:
    python -m src.genera_dati                 # parametri di default
    python -m src.genera_dati --seed 7 --richieste 600 --pulito
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src import config as cfg


# ---------------------------------------------------------------------------
# Anagrafiche
# ---------------------------------------------------------------------------

def date_crescenti(rng, n, inizio, fine, crescita=0.05):
    """Estrae n date tra inizio e fine con densità crescente nel tempo."""
    giorni = pd.date_range(inizio, fine, freq="D")
    mesi = (giorni.year - giorni[0].year) * 12 + (giorni.month - giorni[0].month)
    pesi = (1 + crescita) ** mesi.to_numpy()
    idx = rng.choice(len(giorni), size=n, p=pesi / pesi.sum())
    return giorni[np.sort(idx)]


def genera_clienti(rng, n):
    zone = list(cfg.ZONE)
    pesi_zona = np.array(list(cfg.ZONE.values()))
    return pd.DataFrame({
        "cliente_id": [f"C{i:04d}" for i in range(1, n + 1)],
        "zona": rng.choice(zone, size=n, p=pesi_zona / pesi_zona.sum()),
        "data_iscrizione": date_crescenti(rng, n, cfg.DATA_LANCIO, cfg.DATA_FINE).strftime("%Y-%m-%d"),
        "canale_iscrizione": rng.choice(["app Android", "app iOS", "sito web"], size=n, p=[0.5, 0.35, 0.15]),
    })


PREFISSI = ["Pronto", "Tecno", "Sud", "Casa", "Isola", "Sole", "Trinacria", "Mare",
            "Delta", "Alfa", "Futura", "Rapida", "Nuova", "Punto", "Global"]
RADICI = {"Idraulica": "Idraulica", "Elettricità": "Impianti", "Pulizie": "Clean",
          "Climatizzazione": "Clima", "Elettrodomestici": "Ripara",
          "Giardinaggio": "Verde", "Piccoli traslochi": "Trasporti"}
SUFFISSI = ["Service", "Group", "Srl", "Pro", "Team", "Lab", "Point", "Sicilia"]


def genera_fornitori(rng, n):
    zone, categorie = list(cfg.ZONE), list(cfg.CATEGORIE)
    # Ogni combinazione zona x categoria ha almeno un fornitore partner
    coppie = [(z, c) for z in zone for c in categorie]
    pz = np.array([cfg.ZONE[z] for z in zone]); pz = pz / pz.sum()
    pc = np.array([cfg.CATEGORIE[c]["peso"] for c in categorie]); pc = pc / pc.sum()
    for _ in range(n - len(coppie)):
        coppie.append((rng.choice(zone, p=pz), rng.choice(categorie, p=pc)))
    rng.shuffle(coppie)

    nomi, usati = [], set()
    for _, cat in coppie:
        while True:
            nome = f"{rng.choice(PREFISSI)} {RADICI[cat]} {rng.choice(SUFFISSI)}"
            if nome not in usati:
                break
            nome = f"{nome} {rng.integers(2, 99)}"
            if nome not in usati:
                break
        usati.add(nome); nomi.append(nome)

    return pd.DataFrame({
        "fornitore_id": [f"F{i:03d}" for i in range(1, n + 1)],
        "nome": nomi,
        "categoria": [c for _, c in coppie],
        "zona": [z for z, _ in coppie],
    })


def genera_operatori(rng, n):
    zone, categorie = list(cfg.ZONE), list(cfg.CATEGORIE)
    coppie = [(z, c) for z in zone for c in categorie]
    pz = np.array([cfg.ZONE[z] for z in zone]); pz = pz / pz.sum()
    pc = np.array([cfg.CATEGORIE[c]["peso"] for c in categorie]); pc = pc / pc.sum()
    for _ in range(n - len(coppie)):
        coppie.append((rng.choice(zone, p=pz), rng.choice(categorie, p=pc)))
    rng.shuffle(coppie)
    return pd.DataFrame({
        "operatore_id": [f"O{i:03d}" for i in range(1, n + 1)],
        "zona": [z for z, _ in coppie],
        "tipo_attivita": [cfg.CATEGORIE[c]["operatore"] for _, c in coppie],
        "anni_esperienza": rng.integers(0, 16, size=n),
    })


# ---------------------------------------------------------------------------
# Richieste (tabella dei fatti)
# ---------------------------------------------------------------------------

def genera_richieste(rng, n, clienti, fornitori, operatori):
    categorie = list(cfg.CATEGORIE)
    pc = np.array([cfg.CATEGORIE[c]["peso"] for c in categorie]); pc = pc / pc.sum()

    giorni = pd.date_range(cfg.DATA_INIZIO, cfg.DATA_FINE, freq="D")
    mese_idx = (giorni.month - 1).to_numpy()
    crescita = (1 + cfg.CRESCITA_MENSILE) ** mese_idx
    peso_dow = np.array(cfg.PESO_GIORNO)[giorni.dayofweek.to_numpy()]
    peso_ora = np.array(cfg.PESO_ORA) / sum(cfg.PESO_ORA)

    iscr = pd.to_datetime(clienti["data_iscrizione"]).to_numpy()
    # "Fedeltà" dei clienti: pochi clienti molto attivi, molti occasionali
    fedelta = rng.lognormal(0, 1.0, size=len(clienti))
    # Popolarità dei fornitori: distribuzione molto concentrata (pochi partner forti)
    popolarita = rng.pareto(1.1, size=len(fornitori)) + 0.02
    esperienza = operatori["anni_esperienza"].to_numpy()

    righe = []
    for i in range(1, n + 1):
        cat = rng.choice(categorie, p=pc)
        stag = np.array(cfg.STAGIONALITA.get(cat, [1.0] * 12))[mese_idx]
        p_giorno = crescita * peso_dow * stag
        giorno = giorni[rng.choice(len(giorni), p=p_giorno / p_giorno.sum())]
        ora = int(rng.choice(24, p=peso_ora))
        data_ora = datetime(giorno.year, giorno.month, giorno.day, ora, int(rng.integers(0, 60)))

        # Cliente già iscritto alla data della richiesta
        idonei = np.where(iscr <= np.datetime64(giorno.date()))[0]
        w = fedelta[idonei]
        c_idx = rng.choice(idonei, p=w / w.sum())
        zona = clienti.at[c_idx, "zona"]

        # Fornitore della stessa zona e categoria, scelto per popolarità
        cand = fornitori.index[(fornitori["zona"] == zona) & (fornitori["categoria"] == cat)].to_numpy()
        w = popolarita[cand]
        f_idx = rng.choice(cand, p=w / w.sum())

        # Operatore della stessa zona con la competenza richiesta
        tipo = cfg.CATEGORIE[cat]["operatore"]
        cand_o = operatori.index[(operatori["zona"] == zona) & (operatori["tipo_attivita"] == tipo)].to_numpy()
        o_idx = rng.choice(cand_o)

        par = cfg.CATEGORIE[cat]
        picco = ora in cfg.ORE_PICCO
        weekend = data_ora.weekday() >= 5
        serale = ora >= 19 or ora < 7

        # Annullamenti: più frequenti nelle ore di punta (attese più lunghe)
        p_annullo = 0.11 if picco else 0.07
        if rng.random() < p_annullo:
            stato, importo, tempo = "annullata", 0.0, None
        else:
            tempo = par["tempo"] * rng.lognormal(0, 0.25)
            if picco:
                tempo *= 1.15                       # più carico, più attesa
            tempo *= 1 - min(esperienza[o_idx], 10) * 0.012   # esperienza = più rapidità
            if rng.random() < 0.08:
                tempo *= rng.uniform(1.4, 2.2)      # imprevisti: traffico, ricambi, ecc.
            tempo = int(round(tempo))
            stato = "in_ritardo" if tempo > par["sla"] else "completata"
            importo = max(25.0, rng.normal(par["prezzo"], par["sd"]))
            if weekend or serale:
                importo *= 1.20                     # maggiorazione festiva/serale
            importo = round(importo * 2) / 2        # arrotondato a 0,50 euro

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


# ---------------------------------------------------------------------------
# "Sporcatura" controllata, per mettere alla prova l'ETL
# ---------------------------------------------------------------------------

def _varia_testo(rng, s):
    return rng.choice([s.lower(), s.upper(), f" {s}", f"{s}  "])


def sporca(rng, clienti, fornitori, operatori, richieste, quota):
    def campione(df, q=quota):
        k = max(1, int(round(len(df) * q)))
        return rng.choice(df.index, size=k, replace=False)

    for df, col in [(clienti, "zona"), (fornitori, "zona"), (fornitori, "categoria"), (operatori, "zona")]:
        idx = campione(df)
        df.loc[idx, col] = [_varia_testo(rng, v) for v in df.loc[idx, col]]

    r = richieste.astype({"importo": object, "data_ora": object, "tempo_erogazione_min": object})
    # importi scritti all'italiana ("89,50")
    idx = campione(r)
    r.loc[idx, "importo"] = [f"{float(v):.2f}".replace(".", ",") for v in r.loc[idx, "importo"]]
    # date in formato gg/mm/aaaa
    idx = campione(r)
    r.loc[idx, "data_ora"] = [datetime.strptime(v, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")
                              for v in r.loc[idx, "data_ora"]]
    # stati scritti in modo incoerente
    idx = campione(r)
    varianti = {"completata": ["Completata", "COMPLETATA ", "completato"],
                "in_ritardo": ["In ritardo", "IN_RITARDO", "ritardo"],
                "annullata": ["Annullata", "annullato", "ANNULLATA "]}
    r.loc[idx, "stato"] = [rng.choice(varianti[v]) for v in r.loc[idx, "stato"]]
    # operatore non registrato dal gestionale
    idx = campione(r, quota / 2)
    r.loc[idx, "operatore_id"] = None
    # errori veri: importi negativi e fornitori inesistenti (da scartare)
    validi = r.index[r["stato"].str.strip().str.lower().str.startswith("compl")]
    r.loc[rng.choice(validi, 3, replace=False), "importo"] = -50.0
    r.loc[rng.choice(r.index, 2, replace=False), "fornitore_id"] = "F999"
    # righe esportate due volte
    dup = r.loc[campione(r, quota / 3)]
    r = pd.concat([r, dup]).sort_index(kind="stable").reset_index(drop=True)
    return clienti, fornitori, operatori, r


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=cfg.SEED, help="seme casuale (riproducibilità)")
    ap.add_argument("--clienti", type=int, default=cfg.N_CLIENTI)
    ap.add_argument("--fornitori", type=int, default=cfg.N_FORNITORI)
    ap.add_argument("--operatori", type=int, default=cfg.N_OPERATORI)
    ap.add_argument("--richieste", type=int, default=cfg.N_RICHIESTE)
    ap.add_argument("--pulito", action="store_true", help="non introdurre difetti nei dati")
    ap.add_argument("--out", default=str(cfg.DIR_RAW), help="cartella di destinazione dei CSV")
    a = ap.parse_args(argv)

    rng = np.random.default_rng(a.seed)
    clienti = genera_clienti(rng, a.clienti)
    fornitori = genera_fornitori(rng, a.fornitori)
    operatori = genera_operatori(rng, a.operatori)
    richieste = genera_richieste(rng, a.richieste, clienti, fornitori, operatori)
    if not a.pulito:
        clienti, fornitori, operatori, richieste = sporca(
            rng, clienti, fornitori, operatori, richieste, cfg.QUOTA_SPORCO)

    from pathlib import Path
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for nome, df in [("clienti", clienti), ("fornitori", fornitori),
                     ("operatori", operatori), ("richieste", richieste)]:
        df.to_csv(out / f"{nome}.csv", index=False)
        print(f"  {nome + '.csv':<15} {len(df):>5} righe")
    print(f"Dati generati in {out} (seed={a.seed}, sporco={'no' if a.pulito else 'sì'})")


if __name__ == "__main__":
    main()
