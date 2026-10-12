"""Pagina principale: indicatori e analisi delle richieste."""

import pandas as pd
import plotly.express as px
import streamlit as st

from app.comune import (COLORE, COLORE_2, MESI_BREVI, ORDINE_GIORNI, SCALA, euro, num, stile,
                        verifica_warehouse, vista_richieste)
from src.metriche import filtra, kpi


def delta(attuale, precedente, suffisso="%"):
    """Variazione rispetto al periodo precedente di pari durata."""
    if attuale is None or precedente in (None, 0) or pd.isna(precedente):
        return None
    if suffisso == "%":
        return f"{num(100 * (attuale - precedente) / precedente, 1)}%"
    return f"{num(attuale - precedente, 1)} {suffisso}"


verifica_warehouse()
df = vista_richieste()

st.sidebar.header("Filtri")
d_min, d_max = df["data"].min().date(), df["data"].max().date()
periodo = st.sidebar.date_input("Periodo", value=(d_min, d_max), min_value=d_min,
                                max_value=d_max, format="DD/MM/YYYY")
inizio, fine = (periodo if isinstance(periodo, (tuple, list)) and len(periodo) == 2
                else (d_min, d_max))
zone = st.sidebar.multiselect("Zona", sorted(df["zona"].unique()), placeholder="Tutte le zone")
categorie = st.sidebar.multiselect("Categoria di servizio", sorted(df["categoria"].unique()),
                                   placeholder="Tutte le categorie")
granularita = st.sidebar.radio("Andamento per", ["Settimana", "Mese"], index=1, horizontal=True)
st.sidebar.caption("Dati sintetici generati per il Project Work. Nessuna informazione personale.")

sel = filtra(df, inizio, fine, zone, categorie)
durata = pd.Timestamp(fine) - pd.Timestamp(inizio)
prec = filtra(df, pd.Timestamp(inizio) - durata - pd.Timedelta(days=1),
              pd.Timestamp(inizio) - pd.Timedelta(days=1), zone, categorie)
k, kp = kpi(sel), kpi(prec) if len(prec) else {}

st.title("Interventa · Andamento del servizio")
st.caption(f"Dal {inizio:%d/%m/%Y} al {fine:%d/%m/%Y} · "
           f"{'tutte le zone' if not zone else ', '.join(zone)} · "
           f"{'tutte le categorie' if not categorie else ', '.join(categorie)}")

if sel.empty:
    st.warning("Nessuna richiesta per i filtri selezionati.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Richieste totali", num(k["richieste_totali"]),
          delta(k["richieste_totali"], kp.get("richieste_totali")),
          help="Tutte le richieste ricevute, comprese le annullate.")
c2.metric("Incassi", euro(k["incassi_euro"]), delta(k["incassi_euro"], kp.get("incassi_euro")),
          help="Somma degli importi delle richieste erogate.")
c3.metric("Tempo medio di erogazione", f"{num(k['tempo_medio_min'])} min",
          delta(k["tempo_medio_min"], kp.get("tempo_medio_min"), "min"), delta_color="inverse",
          help="Minuti tra la richiesta e la chiusura dell'intervento (solo richieste erogate).")
c4.metric("Clienti attivi", num(k["clienti_attivi"]),
          delta(k["clienti_attivi"], kp.get("clienti_attivi")),
          help="Clienti distinti con almeno una richiesta erogata nel periodo.")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Clienti che tornano", f"{num(k['tasso_ritorno_perc'], 1)}%",
          delta(k["tasso_ritorno_perc"], kp.get("tasso_ritorno_perc"), "p.p."),
          help="Quota di clienti attivi con almeno 2 richieste erogate nel periodo.")
c6.metric("Richieste annullate", f"{num(k['perc_annullate'], 1)}%",
          delta(k["perc_annullate"], kp.get("perc_annullate"), "p.p."), delta_color="inverse")
c7.metric("Erogate in ritardo", f"{num(k['perc_in_ritardo'], 1)}%",
          delta(k["perc_in_ritardo"], kp.get("perc_in_ritardo"), "p.p."), delta_color="inverse",
          help="Interventi chiusi oltre il tempo massimo previsto per la categoria.")
c8.metric("Scontrino medio",
          euro(k["incassi_euro"] / k["richieste_erogate"]) if k["richieste_erogate"] else "–")
if kp:
    st.caption("Le variazioni sono calcolate rispetto al periodo precedente di pari durata.")

st.divider()

settimanale = granularita == "Settimana"
serie = (sel.assign(periodo=sel["data"].dt.to_period("W" if settimanale else "M").dt.start_time)
            .groupby("periodo")
            .agg(Richieste=("richiesta_id", "count"), Annullate=("flag_annullata", "sum"))
            .reset_index())
