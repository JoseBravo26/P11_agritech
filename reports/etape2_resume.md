# Étape 2 — Résumé du modèle de prédiction du rendement

*Document destiné à alimenter le rapport métier final. Détails techniques et visualisations : `notebooks/02_modelisation.ipynb`. Pipeline : `src/entrainement.py`. Hypothèses économiques : `src/economie.py`.*

## 1. Ce que fait le modèle

À partir de six informations sur la parcelle (**culture, température, pluie, niveau d'intensification (pesticides), engrais oui/non, irrigation oui/non**), le modèle estime le **rendement en tonnes par hectare**. En le répétant pour chaque culture, l'application peut ensuite **classer les cultures par marge attendue** : c'est la fonction de recommandation.

## 2. Comment le modèle a été évalué

- **Jeu de test séparé (20 %)**, utilisé une seule fois à la fin. Il est découpé par **pays-année d'origine** des rendements : le modèle est jugé sur des situations qu'il n'a jamais vues, comme un nouvel agriculteur.
  - **Pourquoi ce choix :** la valeur exacte des pesticides (un total national) désigne presque le pays-année d'origine. Un découpage au hasard aurait laissé le modèle « reconnaître » ces pays-années, et les scores auraient été trop flatteurs (R² 0,91 au lieu de 0,76).
- **Métriques statistiques** :
  - erreur type (RMSE) ;
  - erreur moyenne (MAE) ;
  - part des variations expliquée (R²).
- **Métriques économiques** :
  - erreur sur la marge (USD/ha) ;
  - part des parcelles correctement classées rentables ou non rentables.
- **Reproductibilité** : la graine aléatoire est fixée (42), et toutes les expérimentations sont tracées et annotées dans MLflow (28 runs).

## 3. Comparaison des modèles (validation croisée)

| Modèle | Erreur type (t/ha) | R² | Rentabilité bien classée |
|---|---|---|---|
| Moyenne (référence) | 2,43 | 0,00 | 69 % |
| Régression linéaire (Ridge) | 1,94 | 0,36 | 70 % |
| Gradient boosting | 1,25 | 0,74 | 81 % |
| **Forêt aléatoire** | **1,24** | **0,74** | **84 %** |
| **Forêt aléatoire, 6 variables clés** | **1,24** | **0,74** | **84 %** |

- **Le modèle linéaire échoue** car l'effet du climat dépend de la culture : le maïs aime la fraîcheur, le riz la chaleur.
- **Forêt aléatoire et gradient boosting sont à égalité statistique.** La forêt est retenue pour sa meilleure précision de rentabilité.
- **Région, type de sol, météo dominante et durée de culture sont retirés sans aucune perte** : cela confirme l'étape 1.
- **Contrainte de déploiement :** la taille des feuilles des arbres est limitée pour que le modèle tienne en mémoire dans l'API (environ 100 Mo au lieu d'environ 5 Go).

## 4. Optimisation

Nous avons testé **20 configurations** d'hyperparamètres (recherche aléatoire).
- **Gain :** l'erreur type passe de 1,236 à 1,225 t/ha, soit environ 1 %.
- **Paramètre décisif :** la taille minimale des feuilles des arbres. Les autres réglages ont un effet de second ordre.

## 5. Performance finale (jeu de test, pays-années jamais vus)

| | Valeur |
|---|---|
| Erreur moyenne | **0,68 t/ha** |
| R² | **0,76** |
| Rentabilité correctement prédite | **84 % des parcelles** |
| Culture la mieux prédite | Riz (erreur relative 19 %) |
| Culture la moins bien prédite | Maïs (28 %), dont les rendements varient le plus |

Le modèle est enregistré dans le registre MLflow (`rendement_cultures`, version 1) et dans `models/modele_rendement.joblib` pour l'API.

## 6. Variables les plus importantes

1. **Température** et **culture** : à égalité, ce sont les facteurs dominants.
   - Maïs et blé : meilleurs en climat frais (15-21 °C), puis en net recul au-delà de 22 °C.
   - Riz : culmine vers 22-26 °C.
   - Soja : stable quelle que soit la température.
2. **Pluie** : effet modéré et irrégulier, plutôt favorable entre 500 et 800 mm.
3. **Pesticides (intensification du pays)** : plus l'agriculture du pays est intensive, plus les rendements sont élevés.
4. **Engrais** (+52 % de rendement) et **irrigation** (+40 %) : effet réel, mais plus petit que celui du climat ou du choix de culture.

## 7. Recommandations pour l'agriculteur

*Hypothèses économiques (`src/economie.py`) : prix mondiaux de la Banque mondiale (moyenne 2025) et coûts opérationnels de l'USDA (2025), ramenés à l'intensité des parcelles du jeu de données. Le coût de l'irrigation (200 USD/ha) reste illustratif. Avec les chiffres réels du client, le classement peut changer sans réentraîner le modèle.*

