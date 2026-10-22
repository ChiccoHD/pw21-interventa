"""Pagina principale: indicatori e analisi delle richieste."""

from io import BytesIO

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.comune import (ARANCIO, BLU, MESI_BREVI, ORDINE_GIORNI, SCALA_BLU, applica_stile, esc, euro,
                        griglia_kpi, interroga, intestazione_card, kpi_card, mostra, num, stile_grafico,
                        testata, verifica_warehouse, vista_richieste)
from src import config as cfg
from src.metriche import filtra, kpi

applica_stile()
verifica_warehouse()
df = vista_richieste()


def variazione(attuale, precedente, unita="%"):
    """(variazione, testo) rispetto al periodo precedente; None se non confrontabile."""
    if attuale is None or precedente in (None, 0) or pd.isna(precedente):
        return None
    if unita == "%":
        v = 100 * (attuale - precedente) / precedente
        return v, f"{'+' if v >= 0 else ''}{num(v, 1)}%"
    v = attuale - precedente
    return v, f"{'+' if v >= 0 else ''}{num(v, 1)} {unita}"


def etichetta_mese(d):
    return f"{MESI_BREVI[d.month - 1]} {d.year}"


# --- filtri -------------------------------------------------------------------
st.sidebar.markdown("**Filtri**")
d_min, d_max = df["data"].min().date(), df["data"].max().date()
fine_dati = pd.Timestamp(d_max)
PERIODI = {
    "Tutto": (d_min, d_max),
    f"Anno {d_min.year}": (pd.Timestamp(d_min.year, 1, 1).date(), pd.Timestamp(d_min.year, 12, 31).date()),
    "Ultimi 6 mesi": ((fine_dati - pd.offsets.MonthBegin(6)).date(), d_max),
    "Ultimi 3 mesi": ((fine_dati - pd.offsets.MonthBegin(3)).date(), d_max),
}
scelta_periodo = st.sidebar.radio("Periodo", list(PERIODI) + ["Personalizzato"])
if scelta_periodo == "Personalizzato":
    periodo = st.sidebar.date_input("Intervallo di date", value=(d_min, d_max), min_value=d_min,
                                    max_value=d_max, format="DD/MM/YYYY")
    inizio, fine = (periodo if isinstance(periodo, (tuple, list)) and len(periodo) == 2 else (d_min, d_max))
else:
    inizio, fine = (max(d, d_min) if i == 0 else min(d, d_max) for i, d in enumerate(PERIODI[scelta_periodo]))
zone = st.sidebar.multiselect("Zona", sorted(df["zona"].unique()), placeholder="Tutte le zone")
categorie = st.sidebar.multiselect("Categoria di servizio", sorted(df["categoria"].unique()),
                                   placeholder="Tutte le categorie")
st.sidebar.caption("Dati sintetici generati per il Project Work. Nessuna informazione personale.")

sel = filtra(df, inizio, fine, zone, categorie)
durata = pd.Timestamp(fine) - pd.Timestamp(inizio)
prec = filtra(df, pd.Timestamp(inizio) - durata - pd.Timedelta(days=1),
              pd.Timestamp(inizio) - pd.Timedelta(days=1), zone, categorie)
k, kp = kpi(sel), (kpi(prec) if len(prec) else {})

ultimo = interroga("SELECT periodo, eseguito_il FROM etl_caricamenti WHERE esito = 'COMPLETATO' "
                   "ORDER BY id_caricamento DESC LIMIT 1")
aggiornato = (f"Dati aggiornati al pacchetto {ultimo['periodo'].iloc[0]}" if len(ultimo) else "")
testata("Andamento del servizio",
        f"Dal {inizio:%d/%m/%Y} al {fine:%d/%m/%Y} · {aggiornato}",
        [", ".join(zone) if zone else "Tutte le zone",
         ", ".join(categorie) if categorie else "Tutte le categorie",
         f"{num(len(sel))} richieste"])

if sel.empty:
    st.warning("Nessuna richiesta per i filtri selezionati.")
    st.stop()

