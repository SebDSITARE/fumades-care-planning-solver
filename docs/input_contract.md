# Contrat d'entree normalise

## `stays.csv`

Une ligne par dossier de cure non nominatif ou pseudonymise.

Champs principaux: `stay_id`, `client_ref`, `start_date`, `end_date`, `primary_orientation`, `secondary_orientation`, `package_primary`, `package_secondary`, `preferred_start`, `pmr_level`, `planning_communicated`.

## `care_requests.csv`

Une ligne par occurrence de soin a planifier pour une date donnee.

Champs: `request_id`, `stay_id`, `service_date`, `care_code`, `sector`, `mode_plan`, `preferred_start`, `locked_start`, `locked_resource`, `medical_override`, `catchup_reason`.

`mode_plan` est autoritaire:

- `AVEC_RESSOURCE`: reserve un poste et une duree;
- `SANS_CRENEAU`: rattache l'acte a la journee sans reserver de poste;
- `REPOS`: acte technique/non therapeutique.

Les codes `ENTRH*`, `ENTDER`, `REPOS`, `STH` et `THR` ne sont pas comptes comme soins therapeutiques.

## Nymphéa

Les identifiants a conserver lors de la normalisation sont `CD_DOSSIER`, `CD_CLIENT` et `CD_RDVCLI`. Le module fourni ne lit que des fichiers d'export; il ne contient aucun connecteur d'ecriture.
