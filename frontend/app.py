"""Étape 4 : interface Streamlit d'Agritech Answers.

Aucune logique de Machine Learning ici : l'application envoie le contexte de la
parcelle à l'API FastAPI (étape 3) et affiche ses réponses.

Lancement (depuis la racine du projet, l'API tournant sur le port 8000) :
    streamlit run frontend/app.py
L'adresse de l'API se change avec la variable d'environnement API_URL.
"""

import os

import altair as alt
import pandas as pd
import requests
import streamlit as st

def _adresse_api() -> str:
    """Adresse de l'API : secret Streamlit Cloud, sinon variable d'environnement, sinon locale."""
    try:
        if "API_URL" in st.secrets:  # réglé dans Streamlit Community Cloud (Settings > Secrets)
            return st.secrets["API_URL"]
    except Exception:  # aucun fichier de secrets en local ou dans Docker : cas normal
        pass
    return os.environ.get("API_URL", "http://localhost:8000")


API_URL = _adresse_api().rstrip("/")
TIMEOUT_S = 10

CULTURES = {"Maize": "Maïs", "Rice": "Riz", "Soybean": "Soja", "Wheat": "Blé"}

# Pesticides_tonnes est un total national : il mesure le niveau d'intensification
# de l'agriculture du pays. Les niveaux proposés sont des quantiles du jeu d'entraînement.
NIVEAUX_PESTICIDES = {
    "Faible (25 % des pays-années en dessous)": 470,
    "Médian": 3270,
    "Élevé (75 % en dessous)": 14200,
    "Très élevé (90 % en dessous)": 40700,
    "Valeur personnalisée": None,
}


# --------------------------------------------------------------------------- appels API

def appeler_api(methode: str, chemin: str, **kwargs) -> tuple[dict | None, str | None]:
    """Renvoie (réponse JSON, None) ou (None, message d'erreur lisible)."""
    try:
        r = requests.request(methode, f"{API_URL}{chemin}", timeout=TIMEOUT_S, **kwargs)
    except requests.ConnectionError:
        return None, (f"Impossible de joindre l'API à l'adresse {API_URL}. "
                      "Vérifiez qu'elle est lancée (voir api/README.md).")
    except requests.Timeout:
        return None, f"L'API n'a pas répondu en {TIMEOUT_S} secondes."
    if r.status_code == 422:
        details = r.json().get("detail", [])
        lignes = [f"{' → '.join(str(x) for x in d.get('loc', [])[1:])} : {d.get('msg')}" for d in details]
        return None, "Entrée refusée par l'API :\n\n- " + "\n- ".join(lignes)
    if not r.ok:
        return None, f"Erreur de l'API ({r.status_code}) : {r.text[:300]}"
    return r.json(), None


@st.cache_data(ttl=60, show_spinner=False)
def _sante_en_cache() -> dict:
    res, err = appeler_api("GET", "/health")
    if err:
        raise RuntimeError(err)  # une exception n'est pas mise en cache : on réessaie au prochain affichage
    return res


def etat_api() -> tuple[dict | None, str | None]:
    try:
        return _sante_en_cache(), None
    except RuntimeError as e:
        return None, str(e)


# --------------------------------------------------------------------------- mise en page

st.set_page_config(page_title="Agritech Answers", page_icon="🌾", layout="wide")
st.title("🌾 Agritech Answers")
st.caption("Prédiction du rendement et recommandation de cultures pour une parcelle")

with st.sidebar:
    st.header("Mode")
    mode = st.radio("Que voulez-vous faire ?", ["Prédiction", "Recommandation"],
                    captions=["Rendement d'une culture choisie", "Comparer les quatre cultures"],
                    label_visibility="collapsed")

    st.divider()
    sante, erreur_sante = etat_api()
    if sante:
        m = sante.get("metriques_test", {})
        st.success("API connectée", icon="✅")
        st.caption(f"Modèle : forêt aléatoire, R² test {m.get('test_r2', float('nan')):.2f}, "
                   f"erreur moyenne {m.get('test_mae', float('nan')):.2f} t/ha")
    else:
        st.error(erreur_sante, icon="⚠️")
        if st.button("Réessayer"):
            st.rerun()
    st.caption(f"API : `{API_URL}`")

st.subheader("Contexte de la parcelle")

with st.form("contexte"):
    col1, col2 = st.columns(2)
    with col1:
        if mode == "Prédiction":
            crop = st.selectbox("Culture envisagée", list(CULTURES), format_func=CULTURES.get)
        temperature = st.slider("Température moyenne (°C)", 15.0, 40.0, 25.0, 0.5)
        pluie = st.slider("Pluie sur la saison (mm)", 100, 1000, 600, 10)
    with col2:
        niveau = st.selectbox(
            "Niveau d'intensification agricole du pays (pesticides)", list(NIVEAUX_PESTICIDES), index=1,
            help="Le modèle utilise l'usage national de pesticides (tonnes par an), un indicateur du "
                 "niveau d'intensification de l'agriculture du pays, pas la quantité épandue sur la parcelle.")
        pesticides_perso = st.number_input("Pesticides, valeur personnalisée (tonnes, pays)",
                                           0, 400_000, 3270, 100,
                                           help="Utilisée seulement si « Valeur personnalisée » est choisi.")
        engrais = st.toggle("Engrais appliqué", value=True)
        irrigation = st.toggle("Parcelle irriguée", value=False)
    if mode == "Recommandation":
        tri = st.radio("Classer les cultures par", ["rendement", "marge"], horizontal=True,
                       format_func={"rendement": "Rendement (t/ha)", "marge": "Marge estimée (USD/ha)"}.get)
    envoyer = st.form_submit_button("Lancer la " + mode.lower(), type="primary", width="stretch")