# --- indicatori -----------------------------------------------------------------
mese = sel["data"].dt.to_period("M")
erog = sel[sel["flag_erogata"] == 1]
mensile = pd.DataFrame({
    "richieste": sel.groupby(mese).size(),
    "incassi": sel.groupby(mese)["importo"].sum(),
    "tempo": erog.groupby(erog["data"].dt.to_period("M"))["tempo_erogazione_min"].mean(),
    "clienti": erog.groupby(erog["data"].dt.to_period("M"))["cliente_id"].nunique(),
    "annullate": sel.groupby(mese)["flag_annullata"].mean() * 100,
    "ritardo": erog.groupby(erog["data"].dt.to_period("M"))["flag_ritardo"].mean() * 100,
}).sort_index()
mensile["scontrino"] = mensile["incassi"] / erog.groupby(erog["data"].dt.to_period("M")).size()
nota_trend = ""
scontrino = k["incassi_euro"] / k["richieste_erogate"] if k["richieste_erogate"] else None
scontrino_prec = (kp["incassi_euro"] / kp["richieste_erogate"]) if kp.get("richieste_erogate") else None

griglia_kpi([
    kpi_card("Richieste totali", num(k["richieste_totali"]), variazione(k["richieste_totali"], kp.get("richieste_totali")),
             nota=nota_trend, trend=mensile["richieste"], aiuto="Tutte le richieste ricevute, comprese le annullate."),
    kpi_card("Incassi", euro(k["incassi_euro"]), variazione(k["incassi_euro"], kp.get("incassi_euro")),
             nota=nota_trend, trend=mensile["incassi"], aiuto="Somma degli importi delle richieste erogate."),
    kpi_card("Tempo medio di erogazione", f"{num(k['tempo_medio_min'])} min",
             variazione(k["tempo_medio_min"], kp.get("tempo_medio_min"), "min"), buono_se_sale=False,
             nota=nota_trend, trend=mensile["tempo"],
             aiuto="Minuti tra la richiesta e la chiusura dell'intervento (solo richieste erogate)."),
    kpi_card("Clienti attivi", num(k["clienti_attivi"]), variazione(k["clienti_attivi"], kp.get("clienti_attivi")),
             nota=nota_trend, trend=mensile["clienti"],
             aiuto="Clienti distinti con almeno una richiesta erogata nel periodo."),
    kpi_card("Clienti che tornano", f"{num(k['tasso_ritorno_perc'], 1)}%",
             variazione(k["tasso_ritorno_perc"], kp.get("tasso_ritorno_perc"), "p.p."),
             nota=f"{num(k['clienti_di_ritorno'])} clienti con 2 o più richieste",
             aiuto="Quota di clienti attivi con almeno 2 richieste erogate nel periodo."),
    kpi_card("Richieste annullate", f"{num(k['perc_annullate'], 1)}%",
             variazione(k["perc_annullate"], kp.get("perc_annullate"), "p.p."), buono_se_sale=False,
             nota=nota_trend, trend=mensile["annullate"]),
    kpi_card("Erogate in ritardo", f"{num(k['perc_in_ritardo'], 1)}%",
             variazione(k["perc_in_ritardo"], kp.get("perc_in_ritardo"), "p.p."), buono_se_sale=False,
             nota=nota_trend, trend=mensile["ritardo"],
             aiuto="Interventi chiusi oltre il tempo massimo previsto per la categoria."),
    kpi_card("Scontrino medio", euro(scontrino), variazione(scontrino, scontrino_prec),
             nota=nota_trend, trend=mensile["scontrino"]),
])
if kp:
    st.caption("Le variazioni confrontano il periodo selezionato con il periodo precedente di pari durata.")