serie["etichetta"] = [f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d}" if settimanale
                      else f"{MESI_BREVI[d.month - 1]} {d.year}" for d in serie["periodo"]]
fig = px.line(serie, x="etichetta", y=["Richieste", "Annullate"], markers=True,
              color_discrete_sequence=[COLORE, COLORE_2],
              title=f"Andamento delle richieste per {granularita.lower()}",
              labels={"etichetta": "", "value": "Richieste", "variable": ""})
fig.update_layout(legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
st.plotly_chart(stile(fig), use_container_width=True)

col_a, col_b = st.columns(2)

ultimo_nome = sel.sort_values("data").groupby("fornitore_id")["fornitore"].last()
top5 = (sel.groupby("fornitore_id", as_index=False)
           .agg(Incassi=("importo", "sum"), Richieste=("richiesta_id", "count"),
                categoria=("categoria", "last"), zona=("zona", "last"))
           .nlargest(5, "Incassi").sort_values("Incassi"))
top5["fornitore"] = top5["fornitore_id"].map(ultimo_nome)
fig = px.bar(top5, x="Incassi", y="fornitore", orientation="h", text="Incassi",
             hover_data={"categoria": True, "zona": True, "Richieste": True},
             title="Primi 5 fornitori per incassi", labels={"fornitore": "", "Incassi": "Incassi (€)"},
             color_discrete_sequence=[COLORE])
fig.update_traces(texttemplate="%{x:,.0f} €", textposition="outside", cliponaxis=False)
fig.update_xaxes(range=[0, top5["Incassi"].max() * 1.3])
col_a.plotly_chart(stile(fig), use_container_width=True)

per_zona = (sel.groupby("zona", as_index=False)
               .agg(Richieste=("richiesta_id", "count"), Incassi=("importo", "sum"))
               .sort_values("Richieste", ascending=False))
fig = px.bar(per_zona, x="zona", y="Richieste", text="Richieste", hover_data={"Incassi": ":,.0f"},
             title="Richieste per zona", labels={"zona": ""}, color_discrete_sequence=[COLORE])
fig.update_traces(textposition="outside", cliponaxis=False)
col_b.plotly_chart(stile(fig), use_container_width=True)

col_c, col_d = st.columns(2)

per_cat = (sel.groupby("categoria", as_index=False)
              .agg(Richieste=("richiesta_id", "count"), Incassi=("importo", "sum"),
                   Ritardo=("flag_ritardo", "mean"))
              .sort_values("Richieste"))
fig = px.bar(per_cat, x="Richieste", y="categoria", orientation="h", text="Richieste",
             hover_data={"Incassi": ":,.0f", "Ritardo": ":.1%"},
             title="Richieste per categoria di servizio", labels={"categoria": ""},
             color_discrete_sequence=[COLORE])
fig.update_traces(textposition="outside", cliponaxis=False)
col_c.plotly_chart(stile(fig), use_container_width=True)

heat = (sel.pivot_table(index="nome_giorno", columns="ora", values="richiesta_id",
                        aggfunc="count", fill_value=0)
           .reindex(index=ORDINE_GIORNI, columns=range(24), fill_value=0))
fig = px.imshow(heat, aspect="auto", color_continuous_scale=SCALA,
                labels=dict(x="Ora del giorno", y="", color="Richieste"),
                title="Quando arrivano le richieste (giorno × ora)")
fig.update_xaxes(dtick=2)
col_d.plotly_chart(stile(fig), use_container_width=True)

with st.expander("Dettaglio per zona"):
    tab = (sel.groupby("zona")
              .agg(Richieste=("richiesta_id", "count"), Incassi=("importo", "sum"),
                   **{"Tempo medio (min)": ("tempo_erogazione_min", "mean")},
                   **{"% annullate": ("flag_annullata", "mean")})
              .sort_values("Incassi", ascending=False))
    tab["Quota incassi"] = tab["Incassi"] / tab["Incassi"].sum()
    st.dataframe(tab.style.format({"Incassi": "{:,.0f} €", "Tempo medio (min)": "{:.0f}",
                                   "% annullate": "{:.1%}", "Quota incassi": "{:.1%}"}),
                 use_container_width=True)

with st.expander(f"Elenco richieste filtrate ({len(sel)})"):
    colonne = ["richiesta_id", "data", "ora", "zona", "categoria", "fornitore",
               "stato", "importo", "tempo_erogazione_min"]
    st.dataframe(sel[colonne].sort_values(["data", "ora"]), use_container_width=True, hide_index=True)
    st.download_button("Scarica CSV", sel[colonne].to_csv(index=False).encode("utf-8"),
                       "richieste_filtrate.csv", "text/csv")