| Culture | Prix (USD/t) | Coût de base (USD/ha) | Engrais (USD/ha) | Seuil de rentabilité sans intrants (t/ha) |
|---|---|---|---|---|
| Maïs | 203 | 206 | 125 | 1,0 |
| Riz (paddy) | 273 | 595 | 195 | 2,2 |
| Soja | 414 | 196 | 61 | 0,5 |
| Blé | 243 | 188 | 122 | 0,8 |

1. **Choisir la culture selon le climat de la parcelle :**
   - Climat frais (< 21 °C) → **maïs**, quelle que soit la pluie.
   - Climat chaud (22-30 °C) et humide (600-900 mm) → **riz**. Sa zone s'élargit avec l'irrigation (14 % des climats sans intrants, 24 % avec engrais et irrigation).
   - Climat chaud (> 27 °C) et moyennement sec (< 700 mm) → **blé**. C'est la culture la plus souvent recommandée : 32 à 38 % des climats selon les pratiques.
   - Climat très arrosé (≥ 900 mm) au-delà de 27 °C, ou climat tiède et sec (22-27 °C, < 300 mm) → **soja**.
2. **L'engrais est rentable en moyenne pour toutes les cultures** (+94 à +160 USD/ha). Il l'est sur 97 % des parcelles de soja et 82 % des parcelles de riz, mais seulement sur 60 % des parcelles de maïs.
3. **L'irrigation n'est rentable en moyenne que pour le riz** (+71 USD/ha, 59 % des parcelles). Pour le maïs, le soja et le blé, son coût dépasse en moyenne le gain de rendement (−18 à −34 USD/ha). Cette conclusion dépend du coût d'irrigation, qui n'est pas sourcé.
4. **Exemple de recommandation** pour une parcelle à 25 °C, 600 mm, avec engrais :

   | Culture | Rendement prédit | Marge |
   |---|---|---|
   | Riz | 5,3 t/ha | ≈ 655 USD/ha |
   | Soja | 1,7 t/ha | ≈ 425 USD/ha |
   | Blé | 2,4 t/ha | ≈ 265 USD/ha |
   | Maïs | 2,3 t/ha | ≈ 130 USD/ha |

## 8. Limites

- **Précision plafonnée par construction.** Le rendement cible est construit (étape 1), et sa part aléatoire, issue du tirage du pays-année d'origine, limite la précision atteignable.
- **Effets des pratiques uniformes.** L'effet de l'engrais et de l'irrigation est identique pour toutes les cultures, par construction. Il faudrait le confirmer par des données de terrain.
- **Pesticides au niveau national.** Ils indiquent un niveau d'intensification du pays, pas une dose à appliquer sur la parcelle.
- **Prix et coûts de référence, pas ceux du client.** Les prix sont des cours mondiaux à l'export (Banque mondiale), pas des prix payés au producteur. Les coûts viennent des exploitations américaines (USDA), ramenés à l'intensité du jeu en supposant un coût par tonne constant. Le coût de l'irrigation reste illustratif. Les charges de structure (terre, matériel) sont exclues : il s'agit d'une marge sur coûts opérationnels. Tout est à remplacer par les données du client.

## 9. Captures MLflow à intégrer au rapport

Les captures sont dans `reports/mlflow/`. Pour rouvrir l'interface : `mlflow ui --backend-store-uri sqlite:///mlflow.db`, expérience `P11_rendement_cultures`.

| Fichier | Ce qu'il montre |
|---|---|
| `01_liste_runs_comparaison.png` | Les 3 étapes (A comparaison, B optimisation, C modèle final). Les 5 modèles candidats sont dépliés avec leurs métriques de validation croisée. |
| `02_comparaison_modeles_r2_rmse.png` | Graphiques R² et RMSE des 5 modèles candidats : la forêt et le gradient boosting à égalité, loin devant Ridge et la référence. |
| `03_comparaison_modeles_rentabilite.png` | Précision de rentabilité des candidats, et 84 % pour le modèle final sur le jeu de test. |
| `04_optimisation_coordonnees_paralleles.png` | Les 20 essais d'hyperparamètres. La taille minimale des feuilles (`min_samples_leaf`) détermine l'erreur : les essais à 20 sont en bleu (erreur faible), ceux à 100 en rouge. |
| `05_modele_final_metriques.png` | Run `C_modele_final` : note explicative, métriques de test et d'entraînement, taille du modèle. |
| `06_modele_final_artefacts.png` | Artefacts du modèle final : importance des variables (température et culture en tête). |
| `07_registre_modele.png` | Registre MLflow : `rendement_cultures` version 1, relié au run final, avec le schéma d'entrée des 6 variables. |