# --- andamento nel tempo --------------------------------------------------------
with st.container(key="card_trend"):
    testa, scelta = st.columns([4, 1.4], vertical_alignment="center")
    misura = scelta.segmented_control("Misura", ["Richieste", "Incassi"], default="Richieste",
                                      label_visibility="collapsed") or "Richieste"
    serie = mensile.reset_index(names="mese")
    serie["etichetta"] = [etichetta_mese(m.start_time) for m in serie["mese"]]
    serie["annullate_n"] = sel.groupby(mese)["flag_annullata"].sum().reindex(mensile.index).to_numpy()
    colonna = "richieste" if misura == "Richieste" else "incassi"
    if len(serie) > 1:
        primo, ultimo_v = serie[colonna].iloc[0], serie[colonna].iloc[-1]
        crescita = 100 * (ultimo_v - primo) / primo if primo else 0
        valore = (lambda x: num(x)) if colonna == "richieste" else euro
        frase = (f"Da {serie['etichetta'].iloc[0]} a {serie['etichetta'].iloc[-1]} "
                 f"{'le richieste mensili passano' if colonna == 'richieste' else 'gli incassi mensili passano'} "
                 f"da <b>{valore(primo)}</b> a <b>{valore(ultimo_v)}</b> ({'+' if crescita >= 0 else ''}{num(crescita)}%).")
    else:
        frase = "Selezionare un periodo di almeno due mesi per vedere l'andamento."
    with testa:
        intestazione_card(f"{misura} per mese", frase)

    fig = go.Figure()
    formato = "%{y:,.0f}" if colonna == "richieste" else "%{y:,.0f} €"
    fig.add_trace(go.Scatter(x=serie["etichetta"], y=serie[colonna], name=misura, mode="lines+markers",
                             line=dict(color=BLU, width=2.5, shape="spline", smoothing=0.6),
                             marker=dict(size=8, color=BLU, line=dict(color="#fff", width=2)),
                             fill="tozeroy", fillcolor="rgba(42,120,214,0.08)",
                             hovertemplate=f"<b>%{{x}}</b><br>{misura}: {formato}<extra></extra>"))
    if colonna == "richieste":
        fig.add_trace(go.Scatter(x=serie["etichetta"], y=serie["annullate_n"], name="Annullate",
                                 mode="lines+markers", line=dict(color=ARANCIO, width=2),
                                 marker=dict(size=7, color=ARANCIO, line=dict(color="#fff", width=2)),
                                 hovertemplate="<b>%{x}</b><br>Annullate: %{y}<extra></extra>"))
    if len(serie):
        fig.add_annotation(x=serie["etichetta"].iloc[-1], y=serie[colonna].iloc[-1],
                           text=(num(serie[colonna].iloc[-1]) if colonna == "richieste"
                                 else euro(serie[colonna].iloc[-1])),
                           showarrow=False, yshift=16, font=dict(size=13, color="#14171c"))
    stile_grafico(fig, 330, legenda=colonna == "richieste")
    fig.update_yaxes(rangemode="tozero", ticksuffix=" €" if colonna == "incassi" else "")
    mostra(fig)

col_a, col_b = st.columns(2, gap="medium")

# --- fornitori -------------------------------------------------------------------
with col_a, st.container(key="card_fornitori"):
    ultimo_nome = sel.sort_values("data").groupby("fornitore_id")["fornitore"].last()
    per_fornitore = (sel.groupby("fornitore_id", as_index=False)
                     .agg(Incassi=("importo", "sum"), Richieste=("richiesta_id", "count"),
                          categoria=("categoria", "last"), zona=("zona", "last")))
    top5 = per_fornitore.nlargest(5, "Incassi").sort_values("Incassi")
    top5["fornitore"] = top5["fornitore_id"].map(ultimo_nome)
    quota = 100 * top5["Incassi"].sum() / per_fornitore["Incassi"].sum() if per_fornitore["Incassi"].sum() else 0
    intestazione_card("Primi 5 fornitori per incassi",
                      f"Valgono il <b>{num(quota)}%</b> degli incassi, su {num(len(per_fornitore))} fornitori attivi.")
    fig = px.bar(top5, x="Incassi", y="fornitore", orientation="h", text="Incassi",
                 custom_data=["categoria", "zona", "Richieste"], color_discrete_sequence=[BLU])
    fig.update_traces(texttemplate="%{x:,.0f} €", textposition="outside", cliponaxis=False,
                      textfont=dict(color="#14171c"), marker_cornerradius=4,
                      hovertemplate="<b>%{y}</b><br>%{customdata[0]} · %{customdata[1]}<br>"
                                    "Incassi: %{x:,.0f} €<br>Richieste: %{customdata[2]}<extra></extra>")
    stile_grafico(fig, 300)
    fig.update_xaxes(visible=False, range=[0, top5["Incassi"].max() * 1.28])
    fig.update_yaxes(title=None, gridcolor="rgba(0,0,0,0)")
    mostra(fig)

