"""Construit la table « pays -> usage national de pesticides » utilisée par l'interface.

Le modèle attend l'usage national de pesticides (tonnes par an) : un indicateur du
niveau d'intensification de l'agriculture du pays, inconnu d'un agriculteur. L'interface
lui demande donc son pays et retrouve la valeur dans cette table.

Source : Crop Yield Prediction Dataset (FAO), dernière année disponible (2013).
Sortie : frontend/pays_pesticides.json (livré avec l'interface, qui n'a pas accès aux données brutes).

Lancement : python scripts/generer_pays_pesticides.py
"""

import json
import unicodedata
from pathlib import Path

import pandas as pd

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "Crop Yield Prediction Dataset" / "yield_df.csv"
SORTIE = RACINE / "frontend" / "pays_pesticides.json"

# Noms FAO (anglais) -> noms français affichés dans l'interface
NOMS_FR = {
    "Albania": "Albanie", "Algeria": "Algérie", "Angola": "Angola", "Argentina": "Argentine",
    "Armenia": "Arménie", "Australia": "Australie", "Austria": "Autriche", "Azerbaijan": "Azerbaïdjan",
    "Bahamas": "Bahamas", "Bahrain": "Bahreïn", "Bangladesh": "Bangladesh", "Belarus": "Biélorussie",
    "Belgium": "Belgique", "Botswana": "Botswana", "Brazil": "Brésil", "Bulgaria": "Bulgarie",
    "Burkina Faso": "Burkina Faso", "Burundi": "Burundi", "Cameroon": "Cameroun", "Canada": "Canada",
    "Central African Republic": "République centrafricaine", "Chile": "Chili", "Colombia": "Colombie",
    "Croatia": "Croatie", "Denmark": "Danemark", "Dominican Republic": "République dominicaine",
    "Ecuador": "Équateur", "Egypt": "Égypte", "El Salvador": "Salvador", "Eritrea": "Érythrée",
    "Estonia": "Estonie", "Finland": "Finlande", "France": "France", "Germany": "Allemagne",
    "Ghana": "Ghana", "Greece": "Grèce", "Guatemala": "Guatemala", "Guinea": "Guinée", "Guyana": "Guyana",
    "Haiti": "Haïti", "Honduras": "Honduras", "Hungary": "Hongrie", "India": "Inde", "Indonesia": "Indonésie",
    "Iraq": "Irak", "Ireland": "Irlande", "Italy": "Italie", "Jamaica": "Jamaïque", "Japan": "Japon",
    "Kazakhstan": "Kazakhstan", "Kenya": "Kenya", "Latvia": "Lettonie", "Lebanon": "Liban",
    "Lesotho": "Lesotho", "Libya": "Libye", "Lithuania": "Lituanie", "Madagascar": "Madagascar",
    "Malawi": "Malawi", "Malaysia": "Malaisie", "Mali": "Mali", "Mauritania": "Mauritanie",
    "Mauritius": "Maurice", "Mexico": "Mexique", "Montenegro": "Monténégro", "Morocco": "Maroc",
    "Mozambique": "Mozambique", "Namibia": "Namibie", "Nepal": "Népal", "Netherlands": "Pays-Bas",
    "New Zealand": "Nouvelle-Zélande", "Nicaragua": "Nicaragua", "Niger": "Niger", "Norway": "Norvège",
    "Pakistan": "Pakistan", "Papua New Guinea": "Papouasie-Nouvelle-Guinée", "Peru": "Pérou",
    "Poland": "Pologne", "Portugal": "Portugal", "Qatar": "Qatar", "Romania": "Roumanie",
    "Rwanda": "Rwanda", "Saudi Arabia": "Arabie saoudite", "Senegal": "Sénégal", "Slovenia": "Slovénie",
    "South Africa": "Afrique du Sud", "Spain": "Espagne", "Sri Lanka": "Sri Lanka", "Sudan": "Soudan",
    "Suriname": "Suriname", "Sweden": "Suède", "Switzerland": "Suisse", "Tajikistan": "Tadjikistan",
    "Thailand": "Thaïlande", "Tunisia": "Tunisie", "Turkey": "Turquie", "Uganda": "Ouganda",
    "Ukraine": "Ukraine", "United Kingdom": "Royaume-Uni", "Uruguay": "Uruguay", "Zambia": "Zambie",
    "Zimbabwe": "Zimbabwe",
}


def main() -> None:
    fao = pd.read_csv(SOURCE, index_col=0)
    # L'usage de pesticides est national : une seule valeur par pays et par année, quelle que soit la culture
    dernier = fao.sort_values("Year").groupby("Area").agg(annee=("Year", "last"),
                                                           pesticides=("pesticides_tonnes", "last"))
    manquants = sorted(set(dernier.index) - set(NOMS_FR))
    if manquants:
        raise ValueError(f"Nom français manquant pour : {manquants}")
    table = {
        NOMS_FR[pays]: {"nom_fao": pays, "annee": int(ligne.annee), "pesticides_tonnes": round(float(ligne.pesticides), 2)}
        for pays, ligne in dernier.iterrows()
    }
    # Ordre alphabétique français : les accents sont ignorés pour le tri (« Égypte » avec les E)
    sans_accent = lambda nom: unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().casefold()
    table = dict(sorted(table.items(), key=lambda kv: sans_accent(kv[0])))
    SORTIE.write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    valeurs = [v["pesticides_tonnes"] for v in table.values()]
    print(f"{len(table)} pays -> {SORTIE} (pesticides de {min(valeurs):,.0f} à {max(valeurs):,.0f} t)")


if __name__ == "__main__":
    main()
