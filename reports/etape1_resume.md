# Étape 1 — Résumé des choix de préparation et de fusion des données

*Document destiné à alimenter le rapport métier final. Détails techniques et visualisations : `notebooks/01_exploration_fusion.ipynb`.*

## 1. Les deux sources

| | Agriculture Crop Yield (DS1) | Crop Yield Prediction — FAO (DS2) |
|---|---|---|
| Contenu | 1 000 000 parcelles : sol, région, culture, pluie, température, engrais, irrigation, météo, durée de culture, rendement | Rendements réels par pays, culture et année (1990-2013), pluie, température, pesticides |
| Nature | Synthétique (distributions uniformes, modalités parfaitement équilibrées) | Réelle (FAO / Banque mondiale) |
| Apport | Effet des **pratiques culturales** (engrais, irrigation) | Écarts de rendement **entre cultures** et selon le **climat**, usage de **pesticides** |

**Découverte clé :** dans DS1, le rendement ne dépend pas de la culture (4,65 t/ha pour toutes). Seul, ce jeu ne permettrait pas de recommander une culture plutôt qu'une autre. La FAO apporte ce signal manquant.

## 2. Nettoyage

| Problème | Décision | Justification |
|---|---|---|
| 231 rendements négatifs dans DS1 | Supprimés | Physiquement impossibles ; 0,02 % des données |
| Orge et coton absents de la FAO | Périmètre limité à **maïs, riz, soja, blé** | Aucune référence réelle pour ces deux cultures ; il reste 666 494 parcelles |
| 2 310 doublons exacts dans la FAO | Supprimés | Lignes strictement identiques |
| Rendements FAO répétés une fois par station météo (Inde : 22 fois par an) | Une ligne par pays, culture et année ; température moyennée | Artefact de jointure qui surpondérait les grands pays (28 242 → 13 130 lignes réelles) |
| Rendements extrêmes (maïs du Qatar ~20 t/ha) | Plafonnés au 99ᵉ percentile par culture | Micro-surfaces non représentatives ; plafonner évite de supprimer des observations |
| Unités différentes | Rendement converti de hg/ha en t/ha ; oui/non converti en 0/1 | Cohérence des unités |
| Valeurs manquantes | Aucune dans les fichiers utilisés | Les manquants des fichiers bruts FAO avaient déjà été exclus |

## 3. Stratégie de fusion

**Contrainte :** aucune clé commune. DS1 ne contient ni pays ni année ; une jointure classique est impossible. Les seuls points communs sont la **culture** (exacte) et le **climat** (température, pluie), mais sur des échelles différentes : DS1 décrit la saison sur la parcelle (jusqu'à 40 °C), la FAO des moyennes annuelles nationales (jusqu'à 30 °C).

**Méthode retenue : appariement par « donneur »**
1. Les climats des deux sources sont mis sur une échelle commune par **rang** : une parcelle parmi les 10 % les plus chaudes est comparée aux pays parmi les 10 % les plus chauds.
2. Chaque parcelle reçoit un **donneur** : une observation FAO réelle de la **même culture**, tirée parmi les 10 au climat le plus proche (tirage reproductible).
3. La parcelle hérite de l'**usage de pesticides** du donneur.
4. **Rendement final = rendement réel du donneur × coefficient de conduite de la parcelle.** Le coefficient de conduite, issu de DS1, mesure l'effet des pratiques à climat égal : 0,68 sans engrais ni irrigation, 1,32 avec les deux.

**Contrôles :** écart climatique médian parcelle/donneur de 0,14 écart-type ; 6 581 des 6 582 observations FAO utilisées ; effets relatifs de l'engrais et de l'irrigation conservés ; aucune valeur manquante ni doublon.

**Variables proxy :** la FAO n'indique ni engrais ni irrigation. L'usage de pesticides y sert d'**indicateur d'agriculture intensive** (lié au rendement, r = 0,38). Un rendement élevé malgré une pluie très faible révèle l'**irrigation** (riz égyptien : ~9 t/ha avec 51 mm de pluie par an).

## 4. Dataset consolidé

`data/processed/dataset_consolide.csv` : **666 494 lignes, 11 colonnes**, source de vérité des étapes suivantes.

Région, type de sol, culture, pluie, température, pesticides, engrais (0/1), irrigation (0/1), météo, durée de culture, **rendement (t/ha, cible)**.

## 5. Variables clés identifiées

1. **Culture** : premier facteur de rendement. Médianes : soja 1,5 ; maïs 2,2 ; blé 2,3 ; riz 3,3 t/ha.
2. **Température** : effet négatif pour ces cultures, avec des optimums différents. Le maïs domine par temps frais (~7 t/ha entre 15 et 20 °C), le riz par forte chaleur (~2,8 t/ha au-delà de 35 °C). **Le meilleur choix de culture dépend donc du climat de la parcelle.**
3. **Engrais** : environ +50 % de rendement.
4. **Irrigation** : environ +40 % de rendement. Combinée à l'engrais : ×1,9.
5. **Pesticides** : marqueur d'intensification, lié positivement au rendement.
6. **Pluie** : déterminante dans DS1, mais en partie compensée par l'irrigation dans les données réelles.
7. **Sans effet mesurable** : type de sol, région, météo dominante, durée de culture. Leur exclusion sera confirmée par l'ACP (étape 2).

## 6. Limites

- DS1 est synthétique : l'effet des pratiques suit une règle simple et uniforme.
- Les pesticides FAO sont des tonnes totales par pays, pas des doses par hectare : ils indiquent un niveau d'intensification, pas une dose à appliquer.
- Le rendement cible repose sur l'hypothèse « potentiel culture × climat (réel) × coefficient de conduite (pratiques) ».