# --- zone ------------------------------------------------------------------------------
with col_b, st.container(key="card_zone"):
    per_zona = (sel.groupby("zona", as_index=False)
                .agg(Richieste=("richiesta_id", "count"), Incassi=("importo", "sum"))
                .sort_values("Richieste"))
    prime = per_zona.nlargest(2, "Richieste")
    quota = 100 * prime["Richieste"].sum() / per_zona["Richieste"].sum()
    frase = (f"<b>{esc(prime['zona'].iloc[0])}</b> e <b>{esc(prime['zona'].iloc[1])}</b> generano il "
             f"<b>{num(quota)}%</b> delle richieste." if len(prime) == 2
             else f"Tutte le richieste da <b>{esc(per_zona['zona'].iloc[0])}</b>.")
    intestazione_card("Richieste per zona", frase)
    fig = px.bar(per_zona, x="Richieste", y="zona", orientation="h", text="Richieste",
                 custom_data=["Incassi"], color_discrete_sequence=[BLU])
    fig.update_traces(textposition="outside", cliponaxis=False, textfont=dict(color="#14171c"),
                      marker_cornerradius=4,
                      hovertemplate="<b>%{y}</b><br>Richieste: %{x}<br>Incassi: %{customdata[0]:,.0f} €<extra></extra>")
    stile_grafico(fig, 300)
    fig.update_xaxes(visible=False, range=[0, per_zona["Richieste"].max() * 1.18])
    fig.update_yaxes(title=None, gridcolor="rgba(0,0,0,0)")
    mostra(fig)

col_c, col_d = st.columns(2, gap="medium")

