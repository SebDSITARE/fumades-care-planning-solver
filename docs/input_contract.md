# Contrat d'entrée V1.1.1

## `stays.csv`

Champs obligatoires V1.1.1 :

- `earliest_start` : borne dure. Par défaut, aucun soin avec créneau ne peut commencer avant cette heure ;
- `preferred_day_start` : heure souhaitée du **premier soin quotidien** ;
- `latest_start` : heure limite du premier soin quotidien.

Ces trois valeurs utilisent `HH:MM` sur une grille de cinq minutes et doivent respecter :

```text
earliest_start <= preferred_day_start <= latest_start
```

Compatibilité ascendante : si ces champs sont absents, l'ancien `preferred_start` du séjour initialise `earliest_start` et `preferred_day_start`. `latest_start` vaut alors `12:00`. Cette conversion doit rester transitoire ; les nouveaux exports Nymphéa doivent fournir les trois champs explicites.

## `care_requests.csv`

`locked_start` reste la contrainte dure d'une occurrence imposée. Il doit appartenir à la grille de cinq minutes, ne peut pas précéder `earliest_start` et, avec `locked_resource`, fixe aussi la ressource. Le `preferred_start` d'une occurrence reste une préférence souple et ne remplace pas l'ancrage journalier du séjour.

## Grille

Le modèle travaille en créneaux de cinq minutes. Une durée non multiple de cinq minutes est arrondie au créneau supérieur pour éviter de sous-estimer l'occupation : par exemple six minutes occupent dix minutes de grille.

## Sorties

- `planning.csv` : planning par occurrence ;
- `daily_indicators.csv` : début, fin, durée du parcours, attente totale et écart à `preferred_day_start` par séjour et par jour ;
- `diagnostics.json` : statut, objectif, borne, gap absolu/relatif, branches et conflits ;
- `validation_report.json` : erreurs et avertissements, avec `PROVISIONAL_PARAMETERS` limité aux codes réellement utilisés.