pesticides = NIVEAUX_PESTICIDES[niveau] if NIVEAUX_PESTICIDES[niveau] is not None else pesticides_perso
contexte = {"Rainfall_mm": pluie, "Temperature_Celsius": temperature, "Pesticides_tonnes": pesticides,
            "Fertilizer_Used": engrais, "Irrigation_Used": irrigation}

if not envoyer:
    st.info("Réglez le contexte puis cliquez sur le bouton pour interroger le modèle.")
    st.stop()

# --------------------------------------------------------------------------- résultats

if mode == "Prédiction":
    with st.spinner("Prédiction en cours…"):
        res, err = appeler_api("POST", "/predict", json={**contexte, "Crop": crop})
    if err:
        st.error(err)
        st.stop()

    st.subheader(f"Résultat pour : {CULTURES[res['culture']]}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rendement prédit", f"{res['rendement_t_ha']:.2f} t/ha")
    c2.metric("Marge estimée", f"{res['marge_usd_ha']:,.0f} USD/ha".replace(",", " "))
    c3.metric("Seuil de rentabilité", f"{res['seuil_rentabilite_t_ha']:.2f} t/ha")
    if res["rentable"]:
        st.success(f"Culture rentable : le rendement prédit dépasse le seuil de "
                   f"{res['rendement_t_ha'] - res['seuil_rentabilite_t_ha']:.2f} t/ha.")
    else:
        st.warning(f"Culture non rentable : il manque "
                   f"{res['seuil_rentabilite_t_ha'] - res['rendement_t_ha']:.2f} t/ha pour couvrir les coûts.")

else:
    with st.spinner("Simulation des quatre cultures…"):
        res, err = appeler_api("POST", "/recommend", params={"tri": tri}, json=contexte)
    if err:
        st.error(err)
        st.stop()

    table = pd.DataFrame(res["classement"])
    table.insert(0, "Rang", range(1, len(table) + 1))
    table["Culture"] = table["culture"].map(CULTURES)

    meilleure, rentable = CULTURES[res["meilleure_culture"]], CULTURES[res["culture_la_plus_rentable"]]
    critere = "rendement" if tri == "rendement" else "marge"
    if meilleure == rentable:
        st.success(f"**Culture recommandée : {meilleure}**, meilleure en {critere} et la plus rentable.")
    else:
        st.success(f"**Meilleure culture en {critere} : {meilleure}.** "
                   f"La plus rentable est **{rentable}** (classez par marge pour la comparer).")

    colonne, titre = (("rendement_t_ha", "Rendement prédit (t/ha)") if tri == "rendement"
                      else ("marge_usd_ha", "Marge estimée (USD/ha)"))
    graphique = (
        alt.Chart(table)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            y=alt.Y("Culture:N", sort=None, title=None),
            x=alt.X(f"{colonne}:Q", title=titre),
            color=alt.Color("rentable:N", title="Rentable",
                            scale=alt.Scale(domain=[True, False], range=["#2e7d32", "#c62828"]),
                            legend=alt.Legend(labelExpr="datum.value ? 'oui' : 'non'")),
            tooltip=[alt.Tooltip("Culture:N"),
                     alt.Tooltip("rendement_t_ha:Q", title="Rendement (t/ha)", format=".2f"),
                     alt.Tooltip("marge_usd_ha:Q", title="Marge (USD/ha)", format=",.0f")],
        )
        .properties(height=220)
    )
    st.altair_chart(graphique, width="stretch")

    st.dataframe(
        table[["Rang", "Culture", "rendement_t_ha", "marge_usd_ha", "seuil_rentabilite_t_ha", "rentable"]],
        hide_index=True, width="stretch",
        column_config={
            "rendement_t_ha": st.column_config.NumberColumn("Rendement prédit (t/ha)", format="%.2f"),
            "marge_usd_ha": st.column_config.NumberColumn("Marge estimée (USD/ha)", format="%.0f"),
            "seuil_rentabilite_t_ha": st.column_config.NumberColumn("Seuil de rentabilité (t/ha)", format="%.2f"),
            "rentable": st.column_config.CheckboxColumn("Rentable"),
        },
    )

with st.expander("Comment lire ces chiffres ?"):
    st.markdown(
        "- **Rendement** : prédit par le modèle (forêt aléatoire), en tonnes par hectare.\n"
        "- **Marge** : rendement × prix − coûts opérationnels (hors foncier et matériel). Prix Banque mondiale "
        "2025, coûts USDA 2025 ajustés au rendement moyen du jeu de données. Ce sont des **hypothèses**, "
        "à remplacer par les prix et coûts réels de l'exploitation.\n"
        "- **Seuil de rentabilité** : rendement minimal pour couvrir ces coûts.\n"
        "- Les curseurs sont limités aux plages du jeu d'entraînement : au-delà, le modèle n'est pas fiable.")
    st.caption(f"Pesticides envoyés à l'API : {pesticides:,} tonnes (niveau national).".replace(",", " "))