# --- categorie -----------------------------------------------------------------------
with col_c, st.container(key="card_categorie"):
    per_cat = (sel.groupby("categoria", as_index=False)
               .agg(Richieste=("richiesta_id", "count"), Incassi=("importo", "sum"))
               .merge(erog.groupby("categoria", as_index=False)
                      .agg(Ritardo=("flag_ritardo", "mean"), Tempo=("tempo_erogazione_min", "mean")),
                      on="categoria", how="left")
               .sort_values("Richieste"))
    per_cat["Massimo"] = per_cat["categoria"].map(lambda c: cfg.CATEGORIE[c]["sla"])
    testa = st.container()
    vista = st.segmented_control("Vista categorie", ["Richieste", "Tempi"], default="Richieste",
                                     label_visibility="collapsed", key="vista_categorie") or "Richieste"
    peggiore = (per_cat.dropna(subset=["Ritardo"]).sort_values("Ritardo").iloc[-1]
                if per_cat["Ritardo"].notna().any() else None)
    if vista == "Richieste":
        frase = (f"La quota di interventi in ritardo più alta è in <b>{esc(peggiore['categoria'])}</b> "
                 f"(<b>{num(100 * peggiore['Ritardo'], 1)}%</b>)." if peggiore is not None else "")
        with testa:
            intestazione_card("Richieste per categoria di servizio", frase)
        fig = px.bar(per_cat, x="Richieste", y="categoria", orientation="h", text="Richieste",
                     custom_data=["Incassi", "Ritardo"], color_discrete_sequence=[BLU])
        fig.update_traces(textposition="outside", cliponaxis=False, textfont=dict(color="#14171c"),
                          marker_cornerradius=4,
                          hovertemplate="<b>%{y}</b><br>Richieste: %{x}<br>Incassi: %{customdata[0]:,.0f} €"
                                        "<br>In ritardo: %{customdata[1]:.1%}<extra></extra>")
        stile_grafico(fig, 320)
        fig.update_xaxes(visible=False, range=[0, per_cat["Richieste"].max() * 1.18])
    else:
        tempi = per_cat.dropna(subset=["Tempo"]).sort_values("Tempo")
        with testa:
            intestazione_card("Tempo medio e tempo massimo per categoria",
                              "La barra è il tempo medio di erogazione, il segno grigio il tempo massimo previsto; "
                              "a destra la quota di interventi in ritardo.")
        fig = go.Figure()
        fig.add_trace(go.Bar(x=tempi["Tempo"], y=tempi["categoria"], orientation="h", name="Tempo medio",
                             marker=dict(color=BLU, cornerradius=4),
                             text=[f"{num(r)}%" for r in 100 * tempi["Ritardo"]], textposition="outside",
                             textfont=dict(color="#14171c"), cliponaxis=False,
                             customdata=tempi[["Massimo", "Ritardo"]],
                             hovertemplate="<b>%{y}</b><br>Tempo medio: %{x:.0f} min<br>"
                                           "Tempo massimo: %{customdata[0]} min<br>"
                                           "In ritardo: %{customdata[1]:.1%}<extra></extra>"))
        fig.add_trace(go.Scatter(x=tempi["Massimo"], y=tempi["categoria"], mode="markers", name="Tempo massimo",
                                 marker=dict(symbol="line-ns-open", size=22, color="#898781",
                                             line=dict(width=3, color="#898781")),
                                 hovertemplate="<b>%{y}</b><br>Tempo massimo: %{x} min<extra></extra>"))
        stile_grafico(fig, 320, legenda=True)
        fig.update_xaxes(title="minuti", range=[0, max(tempi["Massimo"].max(), tempi["Tempo"].max()) * 1.22],
                         showgrid=True, gridcolor="#f0efec")
    fig.update_yaxes(title=None, gridcolor="rgba(0,0,0,0)")
    mostra(fig)

# --- giorno x ora ----------------------------------------------------------------------
with col_d, st.container(key="card_orari"):
    heat = (sel.pivot_table(index="nome_giorno", columns="ora", values="richiesta_id",
                            aggfunc="count", fill_value=0)
            .reindex(index=ORDINE_GIORNI, columns=range(24), fill_value=0))
    ore = heat.sum(axis=0)
    giorni = heat.sum(axis=1)
    picchi = ore.sort_values(ascending=False).index[:2].sort_values()
    frase = (f"Fasce più richieste: <b>{picchi[0]}–{picchi[0] + 1}</b> e <b>{picchi[1]}–{picchi[1] + 1}</b>; "
             f"giorno più intenso: <b>{giorni.idxmax()}</b>." if ore.sum() else "")
    intestazione_card("Quando arrivano le richieste", frase)
    fig = go.Figure(go.Heatmap(
        z=heat.values, x=[f"{h:02d}" for h in heat.columns], y=[g.capitalize() for g in heat.index],
        colorscale=[[i / (len(SCALA_BLU) - 1), c] for i, c in enumerate(SCALA_BLU)],
        xgap=2, ygap=2, showscale=False,
        hovertemplate="<b>%{y}, ore %{x}</b><br>Richieste: %{z}<extra></extra>"))
    stile_grafico(fig, 320)
    fig.update_xaxes(title="Ora del giorno", dtick=2, showline=False)
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    mostra(fig)

