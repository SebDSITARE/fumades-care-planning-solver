# Données de recette n°3 — RH + DER difficile

Jeu **entièrement pseudonymisé et synthétique**, construit uniquement à partir des défauts métier explicitement identifiés. Il ne reproduit ni identité, ni numéro de dossier, ni planning nominatif.

## Contenu

- `scenario.json` : tous les paramètres du cas (dates synthétiques, soins, jours chargés, fenêtres, ressources, baseline et seuils de mesure) ;
- `stays.csv` : 1 séjour cible RH + DER et 20 séjours de charge pseudonymisés ;
- `care_requests.csv` : 72 soins cibles et 120 demandes verrouillées matérialisant la charge connue ;
- `nymphea_baseline.csv` : référence inerte reproduisant les défauts, sans aucune connexion ni écriture Nymphéa ;
- `nymphea_baseline_metrics.json` : indicateurs de la référence ;
- `nymphea_resource_occupation.csv` : occupation auditable des postes de la référence.

## Défauts reproduits

- vague RH à 07:45 et double orientation RH + DER ;
- douche générale DER saturée sur 6 jours dans la fenêtre 07:45–09:00 ;
- 6 douches générales non positionnées dans la baseline ;
- lit vapeur indisponible dans cette même fenêtre sur 6 jours ;
- 6 reports manuels de vapeur sur les 6 derniers jours ;
- 6 parcours RH → DER → RH en fin de cure ;
- respect de prescription dégradé dans la référence.

Les nombres de jours, fenêtres, ressources, soins et reports sont configurables dans `scenario.json`. Ils servent à rendre les symptômes reproductibles ; ils ne prétendent pas être un relevé nominatif ou une copie exacte du planning source.

## Sécurité

- `write_to_nymphea` reste `false` dans `config/solver.json` ;
- la baseline est un CSV local en lecture seule du point de vue du solveur ;
- aucune API ou connexion Nymphéa n'est ajoutée ;
- le planning produit reste `PROPOSE` et soumis à validation humaine.
