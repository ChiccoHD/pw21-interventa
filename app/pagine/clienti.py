"""Pagina Clienti: fidelizzazione per coorte, frequenza di utilizzo e canali di iscrizione."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.comune import (ACQUA, BLU, MESI_BREVI, SCALA_BLU, applica_stile, griglia_kpi, interroga,
                        intestazione_card, kpi_card, mostra, num, stile_grafico, testata, verifica_warehouse,
                        vista_richieste)

MIN_COORTE = 5

applica_stile()
verifica_warehouse()
df = vista_richieste()

st.sidebar.markdown("**Filtri**")
tutte_zone = sorted(z for z in df["zona"].unique() if z != "Sconosciuto")
zone = st.sidebar.multiselect("Zona", tutte_zone, placeholder="Tutte le zone", key="clienti_zone")

iscritti = interroga("SELECT cliente_id, zona, canale_iscrizione FROM dim_cliente "
                     "WHERE corrente = 1 AND sk_cliente <> 0")
sel = df[df["zona"].isin(zone)] if zone else df
if zone:
    iscritti = iscritti[iscritti["zona"].isin(zone)]
erog = sel[sel["flag_erogata"] == 1]
per_cliente = erog.groupby("cliente_id").size()

n_iscritti = len(iscritti)
n_attivi = int(per_cliente.size)
ritorno = 100 * (per_cliente >= 2).mean() if n_attivi else None
media = per_cliente.mean() if n_attivi else None
quota_attivi = 100 * n_attivi / n_iscritti if n_iscritti else None

testata("Clienti", "Chi usa il servizio, quanto spesso e quanto a lungo resta attivo",
        [f"{num(n_iscritti)} iscritti", "Zona: " + (", ".join(zone) if zone else "tutte")])

griglia_kpi([
    kpi_card("Clienti iscritti", num(n_iscritti), nota="anagrafica corrente"),
    kpi_card("Clienti attivi", num(n_attivi),
             nota=f"{num(quota_attivi, 1)}% degli iscritti" if quota_attivi is not None else ""),
    kpi_card("Clienti che tornano", f"{num(ritorno, 1)}%" if ritorno is not None else "—",
             nota="2 o più richieste erogate"),
    kpi_card("Richieste per cliente", num(media, 2) if media is not None else "—", nota="media sui clienti attivi"),
])

# --- coorti -------------------------------------------------------------------
with st.container(key="card_coorti"):
    mese = erog["data"].dt.to_period("M")
    primo = mese.groupby(erog["cliente_id"]).transform("min")
    attivita = pd.DataFrame({"cliente_id": erog["cliente_id"], "coorte": primo,
                             "distanza": (mese - primo).apply(lambda d: d.n)}).drop_duplicates()
    dimensioni = attivita[attivita["distanza"] == 0].groupby("coorte")["cliente_id"].nunique()
    dimensioni = dimensioni[dimensioni >= MIN_COORTE]
    attivita = attivita[attivita["coorte"].isin(dimensioni.index) & (attivita["distanza"] > 0)]
    matrice = (attivita.groupby(["coorte", "distanza"])["cliente_id"].nunique()
               .unstack(fill_value=0).reindex(dimensioni.index, fill_value=0))
    ultimo = mese.max() if len(mese) else None
    if len(matrice.columns):
        perc = matrice.div(dimensioni, axis=0) * 100
        for c in perc.index:
            limite = (ultimo - c).n
            perc.loc[c, [d for d in perc.columns if d > limite]] = None
        media_1 = perc[1].mean() if 1 in perc.columns else None
        frase = (f"In media il <b>{num(media_1, 1)}%</b> dei nuovi clienti torna a usare il servizio "
                 "nel mese successivo al primo intervento." if media_1 is not None and not pd.isna(media_1) else "")
        intestazione_card("Fidelizzazione per mese del primo intervento",
                          frase + f" Ogni riga è un gruppo di clienti (almeno {MIN_COORTE}); ogni cella è la quota "
                                  "che ha avuto almeno un intervento a quella distanza in mesi.")
        etichette = [f"{MESI_BREVI[c.month - 1]} {c.year} · {dimensioni[c]}" for c in perc.index]
        testo = perc.map(lambda v: "" if pd.isna(v) else f"{num(v)}%")
        fig = go.Figure(go.Heatmap(
            z=perc.values, x=[f"+{d}" for d in perc.columns], y=etichette, text=testo.values,
            texttemplate="%{text}", textfont=dict(size=11),
            colorscale=[[i / (len(SCALA_BLU) - 1), c] for i, c in enumerate(SCALA_BLU)],
            zmin=0, zmax=max(30, float(pd.Series(perc.values.ravel()).max(skipna=True) or 0)),
            xgap=2, ygap=2, hoverongaps=False, colorbar=dict(title="%", thickness=10, outlinewidth=0),
            hovertemplate="Coorte %{y}<br>Mesi dopo il primo intervento: %{x}<br>Attivi: %{text}<extra></extra>"))
        stile_grafico(fig, max(320, 26 * len(etichette) + 70))
        fig.update_yaxes(autorange="reversed", title=None, gridcolor="rgba(0,0,0,0)")
        fig.update_xaxes(title="mesi dopo il primo intervento", side="top")
        mostra(fig)
        esporta = perc.copy()
        esporta.index = [f"{c.year}-{c.month:02d}" for c in perc.index]
        esporta.insert(0, "clienti", dimensioni.values)
        esporta.columns = ["clienti"] + [f"mese +{d}" for d in perc.columns]
        st.download_button("Scarica la tabella (CSV)", esporta.round(1).to_csv(sep=";", decimal=",",
                                                                                 index_label="coorte"),
                           file_name="fidelizzazione_coorti.csv", mime="text/csv",
                           icon=":material/download:", key="scarica_coorti")
    else:
        intestazione_card("Fidelizzazione per mese del primo intervento",
                          "Dati insufficienti per la selezione corrente.")

col_a, col_b = st.columns(2, gap="medium")

# --- frequenza ----------------------------------------------------------------
with col_a, st.container(key="card_frequenza"):
    classi = per_cliente.clip(upper=5).map(lambda n: "5 o più" if n >= 5 else str(n))
    ordine = ["1", "2", "3", "4", "5 o più"]
    freq = classi.value_counts().reindex(ordine, fill_value=0).rename_axis("Richieste").reset_index(name="Clienti")
    freq["Quota"] = 100 * freq["Clienti"] / max(1, freq["Clienti"].sum())
    intestazione_card("Clienti per numero di richieste erogate",
                      f"Il <b>{num(freq.loc[0, 'Quota'], 1)}%</b> dei clienti attivi ha usato il servizio una "
                      "sola volta." if n_attivi else "")
    fig = px.bar(freq, x="Richieste", y="Clienti", text="Clienti", custom_data=["Quota"],
                 color_discrete_sequence=[BLU])
    fig.update_traces(textposition="outside", cliponaxis=False, textfont=dict(color="#14171c"),
                      marker_cornerradius=4,
                      hovertemplate="%{x} richieste: %{y} clienti (%{customdata[0]:.1f}%)<extra></extra>")
    stile_grafico(fig, 300)
    fig.update_yaxes(visible=False, range=[0, max(1, freq["Clienti"].max()) * 1.18])
    fig.update_xaxes(title="richieste erogate per cliente", type="category")
    mostra(fig)

# --- canali -------------------------------------------------------------------
with col_b, st.container(key="card_canali"):
    canale_cliente = iscritti.set_index("cliente_id")["canale_iscrizione"]
    attivi = pd.DataFrame({"n": per_cliente})
    attivi["canale"] = canale_cliente.reindex(attivi.index).fillna("Sconosciuto")
    canali = (iscritti.groupby("canale_iscrizione").size().rename("Iscritti").to_frame()
              .join(attivi.groupby("canale").agg(Attivi=("n", "size"),
                                                 Ritorno=("n", lambda s: 100 * (s >= 2).mean())))
              .fillna(0).reset_index(names="Canale"))
    canali = canali[canali["Canale"] != "Sconosciuto"].sort_values("Iscritti")
    canali["Quota"] = 100 * canali["Attivi"] / canali["Iscritti"].where(canali["Iscritti"] > 0)
    intestazione_card("Canali di iscrizione",
                      "Quota di iscritti diventati clienti attivi e quota di attivi che tornano, per canale.")
    fig = go.Figure()
    for col, nome, colore in [("Quota", "Attivi sugli iscritti", BLU), ("Ritorno", "Clienti che tornano", ACQUA)]:
        fig.add_trace(go.Bar(y=canali["Canale"], x=canali[col], name=nome, orientation="h",
                             marker=dict(color=colore, cornerradius=4),
                             text=[f"{num(v)}%" for v in canali[col]], textposition="outside", cliponaxis=False,
                             textfont=dict(color="#14171c"),
                             hovertemplate=f"<b>%{{y}}</b><br>{nome}: %{{x:.1f}}%<extra></extra>"))
    stile_grafico(fig, 300, legenda=True)
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.1)
    fig.update_xaxes(visible=False, range=[0, 118])
    fig.update_yaxes(title=None, gridcolor="rgba(0,0,0,0)")
    mostra(fig)

with st.expander("Dettaglio per canale di iscrizione"):
    st.dataframe(canali.sort_values("Iscritti", ascending=False), width="stretch", hide_index=True,
                 column_config={
                     "Canale": "Canale",
                     "Iscritti": st.column_config.NumberColumn("Iscritti", format="%d"),
                     "Attivi": st.column_config.NumberColumn("Attivi", format="%d"),
                     "Quota": st.column_config.ProgressColumn("Attivi sugli iscritti", format="%.1f%%",
                                                              min_value=0, max_value=100),
                     "Ritorno": st.column_config.ProgressColumn("Clienti che tornano", format="%.1f%%",
                                                                min_value=0, max_value=100),
                 })