# --- dettaglio -------------------------------------------------------------------------
with st.expander("Dettaglio per zona"):
    tab = (sel.groupby("zona", as_index=False)
           .agg(Richieste=("richiesta_id", "count"), Incassi=("importo", "sum"),
                Tempo=("tempo_erogazione_min", "mean"), Annullate=("flag_annullata", "mean"))
           .sort_values("Incassi", ascending=False))
    tab["Quota"] = 100 * tab["Incassi"] / tab["Incassi"].sum()
    tab["Annullate"] = 100 * tab["Annullate"]
    tab["Incassi"] = tab["Incassi"].map(euro)
    st.dataframe(tab, width="stretch", hide_index=True, column_config={
        "zona": st.column_config.TextColumn("Zona"),
        "Richieste": st.column_config.NumberColumn("Richieste", format="%d"),
        "Incassi": st.column_config.TextColumn("Incassi"),
        "Quota": st.column_config.ProgressColumn("Quota degli incassi", format="%.1f%%", min_value=0, max_value=100),
        "Tempo": st.column_config.NumberColumn("Tempo medio", format="%.0f min"),
        "Annullate": st.column_config.NumberColumn("Annullate", format="%.1f%%"),
    })

with st.expander(f"Elenco delle richieste filtrate ({num(len(sel))})"):
    colonne = ["richiesta_id", "data", "ora", "zona", "categoria", "fornitore",
               "stato", "importo", "tempo_erogazione_min"]
    st.dataframe(sel[colonne].sort_values(["data", "ora"]), width="stretch", hide_index=True, column_config={
        "richiesta_id": st.column_config.TextColumn("Richiesta"),
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "ora": st.column_config.NumberColumn("Ora", format="%d:00"),
        "zona": "Zona", "categoria": "Categoria", "fornitore": "Fornitore", "stato": "Stato",
        "importo": st.column_config.NumberColumn("Importo", format="%.2f €"),
        "tempo_erogazione_min": st.column_config.NumberColumn("Tempo", format="%d min"),
    })


def esporta_excel() -> bytes:
    """Cartella di lavoro Excel con i filtri applicati e le analisi della pagina, un foglio per tabella."""
    filtri = pd.DataFrame({"Filtro": ["Periodo", "Zone", "Categorie"],
                           "Valore": [f"{inizio:%d/%m/%Y} – {fine:%d/%m/%Y}",
                                      ", ".join(zone) or "Tutte", ", ".join(categorie) or "Tutte"]})
    indicatori = pd.DataFrame({"Indicatore": ["Richieste totali", "Richieste erogate", "Incassi (€)",
                                              "Tempo medio di erogazione (min)", "Clienti attivi",
                                              "Clienti che tornano (%)", "Richieste annullate (%)",
                                              "Erogate in ritardo (%)"],
                               "Valore": [k["richieste_totali"], k["richieste_erogate"], k["incassi_euro"],
                                          k["tempo_medio_min"], k["clienti_attivi"], k["tasso_ritorno_perc"],
                                          k["perc_annullate"], k["perc_in_ritardo"]]})
    per_mese = mensile.reset_index(names="mese").assign(mese=lambda d: d["mese"].astype(str)).round(2)
    fornitori = (per_fornitore.assign(fornitore=per_fornitore["fornitore_id"].map(ultimo_nome))
                 .sort_values("Incassi", ascending=False))
    fogli = {"Filtri": filtri, "Indicatori": indicatori, "Per mese": per_mese,
             "Per zona": per_zona.sort_values("Richieste", ascending=False),
             "Per categoria": per_cat.sort_values("Richieste", ascending=False),
             "Per fornitore": fornitori, "Richieste": sel[colonne].sort_values(["data", "ora"])}
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nome, tabella in fogli.items():
            tabella.to_excel(writer, sheet_name=nome, index=False)
            foglio = writer.sheets[nome]
            for colonna in foglio.columns:
                larghezza = max(len(str(c.value)) if c.value is not None else 0 for c in colonna)
                foglio.column_dimensions[colonna[0].column_letter].width = min(max(larghezza + 2, 10), 45)
    return buffer.getvalue()


c_csv, c_xlsx, _ = st.columns([1, 1.3, 4])
c_csv.download_button("Scarica CSV", sel[colonne].to_csv(index=False).encode("utf-8"),
                      "richieste_filtrate.csv", "text/csv", icon=":material/download:")
c_xlsx.download_button("Scarica Excel", esporta_excel(), "interventa_analisi.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       icon=":material/table_view:", help="Indicatori, analisi e richieste con i filtri applicati")
